"""Avalia permissões organizacionais persistidas, sem autenticar o solicitante."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import (
    MembershipStatus,
    OrganizationMembership,
    User,
    UserStatus,
)


class OrganizationAccessPolicy:
    """Consulta permissões no banco, sem cache ORM, commit ou rollback.

    O identificador do usuário deve vir de autenticação validada no servidor,
    nunca diretamente de parâmetros HTTP. O chamador fornece sessão de leitura
    separada da sessão de criação controlada pelo OrganizationService.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def can_provision_organizations(self, user_id: UUID | None) -> bool:
        """Exige identidade ativa e concessão explícita de provisionamento."""

        if not isinstance(user_id, UUID):
            return False

        authorized = select(User.id).where(
            User.id == user_id,
            User.status == UserStatus.ACTIVE,
            User.can_provision_organizations.is_(True),
        )
        with self._session.no_autoflush:
            return (await self._session.scalar(select(authorized.exists()))) is True

    async def can_read_organization(
        self, user_id: UUID | None, organization_id: UUID,
    ) -> bool:
        """Exige usuário ativo, vínculo ativo e leitura concedida no tenant solicitado."""

        if not isinstance(user_id, UUID) or not isinstance(organization_id, UUID):
            return False

        authorized = (
            select(OrganizationMembership.user_id)
            .join(User, User.id == OrganizationMembership.user_id)
            .where(
                User.id == user_id,
                User.status == UserStatus.ACTIVE,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.status == MembershipStatus.ACTIVE,
                OrganizationMembership.can_read_organization.is_(True),
            )
        )
        with self._session.no_autoflush:
            return (await self._session.scalar(select(authorized.exists()))) is True
