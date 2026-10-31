"""Expõe organizações somente após autenticação e autorização organizacional."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import SecretStr
from uuid import UUID

from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity
from app.modules.identity.authorization import OrganizationAccessPolicy
from app.modules.identity.sessions import AuthenticatedSession
from app.modules.organizations.schemas import OrganizationCreate, OrganizationResponse
from app.modules.organizations.service import OrganizationService


router = APIRouter(prefix="/organizations", tags=["Organizações"])


@router.post("", response_model=OrganizationResponse, status_code=201)
async def create_organization(
    data: OrganizationCreate, request: Request, response: Response,
    current: AuthenticatedSession = Depends(get_current_session),
    token: SecretStr = Depends(get_session_token),
) -> OrganizationResponse:
    async with request.app.state.session_factory() as reader:
        allowed = await OrganizationAccessPolicy(reader).can_provision_organizations(current.user_id)
    if not allowed:
        raise HTTPException(403, "Operação não permitida.")
    await record_authorized_activity(request, token)
    async with request.app.state.session_factory() as writer:
        organization = await OrganizationService(writer).create(data)
    response.headers["Location"] = f"{request.app.state.settings.api_v1_prefix}/organizations/{organization.id}"
    return organization


@router.get("/{organization_id}", response_model=OrganizationResponse)
async def get_organization(
    organization_id: UUID, request: Request,
    current: AuthenticatedSession = Depends(get_current_session),
    token: SecretStr = Depends(get_session_token),
) -> OrganizationResponse:
    async with request.app.state.session_factory() as reader:
        if not await OrganizationAccessPolicy(reader).can_read_organization(current.user_id, organization_id):
            raise HTTPException(404, "Organização não encontrada.")
        organization = await OrganizationService(reader).get_by_id(organization_id)
    if organization is None:
        raise HTTPException(404, "Organização não encontrada.")
    await record_authorized_activity(request, token)
    return organization
