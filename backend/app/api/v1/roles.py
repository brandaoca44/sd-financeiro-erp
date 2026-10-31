"""Gestão de acesso com reautenticação, teto explícito e respostas administrativas mínimas."""

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, SecretStr
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity, unavailable
from app.modules.identity.permissions import PERMISSION_CATALOG
from app.modules.identity.rate_limit import LoginRateLimitExceededError, LoginRateLimitUnavailableError
from app.modules.identity.role_schemas import (
    AssignmentPage, AssignmentRequest, AssignmentResponse, DelegationRequest, DelegationResponse,
    MemberPage, RoleCreateRequest, RolePage, RoleResponse, RoleUpdateRequest,
)
from app.modules.identity.roles import AccessManagementDeniedError, AccessRevisionConflictError, RoleService
from app.modules.identity.sessions import AuthenticatedSession

router = APIRouter(tags=["Perfis e permissões"])


class PermissionResponse(BaseModel):
    key: str
    description: str
    scope: str
    grant_source: str


@asynccontextmanager
async def guarded_access(request, actor_id, *, service_class=RoleService):
    limiter, slots = request.app.state.access_manage_limiter, request.app.state.auth_hash_slots
    if limiter is None or slots is None or request.client is None:
        raise unavailable()
    try:
        await limiter.check(account_identifier=str(actor_id), origin_ip=request.client.host)
        try:
            await asyncio.wait_for(slots.acquire(), timeout=0.25)
        except TimeoutError:
            raise unavailable() from None
        try:
            async with request.app.state.session_factory() as writer:
                yield service_class(writer, idle_timeout=timedelta(seconds=request.app.state.settings.auth_idle_timeout_seconds))
        finally:
            slots.release()
    except AccessManagementDeniedError:
        raise HTTPException(404, "Operação de acesso não permitida.") from None
    except AccessRevisionConflictError:
        raise HTTPException(409, "Concessão alterada. Atualize os dados antes de tentar novamente.") from None
    except LoginRateLimitExceededError as error:
        raise HTTPException(429, "Muitas tentativas. Aguarde antes de tentar novamente.",
                            headers={"Retry-After": str(error.retry_after_seconds)}) from None
    except IntegrityError as error:
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "uq_organization_roles_name":
            raise HTTPException(409, "Já existe um perfil com esse nome na organização.") from None
        raise unavailable() from None
    except (LoginRateLimitUnavailableError, SQLAlchemyError, ValueError):
        raise unavailable() from None


@router.get("/auth/permissions", response_model=list[PermissionResponse])
async def permission_catalog(current: AuthenticatedSession = Depends(get_current_session)):
    return PERMISSION_CATALOG


@router.get("/organizations/{organization_id}/roles", response_model=RolePage)
async def list_roles(organization_id: UUID, request: Request, cursor: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100), current: AuthenticatedSession = Depends(get_current_session),
    token: SecretStr = Depends(get_session_token),
):
    try:
        async with request.app.state.session_factory() as reader:
            result = await RoleService(reader).list_roles(organization_id, current.user_id, cursor=cursor, limit=limit)
    except AccessManagementDeniedError:
        raise HTTPException(404, "Operação de acesso não permitida.") from None
    await record_authorized_activity(request, token)
    return result


@router.post("/organizations/{organization_id}/roles", response_model=RoleResponse, status_code=201)
async def create_role(organization_id: UUID, data: RoleCreateRequest, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
):
    async with guarded_access(request, current.user_id) as service:
        return await service.create(organization_id, data, token=token)


@router.put("/organizations/{organization_id}/roles/{role_id}", response_model=RoleResponse)
async def update_role(organization_id: UUID, role_id: UUID, data: RoleUpdateRequest, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
):
    async with guarded_access(request, current.user_id) as service:
        return await service.update(organization_id, role_id, data, token=token)


@router.put("/organizations/{organization_id}/members/{user_id}/roles/{role_id}", response_model=AssignmentResponse)
async def set_assignment(organization_id: UUID, user_id: UUID, role_id: UUID, data: AssignmentRequest, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
):
    async with guarded_access(request, current.user_id) as service:
        return await service.assign(organization_id, user_id, role_id, data, token=token)


@router.put("/organizations/{organization_id}/members/{user_id}/delegation", response_model=DelegationResponse)
async def set_delegation(organization_id: UUID, user_id: UUID, data: DelegationRequest, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
):
    async with guarded_access(request, current.user_id) as service:
        return await service.set_delegation(organization_id, user_id, data, token=token)


async def read_member_access(organization_id, user_id, request, current, token, *, delegation=False, cursor=None, limit=50):
    try:
        async with request.app.state.session_factory() as reader:
            result = await RoleService(reader).member_access(organization_id, current.user_id, user_id,
                delegation=delegation, cursor=cursor, limit=limit)
    except AccessManagementDeniedError:
        raise HTTPException(404, "Operação de acesso não permitida.") from None
    await record_authorized_activity(request, token)
    return result


@router.get("/organizations/{organization_id}/members/{user_id}/roles", response_model=AssignmentPage)
async def list_member_roles(organization_id: UUID, user_id: UUID, request: Request, cursor: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100), current: AuthenticatedSession = Depends(get_current_session),
    token: SecretStr = Depends(get_session_token),
):
    return await read_member_access(organization_id, user_id, request, current, token, cursor=cursor, limit=limit)


@router.get("/organizations/{organization_id}/members/{user_id}/delegation", response_model=DelegationResponse | None)
async def read_delegation(organization_id: UUID, user_id: UUID, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token),
):
    return await read_member_access(organization_id, user_id, request, current, token, delegation=True)


@router.get("/organizations/{organization_id}/members", response_model=MemberPage)
async def list_members(organization_id: UUID, request: Request, cursor: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100), current: AuthenticatedSession = Depends(get_current_session),
    token: SecretStr = Depends(get_session_token),
):
    try:
        async with request.app.state.session_factory() as reader:
            result = await RoleService(reader).list_members(organization_id, current.user_id, cursor=cursor, limit=limit)
    except AccessManagementDeniedError:
        raise HTTPException(404, "Operação de acesso não permitida.") from None
    await record_authorized_activity(request, token)
    return result
