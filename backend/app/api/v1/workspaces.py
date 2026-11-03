"""Contextos financeiros do próprio usuário, sem diretório global de clientes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, SecretStr
from sqlalchemy import case, or_, select

from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.permissions import FinancialPermissionKey
from app.modules.identity.sessions import AuthenticatedSession
from app.modules.organizations.models import Company

router = APIRouter(tags=["Contexto financeiro"])


class FinancialWorkspace(BaseModel):
    organization_id: UUID
    company_id: UUID
    company_name: str | None
    permissions: list[FinancialPermissionKey]


class WorkspacePage(BaseModel):
    items: list[FinancialWorkspace]
    next_cursor: UUID | None


@router.get("/auth/workspaces", response_model=WorkspacePage)
async def financial_workspaces(request: Request, cursor: UUID | None = None, limit: int = Query(default=50, ge=1, le=100),
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token)):
    async with request.app.state.session_factory() as session:
        policy = CompanyAccessPolicy(session)
        permissions = list(FinancialPermissionKey)
        allowed = [policy.financial_visibility(current.user_id, Company.organization_id, key) for key in permissions]
        query = select(Company.organization_id, Company.id.label("company_id"),
            case((policy.visibility(current.user_id, Company.organization_id), Company.legal_name), else_=None).label("company_name"),
            *[condition.label(f"permission_{index}") for index, condition in enumerate(allowed)]
        ).where(or_(*allowed))
        if cursor is not None:
            query = query.where(Company.id > cursor)
        rows = (await session.execute(query.order_by(Company.id).limit(limit+1))).mappings().all()
        result = WorkspacePage(items=[FinancialWorkspace(organization_id=row["organization_id"], company_id=row["company_id"],
            company_name=row["company_name"], permissions=[key for index,key in enumerate(permissions) if row[f"permission_{index}"]])
            for row in rows[:limit]], next_cursor=rows[limit-1]["company_id"] if len(rows)>limit else None)
    await record_authorized_activity(request, token)
    return result
