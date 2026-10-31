"""Designação e transferência internas, com reautenticação e transação própria."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.access_models import OrganizationOwnership, OwnershipChange
from app.modules.identity.models import (
    MembershipStatus, OrganizationMembership, User, UserPasswordCredential, UserSession, UserStatus,
)
from app.modules.identity.passwords import verify_password
from app.modules.identity.sessions import SessionService
from app.modules.organizations.models import Organization, OrganizationStatus


class OwnershipChangeDeniedError(Exception):
    """Resposta única para credenciais, destinatário ou autoridade inválidos."""


class OrganizationOwnershipService:
    """Exige sessão de escrita nova e limitação pelo adaptador HTTP.

    O chamador futuro deve limitar tentativas e concorrência antes de verificar senha.
    Não cria vínculos nem altera concessões legadas. Não oferece recuperação de Master.
    """

    def __init__(self, session: AsyncSession, *, idle_timeout: timedelta = timedelta(minutes=30)):
        if not isinstance(idle_timeout, timedelta) or not timedelta(0) < idle_timeout <= timedelta(days=1):
            raise ValueError("Prazo de inatividade inválido.")
        self._session = session
        self._idle_timeout = idle_timeout

    async def designate(self, *, organization_id: UUID, new_owner_id: UUID,
                        token: SecretStr, password: SecretStr) -> None:
        """Permite ao provisionador designar apenas organização sem proprietário."""
        await self._change(organization_id, new_owner_id, token, password, initial=True)

    async def transfer(self, *, organization_id: UUID, new_owner_id: UUID,
                       token: SecretStr, password: SecretStr) -> None:
        """Somente o proprietário atual pode transferir para outro vínculo ativo."""
        await self._change(organization_id, new_owner_id, token, password, initial=False)

    @staticmethod
    def _deny():
        raise OwnershipChangeDeniedError("Não foi possível alterar o proprietário.")

    async def _change(self, organization_id, new_owner_id, token, password, *, initial):
        if not isinstance(organization_id, UUID) or not isinstance(new_owner_id, UUID):
            self._deny()
        token_hash = SessionService._token_hash(token)
        if token_hash is None or not isinstance(password, SecretStr):
            self._deny()
        async with self._session.begin():
            await self._session.execute(text("SET LOCAL lock_timeout = '5s'"))
            # A organização serializa inclusive duas designações quando ainda não há owner.
            organization = await self._session.scalar(select(Organization).where(
                Organization.id == organization_id,
            ).with_for_update())
            if organization is None or organization.status != OrganizationStatus.ACTIVE:
                self._deny()
            actor_id = await self._session.scalar(select(UserSession.user_id).where(
                UserSession.token_hash == token_hash,
            ))
            if actor_id is None:
                self._deny()
            owner = await self._session.scalar(select(OrganizationOwnership).where(
                OrganizationOwnership.organization_id == organization_id,
            ).with_for_update())
            # Recusa atores sem autoridade antes de consultar dados do destinatário.
            provisioner = await self._session.scalar(select(User.can_provision_organizations).where(
                User.id == actor_id, User.status == UserStatus.ACTIVE,
            ))
            if initial:
                if owner is not None or not provisioner:
                    self._deny()
            elif owner is None or owner.user_id != actor_id or actor_id == new_owner_id:
                self._deny()
            # Ordem estável entre atores/destinatários compartilhados por vários tenants.
            users = (await self._session.scalars(select(User).where(
                User.id.in_({actor_id, new_owner_id}),
            ).order_by(User.id).with_for_update())).all()
            by_id = {user.id: user for user in users}
            if any(uid not in by_id or by_id[uid].status != UserStatus.ACTIVE
                   for uid in (actor_id, new_owner_id)):
                self._deny()
            credential = await self._session.scalar(select(UserPasswordCredential.password_hash).where(
                UserPasswordCredential.user_id == actor_id,
            ).with_for_update())
            if credential is None:
                self._deny()
            verification = asyncio.create_task(verify_password(password, credential))
            try:
                valid, _ = await asyncio.shield(verification)
            except asyncio.CancelledError:
                # A thread de Argon2 continua; manter a vaga até terminar e reverter.
                await asyncio.shield(verification)
                raise
            if not valid:
                self._deny()
            # Revalida após Argon2 e espera por locks; logout concorrente não é ignorado.
            login = await self._session.scalar(select(UserSession).where(
                UserSession.token_hash == token_hash,
            ).with_for_update())
            now = datetime.now(timezone.utc)
            if login is None or login.revoked_at is not None or not login.created_at <= now < login.expires_at:
                self._deny()
            if initial:
                if owner is not None or not by_id[actor_id].can_provision_organizations:
                    self._deny()
            elif owner is None or owner.user_id != actor_id or actor_id == new_owner_id:
                self._deny()
            required_members = {new_owner_id} if initial else {actor_id, new_owner_id}
            members = (await self._session.scalars(select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id.in_(required_members),
            ).order_by(OrganizationMembership.user_id).with_for_update())).all()
            if {m.user_id for m in members if m.status == MembershipStatus.ACTIVE} != required_members:
                self._deny()
            previous = owner.user_id if owner is not None else None
            if owner is None:
                self._session.add(OrganizationOwnership(organization_id=organization_id, user_id=new_owner_id))
            else:
                owner.user_id = new_owner_id
                owner.revision += 1
            self._session.add(OwnershipChange(organization_id=organization_id, actor_user_id=actor_id,
                                             previous_user_id=previous, new_user_id=new_owner_id))
            login.expires_at = max(login.expires_at, now + self._idle_timeout)
            await self._session.flush()
