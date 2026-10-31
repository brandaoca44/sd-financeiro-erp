"""Consulta e altera status do vínculo somente pelo Master, com reautenticação."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import SecretStr

from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity
from app.api.v1.roles import guarded_access
from app.modules.identity.membership_schemas import MembershipStatusRequest, MembershipStatusResponse
from app.modules.identity.memberships import MembershipService
from app.modules.identity.roles import AccessManagementDeniedError
from app.modules.identity.sessions import AuthenticatedSession

router = APIRouter(tags=["Vínculos organizacionais"])


@router.get("/organizations/{organization_id}/members/{user_id}/status", response_model=MembershipStatusResponse)
async def read_membership_status(organization_id: UUID, user_id: UUID, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
):
    try:
        async with request.app.state.session_factory() as reader:
            result = await MembershipService(reader).read_status(organization_id, current.user_id, user_id)
    except AccessManagementDeniedError:
        raise HTTPException(404, "Operação de acesso não permitida.") from None
    await record_authorized_activity(request, token)
    return result


@router.put("/organizations/{organization_id}/members/{user_id}/status", response_model=MembershipStatusResponse)
async def set_membership_status(organization_id: UUID, user_id: UUID, data: MembershipStatusRequest, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
):
    async with guarded_access(request, current.user_id, service_class=MembershipService) as service:
        return await service.set_status(organization_id, user_id, data, token=token)
