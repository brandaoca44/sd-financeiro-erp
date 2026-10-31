"""Administra empresas pelo Master e expõe leitura apenas no escopo autorizado."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import SecretStr

from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity
from app.api.v1.roles import guarded_access
from app.modules.identity.access_security import AccessManagementDeniedError
from app.modules.identity.sessions import AuthenticatedSession
from app.modules.organizations.company_schemas import CompanyCreate, CompanyPage, CompanyResponse, CompanyUpdate
from app.modules.organizations.company_service import CompanyService

router = APIRouter(prefix="/organizations/{organization_id}/companies", tags=["Empresas"])


@router.post("", response_model=CompanyResponse, status_code=201)
async def create_company(organization_id: UUID, data: CompanyCreate, request: Request, response: Response,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
):
    async with guarded_access(request, current.user_id, service_class=CompanyService) as service:
        company = await service.create(organization_id, data, token=token)
    response.headers["Location"] = f"{request.app.state.settings.api_v1_prefix}/organizations/{organization_id}/companies/{company.id}"
    return company


@router.put("/{company_id}", response_model=CompanyResponse)
async def update_company(organization_id: UUID, company_id: UUID, data: CompanyUpdate, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
):
    async with guarded_access(request, current.user_id, service_class=CompanyService) as service:
        return await service.update(organization_id, company_id, data, token=token)


@router.get("", response_model=CompanyPage)
async def list_companies(organization_id: UUID, request: Request, cursor: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100), current: AuthenticatedSession = Depends(get_current_session),
    token: SecretStr = Depends(get_session_token),
):
    try:
        async with request.app.state.session_factory() as reader:
            result = await CompanyService(reader).list(organization_id, current.user_id, cursor=cursor, limit=limit)
    except AccessManagementDeniedError:
        raise HTTPException(404, "Operação de acesso não permitida.") from None
    await record_authorized_activity(request, token)
    return result


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(organization_id: UUID, company_id: UUID, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
):
    try:
        async with request.app.state.session_factory() as reader:
            result = await CompanyService(reader).get(organization_id, company_id, current.user_id)
    except AccessManagementDeniedError:
        raise HTTPException(404, "Operação de acesso não permitida.") from None
    await record_authorized_activity(request, token)
    return result
