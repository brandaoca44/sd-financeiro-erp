"""Avalia visibilidade do cadastro jurídico no escopo exato da empresa."""

from uuid import UUID

from sqlalchemy import and_, or_, select

from app.modules.identity.access_models import OrganizationOwnership
from app.modules.identity.authorization import OrganizationAccessPolicy
from app.modules.identity.company_access_models import CompanyPermissionGrant
from app.modules.identity.models import MembershipStatus, OrganizationMembership, User, UserStatus
from app.modules.identity.permissions import PermissionKey
from app.modules.organizations.models import Company, CompanyStatus, Organization, OrganizationStatus


class CompanyAccessPolicy:
    def __init__(self, session):
        self.session = session

    @staticmethod
    def _active_actor(user_id, organization_id):
        return select(OrganizationMembership.user_id).join(User).join(
            Organization, Organization.id == OrganizationMembership.organization_id,
        ).where(User.id == user_id, User.status == UserStatus.ACTIVE,
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.status == MembershipStatus.ACTIVE,
            Organization.status == OrganizationStatus.ACTIVE).exists()

    @staticmethod
    def _direct_grant(user_id, organization_id):
        return select(CompanyPermissionGrant.user_id).where(
            CompanyPermissionGrant.organization_id == organization_id,
            CompanyPermissionGrant.company_id == Company.id,
            CompanyPermissionGrant.user_id == user_id,
            CompanyPermissionGrant.permission_key == PermissionKey.COMPANIES_READ,
            CompanyPermissionGrant.status == "ACTIVE",
        ).correlate(Company).exists()

    def visibility(self, user_id: UUID, organization_id: UUID):
        owner = select(OrganizationOwnership.organization_id).where(
            OrganizationOwnership.organization_id == organization_id, OrganizationOwnership.user_id == user_id,
        ).exists()
        return and_(Company.organization_id == organization_id, self._active_actor(user_id, organization_id), or_(owner,
            and_(Company.status == CompanyStatus.ACTIVE, self._direct_grant(user_id, organization_id))))

    async def can_read(self, user_id: UUID, organization_id: UUID, company_id: UUID, *, grant_only=False):
        if not all(isinstance(value, UUID) for value in (user_id, organization_id, company_id)):
            return False
        condition = self.visibility(user_id, organization_id)
        if grant_only:
            condition = and_(self._active_actor(user_id, organization_id),
                Company.status == CompanyStatus.ACTIVE, self._direct_grant(user_id, organization_id))
        query = select(Company.id).where(Company.organization_id == organization_id, Company.id == company_id, condition)
        with self.session.no_autoflush:
            return (await self.session.scalar(select(query.exists()))) is True

    async def can_list(self, user_id: UUID, organization_id: UUID):
        if not isinstance(user_id, UUID) or not isinstance(organization_id, UUID):
            return False
        if await OrganizationAccessPolicy(self.session).has_permission(user_id, organization_id, PermissionKey.COMPANIES_MANAGE):
            return True
        query = select(Company.id).where(Company.organization_id == organization_id, self.visibility(user_id, organization_id))
        with self.session.no_autoflush:
            return (await self.session.scalar(select(query.exists()))) is True
