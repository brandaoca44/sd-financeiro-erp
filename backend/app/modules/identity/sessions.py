"""Gerencia sessões internas sem expor login, transporte HTTP ou permissões."""

import hashlib
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import User, UserPasswordCredential, UserSession, UserStatus


@dataclass(frozen=True)
class IssuedSession:
    """Retorna o token somente após confirmar sua persistência."""

    id: UUID
    token: SecretStr
    expires_at: datetime


@dataclass(frozen=True)
class AuthenticatedSession:
    """Identifica a sessão válida, sem carregar o token ou permissões do usuário."""

    id: UUID
    user_id: UUID
    expires_at: datetime


class SessionIssueDeniedError(Exception):
    """Indica que a identidade não pode receber uma sessão."""


class SessionService:
    """Emite, registra atividade e revoga com transações próprias.

    A emissão só pode ser chamada após autenticação real do usuário. Emissão,
    registro de atividade e revogação exigem sessão sem transação anterior; use
    sessões de escrita separadas da resolução/autorização. O prazo de inatividade
    e o relógio são configurações do servidor. Não há limite absoluto de duração.
    """

    def __init__(
        self, session: AsyncSession, *, idle_timeout: timedelta = timedelta(minutes=30),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(idle_timeout, timedelta) or not timedelta(0) < idle_timeout <= timedelta(days=1):
            raise ValueError("O prazo de inatividade deve ser positivo e não ultrapassar 24 horas.")
        self._session = session
        self._idle_timeout = idle_timeout
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("O relógio da sessão deve fornecer data e hora com fuso.")
        return now.astimezone(timezone.utc)

    @staticmethod
    def _token_hash(token: SecretStr) -> str | None:
        if not isinstance(token, SecretStr):
            return None
        value = token.get_secret_value()
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", value) is None:
            return None
        return hashlib.sha256(value.encode("ascii")).hexdigest()

    async def issue_for_authenticated_user(
        self, user_id: UUID, *, expected_password_hash: str | None = None,
        replacement_hash: SecretStr | None = None,
    ) -> IssuedSession:
        """Emite token novo para identidade ativa já autenticada pelo chamador."""

        if not isinstance(user_id, UUID):
            raise SessionIssueDeniedError("Não foi possível emitir a sessão.")
        async with self._session.begin():
            active_user = await self._session.scalar(select(User.id).where(
                User.id == user_id, User.status == UserStatus.ACTIVE,
            ).with_for_update())
            if active_user is None:
                raise SessionIssueDeniedError("Não foi possível emitir a sessão.")
            if expected_password_hash is not None:
                current_hash = await self._session.scalar(select(UserPasswordCredential.password_hash).where(
                    UserPasswordCredential.user_id == user_id,
                ).with_for_update())
                if current_hash is None or not secrets.compare_digest(current_hash, expected_password_hash):
                    raise SessionIssueDeniedError("Não foi possível emitir a sessão.")
                if replacement_hash is not None:
                    await self._session.execute(update(UserPasswordCredential).where(
                        UserPasswordCredential.user_id == user_id,
                    ).values(password_hash=replacement_hash.get_secret_value()))
            elif replacement_hash is not None:
                raise SessionIssueDeniedError("Não foi possível emitir a sessão.")
            now = self._now()
            token = SecretStr(secrets.token_urlsafe(32))
            session = UserSession(
                user_id=active_user, token_hash=self._token_hash(token),
                created_at=now, expires_at=now + self._idle_timeout,
            )
            self._session.add(session)
            await self._session.flush()
            issued = IssuedSession(id=session.id, token=token, expires_at=session.expires_at)
        return issued

    async def resolve(self, token: SecretStr) -> AuthenticatedSession | None:
        """Rejeita tokens inválidos, expirados, revogados ou de usuários inativos."""

        token_hash = self._token_hash(token)
        if token_hash is None:
            return None
        now = self._now()
        with self._session.no_autoflush:
            row = (await self._session.execute(
                select(UserSession.id, UserSession.user_id, UserSession.expires_at)
                .join(User, User.id == UserSession.user_id)
                .where(
                    UserSession.token_hash == token_hash,
                    UserSession.created_at <= now,
                    UserSession.expires_at > now,
                    UserSession.revoked_at.is_(None),
                    User.status == UserStatus.ACTIVE,
                )
            )).one_or_none()
        return AuthenticatedSession(*row) if row is not None else None

    async def revoke(self, token: SecretStr) -> None:
        """Revoga pelo token possuído, sem revelar existência ou repetir efeitos."""

        token_hash = self._token_hash(token)
        if token_hash is None:
            return
        now = self._now()
        async with self._session.begin():
            await self._session.execute(update(UserSession).where(
                UserSession.token_hash == token_hash,
                UserSession.revoked_at.is_(None),
            ).values(revoked_at=now).execution_options(synchronize_session=False))

    async def record_activity(self, token: SecretStr) -> AuthenticatedSession | None:
        """Renova sessão válida por atividade real, sem ressuscitar sessão expirada.

        O chamador deve registrar somente interações autenticadas e autorizadas,
        não polling, heartbeats ou atualizações automáticas em segundo plano.
        """

        token_hash = self._token_hash(token)
        if token_hash is None:
            return None
        now = self._now()
        async with self._session.begin():
            row = (await self._session.execute(
                update(UserSession).where(
                    UserSession.token_hash == token_hash,
                    UserSession.created_at <= now,
                    UserSession.expires_at > now,
                    UserSession.revoked_at.is_(None),
                    UserSession.user_id.in_(select(User.id).where(User.status == UserStatus.ACTIVE)),
                ).values(expires_at=func.greatest(
                    UserSession.expires_at, now + self._idle_timeout,
                )).returning(
                    UserSession.id, UserSession.user_id, UserSession.expires_at,
                ).execution_options(synchronize_session=False)
            )).one_or_none()
            result = AuthenticatedSession(*row) if row is not None else None
        return result
