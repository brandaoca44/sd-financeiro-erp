from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.database.session import close_database_engine

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Gerencia recursos compartilhados durante o ciclo da aplicação."""

    yield

    await close_database_engine()


app = FastAPI(
    title=settings.app_name,
    description="API do Sistema Digital Financeiro.",
    version=settings.app_version,
    debug=settings.app_debug,
    lifespan=lifespan,
)

app.include_router(
    health_router,
    prefix=settings.api_v1_prefix,
)