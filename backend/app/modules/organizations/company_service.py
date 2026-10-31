"""Administra cadastro jurídico e aplica leitura no escopo da empresa autorizada."""

from datetime import timedelta
from sqlalchemy import update

from app.modules.identity.access_security import AccessManagementDeniedError, AccessRevisionConflictError, authorize_access_change
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.company_access_models import CompanyPermissionGrant
from app.modules.organizations.company_repository import CompanyRepository
from app.modules.organizations.company_schemas import CompanyResponse
from app.modules.organizations.models import CompanyChange, CompanyStatus


class CompanyService:
    def __init__(self, session, *, idle_timeout=timedelta(minutes=30)):
        if not isinstance(idle_timeout, timedelta) or not timedelta(0) < idle_timeout <= timedelta(days=1):
            raise ValueError("Prazo de inatividade inválido.")
        self.session, self.idle_timeout = session, idle_timeout
        self.repository = CompanyRepository(session)

    @staticmethod
    def deny():
        raise AccessManagementDeniedError("Operação de acesso não permitida.")

    async def _authorize_read(self, organization_id, actor_id):
        if not await CompanyAccessPolicy(self.session).can_list(actor_id, organization_id):
            self.deny()

    def _audit(self, organization_id, company, actor_id, action, before, changed_fields, *, grants_reset=0):
        self.session.add(CompanyChange(organization_id=organization_id, company_id=company.id, actor_user_id=actor_id,
            action=action, before_state=before, after_state={"revision":company.revision, "status":company.status,
                                                            "changed_fields":changed_fields, "company_grants_reset":grants_reset}))

    async def create(self, organization_id, data, *, token):
        async with self.session.begin():
            actor_id, *_ = await authorize_access_change(self.session, organization_id, token, data.password, idle_timeout=self.idle_timeout)
            company = await self.repository.create(organization_id, legal_name=data.legal_name, trade_name=data.trade_name, tax_id=data.tax_id)
            self._audit(organization_id, company, actor_id, "CREATED", {}, ["legal_name", "trade_name", "tax_id", "status"])
            await self.session.flush()
            result = CompanyResponse.model_validate(company)
        return result

    async def update(self, organization_id, company_id, data, *, token):
        async with self.session.begin():
            actor_id, *_ = await authorize_access_change(self.session, organization_id, token, data.password, idle_timeout=self.idle_timeout)
            company = await self.repository.get(organization_id, company_id, lock=True)
            if company is None:
                self.deny()
            if data.expected_revision != company.revision:
                raise AccessRevisionConflictError("Empresa alterada. Atualize os dados antes de tentar novamente.")
            before = {"revision":company.revision, "status":company.status}
            changed = [field for field in ("legal_name", "trade_name", "status") if getattr(company, field) != getattr(data, field)]
            grants_reset = 0
            if data.status == CompanyStatus.INACTIVE or company.status == CompanyStatus.INACTIVE:
                reset = await self.session.execute(update(CompanyPermissionGrant).where(
                    CompanyPermissionGrant.organization_id == organization_id, CompanyPermissionGrant.company_id == company_id,
                ).values(status="INACTIVE", revision=CompanyPermissionGrant.revision + 1, updated_by_user_id=actor_id))
                grants_reset = reset.rowcount
            company.legal_name, company.trade_name, company.status = data.legal_name, data.trade_name, data.status
            company.revision += 1
            # O flush obtém updated_at sem lazy loading durante a serialização.
            await self.session.flush()
            await self.session.refresh(company)
            self._audit(organization_id, company, actor_id, "UPDATED", before, changed, grants_reset=grants_reset)
            await self.session.flush()
            result = CompanyResponse.model_validate(company)
        return result

    async def get(self, organization_id, company_id, actor_id):
        company = await self.repository.get(organization_id, company_id,
            visibility=CompanyAccessPolicy(self.session).visibility(actor_id, organization_id))
        if company is None:
            self.deny()
        return CompanyResponse.model_validate(company)

    async def list(self, organization_id, actor_id, *, cursor=None, limit=50):
        await self._authorize_read(organization_id, actor_id)
        rows = await self.repository.list(organization_id, cursor=cursor, limit=limit,
            visibility=CompanyAccessPolicy(self.session).visibility(actor_id, organization_id))
        return {"items":[CompanyResponse.model_validate(company) for company in rows[:limit]],
                "next_cursor":rows[limit - 1].id if len(rows) > limit else None}
