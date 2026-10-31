"""Expõe mudanças de propriedade com reautenticação limitada e respostas mínimas."""

import asyncio
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.auth import get_current_session, get_session_token, unavailable
from app.modules.identity.ownership import OrganizationOwnershipService, OwnershipChangeDeniedError
from app.modules.identity.rate_limit import LoginRateLimitExceededError, LoginRateLimitUnavailableError
from app.modules.identity.sessions import AuthenticatedSession

router = APIRouter(prefix="/organizations", tags=["Propriedade da organização"])


class OwnershipChangeRequest(BaseModel):
    """O ator vem da sessão; o cliente indica somente destinatário e senha do ator."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    new_owner_id: UUID
    password: SecretStr = Field(min_length=1, max_length=128)


async def change_ownership(data, organization_id, request, current, token, *, initial):
    limiter = request.app.state.ownership_limiter
    if limiter is None or request.client is None:
        raise unavailable()
    try:
        # UUID do ator, comum às suas sessões e aos dois endpoints; nunca o destinatário.
        await limiter.check(account_identifier=str(current.user_id), origin_ip=request.client.host)
        slots = request.app.state.auth_hash_slots
        try:
            await asyncio.wait_for(slots.acquire(), timeout=0.25)
        except TimeoutError:
            raise unavailable() from None
        try:
            async with request.app.state.session_factory() as writer:
                service = OrganizationOwnershipService(writer, idle_timeout=timedelta(
                    seconds=request.app.state.settings.auth_idle_timeout_seconds,
                ))
                method = service.designate if initial else service.transfer
                await method(organization_id=organization_id, new_owner_id=data.new_owner_id,
                             token=token, password=data.password)
        finally:
            slots.release()
    except OwnershipChangeDeniedError:
        # Mesmo contrato para senha, autoridade, destinatário e organização inválidos.
        raise HTTPException(404, "Não foi possível alterar o proprietário.") from None
    except LoginRateLimitExceededError as error:
        raise HTTPException(429, "Muitas tentativas. Aguarde antes de tentar novamente.",
                            headers={"Retry-After": str(error.retry_after_seconds)}) from None
    except (LoginRateLimitUnavailableError, SQLAlchemyError, ValueError):
        raise unavailable() from None
    return Response(status_code=204)


@router.post("/{organization_id}/ownership/designate", status_code=204)
async def designate_owner(
    organization_id: UUID, data: OwnershipChangeRequest, request: Request,
    current: AuthenticatedSession = Depends(get_current_session),
    token: SecretStr = Depends(get_session_token),
) -> Response:
    return await change_ownership(data, organization_id, request, current, token, initial=True)


@router.post("/{organization_id}/ownership/transfer", status_code=204)
async def transfer_owner(
    organization_id: UUID, data: OwnershipChangeRequest, request: Request,
    current: AuthenticatedSession = Depends(get_current_session),
    token: SecretStr = Depends(get_session_token),
) -> Response:
    return await change_ownership(data, organization_id, request, current, token, initial=False)
