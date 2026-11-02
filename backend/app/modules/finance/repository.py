"""Persistência interna; o chamador precisa autorizar o ator antes de utilizá-la."""

from sqlalchemy import select

from app.modules.finance.models import Payable, PayableChange


class PayableRepository:
    def __init__(self, session):
        self.session = session

    async def create(self, organization_id, company_id, actor_user_id, data):
        title = Payable(organization_id=organization_id, company_id=company_id,
                        created_by_user_id=actor_user_id, **data.model_dump())
        self.session.add(title)
        await self.session.flush()
        self.session.add(PayableChange(organization_id=organization_id, company_id=company_id,
            payable_id=title.id, actor_user_id=actor_user_id, action="CREATED", before_state={},
            after_state={"revision": title.revision, "amount": str(title.amount), "currency": title.currency,
                         "issue_date": title.issue_date.isoformat(), "due_date": title.due_date.isoformat(), "status": title.status}))
        await self.session.flush()
        return title

    async def get(self, organization_id, company_id, payable_id, *, lock=False, visibility=None):
        query = select(Payable).where(Payable.organization_id == organization_id,
            Payable.company_id == company_id, Payable.id == payable_id)
        if visibility is not None:
            query = query.where(visibility)
        if lock:
            query = query.with_for_update()
        return await self.session.scalar(query)

    async def list(self, organization_id, company_id, *, limit=50, after_id=None, visibility=None,
                   due_from=None, due_to=None, status=None):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Limite de paginação inválido.")
        query = select(Payable).where(Payable.organization_id == organization_id, Payable.company_id == company_id)
        if visibility is not None:
            query = query.where(visibility)
        if due_from is not None:
            query = query.where(Payable.due_date >= due_from)
        if due_to is not None:
            query = query.where(Payable.due_date <= due_to)
        if status is not None:
            query = query.where(Payable.status == status)
        if after_id is not None:
            query = query.where(Payable.id > after_id)
        return list((await self.session.scalars(query.order_by(Payable.id).limit(limit))).all())
