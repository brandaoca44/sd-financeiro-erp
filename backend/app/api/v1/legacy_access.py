"""Revisão da origem da leitura e alterações explícitas pelo Master."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import SecretStr

from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity
from app.api.v1.roles import guarded_access
from app.modules.identity.legacy_access import LegacyReadService
from app.modules.identity.legacy_access_schemas import (
    LegacyReadConversionResponse, LegacyReadConvertRequest, LegacyReadRevokeRequest, ReadAccessReview,
)
from app.modules.identity.roles import AccessManagementDeniedError
from app.modules.identity.sessions import AuthenticatedSession

router = APIRouter(tags=["Revisão das concessões antigas"])


@router.get("/organizations/{organization_id}/members/{user_id}/read-access", response_model=ReadAccessReview)
async def review_read_access(organization_id: UUID, user_id: UUID, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
):
    try:
        async with request.app.state.session_factory() as reader:
            result = await LegacyReadService(reader).review(organization_id, current.user_id, user_id)
    except AccessManagementDeniedError:
        raise HTTPException(404, "Operação de acesso não permitida.") from None
    await record_authorized_activity(request, token)
    return result


@router.post("/organizations/{organization_id}/members/{user_id}/legacy-read/convert", response_model=LegacyReadConversionResponse)
async def convert_legacy_read(organization_id: UUID, user_id: UUID, data: LegacyReadConvertRequest, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
):
    async with guarded_access(request, current.user_id, service_class=LegacyReadService) as service:
        return await service.convert(organization_id, user_id, data, token=token)


@router.post("/organizations/{organization_id}/members/{user_id}/legacy-read/revoke", response_model=ReadAccessReview)
async def revoke_legacy_read(organization_id: UUID, user_id: UUID, data: LegacyReadRevokeRequest, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
):
    async with guarded_access(request, current.user_id, service_class=LegacyReadService) as service:
        return await service.revoke(organization_id, user_id, data, token=token)
