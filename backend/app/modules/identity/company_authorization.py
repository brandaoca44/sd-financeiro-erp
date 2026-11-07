"""Avalia visibilidade do cadastro jurídico no escopo exato da empresa."""

from uuid import UUID

from sqlalchemy import and_, func, or_, select

from app.modules.commercial.catalog import CATALOG_VERSION, FEATURES, PLANS, Feature
from app.modules.commercial.models import BusinessCompanyActivation, BusinessContract
from app.modules.identity.access_models import OrganizationOwnership
from app.modules.identity.authorization import OrganizationAccessPolicy
from app.modules.identity.company_access_models import CompanyPermissionGrant
from app.modules.identity.models import MembershipStatus, OrganizationMembership, User, UserStatus
from app.modules.identity.permissions import PermissionKey, COMPANY_PERMISSIONS
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
    def _direct_grant(user_id, organization_id, permission_key=PermissionKey.COMPANIES_READ):
        return select(CompanyPermissionGrant.user_id).where(
            CompanyPermissionGrant.organization_id == organization_id,
            CompanyPermissionGrant.company_id == Company.id,
            CompanyPermissionGrant.user_id == user_id,
            CompanyPermissionGrant.permission_key == permission_key,
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

    @staticmethod
    def _licensed_company(organization_id, permission_key):
        feature_key = Feature.RECEIVABLES if permission_key.startswith("billing.") else (
            Feature.STAFF_COSTS if permission_key.startswith("people.") else
            Feature.CASHFLOW if permission_key.startswith("accounts.") else Feature.PAYABLES)
        feature = FEATURES[feature_key]
        plans = [key.value for key, plan in PLANS.items() if feature.key in plan.features]
        if not feature.available or permission_key not in feature.permissions:
            plans = []
        return select(BusinessCompanyActivation.company_id).join(
            BusinessContract, BusinessContract.organization_id == BusinessCompanyActivation.organization_id,
        ).where(
            BusinessCompanyActivation.organization_id == organization_id,
            BusinessCompanyActivation.company_id == Company.id,
            BusinessContract.catalog_version == CATALOG_VERSION,
            BusinessContract.plan.in_(plans),
            BusinessContract.status == "ACTIVE",
            BusinessContract.valid_from <= func.statement_timestamp(),
            BusinessContract.valid_until > func.statement_timestamp(),
        ).correlate(Company).exists()

    async def lock_financial_contract(self, organization_id, company_id):
        contract_id = await self.session.scalar(select(BusinessContract.organization_id).where(
            BusinessContract.organization_id == organization_id,
        ).with_for_update(read=True))
        if contract_id is None:
            return False
        activation_id = await self.session.scalar(select(BusinessCompanyActivation.company_id).where(
            BusinessCompanyActivation.organization_id == organization_id,
            BusinessCompanyActivation.company_id == company_id,
        ).with_for_update(read=True))

        return activation_id is not None

    def operation_visibility(self, user_id, organization_id, permission_key, *, grant_only=False):
        if not isinstance(permission_key, str) or permission_key not in COMPANY_PERMISSIONS:
            from sqlalchemy import false
            return false()
        owner = select(OrganizationOwnership.organization_id).where(
            OrganizationOwnership.organization_id == organization_id, OrganizationOwnership.user_id == user_id).exists()
        grant = self._direct_grant(user_id, organization_id, permission_key)
        return and_(Company.organization_id == organization_id, Company.status == CompanyStatus.ACTIVE,
            self._licensed_company(organization_id, permission_key),
            self._active_actor(user_id, organization_id), grant if grant_only else or_(owner, grant))

    async def has_operation_permission(self, user_id, organization_id, company_id, permission_key, *, grant_only=False):
        if not all(isinstance(value, UUID) for value in (user_id, organization_id, company_id)):
            return False
        query = select(Company.id).where(Company.id == company_id,
            self.operation_visibility(user_id, organization_id, permission_key, grant_only=grant_only))
        with self.session.no_autoflush:
            return (await self.session.scalar(select(query.exists()))) is True

    # Compatibility for existing accounts-payable callers.
    financial_visibility = operation_visibility
    has_financial_permission = has_operation_permission
