"""Rotas de títulos com concessões financeiras independentes e respostas mínimas."""

from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.auth import get_current_session, get_session_token, record_authorized_activity, unavailable
from app.modules.finance.schemas import CalendarDate, PayableCreate, PayableUpdate, PayableCancel, PayableReceipt, PayableResponse, PayablePage
from app.modules.finance.service import PayableService, PayableConflictError
from app.modules.finance.movements import PayableMovementService
from app.modules.finance.summary import PayableSummaryService
from app.modules.finance.schemas import PayablesSummary
from app.modules.finance.schemas import PayablePayment, PayableReversal, MovementReceipt, MovementPage, PayablePosition
from app.modules.identity.access_security import AccessManagementDeniedError, AccessRevisionConflictError
from app.modules.identity.rate_limit import LoginRateLimitExceededError, LoginRateLimitUnavailableError
from app.modules.identity.sessions import AuthenticatedSession

router = APIRouter(prefix="/organizations/{organization_id}/companies/{company_id}/payables", tags=["Contas a pagar"])


@asynccontextmanager
async def writer(request, actor_id, *, service_class=PayableService):
    limiter = request.app.state.payables_manage_limiter
    if limiter is None or request.client is None:
        raise unavailable()
    try:
        await limiter.check(account_identifier=str(actor_id), origin_ip=request.client.host)
        async with request.app.state.session_factory() as session:
            yield service_class(session, idle_timeout=timedelta(seconds=request.app.state.settings.auth_idle_timeout_seconds))
    except AccessManagementDeniedError:
        raise HTTPException(404, "Operação financeira não permitida.") from None
    except (AccessRevisionConflictError, PayableConflictError):
        raise HTTPException(409, "Título alterado ou operação incompatível com seu estado. Atualize os dados.") from None
    except LoginRateLimitExceededError as error:
        raise HTTPException(429, "Muitas tentativas. Aguarde antes de tentar novamente.", headers={"Retry-After": str(error.retry_after_seconds)}) from None
    except (LoginRateLimitUnavailableError, SQLAlchemyError):
        raise unavailable() from None


@router.post("", response_model=PayableReceipt, status_code=201)
async def create_payable(organization_id: UUID, company_id: UUID, data: PayableCreate, request: Request, response: Response,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token)):
    async with writer(request, current.user_id) as service:
        result = await service.create(organization_id, company_id, data, token=token)
    response.headers["Location"] = f"{request.app.state.settings.api_v1_prefix}/organizations/{organization_id}/companies/{company_id}/payables/{result.id}"
    return result


@router.post("/{payable_id}/payments", response_model=MovementReceipt, status_code=201)
async def pay_title(organization_id: UUID, company_id: UUID, payable_id: UUID, data: PayablePayment, request: Request,
    idempotency_key: UUID = Header(alias="Idempotency-Key"), current: AuthenticatedSession = Depends(get_current_session),
    token: SecretStr = Depends(get_session_token)):
    async with writer(request, current.user_id, service_class=PayableMovementService) as service:
        return await service.pay(organization_id, company_id, payable_id, data, token=token, request_key=idempotency_key)


@router.post("/{payable_id}/payments/{payment_id}/reverse", response_model=MovementReceipt, status_code=201)
async def reverse_payment(organization_id: UUID, company_id: UUID, payable_id: UUID, payment_id: UUID, data: PayableReversal, request: Request,
    idempotency_key: UUID = Header(alias="Idempotency-Key"), current: AuthenticatedSession = Depends(get_current_session),
    token: SecretStr = Depends(get_session_token)):
    async with writer(request, current.user_id, service_class=PayableMovementService) as service:
        return await service.reverse(organization_id, company_id, payable_id, payment_id, data, token=token, request_key=idempotency_key)


@router.get("/{payable_id}/position", response_model=PayablePosition)
async def title_position(organization_id: UUID, company_id: UUID, payable_id: UUID, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token)):
    try:
        async with request.app.state.session_factory() as session:
            result = await PayableMovementService(session).position(organization_id, company_id, payable_id, current.user_id)
    except AccessManagementDeniedError:
        raise HTTPException(404, "Operação financeira não permitida.") from None
    except PayableConflictError:
        raise HTTPException(409, "Posição financeira inconsistente; revisão necessária.") from None
    await record_authorized_activity(request, token)
    return result


@router.get("/{payable_id}/movements", response_model=MovementPage)
async def title_movements(organization_id: UUID, company_id: UUID, payable_id: UUID, request: Request,
    cursor: UUID | None = None, limit: int = Query(default=50, ge=1, le=100),
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token)):
    try:
        async with request.app.state.session_factory() as session:
            result = await PayableMovementService(session).list_movements(organization_id, company_id, payable_id,
                current.user_id, cursor=cursor, limit=limit)
    except AccessManagementDeniedError:
        raise HTTPException(404, "Operação financeira não permitida.") from None
    await record_authorized_activity(request, token)
    return result


@router.put("/{payable_id}", response_model=PayableReceipt)
async def update_payable(organization_id: UUID, company_id: UUID, payable_id: UUID, data: PayableUpdate, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token)):
    async with writer(request, current.user_id) as service:
        return await service.update(organization_id, company_id, payable_id, data, token=token)


@router.post("/{payable_id}/cancel", response_model=PayableReceipt)
async def cancel_payable(organization_id: UUID, company_id: UUID, payable_id: UUID, data: PayableCancel, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token)):
    async with writer(request, current.user_id) as service:
        return await service.cancel(organization_id, company_id, payable_id, data, token=token)


@router.get("", response_model=PayablePage)
async def list_payables(organization_id: UUID, company_id: UUID, request: Request,
    cursor: UUID | None = None, limit: int = Query(default=50, ge=1, le=100),
    due_from: CalendarDate | None = None, due_to: CalendarDate | None = None, status: Literal["OPEN", "CANCELLED"] | None = None,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token)):
    if due_from and due_to and due_from > due_to:
        raise HTTPException(422, "Intervalo de datas inválido.")
    try:
        async with request.app.state.session_factory() as session:
            result = await PayableService(session).list(organization_id, company_id, current.user_id,
                cursor=cursor, limit=limit, due_from=due_from, due_to=due_to, status=status)
    except AccessManagementDeniedError:
        raise HTTPException(404, "Operação financeira não permitida.") from None
    await record_authorized_activity(request, token)
    return result


@router.get("/summary", response_model=PayablesSummary)
async def payable_summary(organization_id: UUID, company_id: UUID, period_start: CalendarDate, period_end: CalendarDate,
    request: Request, upcoming_days: int = Query(default=7, ge=1, le=90),
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token)):
    allowed = {"period_start", "period_end", "upcoming_days"}
    if (set(request.query_params)-allowed or any(len(request.query_params.getlist(key)) != 1 for key in request.query_params)
            or period_end < period_start or (period_end-period_start).days > 365):
        raise HTTPException(422, "Período ou parâmetros inválidos; use até 366 dias inclusivos.")
    try:
        async with request.app.state.session_factory() as session:
            result = await PayableSummaryService(session).summary(organization_id, company_id, current.user_id,
                period_start, period_end, upcoming_days=upcoming_days)
    except AccessManagementDeniedError:
        raise HTTPException(404, "Operação financeira não permitida.") from None
    except PayableConflictError:
        raise HTTPException(409, "Posição financeira inconsistente; revisão necessária.") from None
    await record_authorized_activity(request, token)
    return result


@router.get("/{payable_id}", response_model=PayableResponse)
async def get_payable(organization_id: UUID, company_id: UUID, payable_id: UUID, request: Request,
    current: AuthenticatedSession = Depends(get_current_session), token: SecretStr = Depends(get_session_token)):
    try:
        async with request.app.state.session_factory() as session:
            result = await PayableService(session).get(organization_id, company_id, payable_id, current.user_id)
    except AccessManagementDeniedError:
        raise HTTPException(404, "Operação financeira não permitida.") from None
    await record_authorized_activity(request, token)
    return result
