"""Perfil pessoal do próprio usuário, protegido por criptografia e revisão."""
import hashlib
import hmac
import json
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import ConfigDict, Field, SecretStr, StringConstraints, field_validator
from sqlalchemy import ForeignKey, Integer, Text, Uuid, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import mapped_column

from app.api.v1.account import execute, limited, service
from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity
from app.database.base import Base
from app.modules.identity.account_models import AccountSecurity
from app.modules.identity.account_security import AccountUnavailable, RegisterRequest
from app.modules.identity.models import User, UserPasswordCredential, UserSession, UserStatus
from app.modules.identity.pix import PixDetails, normalize_passport

Text80 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Digits = Annotated[str, StringConstraints(pattern=r"^[0-9]{1,30}$")]


class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    encrypted_data = mapped_column(Text, nullable=False)
    revision = mapped_column(Integer, nullable=False)


class PersonalDetails(PixDetails):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    cpf: Annotated[str, StringConstraints(pattern=r"^[0-9]{11}$")] | None = None
    rg: Digits | None = None
    passport: Text80 | None = None
    cnh: Annotated[str, StringConstraints(pattern=r"^[0-9]{11}$")] | None = None
    birth_date: date | None = None
    phone: Annotated[str, StringConstraints(pattern=r"^[0-9]{10,11}$")] | None = None
    cep: Annotated[str, StringConstraints(pattern=r"^[0-9]{8}$")] | None = None
    address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)] | None = None
    bank: Text80 | None = None
    branch: Digits | None = None
    account: Digits | None = None
    account_type: Literal["CORRENTE", "POUPANCA", "SALARIO", "PAGAMENTO"] | None = None

    @field_validator("cpf")
    @classmethod
    def validate_cpf(cls, value):
        return RegisterRequest.cpf_valid(SecretStr(value)).get_secret_value() if value else value

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, value):
        if value and value > date.today():
            raise ValueError("Confira a data de nascimento.")
        return value


class ProfileResponse(PersonalDetails):
    name: str
    email: str
    revision: int
    cpf_locked: bool


class ProfileUpdate(PersonalDetails):
    @field_validator("passport")
    @classmethod
    def validate_passport(cls, value):
        return normalize_passport(value)

    name: Annotated[str, StringConstraints(min_length=2, max_length=150)]
    expected_revision: int = Field(ge=0, strict=True)
    password: SecretStr = Field(min_length=1, max_length=128, repr=False)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        return RegisterRequest.name_valid(value)


def profile_cipher(request):
    key = request.app.state.settings.auth_identity_encryption_key
    if key is None:
        raise AccountUnavailable()
    return Fernet(key.get_secret_value().encode("ascii"))


def decode_profile(row, security, user_id, request):
    details = PersonalDetails()
    try:
        if row:
            envelope = json.loads(profile_cipher(request).decrypt(row.encrypted_data.encode()))
            if envelope["user_id"] != str(user_id):
                raise AccountUnavailable()
            details = PersonalDetails.model_validate(envelope["details"])
        if security and security.cpf_encrypted:
            details.cpf = profile_cipher(request).decrypt(security.cpf_encrypted.encode()).decode("ascii")
        return details
    except (InvalidToken, ValueError, KeyError):
        raise AccountUnavailable() from None


router = APIRouter(prefix="/auth/profile", tags=["Minha conta"])


@router.get("", response_model=ProfileResponse)
async def get_profile(request: Request, response: Response,
                      current=Depends(get_current_session), token=Depends(get_session_token)):
    async def work():
        await limited(request, str(current.user_id))
        async with request.app.state.session_factory() as session:
            user = await session.get(User, current.user_id)
            if user is None or user.status != UserStatus.ACTIVE:
                raise HTTPException(401, "Sessão inválida.")
            security = await session.get(AccountSecurity, current.user_id)
            row = await session.get(UserProfile, current.user_id)
            data = decode_profile(row, security, user.id, request)
            result = ProfileResponse(name=user.name, email=user.email, revision=row.revision if row else 0,
                                     cpf_locked=bool(security and security.cpf_encrypted), **data.model_dump())
        await record_authorized_activity(request, token)
        response.headers["Cache-Control"] = "no-store"
        return result
    return await execute(work())


@router.put("", response_model=ProfileResponse)
async def update_profile(data: ProfileUpdate, request: Request, response: Response,
                         current=Depends(get_current_session), token=Depends(get_session_token), accounts=Depends(service)):
    async def work():
        await limited(request, str(current.user_id))
        cipher = profile_cipher(request)
        try:
            async with request.app.state.session_factory() as session, session.begin():
                user = await session.scalar(select(User).where(User.id == current.user_id).with_for_update())
                if user is None or user.status != UserStatus.ACTIVE:
                    raise HTTPException(401, "Sessão inválida.")
                credential = await session.scalar(select(UserPasswordCredential.password_hash).where(
                    UserPasswordCredential.user_id == user.id).with_for_update())
                if credential is None or not await accounts.password_matches(data.password, credential):
                    raise HTTPException(403, "Não foi possível confirmar a alteração.")
                security = await session.scalar(select(AccountSecurity).where(
                    AccountSecurity.user_id == user.id).with_for_update())
                login = await session.scalar(select(UserSession).where(
                    UserSession.id == current.id, UserSession.user_id == user.id).with_for_update())
                now = datetime.now(timezone.utc)
                if login is None or login.revoked_at or not login.created_at <= now < login.expires_at:
                    raise HTTPException(401, "Sessão inválida.")
                row = await session.get(UserProfile, user.id)
                revision = row.revision if row else 0
                if data.expected_revision != revision:
                    raise HTTPException(409, "O perfil foi alterado. Recarregue antes de salvar.")
                original = decode_profile(row, security, user.id, request)
                if original.cpf and data.cpf != original.cpf:
                    raise HTTPException(409, "O CPF já registrado não pode ser alterado por esta tela.")
                details = PersonalDetails.model_validate(data.model_dump(exclude={"name", "password", "expected_revision"}))
                if details.cpf and not (security and security.cpf_encrypted):
                    if security is None:
                        security = AccountSecurity(user_id=user.id)
                        session.add(security)
                    key = request.app.state.settings.auth_identity_encryption_key.get_secret_value().encode()
                    security.cpf_encrypted = cipher.encrypt(details.cpf.encode()).decode()
                    security.cpf_digest = hmac.new(key, ("cpf:" + details.cpf).encode(), hashlib.sha256).hexdigest()
                envelope = json.dumps({"user_id": str(user.id), "details": details.model_dump(mode="json")})
                encrypted = cipher.encrypt(envelope.encode()).decode()
                if row is None:
                    session.add(UserProfile(user_id=user.id, encrypted_data=encrypted, revision=1))
                else:
                    row.encrypted_data = encrypted
                    row.revision += 1
                user.name = data.name
                login.expires_at = max(login.expires_at, now + timedelta(
                    seconds=request.app.state.settings.auth_idle_timeout_seconds))
                await session.flush()
                result = ProfileResponse(name=user.name, email=user.email, revision=revision+1,
                                         cpf_locked=bool(details.cpf), **details.model_dump())
        except IntegrityError:
            raise HTTPException(409, "Não foi possível salvar os dados de identificação.") from None
        response.headers["Cache-Control"] = "no-store"
        return result
    return await execute(work())
