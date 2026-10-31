"""Consulta e define leitura explícita por empresa, exclusivamente pelo Master."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import SecretStr

from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity
from app.api.v1.roles import guarded_access
from app.modules.identity.access_security import AccessManagementDeniedError
from app.modules.identity.company_access import CompanyGrantService
from app.modules.identity.company_access_schemas import CompanyReadGrantRequest, CompanyReadGrantResponse
from app.modules.identity.sessions import AuthenticatedSession

router = APIRouter(tags=["Acesso por empresa"])


@router.get("/organizations/{organization_id}/companies/{company_id}/members/{user_id}/read-access", response_model=CompanyReadGrantResponse | None)
async def read_company_grant(organization_id: UUID, company_id: UUID, user_id: UUID, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
):
    try:
        async with request.app.state.session_factory() as reader:
            result = await CompanyGrantService(reader).read(organization_id, company_id, user_id, current.user_id)
    except AccessManagementDeniedError:
        raise HTTPException(404, "Operação de acesso não permitida.") from None
    await record_authorized_activity(request, token)
    return result


@router.put("/organizations/{organization_id}/companies/{company_id}/members/{user_id}/read-access", response_model=CompanyReadGrantResponse)
async def set_company_grant(organization_id: UUID, company_id: UUID, user_id: UUID, data: CompanyReadGrantRequest, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
):
    async with guarded_access(request, current.user_id, service_class=CompanyGrantService) as service:
        return await service.set_read(organization_id, company_id, user_id, data, token=token)
