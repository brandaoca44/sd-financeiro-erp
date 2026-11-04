from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
import asyncio
import secrets

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import SecretStr
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from starlette.responses import JSONResponse

from app.api.v1.account import router as account_router
from app.api.v1.catalog import router as catalog_router
from app.modules.identity.account_security import AccountService
from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.ownership import router as ownership_router
from app.api.v1.invitations import router as invitations_router
from app.api.v1.roles import router as roles_router
from app.api.v1.memberships import router as memberships_router
from app.api.v1.legacy_access import router as legacy_access_router
from app.api.v1.company_access import router as company_access_router
from app.api.v1.workspaces import router as workspace_router
from app.core.config import Settings, get_settings
from app.core.http_security import ProtectedApiBoundary
from app.core.observability import SafeHttpBoundary
from app.database.session import async_session_factory, close_database_engine
from app.modules.identity.authentication import AuthenticationService
from app.modules.identity.passwords import hash_password
from app.modules.identity.rate_limit import LoginRateLimiter, LoginRateLimitPolicy
from app.modules.organizations.router import router as organization_router
from app.modules.organizations.company_router import router as company_router
from app.modules.finance.router import router as payable_router
from app.modules.people.collaborators import router as collaborators_router
from app.modules.identity.profile import router as profile_router
from app.modules.finance.results import router as results_router
from app.modules.finance.billing import router as billing_router, customers_router
from app.modules.finance.expenses import router as expenses_router, supplier_router

def create_app(
    settings: Settings | None = None, *, session_factory=None, redis_client: Redis | None = None,
    rate_limit_namespace: str | None = None,
) -> FastAPI:
    """Monta a aplicação; injeções de infraestrutura permitem testes isolados."""

    config = settings if settings is not None else get_settings()
    factory = session_factory if session_factory is not None else async_session_factory

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        client = redis_client
        try:
            if config.auth_rate_limit_key is not None:
                if client is None:
                    client = Redis(
                        host=config.redis_host, port=config.redis_port, db=config.redis_db,
                        username=config.redis_username,
                        password=config.redis_password.get_secret_value() if config.redis_password else None,
                        socket_connect_timeout=2, socket_timeout=2, max_connections=20,
                        retry=Retry(NoBackoff(), 0),
                    )
                limiter = LoginRateLimiter(
                    client, key_secret=config.auth_rate_limit_key,
                    namespace=rate_limit_namespace or f"sd-financeiro:{config.app_environment}",
                    policy=LoginRateLimitPolicy(
                        account_limit=config.auth_account_limit, account_window_seconds=config.auth_account_window_seconds,
                        origin_limit=config.auth_origin_limit, origin_window_seconds=config.auth_origin_window_seconds,
                        global_limit=config.auth_global_limit, global_window_seconds=config.auth_global_window_seconds,
                    ),
                )
                dummy_hash = await hash_password(SecretStr(secrets.token_urlsafe(32)))
                application.state.auth_hash_slots = asyncio.Semaphore(config.auth_hash_concurrency)
                application.state.ownership_limiter = LoginRateLimiter(
                    client, key_secret=config.auth_rate_limit_key,
                    namespace=rate_limit_namespace or f"sd-financeiro:{config.app_environment}",
                    operation="ownership",
                )
                for operation in ("invitation_manage", "invitation_accept", "access_manage", "account_actions", "mfa"):
                    setattr(application.state, operation + "_limiter", LoginRateLimiter(
                        client, key_secret=config.auth_rate_limit_key,
                        namespace=rate_limit_namespace or f"sd-financeiro:{config.app_environment}",
                        operation=operation,
                    ))
                application.state.payables_manage_limiter = LoginRateLimiter(client,
                    key_secret=config.auth_rate_limit_key,
                    namespace=rate_limit_namespace or f"sd-financeiro:{config.app_environment}",
                    operation="payables_manage", policy=LoginRateLimitPolicy(
                        account_limit=60, account_window_seconds=60, origin_limit=180,
                        origin_window_seconds=60, global_limit=1200, global_window_seconds=60))
                application.state.authentication = AuthenticationService(
                    factory, limiter, dummy_hash=dummy_hash,
                    idle_timeout=timedelta(seconds=config.auth_idle_timeout_seconds),
                    hash_concurrency=config.auth_hash_concurrency,
                    hash_slots=application.state.auth_hash_slots,
                )
                application.state.accounts = AccountService(factory, hash_slots=application.state.auth_hash_slots,
                    encryption_key=config.auth_mfa_encryption_key,
                    identity_key=config.auth_identity_encryption_key,
                    idle_timeout=timedelta(seconds=config.auth_idle_timeout_seconds))
                application.state.authentication.account_service = application.state.accounts
            yield
        finally:
            application.state.accounts = None
            application.state.authentication = None
            application.state.ownership_limiter = None
            application.state.auth_hash_slots = None
            application.state.invitation_manage_limiter = None
            application.state.invitation_accept_limiter = None
            application.state.access_manage_limiter = None
            application.state.payables_manage_limiter = None
            application.state.account_actions_limiter = None
            application.state.mfa_limiter = None
            if client is not None and redis_client is None:
                await client.aclose()
            if session_factory is None:
                await close_database_engine()

    application = FastAPI(
        title=config.app_name, description="API do Sistema Digital Financeiro.",
        version=config.app_version, debug=config.app_debug, lifespan=lifespan,
        docs_url="/docs" if config.app_environment in ("development", "test") else None,
        redoc_url="/redoc" if config.app_environment in ("development", "test") else None,
        openapi_url="/openapi.json" if config.app_environment in ("development", "test") else None,
    )
    application.state.authentication = None
    application.state.ownership_limiter = None
    application.state.auth_hash_slots = None
    application.state.invitation_manage_limiter = None
    application.state.invitation_accept_limiter = None
    application.state.access_manage_limiter = None
    application.state.payables_manage_limiter = None
    application.state.accounts = None
    application.state.account_actions_limiter = None
    application.state.mfa_limiter = None
    application.state.settings = config
    application.state.session_factory = factory
    application.add_middleware(ProtectedApiBoundary, api_prefix=config.api_v1_prefix)
    application.add_middleware(SafeHttpBoundary)

    @application.exception_handler(RequestValidationError)
    async def safe_validation_error(request: Request, error: RequestValidationError):
        # Mensagem fixa: não serializar input, ctx, corpo ou erros que reflitam valores.
        return JSONResponse({"detail": "Dados de entrada inválidos."}, status_code=422)

    application.include_router(health_router, prefix=config.api_v1_prefix)
    application.include_router(profile_router, prefix=config.api_v1_prefix)
    application.include_router(auth_router, prefix=config.api_v1_prefix)
    application.include_router(account_router, prefix=config.api_v1_prefix)
    application.include_router(catalog_router, prefix=config.api_v1_prefix)
    application.include_router(organization_router, prefix=config.api_v1_prefix)
    application.include_router(ownership_router, prefix=config.api_v1_prefix)
    application.include_router(invitations_router, prefix=config.api_v1_prefix)
    application.include_router(roles_router, prefix=config.api_v1_prefix)
    application.include_router(memberships_router, prefix=config.api_v1_prefix)
    application.include_router(legacy_access_router, prefix=config.api_v1_prefix)
    application.include_router(company_router, prefix=config.api_v1_prefix)
    application.include_router(company_access_router, prefix=config.api_v1_prefix)
    application.include_router(workspace_router, prefix=config.api_v1_prefix)
    application.include_router(payable_router, prefix=config.api_v1_prefix)
    application.include_router(collaborators_router, prefix=config.api_v1_prefix)
    application.include_router(customers_router, prefix=config.api_v1_prefix)
    application.include_router(results_router, prefix=config.api_v1_prefix)
    application.include_router(billing_router, prefix=config.api_v1_prefix)
    application.include_router(expenses_router, prefix=config.api_v1_prefix)
    application.include_router(supplier_router, prefix=config.api_v1_prefix)
    return application


app = create_app()
