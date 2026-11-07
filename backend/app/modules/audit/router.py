"""Consulta do histórico pelo Master, filtrada antes da paginação."""
import base64
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import String, cast, literal, select, tuple_, union_all
from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity
from app.modules.audit.models import OperationEvent
from app.modules.identity.access_models import OrganizationOwnership
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.models import User
from app.modules.organizations.models import Company

Domain = Literal['EXPENSE', 'PAYABLE', 'BILLING', 'PEOPLE', 'ACCOUNTS']
Action = Literal['CREATED', 'UPDATED', 'CANCELLED', 'PAYMENT', 'REVERSAL', 'RECEIVED', 'TERMINATED']
router = APIRouter(prefix='/organizations/{organization_id}/companies/{company_id}/audit', tags=['Auditoria'])

class AuditItem(BaseModel):
    id: UUID
    source: str
    domain: Domain
    resource_type: str
    resource_id: UUID
    actor_user_id: UUID
    actor_name: str
    action: Action
    created_at: AwareDatetime

class AuditPage(BaseModel):
    items: list[AuditItem]
    next_cursor: str | None


def visibility(user_id, organization_id, company_id):
    owner = select(OrganizationOwnership.organization_id).where(
        OrganizationOwnership.organization_id == organization_id,
        OrganizationOwnership.user_id == user_id).exists()
    return select(Company.id).where(Company.id == company_id,
        Company.organization_id == organization_id,
        CompanyAccessPolicy._active_actor(user_id, organization_id), owner).exists()


def history_query(organization_id, company_id):
    from app.modules.finance.expenses import ExpenseChange
    from app.modules.finance.models import PayableChange
    def old(model, source, domain, resource_id):
        return select(model.id, literal(source).label('source'), literal(domain).label('domain'),
            literal(domain).label('resource_type'), resource_id.label('resource_id'), model.actor_user_id,
            model.action, model.created_at).where(model.organization_id == organization_id, model.company_id == company_id)
    events = select(OperationEvent.id, literal('operation').label('source'), OperationEvent.domain,
        OperationEvent.resource_type, OperationEvent.resource_id, OperationEvent.actor_user_id,
        OperationEvent.action, OperationEvent.created_at).where(
        OperationEvent.organization_id == organization_id, OperationEvent.company_id == company_id)
    return union_all(old(ExpenseChange, 'expense', 'EXPENSE', ExpenseChange.expense_id),
        old(PayableChange, 'payable', 'PAYABLE', PayableChange.payable_id), events).subquery()


def decode_cursor(value):
    try:
        raw = json.loads(base64.b64decode(value, altchars=b'-_', validate=True))
        at = datetime.fromisoformat(raw['at'])
        if at.tzinfo is None or raw['source'] not in {'operation', 'expense', 'payable'}:
            raise ValueError()
        return at, raw['source'], str(UUID(raw['id']))
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise HTTPException(422, 'Cursor de auditoria inválido.') from None


@router.get('', response_model=AuditPage)
async def history(organization_id: UUID, company_id: UUID, request: Request,
    start: date | None = None, end: date | None = None, domain: Domain | None = None,
    action: Action | None = None, actor_id: UUID | None = None,
    cursor: str | None = Query(default=None, max_length=512), limit: int = Query(default=50, ge=1, le=100),
    current=Depends(get_current_session), token=Depends(get_session_token)):
    end = end or datetime.now(timezone.utc).date()
    start = start or date.fromordinal(max(1, end.toordinal() - 29))
    if end < start or (end - start).days > 92 or end == date.max:
        raise HTTPException(422, 'Selecione um período de até 93 dias.')
    async with request.app.state.session_factory() as session:
        allowed = visibility(current.user_id, organization_id, company_id)
        if not await session.scalar(select(allowed)):
            raise HTTPException(404, 'Histórico indisponível.')
        h = history_query(organization_id, company_id)
        query = select(h, User.name.label('actor_name')).join(User, User.id == h.c.actor_user_id).where(allowed,
            h.c.created_at >= datetime.combine(start, time.min, timezone.utc),
            h.c.created_at < datetime.combine(end + timedelta(days=1), time.min, timezone.utc))
        if domain is not None: query = query.where(h.c.domain == domain)
        if action is not None: query = query.where(h.c.action == action)
        if actor_id is not None: query = query.where(h.c.actor_user_id == actor_id)
        if cursor is not None:
            query = query.where(tuple_(h.c.created_at, h.c.source, cast(h.c.id, String)) < tuple_(*decode_cursor(cursor)))
        rows = (await session.execute(query.order_by(h.c.created_at.desc(), h.c.source.desc(), cast(h.c.id, String).desc())
            .limit(limit + 1))).mappings().all()
        items = [AuditItem(**row) for row in rows[:limit]]
        next_cursor = None
        if len(rows) > limit:
            last = items[-1]
            next_cursor = base64.urlsafe_b64encode(json.dumps(dict(at=last.created_at.isoformat(),
                source=last.source, id=str(last.id))).encode()).decode()
    await record_authorized_activity(request, token)
    return AuditPage(items=items, next_cursor=next_cursor)
