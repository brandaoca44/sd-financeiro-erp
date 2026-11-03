"""Integra rate limit, senha e emissão transacional sem detalhes HTTP."""

import asyncio
from datetime import timedelta

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.modules.identity.account_models import AccountSecurity
from app.modules.identity.account_security import InvalidAction
from app.modules.identity.models import User, UserPasswordCredential, UserStatus
from app.modules.identity.passwords import verify_password
from app.modules.identity.rate_limit import LoginRateLimiter
from app.modules.identity.sessions import IssuedSession, SessionIssueDeniedError, SessionService


class LoginRequest(BaseModel):
    """Recebe somente credenciais, sem privilégios ou contexto de tenant do cliente."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class InvalidCredentialsError(Exception):
    """Representa qualquer falha de credencial sem revelar existência da conta."""


class AuthenticationBusyError(Exception):
    """Evita trabalho e fila ilimitados de hash dentro de cada worker."""


class AuthenticationService:
    def __init__(
        self, session_factory: async_sessionmaker, limiter: LoginRateLimiter,
        *, dummy_hash: SecretStr, idle_timeout: timedelta, hash_concurrency: int = 2,
        hash_slots: asyncio.Semaphore | None = None,
    ) -> None:
        self.account_service = None
        self._factory = session_factory
        self._limiter = limiter
        self._dummy_hash = dummy_hash
        self._idle_timeout = idle_timeout
        self._hash_slots = hash_slots if hash_slots is not None else asyncio.Semaphore(hash_concurrency)

    async def login(self, data: LoginRequest, *, origin_ip: str) -> IssuedSession:
        await self._limiter.check(account_identifier=str(data.email), origin_ip=origin_ip)
        try:
            await asyncio.wait_for(self._hash_slots.acquire(), timeout=0.25)
        except TimeoutError:
            raise AuthenticationBusyError("Autenticação temporariamente indisponível.") from None
        try:
            async with self._factory() as reader:
                row = (await reader.execute(select(
                    User.id, User.status, UserPasswordCredential.password_hash,
                ).outerjoin(UserPasswordCredential, UserPasswordCredential.user_id == User.id)
                  .where(func.lower(User.email) == str(data.email)))).one_or_none()
            eligible = row is not None and row.status == UserStatus.ACTIVE and row.password_hash is not None
            candidate_hash = row.password_hash if eligible else self._dummy_hash.get_secret_value()
            verification = asyncio.create_task(verify_password(data.password, candidate_hash))
            try:
                valid, replacement = await asyncio.shield(verification)
            except asyncio.CancelledError:
                # Hash em thread continua após cancelamento; não liberar a vaga antes dele.
                await asyncio.shield(verification)
                raise
            if not eligible or not valid:
                raise InvalidCredentialsError("E-mail ou senha inválidos.")
            async with self._factory() as reader:
                enabled = await reader.scalar(select(AccountSecurity.mfa_enabled).where(AccountSecurity.user_id == row.id))
            if enabled:
                if self.account_service is None:
                    raise AuthenticationBusyError()
                try:
                    return await self.account_service.issue_mfa_challenge(row.id, row.password_hash)
                except InvalidAction:
                    raise InvalidCredentialsError() from None
            async with self._factory() as writer:
                try:
                    return await SessionService(writer, idle_timeout=self._idle_timeout).issue_for_authenticated_user(
                        row.id, expected_password_hash=row.password_hash, replacement_hash=replacement,
                    )
                except SessionIssueDeniedError:
                    raise InvalidCredentialsError("E-mail ou senha inválidos.") from None
        finally:
            self._hash_slots.release()
