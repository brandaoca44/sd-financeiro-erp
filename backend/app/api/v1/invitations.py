"""Contratos HTTP de onboarding e convites; não envia mensagens nem cria sessões."""

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.auth import get_authentication, get_current_session, get_session_token, unavailable
from app.modules.identity.authentication import AuthenticationService
from app.modules.identity.invitation_schemas import (
    AcceptInvitationRequest, ConfirmPassword, InvitationResponse, InviteMemberRequest,
    InviteOwnerRequest, OnboardingRequest,
)
from app.modules.identity.invitations import InvitationDeniedError, InvitationService
from app.modules.identity.rate_limit import LoginRateLimitExceededError, LoginRateLimitUnavailableError
from app.modules.identity.sessions import AuthenticatedSession

router = APIRouter(tags=["Onboarding e convites"])


@asynccontextmanager
async def guarded_invitation(request: Request, identifier: str, *, accepting=False):
    limiter = request.app.state.invitation_accept_limiter if accepting else request.app.state.invitation_manage_limiter
    slots = request.app.state.auth_hash_slots
    if limiter is None or slots is None or request.client is None:
        raise unavailable()
    try:
        await limiter.check(account_identifier=identifier, origin_ip=request.client.host)
        try:
            await asyncio.wait_for(slots.acquire(), timeout=0.25)
        except TimeoutError:
            raise unavailable() from None
        try:
            async with request.app.state.session_factory() as writer:
                yield InvitationService(writer, idle_timeout=timedelta(
                    seconds=request.app.state.settings.auth_idle_timeout_seconds))
        finally:
            slots.release()
    except InvitationDeniedError:
        detail = "Não foi possível aceitar o convite." if accepting else "Operação de convite não permitida."
        raise HTTPException(400 if accepting else 404, detail) from None
    except LoginRateLimitExceededError as error:
        raise HTTPException(429, "Muitas tentativas. Aguarde antes de tentar novamente.",
                            headers={"Retry-After": str(error.retry_after_seconds)}) from None
    except (LoginRateLimitUnavailableError, SQLAlchemyError, ValueError):
        raise unavailable() from None


def invitation_response(issued) -> InvitationResponse:
    # Segredo entregue uma única vez ao autor autenticado, para entrega ao convidado.
    return InvitationResponse(organization_id=issued.organization_id, invitation_id=issued.invitation_id,
                              invitation_token=issued.token.get_secret_value(), expires_at=issued.expires_at)


@router.post("/organizations/onboarding", response_model=InvitationResponse, status_code=201)
async def onboard_organization(data: OnboardingRequest, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
) -> InvitationResponse:
    async with guarded_invitation(request, str(current.user_id)) as service:
        return invitation_response(await service.onboard(data, token=token))


@router.post("/organizations/{organization_id}/owner-invitations", response_model=InvitationResponse, status_code=201)
async def invite_initial_owner(organization_id: UUID, data: InviteOwnerRequest, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
) -> InvitationResponse:
    async with guarded_invitation(request, str(current.user_id)) as service:
        return invitation_response(await service.issue(organization_id, data, token=token, owner=True))


@router.post("/organizations/{organization_id}/invitations", response_model=InvitationResponse, status_code=201)
async def invite_member(organization_id: UUID, data: InviteMemberRequest, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
) -> InvitationResponse:
    async with guarded_invitation(request, str(current.user_id)) as service:
        return invitation_response(await service.issue(organization_id, data, token=token, owner=False))


@router.post("/organizations/{organization_id}/invitations/{invitation_id}/revoke", status_code=204)
async def revoke_invitation(organization_id: UUID, invitation_id: UUID, data: ConfirmPassword, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
) -> Response:
    async with guarded_invitation(request, str(current.user_id)) as service:
        await service.revoke(organization_id, invitation_id, token=token, password=data.password)
    return Response(status_code=204)


@router.post("/auth/invitations/accept", status_code=204)
async def accept_invitation(data: AcceptInvitationRequest, request: Request,
    authentication: AuthenticationService = Depends(get_authentication),
) -> Response:
    async with guarded_invitation(request, data.token.get_secret_value(), accepting=True) as service:
        await service.accept(data)
    return Response(status_code=204)
