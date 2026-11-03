"""Expõe login e logout e fornece dependências de autenticação para outras rotas."""

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AwareDatetime, BaseModel, Field, SecretStr
from sqlalchemy.exc import SQLAlchemyError

from app.modules.identity.account_security import MfaChallenge, AccountUnavailable
from app.modules.identity.authentication import (
    AuthenticationBusyError, AuthenticationService, InvalidCredentialsError, LoginRequest,
)
from app.modules.identity.rate_limit import LoginRateLimitExceededError, LoginRateLimitUnavailableError
from app.modules.identity.sessions import AuthenticatedSession, SessionService


router = APIRouter(prefix="/auth", tags=["Autenticação"])
_bearer = HTTPBearer(auto_error=False)


class LoginResponse(BaseModel):
    """Entrega o token somente no login, sem perfil, hashes ou permissões."""

    access_token: str = Field(repr=False)
    token_type: Literal["bearer"] = "bearer"
    expires_at: AwareDatetime


class MfaChallengeResponse(BaseModel):
    mfa_required: Literal[True] = True
    challenge_token: str = Field(repr=False)
    expires_at: AwareDatetime


def unavailable() -> HTTPException:
    return HTTPException(503, "Serviço temporariamente indisponível.")


def get_authentication(request: Request) -> AuthenticationService:
    service = request.app.state.authentication
    if service is None:
        raise unavailable()
    if request.app.state.settings.app_environment in ("staging", "production") and request.url.scheme != "https":
        raise unavailable()
    return service


def get_session_token(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> SecretStr:
    if credentials is None:
        raise HTTPException(401, "Autenticação necessária.", headers={"WWW-Authenticate": "Bearer"})
    return SecretStr(credentials.credentials)


async def get_current_session(
    request: Request, token: SecretStr = Depends(get_session_token),
    authentication: AuthenticationService = Depends(get_authentication),
) -> AuthenticatedSession:
    try:
        async with request.app.state.session_factory() as reader:
            current = await SessionService(reader).resolve(token)
    except SQLAlchemyError:
        raise unavailable() from None
    if current is None:
        raise HTTPException(401, "Sessão inválida ou expirada.", headers={"WWW-Authenticate": "Bearer"})
    return current


async def record_authorized_activity(request: Request, token: SecretStr) -> None:
    async with request.app.state.session_factory() as writer:
        renewed = await SessionService(writer, idle_timeout=timedelta(
            seconds=request.app.state.settings.auth_idle_timeout_seconds,
        )).record_activity(token)
    if renewed is None:
        raise HTTPException(401, "Sessão inválida ou expirada.", headers={"WWW-Authenticate": "Bearer"})


@router.post("/login", response_model=LoginResponse | MfaChallengeResponse)
async def login(
    data: LoginRequest, request: Request,
    authentication: AuthenticationService = Depends(get_authentication),
) -> LoginResponse | MfaChallengeResponse:
    if request.client is None:
        raise unavailable()
    try:
        issued = await authentication.login(data, origin_ip=request.client.host)
    except InvalidCredentialsError:
        raise HTTPException(401, "E-mail ou senha inválidos.", headers={"WWW-Authenticate": "Bearer"}) from None
    except LoginRateLimitExceededError as error:
        raise HTTPException(429, "Muitas tentativas. Aguarde antes de tentar novamente.",
                            headers={"Retry-After": str(error.retry_after_seconds)}) from None
    except (LoginRateLimitUnavailableError, AuthenticationBusyError, AccountUnavailable, SQLAlchemyError, ValueError):
        raise unavailable() from None
    if isinstance(issued, MfaChallenge):
        return MfaChallengeResponse(challenge_token=issued.token.get_secret_value(), expires_at=issued.expires_at)
    return LoginResponse(access_token=issued.token.get_secret_value(), expires_at=issued.expires_at)


@router.post("/logout", status_code=204)
async def logout(request: Request, token: SecretStr = Depends(get_session_token)) -> Response:
    # Revogar não depende do limitador nem da existência de uma sessão ainda válida.
    if request.app.state.settings.app_environment in ("staging", "production") and request.url.scheme != "https":
        raise unavailable()
    try:
        async with request.app.state.session_factory() as writer:
            await SessionService(writer).revoke(token)
    except SQLAlchemyError:
        raise unavailable() from None
    return Response(status_code=204)
