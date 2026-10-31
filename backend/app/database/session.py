from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.database_echo,
    hide_parameters=True,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 5},
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


async def get_database_session() -> AsyncIterator[AsyncSession]:
    """Fornece uma sessão de banco isolada para cada requisição."""

    async with async_session_factory() as session:
        yield session


async def close_database_engine() -> None:
    """Libera as conexões mantidas pelo pool durante o encerramento."""

    await engine.dispose()
