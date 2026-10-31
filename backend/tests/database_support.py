"""Fornece banco temporário exclusivo para testes de integração opt-in."""

import asyncio
import os
import selectors
import subprocess
import sys
import unittest
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings


@unittest.skipUnless(
    os.environ.get("SD_RUN_DATABASE_TESTS") == "1",
    "Defina SD_RUN_DATABASE_TESTS=1 para criar um banco temporário exclusivo.",
)
class DatabaseTestCase(unittest.IsolatedAsyncioTestCase):
    """Cria o banco com migrations e o remove após fechar as sessões."""

    loop_factory = staticmethod(lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))

    @classmethod
    def setUpClass(cls):
        cls.settings = Settings()
        if cls.settings.database_host != "127.0.0.1" or cls.settings.database_port != 5433:
            raise RuntimeError("Os testes exigem o PostgreSQL local do ERP na porta 5433.")
        cls.test_database = "sd_repository_test_" + uuid4().hex
        cls.database_created = False
        cls.addClassCleanup(cls._drop_test_database)
        try:
            with cls._maintenance_connection() as connection:
                connection.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(cls.test_database))
                )
            cls.database_created = True
        except psycopg.Error:
            raise RuntimeError("Não foi possível criar o banco exclusivo de testes.") from None
        cls.run_migration("upgrade", "head")

    @classmethod
    def run_migration(cls, *arguments):
        """Executa Alembic apenas no banco temporário desta classe."""

        environment = os.environ.copy()
        environment.update(
            DATABASE_NAME=cls.test_database, DATABASE_HOST="127.0.0.1", DATABASE_PORT="5433",
            DATABASE_USER=cls.settings.database_user,
            DATABASE_PASSWORD=cls.settings.database_password.get_secret_value(),
            DATABASE_ECHO="false",
        )
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *arguments],
            cwd=Path(__file__).resolve().parents[1], env=environment,
            capture_output=True, timeout=60,
        )
        if result.returncode:
            raise RuntimeError("Falha na validação de migrations do banco exclusivo de testes.")

    @classmethod
    def _maintenance_connection(cls):
        return psycopg.connect(
            host="127.0.0.1", port=5433, dbname="postgres", user=cls.settings.database_user,
            password=cls.settings.database_password.get_secret_value(),
            autocommit=True, connect_timeout=5,
        )

    @classmethod
    def _drop_test_database(cls):
        if not cls.database_created:
            return
        if not cls.test_database.startswith("sd_repository_test_"):
            raise RuntimeError("Nome de banco temporário inválido; remoção bloqueada.")
        UUID(cls.test_database.removeprefix("sd_repository_test_"))
        with cls._maintenance_connection() as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {}").format(sql.Identifier(cls.test_database))
            )

    async def asyncSetUp(self):
        settings = self.settings.model_copy(update={"database_name": self.test_database})
        self.engine = create_async_engine(
            settings.database_url, echo=False, connect_args={"connect_timeout": 5}
        )
        self.addAsyncCleanup(self.engine.dispose)
        self.session = AsyncSession(self.engine, expire_on_commit=False)
        self.addAsyncCleanup(self.session.close)
