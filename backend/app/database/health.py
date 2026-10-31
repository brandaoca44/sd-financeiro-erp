from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database.session import engine


async def is_database_available() -> bool:
    """Verifica se o PostgreSQL aceita uma consulta simples."""

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

        return True

    except (SQLAlchemyError, OSError):
        # Remove do pool conexões que podem ter sido encerradas pelo PostgreSQL.
        await engine.dispose()

        return False
