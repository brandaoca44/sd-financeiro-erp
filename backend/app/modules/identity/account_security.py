"""Ciclo de conta e TOTP. O transporte de e-mail é uma dependência ainda não implementada."""
import asyncio
import base64
import hashlib
import hmac
import json
import re
import secrets
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.modules.identity.account_models import AccountAction, AccountSecurity
from app.modules.identity.models import User, UserPasswordCredential, UserSession, UserStatus
from app.modules.identity.passwords import hash_password, run_password_work, validate_new_password, verify_password
from app.modules.identity.sessions import IssuedSession, SessionService


def now():
    return datetime.now(timezone.utc)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class AccountUnavailable(Exception):
    pass


class InvalidAction(Exception):
    pass


class EmailDelivery(Protocol):
    """Contrato futuro: usar destino e finalidade fixos, sem registrar tokens ou corpo."""
    async def send_account_action(self, *, email: str, purpose: str, token: SecretStr) -> None: ...


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    email: EmailStr = Field(max_length=254)

    @field_validator("email", mode="before")
    @classmethod
    def normalize(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class RegisterRequest(EmailRequest):
    name: str = Field(min_length=2, max_length=150)
    cpf: SecretStr = Field(min_length=11, max_length=14)
    password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def name_valid(cls, value):
        value = " ".join(value.split())
        if len(value.split()) < 2 or any(not (c.isalpha() or c in " '-’") for c in value):
            raise ValueError("Nome inválido.")
        return value

    @field_validator("cpf")
    @classmethod
    def cpf_valid(cls, value):
        raw = value.get_secret_value()
        if re.fullmatch(r"(?:[0-9]{11}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2})", raw) is None:
            raise ValueError("CPF inválido.")
        digits = raw.replace(".", "").replace("-", "")
        if len(set(digits)) == 1:
            raise ValueError("CPF inválido.")
        for size in (9, 10):
            number = (sum(int(digits[i]) * (size + 1 - i) for i in range(size)) * 10) % 11
            if int(digits[size]) != (0 if number == 10 else number):
                raise ValueError("CPF inválido.")
        return SecretStr(digits)

    @field_validator("password")
    @classmethod
    def password_valid(cls, value):
        return validate_new_password(value)


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    token: SecretStr = Field(min_length=43, max_length=43)


class ResetRequest(TokenRequest):
    password: SecretStr = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_valid(cls, value):
        return validate_new_password(value)


class FactorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    code: SecretStr = Field(min_length=6, max_length=64)


class MfaLoginRequest(FactorRequest):
    challenge_token: SecretStr = Field(min_length=43, max_length=43)


class MfaSetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    password: SecretStr = Field(min_length=1, max_length=128)


class MfaDisableRequest(MfaSetupRequest, FactorRequest):
    pass


@dataclass(frozen=True)
class MfaChallenge:
    token: SecretStr
    expires_at: datetime


def totp(secret: str, step: int, digits: int = 6) -> str:
    """RFC 6238 / SHA-1, intervalo de 30s; segredo base32 de 160 bits."""
    key = base64.b32decode(secret, casefold=True)
    mac = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = mac[-1] & 15
    value = (struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7fffffff) % 10**digits
    return str(value).zfill(digits)


class AccountService:
    def __init__(self, factory, *, hash_slots: asyncio.Semaphore, encryption_key: SecretStr | None = None,
                 delivery: EmailDelivery | None = None, idle_timeout: timedelta = timedelta(minutes=30),
                 identity_key: SecretStr | None = None):
        self.factory, self.slots, self.delivery = factory, hash_slots, delivery
        self.key, self.idle_timeout = encryption_key, idle_timeout
        self.identity_key = identity_key

    def cipher(self):
        if self.key is None:
            raise AccountUnavailable()
        try:
            return Fernet(self.key.get_secret_value().encode())
        except (ValueError, TypeError):
            raise AccountUnavailable() from None

    async def password_hash(self, password):
        try:
            await asyncio.wait_for(self.slots.acquire(), .25)
        except TimeoutError:
            raise AccountUnavailable() from None
        try:
            return (await run_password_work(hash_password(password))).get_secret_value()
        finally:
            self.slots.release()

    async def password_matches(self, password, stored):
        try:
            await asyncio.wait_for(self.slots.acquire(), .25)
        except TimeoutError:
            raise AccountUnavailable() from None
        try:
            valid, _ = await run_password_work(verify_password(password, stored))
            return valid
        finally:
            self.slots.release()

    @staticmethod
    async def invalidate(session, user_id, purpose=None):
        query = update(AccountAction).where(AccountAction.user_id == user_id, AccountAction.consumed_at.is_(None))
        if purpose:
            query = query.where(AccountAction.purpose == purpose)
        await session.execute(query.values(consumed_at=now()))

    async def request_email(self, data: EmailRequest, purpose: str):
        # Provedor indefinido: falhar antes de qualquer cadastro/mutação ou falsa promessa de envio.
        if self.delivery is None:
            raise AccountUnavailable()
        cpf_encrypted = cpf_digest = None
        if isinstance(data, RegisterRequest):
            if self.identity_key is None:
                raise AccountUnavailable()
            raw = data.cpf.get_secret_value()
            key = self.identity_key.get_secret_value().encode()
            cpf_encrypted = Fernet(key).encrypt(raw.encode()).decode()
            cpf_digest = hmac.new(key, ("cpf:" + raw).encode(), hashlib.sha256).hexdigest()
        hashed = await self.password_hash(data.password) if isinstance(data, RegisterRequest) else None
        token, destination = SecretStr(secrets.token_urlsafe(32)), None
        try:
            async with self.factory() as session, session.begin():
                user = await session.scalar(select(User).where(func.lower(User.email) == str(data.email)).with_for_update())
                if user is None and isinstance(data, RegisterRequest):
                    user = User(name=data.name, email=str(data.email), status=UserStatus.INACTIVE)
                    session.add(user)
                    await session.flush()
                    session.add(UserPasswordCredential(user_id=user.id, password_hash=hashed))
                    session.add(AccountSecurity(user_id=user.id, registration_pending=True,
                                               cpf_encrypted=cpf_encrypted, cpf_digest=cpf_digest))
                    await session.flush()
                if user is not None:
                    security = await session.get(AccountSecurity, user.id)
                    credential = await session.scalar(select(UserPasswordCredential.password_hash).where(UserPasswordCredential.user_id == user.id))
                    eligible = ((purpose == "VERIFY" and security is not None and security.registration_pending
                                 and user.status == UserStatus.INACTIVE)
                                or (purpose == "RESET" and user.status == UserStatus.ACTIVE and credential is not None))
                    if eligible:
                        await self.invalidate(session, user.id, purpose)
                        session.add(AccountAction(user_id=user.id, purpose=purpose, token_hash=digest(token.get_secret_value()),
                            credential_hash=credential, created_at=now(), expires_at=now() + timedelta(minutes=30 if purpose == "RESET" else 1440)))
                        destination = user.email
        except IntegrityError:
            # Cadastro concorrente retorna a mesma resposta, sem revelar existência.
            return
        if destination:
            # Transporte futuro deve ser assíncrono, com timeout e erros sanitizados.
            try:
                await self.delivery.send_account_action(email=destination, purpose=purpose, token=token)
            except Exception:
                raise AccountUnavailable() from None

    async def action(self, session, token: SecretStr, purpose: str):
        raw = token.get_secret_value()
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", raw) is None:
            raise InvalidAction()
        # Ordem de locks: usuário -> segurança/desafio/credencial, inclusive reset e MFA.
        candidate = await session.scalar(select(AccountAction.user_id).where(AccountAction.token_hash == digest(raw), AccountAction.purpose == purpose))
        if candidate is None:
            raise InvalidAction()
        user = await session.scalar(select(User).where(User.id == candidate).with_for_update())
        action = await session.scalar(select(AccountAction).where(AccountAction.token_hash == digest(raw), AccountAction.purpose == purpose).with_for_update())
        if user is None or action is None or action.consumed_at or action.expires_at <= now():
            raise InvalidAction()
        return user, action

    async def confirm_email(self, token):
        async with self.factory() as session, session.begin():
            user, action = await self.action(session, token, "VERIFY")
            security = await session.get(AccountSecurity, user.id)
            if security is None or not security.registration_pending or user.status != UserStatus.INACTIVE:
                raise InvalidAction()
            security.registration_pending = False
            security.email_verified_at = now()
            user.status = UserStatus.ACTIVE
            await self.invalidate(session, user.id)

    async def reset_password(self, data: ResetRequest):
        # Checar validade antes do trabalho de Argon2; revalidar após o hash na transação.
        async with self.factory() as reader:
            exists = await reader.scalar(select(AccountAction.id).where(AccountAction.token_hash == digest(data.token.get_secret_value()),
                AccountAction.purpose == "RESET", AccountAction.consumed_at.is_(None), AccountAction.expires_at > now()))
        if exists is None:
            raise InvalidAction()
        hashed = await self.password_hash(data.password)
        async with self.factory() as session, session.begin():
            user, action = await self.action(session, data.token, "RESET")
            credential = await session.get(UserPasswordCredential, user.id)
            current_hash = await session.scalar(select(UserPasswordCredential.password_hash).where(UserPasswordCredential.user_id == user.id))
            if user.status != UserStatus.ACTIVE or credential is None or current_hash != action.credential_hash:
                raise InvalidAction()
            credential.password_hash = hashed
            await self.invalidate(session, user.id)
            await self.revoke_sessions(session, user.id)
            # Recuperação de senha não remove o segundo fator.

    @staticmethod
    async def revoke_sessions(session, user_id, keep=None):
        query = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        if keep:
            query = query.where(UserSession.id != keep)
        await session.execute(query.values(revoked_at=now()))

    async def issue_mfa_challenge(self, user_id, expected_hash):
        async with self.factory() as session, session.begin():
            user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
            security = await session.get(AccountSecurity, user_id)
            credential = await session.scalar(select(UserPasswordCredential.password_hash).where(UserPasswordCredential.user_id == user_id))
            if user is None or user.status != UserStatus.ACTIVE or not security or not security.mfa_enabled or credential != expected_hash:
                raise InvalidAction()
            self.cipher()  # Uma chave ausente nunca permite pular MFA.
            await self.invalidate(session, user_id, "MFA_LOGIN")
            token, expires = SecretStr(secrets.token_urlsafe(32)), now() + timedelta(minutes=5)
            session.add(AccountAction(user_id=user_id, purpose="MFA_LOGIN", token_hash=digest(token.get_secret_value()),
                credential_hash=expected_hash, created_at=now(), expires_at=expires))
            return MfaChallenge(token, expires)

    def verify_factor(self, security, code: SecretStr, *, recovery=True):
        if not security or not security.mfa_secret:
            raise InvalidAction()
        try:
            secret = self.cipher().decrypt(security.mfa_secret.encode()).decode()
        except (InvalidToken, ValueError, UnicodeError):
            raise AccountUnavailable() from None
        value = code.get_secret_value().strip()
        if re.fullmatch(r"[0-9]{6}", value):
            step = int(now().timestamp()) // 30
            for candidate in (step, step - 1, step + 1):
                if candidate > security.mfa_last_step and hmac.compare_digest(totp(secret, candidate), value):
                    security.mfa_last_step = candidate
                    return
        elif recovery and security.mfa_enabled:
            hashes = json.loads(security.recovery_hashes or "[]")
            matching = next((item for item in hashes if hmac.compare_digest(item, digest(value))), None)
            if matching:
                hashes.remove(matching)
                security.recovery_hashes = json.dumps(hashes)
                return
        raise InvalidAction()

    async def complete_mfa_login(self, data):
        async with self.factory() as session, session.begin():
            user, action = await self.action(session, data.challenge_token, "MFA_LOGIN")
            security = await session.get(AccountSecurity, user.id)
            credential = await session.scalar(select(UserPasswordCredential.password_hash).where(UserPasswordCredential.user_id == user.id))
            if user.status != UserStatus.ACTIVE or not security or not security.mfa_enabled or credential != action.credential_hash:
                raise InvalidAction()
            self.verify_factor(security, data.code)
            action.consumed_at = now()
            token, created = SecretStr(secrets.token_urlsafe(32)), now()
            issued = UserSession(user_id=user.id, token_hash=digest(token.get_secret_value()), created_at=created, expires_at=created+self.idle_timeout)
            session.add(issued)
            await session.flush()
            return IssuedSession(issued.id, token, issued.expires_at)

    async def setup_mfa(self, current, password):
        cipher = self.cipher()
        async with self.factory() as reader:
            stored = await reader.scalar(select(UserPasswordCredential.password_hash).where(UserPasswordCredential.user_id == current.user_id))
        if not stored or not await self.password_matches(password, stored):
            raise InvalidAction()
        async with self.factory() as session, session.begin():
            await self.lock_active(session, current, stored)
            security = await session.get(AccountSecurity, current.user_id)
            if security is None:
                security = AccountSecurity(user_id=current.user_id)
                session.add(security)
            if security.mfa_enabled:
                raise InvalidAction()
            secret = base64.b32encode(secrets.token_bytes(20)).decode()
            security.mfa_secret = cipher.encrypt(secret.encode()).decode()
            security.mfa_pending_expires_at = now() + timedelta(minutes=10)
            security.mfa_last_step = -1
            return secret

    async def lock_active(self, session, current, stored=None):
        user = await session.scalar(select(User).where(User.id == current.user_id).with_for_update())
        live = await session.scalar(select(UserSession.id).where(UserSession.id == current.id, UserSession.revoked_at.is_(None), UserSession.expires_at > now()))
        credential = await session.scalar(select(UserPasswordCredential.password_hash).where(UserPasswordCredential.user_id == current.user_id))
        if not user or user.status != UserStatus.ACTIVE or live is None or (stored is not None and credential != stored):
            raise InvalidAction()

    async def enable_mfa(self, current, code):
        async with self.factory() as session, session.begin():
            await self.lock_active(session, current)
            security = await session.get(AccountSecurity, current.user_id)
            if not security or security.mfa_enabled or not security.mfa_pending_expires_at or security.mfa_pending_expires_at <= now():
                raise InvalidAction()
            self.verify_factor(security, code, recovery=False)
            codes = [secrets.token_hex(12) for _ in range(8)]
            security.recovery_hashes = json.dumps([digest(c) for c in codes])
            security.mfa_enabled = True
            security.mfa_pending_expires_at = None
            await self.revoke_sessions(session, current.user_id, keep=current.id)
            await self.invalidate(session, current.user_id, "MFA_LOGIN")
            return codes

    async def disable_mfa(self, current, data):
        async with self.factory() as reader:
            stored = await reader.scalar(select(UserPasswordCredential.password_hash).where(UserPasswordCredential.user_id == current.user_id))
        if not stored or not await self.password_matches(data.password, stored):
            raise InvalidAction()
        async with self.factory() as session, session.begin():
            await self.lock_active(session, current, stored)
            security = await session.get(AccountSecurity, current.user_id)
            if not security or not security.mfa_enabled:
                raise InvalidAction()
            self.verify_factor(security, data.code)
            security.mfa_enabled = False
            security.mfa_secret = security.recovery_hashes = None
            security.mfa_last_step = -1
            await self.revoke_sessions(session, current.user_id, keep=current.id)
            await self.invalidate(session, current.user_id, "MFA_LOGIN")
