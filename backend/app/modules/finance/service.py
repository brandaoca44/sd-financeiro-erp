"""Títulos financeiros transacionais, sem implementar baixas ou estornos."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import case, func, select, text

from app.modules.finance.models import Payable, PayableChange, PayableMovement
from app.modules.finance.repository import PayableRepository
from app.modules.finance.schemas import PayableReceipt, PayableResponse
from app.modules.identity.access_security import AccessManagementDeniedError, AccessRevisionConflictError
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.models import OrganizationMembership, User, UserSession
from app.modules.identity.permissions import PermissionKey
from app.modules.identity.sessions import SessionService
from app.modules.organizations.models import Company, Organization


class PayableConflictError(Exception):
    pass


class PayableService:
    def __init__(self, session, *, idle_timeout=timedelta(minutes=30)):
        if not isinstance(idle_timeout, timedelta) or not timedelta(0) < idle_timeout <= timedelta(days=1):
            raise ValueError("Prazo de inatividade inválido.")
        self.session, self.idle_timeout = session, idle_timeout
        self.repository = PayableRepository(session)

    @staticmethod
    def deny():
        raise AccessManagementDeniedError("Operação financeira não permitida.")

    async def _authorize_write(self, organization_id, company_id, token, *, permission_key=PermissionKey.PAYABLES_MANAGE):
        await self.session.execute(text("SET LOCAL lock_timeout = '5s'"))
        org = await self.session.scalar(select(Organization).where(Organization.id == organization_id).with_for_update())
        if org is None or org.status != "ACTIVE":
            self.deny()
        token_hash = SessionService._token_hash(token)
        if token_hash is None:
            self.deny()
        actor_id = await self.session.scalar(select(UserSession.user_id).where(UserSession.token_hash == token_hash))
        actor = await self.session.scalar(select(User).where(User.id == actor_id).with_for_update())
        member = await self.session.scalar(select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_id == actor_id).with_for_update())
        company = await self.session.scalar(select(Company).where(Company.organization_id == organization_id,
            Company.id == company_id).with_for_update())
        if actor is None or member is None or company is None:
            self.deny()
        policy = CompanyAccessPolicy(self.session)
        if not await policy.lock_financial_contract(organization_id, company_id):
            self.deny()
        if not await policy.has_financial_permission(actor_id, organization_id, company_id, permission_key):
            self.deny()
        login = await self.session.scalar(select(UserSession).where(UserSession.token_hash == token_hash).with_for_update())
        now = datetime.now(timezone.utc)
        if login is None or login.revoked_at is not None or not login.created_at <= now < login.expires_at:
            self.deny()
        login.expires_at = max(login.expires_at, now + self.idle_timeout)
        return actor_id

    def _visibility(self, actor_id, organization_id):
        return select(Company.id).where(Company.id == Payable.company_id,
            Company.organization_id == Payable.organization_id,
            CompanyAccessPolicy(self.session).financial_visibility(actor_id, organization_id, PermissionKey.PAYABLES_READ)
        ).correlate(Payable).exists()

    async def get(self, organization_id, company_id, payable_id, actor_id):
        title = await self.repository.get(organization_id, company_id, payable_id,
            visibility=self._visibility(actor_id, organization_id))
        if title is None:
            self.deny()
        return PayableResponse.model_validate(title)

    async def list(self, organization_id, company_id, actor_id, *, limit=50, cursor=None, **filters):
        if not await CompanyAccessPolicy(self.session).has_financial_permission(actor_id, organization_id, company_id, PermissionKey.PAYABLES_READ):
            self.deny()
        # Uma linha adicional identifica a próxima página sem consultar outra empresa.
        rows = await self.repository.list(organization_id, company_id, limit=limit, after_id=cursor,
            visibility=self._visibility(actor_id, organization_id), **filters)
        next_cursor = None
        if len(rows) == limit:
            more = await self.repository.list(organization_id, company_id, limit=1, after_id=rows[-1].id,
                visibility=self._visibility(actor_id, organization_id), **filters)
            if more:
                next_cursor = rows[-1].id
        return {"items": [PayableResponse.model_validate(row) for row in rows], "next_cursor": next_cursor}

    async def create(self, organization_id, company_id, data, *, token):
        async with self.session.begin():
            actor = await self._authorize_write(organization_id, company_id, token)
            title = await self.repository.create(organization_id, company_id, actor, data)
            result = PayableReceipt.model_validate(title)
        return result

    @staticmethod
    def snapshot(title):
        return {"revision": title.revision, "status": title.status, "amount": str(title.amount),
                "issue_date": title.issue_date.isoformat(), "due_date": title.due_date.isoformat()}

    async def _change(self, organization_id, company_id, payable_id, data, token, *, cancel):
        async with self.session.begin():
            actor = await self._authorize_write(organization_id, company_id, token)
            title = await self.repository.get(organization_id, company_id, payable_id, lock=True)
            if title is None:
                self.deny()
            if title.revision != data.expected_revision:
                raise AccessRevisionConflictError()
            if title.status != "OPEN":
                raise PayableConflictError()
            net = await self.session.scalar(select(func.coalesce(func.sum(case(
                (PayableMovement.kind == "PAYMENT", PayableMovement.amount), else_=-PayableMovement.amount)), 0)).where(
                    PayableMovement.organization_id == organization_id, PayableMovement.company_id == company_id,
                    PayableMovement.payable_id == payable_id))
            if not Decimal(0) <= net <= title.amount or (cancel and net != 0) or (not cancel and data.amount < net):
                raise PayableConflictError()
            before = self.snapshot(title)
            if cancel:
                title.status = "CANCELLED"
                changed = ["status"]
            else:
                earlier = await self.session.scalar(select(PayableMovement.id).where(
                    PayableMovement.organization_id == organization_id, PayableMovement.company_id == company_id,
                    PayableMovement.payable_id == payable_id, PayableMovement.occurred_on < data.issue_date).limit(1))
                if earlier is not None:
                    raise PayableConflictError()
                changed = [field for field in ("description", "amount", "issue_date", "due_date") if getattr(title, field) != getattr(data, field)]
                for field in ("description", "amount", "issue_date", "due_date"):
                    setattr(title, field, getattr(data, field))
            title.revision += 1
            self.session.add(PayableChange(organization_id=organization_id, company_id=company_id, payable_id=payable_id,
                actor_user_id=actor, action="CANCELLED" if cancel else "UPDATED", before_state=before,
                after_state={**self.snapshot(title), "changed_fields": changed}))
            await self.session.flush()
            result = PayableReceipt.model_validate(title)
        return result

    async def update(self, organization_id, company_id, payable_id, data, *, token):
        return await self._change(organization_id, company_id, payable_id, data, token, cancel=False)

    async def cancel(self, organization_id, company_id, payable_id, data, *, token):
        return await self._change(organization_id, company_id, payable_id, data, token, cancel=True)
