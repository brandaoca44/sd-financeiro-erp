"""Valida falhas de conexão e configurações sem acessar o banco real."""

import os
import unittest
from configparser import ConfigParser
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.core.config import Settings, get_settings


# A importação do módulo de sessão utiliza somente configurações fictícias.
with patch.dict(os.environ, {"DATABASE_PASSWORD": "senha_ficticia"}):
    from app.database import health
    from app.api.v1.health import get_health

get_settings.cache_clear()


class HealthTests(unittest.IsolatedAsyncioTestCase):
    """Garante respostas previsíveis para sucesso e indisponibilidade."""

    async def test_database_available(self):
        connection = AsyncMock()
        engine = MagicMock()
        engine.connect.return_value.__aenter__ = AsyncMock(return_value=connection)
        engine.connect.return_value.__aexit__ = AsyncMock(return_value=False)
        engine.dispose = AsyncMock()
        with patch.object(health, "engine", engine):
            self.assertTrue(await health.is_database_available())
        connection.execute.assert_awaited_once()
        engine.dispose.assert_not_awaited()

    async def test_connection_failures_return_false(self):
        for error in (
            OSError("detalhe_privado"),
            OperationalError("SELECT 1", {}, Exception("detalhe_privado")),
        ):
            with self.subTest(error=type(error).__name__):
                engine = MagicMock()
                engine.connect.side_effect = error
                engine.dispose = AsyncMock()
                with patch.object(health, "engine", engine):
                    self.assertFalse(await health.is_database_available())
                engine.dispose.assert_awaited_once()

    async def test_unavailable_endpoint_returns_503(self):
        from fastapi import Response

        response = Response()
        with patch("app.api.v1.health.is_database_available", AsyncMock(return_value=False)):
            result = await get_health(response)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(result.status, "unhealthy")
        self.assertEqual(result.model_dump(), {"status": "unhealthy"})
        self.assertNotIn("password", result.model_dump_json().lower())


class SettingsTests(unittest.TestCase):
    """Verifica localização do ambiente e proteção de valores sensíveis."""

    def test_env_file_is_backend_specific(self):
        expected = Path(__file__).resolve().parents[1] / ".env"
        self.assertEqual(Settings.model_config["env_file"], expected)

    def test_validation_error_hides_input(self):
        with self.assertRaises(ValidationError) as caught:
            Settings(_env_file=None, database_password="segredo_ficticio", database_port="valor_privado")
        self.assertNotIn("valor_privado", str(caught.exception))
        self.assertNotIn("segredo_ficticio", str(caught.exception))

    def test_alembic_preserves_encoded_credentials(self):
        settings = Settings(_env_file=None, database_password="senha@%:ficticia")
        config = ConfigParser()
        config.add_section("alembic")
        config.set("alembic", "sqlalchemy.url", settings.database_url.replace("%", "%%"))
        self.assertEqual(config.get("alembic", "sqlalchemy.url"), settings.database_url)
        self.assertNotIn("senha@%:ficticia", repr(settings))


if __name__ == "__main__":
    unittest.main()
