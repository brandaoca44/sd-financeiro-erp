"""Inicializa o primeiro operador por execução administrativa, sem API pública."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, StringConstraints, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import PlatformBootstrap, User, UserPasswordCredential, UserStatus
from app.modules.identity.passwords import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, hash_password


# Identificador estável compartilhado por todas as execuções deste bootstrap.
_BOOTSTRAP_LOCK_ID = 734_905_318_612
_COMMON_BOOTSTRAP_PASSWORDS = frozenset({
    "123456789012345", "12345678901234567890", "password123456789",
    "senha12345678901", "administrador123", "qwertyuiop123456",
})


class BootstrapOperatorInput(BaseModel):
    """Valida os dados administrativos sem aceitar status ou permissões do chamador."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        """Aplica a mesma convenção de comparação da identidade."""

        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def reject_obvious_weak_passwords(cls, value: SecretStr) -> SecretStr:
        """Aplica bloqueio local mínimo; não consulta serviços externos com a senha."""

        plain = value.get_secret_value()
        if plain.lower() in _COMMON_BOOTSTRAP_PASSWORDS or len(set(plain)) == 1:
            raise ValueError("Escolha uma senha menos previsível.")
        return value


class BootstrapAlreadyInitializedError(Exception):
    """Impede repetição do bootstrap ou criação paralela de operadores iniciais."""


class BootstrapAccountConflictError(Exception):
    """Impede promoção implícita de uma conta já existente."""


class PlatformBootstrapService:
    """Cria identidade, hash e marcador em uma única transação administrativa.

    Exige sessão dedicada sem transação anterior. Não fornece cadastro público,
    recuperação de acesso ou concessão de vínculos com organizações.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_operator(self, data: BootstrapOperatorInput) -> UUID:
        """Inicializa uma vez; retorna apenas o UUID após confirmar a transação."""

        async with self._session.begin():
            await self._session.execute(text("SET LOCAL lock_timeout = '5s'"))
            await self._session.execute(select(func.pg_advisory_xact_lock(_BOOTSTRAP_LOCK_ID)))
            initialized = await self._session.scalar(select(PlatformBootstrap.id).limit(1))
            existing_operator = await self._session.scalar(select(User.id).where(
                User.can_provision_organizations.is_(True),
            ).limit(1))
            if initialized is not None or existing_operator is not None:
                raise BootstrapAlreadyInitializedError("Inicialização já concluída ou operador preexistente.")
            existing_account = await self._session.scalar(select(User.id).where(func.lower(User.email) == str(data.email)))
            if existing_account is not None:
                raise BootstrapAccountConflictError("O bootstrap não pode promover uma conta existente.")
            password_hash = await hash_password(data.password)
            user = User(
                name=data.name, email=str(data.email), status=UserStatus.ACTIVE,
                can_provision_organizations=True,
            )
            self._session.add(user)
            await self._session.flush()
            self._session.add_all([
                UserPasswordCredential(user_id=user.id, password_hash=password_hash.get_secret_value()),
                PlatformBootstrap(id=1, user_id=user.id),
            ])
            await self._session.flush()
            user_id = user.id
        return user_id
