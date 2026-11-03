"""Rotas do ciclo de conta. Sem provedor configurado, envio permanece indisponível."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.api.v1.auth import LoginResponse, get_authentication, get_current_session
from app.modules.identity.account_models import AccountSecurity
from app.modules.identity.account_security import (
    AccountUnavailable, digest, EmailRequest, FactorRequest, InvalidAction, MfaDisableRequest,
    MfaLoginRequest, MfaSetupRequest, RegisterRequest, ResetRequest, TokenRequest,
)
from app.modules.identity.rate_limit import LoginRateLimitExceededError, LoginRateLimitUnavailableError

router = APIRouter(prefix="/auth", tags=["Segurança da conta"])


class MessageResponse(BaseModel):
    detail: str


class SetupResponse(BaseModel):
    secret: str = Field(repr=False)
    issuer: str = "Sistema Digital Financeiro"
    algorithm: str = "SHA1"
    digits: int = 6
    period: int = 30


class RecoveryResponse(BaseModel):
    recovery_codes: list[str] = Field(repr=False)


async def service(request: Request, authentication=Depends(get_authentication)):
    accounts = request.app.state.accounts
    if accounts is None or request.client is None:
        raise HTTPException(503, "Serviço temporariamente indisponível.")
    return accounts


async def limited(request, identifier, operation="account_actions"):
    limiter = getattr(request.app.state, operation + "_limiter", None)
    if limiter is None or request.client is None:
        raise AccountUnavailable()
    await limiter.check(account_identifier=identifier, origin_ip=request.client.host)


async def execute(work):
    try:
        return await work
    except InvalidAction:
        raise HTTPException(400, "Não foi possível validar a solicitação. Confira o código ou solicite um novo link.") from None
    except LoginRateLimitExceededError as error:
        raise HTTPException(429, "Muitas tentativas. Aguarde antes de tentar novamente.", headers={"Retry-After": str(error.retry_after_seconds)}) from None
    except (AccountUnavailable, LoginRateLimitUnavailableError, SQLAlchemyError, ValueError):
        raise HTTPException(503, "Recurso temporariamente indisponível.") from None


@router.get("/capabilities")
async def capabilities(request: Request):
    accounts = request.app.state.accounts
    # Não revela informações de contas, infraestrutura ou destinatários.
    return {"email_flows_available": bool(accounts and accounts.delivery and accounts.identity_key),
            "mfa_enrollment_available": bool(accounts and accounts.key)}


async def email_operation(data, purpose, request, accounts):
    async def work():
        await limited(request, str(data.email))
        await accounts.request_email(data, purpose)
        return MessageResponse(detail="Se os dados forem elegíveis, você receberá as instruções por e-mail.")
    return await execute(work())


@router.post("/register", response_model=MessageResponse, status_code=202)
async def register(data: RegisterRequest, request: Request, accounts=Depends(service)):
    return await email_operation(data, "VERIFY", request, accounts)


@router.post("/email/resend", response_model=MessageResponse, status_code=202)
async def resend(data: EmailRequest, request: Request, accounts=Depends(service)):
    return await email_operation(data, "VERIFY", request, accounts)


@router.post("/password/forgot", response_model=MessageResponse, status_code=202)
async def forgot(data: EmailRequest, request: Request, accounts=Depends(service)):
    return await email_operation(data, "RESET", request, accounts)


@router.post("/email/confirm", response_model=MessageResponse)
async def confirm(data: TokenRequest, request: Request, accounts=Depends(service)):
    async def work():
        await limited(request, digest(data.token.get_secret_value()))
        await accounts.confirm_email(data.token)
        return MessageResponse(detail="E-mail confirmado. Acesse o sistema com suas credenciais.")
    return await execute(work())


@router.post("/password/reset", response_model=MessageResponse)
async def reset(data: ResetRequest, request: Request, accounts=Depends(service)):
    async def work():
        await limited(request, digest(data.token.get_secret_value()))
        await accounts.reset_password(data)
        return MessageResponse(detail="Senha redefinida. Entre novamente. O segundo fator permanece ativo, caso configurado.")
    return await execute(work())


@router.post("/mfa/login", response_model=LoginResponse)
async def mfa_login(data: MfaLoginRequest, request: Request, accounts=Depends(service)):
    async def work():
        # Uma chave por desafio, além dos limites de IP/global. Tokens nunca são chaves em texto puro.
        from app.modules.identity.account_security import digest
        await limited(request, digest(data.challenge_token.get_secret_value()), "mfa")
        issued = await accounts.complete_mfa_login(data)
        return LoginResponse(access_token=issued.token.get_secret_value(), expires_at=issued.expires_at)
    return await execute(work())


@router.get("/mfa/status")
async def mfa_status(current=Depends(get_current_session), accounts=Depends(service)):
    async def work():
        async with accounts.factory() as session:
            enabled = await session.scalar(select(AccountSecurity.mfa_enabled).where(AccountSecurity.user_id == current.user_id))
        return {"enabled": bool(enabled), "enrollment_available": accounts.key is not None}
    return await execute(work())


@router.post("/mfa/setup", response_model=SetupResponse)
async def mfa_setup(data: MfaSetupRequest, request: Request, current=Depends(get_current_session), accounts=Depends(service)):
    async def work():
        await limited(request, str(current.user_id), "mfa")
        secret = await accounts.setup_mfa(current, data.password)
        return SetupResponse(secret=secret)
    return await execute(work())


@router.post("/mfa/enable", response_model=RecoveryResponse)
async def mfa_enable(data: FactorRequest, request: Request, current=Depends(get_current_session), accounts=Depends(service)):
    async def work():
        await limited(request, str(current.user_id), "mfa")
        return RecoveryResponse(recovery_codes=await accounts.enable_mfa(current, data.code))
    return await execute(work())


@router.post("/mfa/disable", response_model=MessageResponse)
async def mfa_disable(data: MfaDisableRequest, request: Request, current=Depends(get_current_session), accounts=Depends(service)):
    async def work():
        await limited(request, str(current.user_id), "mfa")
        await accounts.disable_mfa(current, data)
        return MessageResponse(detail="Segundo fator desativado. Outras sessões foram encerradas.")
    return await execute(work())
