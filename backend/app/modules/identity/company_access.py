"""Concede leitura do cadastro de uma empresa por decisão explícita do Master."""

from datetime import timedelta

from sqlalchemy import select

from app.modules.identity.access_security import AccessManagementDeniedError, AccessRevisionConflictError, authorize_access_change
from app.modules.identity.authorization import OrganizationAccessPolicy
from app.modules.identity.company_access_models import CompanyPermissionChange, CompanyPermissionGrant
from app.modules.identity.company_access_schemas import CompanyReadGrantResponse
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.models import MembershipStatus, OrganizationMembership, UserStatus
from app.modules.identity.permissions import PermissionKey
from app.modules.organizations.models import Company, CompanyStatus


class CompanyGrantService:
    def __init__(self, session, *, idle_timeout=timedelta(minutes=30)):
        if not isinstance(idle_timeout, timedelta) or not timedelta(0) < idle_timeout <= timedelta(days=1):
            raise ValueError("Prazo de inatividade inválido.")
        self.session, self.idle_timeout = session, idle_timeout

    @staticmethod
    def deny():
        raise AccessManagementDeniedError("Operação de acesso não permitida.")

    @staticmethod
    def check_revision(expected, actual):
        if expected != actual:
            raise AccessRevisionConflictError("Concessão alterada. Atualize os dados antes de tentar novamente.")

    async def _company(self, organization_id, company_id):
        company = await self.session.scalar(select(Company).where(
            Company.organization_id == organization_id, Company.id == company_id))
        if company is None:
            self.deny()
        return company

    async def _response(self, organization_id, company, member, grant):
        effective = await CompanyAccessPolicy(self.session).can_read(member.user_id, organization_id, company.id, grant_only=True)
        return CompanyReadGrantResponse(company_id=company.id, user_id=member.user_id, status=grant.status,
            revision=grant.revision, company_revision=company.revision, membership_revision=member.revision, effective=effective)

    async def read(self, organization_id, company_id, user_id, actor_id):
        if not await OrganizationAccessPolicy(self.session).has_permission(actor_id, organization_id, PermissionKey.COMPANY_ACCESS_MANAGE):
            self.deny()
        company = await self._company(organization_id, company_id)
        member = await self.session.get(OrganizationMembership, (user_id, organization_id))
        if member is None:
            self.deny()
        grant = await self.session.get(CompanyPermissionGrant, (organization_id, company_id, user_id, PermissionKey.COMPANIES_READ))
        return None if grant is None else await self._response(organization_id, company, member, grant)

    async def set_read(self, organization_id, company_id, user_id, data, *, token):
        async with self.session.begin():
            actor_id, owner, users, members, _ = await authorize_access_change(self.session,
                organization_id, token, data.password, idle_timeout=self.idle_timeout, target_id=user_id)
            if user_id == owner.user_id:
                self.deny()
            company = await self._company(organization_id, company_id)
            member = members[user_id]
            self.check_revision(data.expected_company_revision, company.revision)
            self.check_revision(data.expected_membership_revision, member.revision)
            if data.status == MembershipStatus.ACTIVE and (company.status != CompanyStatus.ACTIVE or
                member.status != MembershipStatus.ACTIVE or users[user_id].status != UserStatus.ACTIVE):
                self.deny()
            grant = await self.session.get(CompanyPermissionGrant,
                (organization_id, company_id, user_id, PermissionKey.COMPANIES_READ))
            self.check_revision(data.expected_revision, grant.revision if grant else 0)
            before = {} if grant is None else {"status": grant.status, "revision": grant.revision}
            if grant is None:
                grant = CompanyPermissionGrant(organization_id=organization_id, company_id=company_id, user_id=user_id,
                    permission_key=PermissionKey.COMPANIES_READ, revision=1, updated_by_user_id=actor_id)
                self.session.add(grant)
            else:
                grant.revision += 1
            grant.status, grant.updated_by_user_id = data.status, actor_id
            await self.session.flush()
            self.session.add(CompanyPermissionChange(organization_id=organization_id, company_id=company_id,
                user_id=user_id, permission_key=PermissionKey.COMPANIES_READ, actor_user_id=actor_id, action="COMPANY_READ_SET",
                before_state=before, after_state={"status": grant.status, "revision": grant.revision,
                    "company_revision": company.revision, "membership_revision": member.revision}))
            await self.session.flush()
            result = await self._response(organization_id, company, member, grant)
        return result
