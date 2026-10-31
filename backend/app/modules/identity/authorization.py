"""Avalia permissões organizacionais persistidas, sem autenticar o solicitante."""

from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.modules.identity.access_models import (
    OrganizationOwnership, OrganizationRole, OrganizationRoleAssignment, RoleAssignmentStatus, RoleStatus,
)
from app.modules.identity.permission_models import (
    OrganizationAccessDelegation, OrganizationDelegationPermission, OrganizationRolePermission,
)
from app.modules.identity.permissions import PermissionKey
from app.modules.organizations.models import Organization, OrganizationStatus

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

    @staticmethod
    def delegation_query(user_id, organization_id, *, revision=None, permission_key=None):
        """Autoridade direta do Master vigente; sem somar perfis ou redelegar."""
        owner_user, delegate_user = aliased(User), aliased(User)
        owner_member, delegate_member = aliased(OrganizationMembership), aliased(OrganizationMembership)
        d, o = OrganizationAccessDelegation, OrganizationOwnership
        query = select(d.user_id).join(o, and_(
            o.organization_id == d.organization_id, o.user_id == d.granted_by_user_id, o.revision == d.owner_revision,
        )).join(owner_user, owner_user.id == o.user_id).join(owner_member, and_(
            owner_member.user_id == o.user_id, owner_member.organization_id == o.organization_id,
        )).join(delegate_user, delegate_user.id == d.user_id).join(delegate_member, and_(
            delegate_member.user_id == d.user_id, delegate_member.organization_id == d.organization_id,
        )).where(
            d.user_id == user_id, d.organization_id == organization_id, d.status == "ACTIVE",
            owner_user.status == UserStatus.ACTIVE, delegate_user.status == UserStatus.ACTIVE,
            owner_member.status == MembershipStatus.ACTIVE, delegate_member.status == MembershipStatus.ACTIVE,
        )
        if revision is not None:
            query = query.where(d.revision == revision)
        if permission_key is not None:
            query = query.join(OrganizationDelegationPermission, and_(
                OrganizationDelegationPermission.organization_id == d.organization_id,
                OrganizationDelegationPermission.user_id == d.user_id,
            )).where(OrganizationDelegationPermission.permission_key == permission_key)
        return query

    def _role_grant(self, user_id, organization_id, permission_key):
        a, r, p = OrganizationRoleAssignment, OrganizationRole, OrganizationRolePermission
        source = self.delegation_query(a.delegated_by_user_id, a.organization_id,
            revision=a.delegation_revision, permission_key=permission_key).correlate(a).exists()
        return select(a.user_id).join(r, and_(r.id == a.role_id, r.organization_id == a.organization_id)).join(
            p, and_(p.role_id == r.id, p.organization_id == r.organization_id),
        ).where(
            a.user_id == user_id, a.organization_id == organization_id,
            a.status == RoleAssignmentStatus.ACTIVE, r.status == RoleStatus.ACTIVE,
            p.permission_key == permission_key, or_(a.delegated_by_user_id.is_(None), source),
        ).exists()

    async def has_permission(self, user_id: UUID, organization_id: UUID, permission_key: str) -> bool:
        if not isinstance(user_id, UUID) or not isinstance(organization_id, UUID):
            return False
        try:
            key = PermissionKey(permission_key)
        except (ValueError, TypeError):
            return False
        if key == PermissionKey.ORGANIZATION_READ:
            return await self.can_read_organization(user_id, organization_id)
        owner = select(OrganizationOwnership.organization_id).where(
            OrganizationOwnership.organization_id == organization_id, OrganizationOwnership.user_id == user_id,
        ).exists()
        authority = owner
        if key == PermissionKey.ROLES_READ:
            authority = or_(owner, self._role_grant(user_id, organization_id, key))
        elif key == PermissionKey.ASSIGNMENTS_MANAGE:
            authority = or_(owner, self.delegation_query(user_id, organization_id).exists())
        authorized = select(OrganizationMembership.user_id).join(User).join(
            Organization, Organization.id == OrganizationMembership.organization_id,
        ).where(
            User.id == user_id, User.status == UserStatus.ACTIVE,
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.status == MembershipStatus.ACTIVE,
            Organization.status == OrganizationStatus.ACTIVE, authority,
        )
        with self._session.no_autoflush:
            return (await self._session.scalar(select(authorized.exists()))) is True

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
                or_(OrganizationMembership.can_read_organization.is_(True),
                    self._role_grant(user_id, organization_id, PermissionKey.ORGANIZATION_READ)),
            )
        )
        with self._session.no_autoflush:
            return (await self._session.scalar(select(authorized.exists()))) is True
