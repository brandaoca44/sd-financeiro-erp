"""Erros e logs não podem refletir credenciais, parâmetros ou dados de clientes."""

import asyncio
import contextlib
import io
import json
import logging
import os
import unittest
from unittest.mock import patch

import httpx
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import StreamingResponse

from app.core.config import Settings, get_settings
from app.core.observability import SafeHttpBoundary, SafeJsonFormatter, http_logger, logging_config
from app.main import create_app
from ops import serve


PRIVATE = "segredo-cliente-token-email-cnpj-nao-publicar"


class OperationalHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        settings = Settings(_env_file=None, database_password="ficticia", app_environment="test", app_debug=True)
        self.app = create_app(settings, session_factory=object())
        self.output = io.StringIO()
        handler = logging.StreamHandler(self.output)
        handler.setFormatter(SafeJsonFormatter())
        original = http_logger.handlers[:]
        http_logger.handlers = [handler]
        self.addCleanup(setattr, http_logger, "handlers", original)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False), base_url="http://testserver")
        self.addAsyncCleanup(self.client.aclose)

        @self.app.get("/probe/{identifier}")
        async def probe(identifier: str):
            return {"status": "ok"}

        @self.app.get("/failure")
        async def failure():
            raise RuntimeError(PRIVATE)

        @self.app.post("/validated")
        async def validated(count: int):
            return {"count": count}

        @self.app.get("/database-failure")
        async def database_failure():
            raise SQLAlchemyError(PRIVATE)

        @self.app.get("/stream-failure")
        async def stream_failure():
            async def stream():
                yield b"public fragment"
                raise RuntimeError(PRIVATE)
            return StreamingResponse(stream())

    def events(self):
        data = self.output.getvalue()
        self.assertNotIn(PRIVATE, data)
        return [json.loads(line) for line in data.splitlines()]

    async def test_request_id_generated_not_echoed_and_sensitive_context_not_logged(self):
        response = await self.client.get("/probe/" + PRIVATE, params={"token": PRIVATE}, headers={
            "X-Request-ID": PRIVATE, "Authorization": "Bearer " + PRIVATE,
            "Cookie": "session=" + PRIVATE, "X-Forwarded-For": PRIVATE,
        })
        self.assertEqual(response.status_code, 200)
        request_id = response.headers["x-request-id"]
        self.assertRegex(request_id, r"^[0-9a-f]{32}$")
        self.assertEqual(response.headers["cache-control"], "no-store")
        event = self.events()[0]
        self.assertEqual(event["request_id"], request_id)
        self.assertEqual(set(event), {"event", "level", "method", "status", "request_id", "outcome", "duration_ms"})

    async def test_unknown_routes_and_validation_have_id_no_store_and_no_body_logs(self):
        for path, data, code in (("/missing/" + PRIVATE, {}, 404),
                                 ("/validated", {"email": PRIVATE, "password": PRIVATE}, 422)):
            response = await (self.client.post(path, json=data) if data else self.client.get(path))
            self.assertEqual(response.status_code, code)
            self.assertIn("x-request-id", response.headers)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertNotIn(PRIVATE, response.text)
        self.assertEqual(len(self.events()), 2)

    async def test_unexpected_and_database_errors_are_safe_even_in_debug(self):
        for path, code, outcome in (("/failure", 500, "internal_error"), ("/database-failure", 503, "unavailable")):
            response = await self.client.get(path)
            self.assertEqual(response.status_code, code)
            self.assertNotIn(PRIVATE, response.text)
            self.assertEqual(response.headers["content-type"], "application/json")
            self.assertEqual(self.events()[-1]["outcome"], outcome)

    async def test_concurrent_requests_have_distinct_ids(self):
        responses = await asyncio.gather(*(self.client.get("/probe/" + PRIVATE) for _ in range(10)))
        ids = {response.headers["x-request-id"] for response in responses}
        self.assertEqual(len(ids), 10)
        self.assertEqual({event["request_id"] for event in self.events()}, ids)

    async def test_stream_error_logged_without_original_exception(self):
        response = await self.client.get("/stream-failure")
        self.assertEqual(response.status_code, 200)  # Headers já enviados não podem ser substituídos.
        self.assertNotIn(PRIVATE, response.text)
        self.assertEqual(self.events()[-1]["outcome"], "interrupted")

    async def test_early_body_rejection_also_has_safe_log_and_id(self):
        response = await self.client.post("/api/v1/auth/login", content=PRIVATE * 200, headers={"content-type": "application/json"})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.events()[-1]["status"], 413)
        self.assertIn("x-request-id", response.headers)


class SafeLoggingTests(unittest.TestCase):
    def test_external_messages_args_exceptions_and_extra_are_omitted(self):
        record = logging.LogRecord("uvicorn.error", logging.ERROR, PRIVATE, 1, PRIVATE + " %s", (PRIVATE,), (RuntimeError, RuntimeError(PRIVATE), None))
        record.stack_info = PRIVATE
        record.arbitrary_extra = PRIVATE
        output = SafeJsonFormatter().format(record)
        self.assertNotIn(PRIVATE, output)
        self.assertEqual(json.loads(output), {"event": "runtime_message", "level": "ERROR"})

    def test_invalid_extra_fields_cannot_inject_log_content(self):
        record = logging.makeLogRecord({"name": "sd_financeiro.http", "levelname": "INFO", "safe_http": True,
            "request_id": PRIVATE, "method": PRIVATE, "status": PRIVATE, "duration_ms": PRIVATE, "outcome": PRIVATE})
        self.assertNotIn(PRIVATE, SafeJsonFormatter().format(record))

    def test_launcher_disables_access_logs_and_formats_runtime_logs(self):
        config = logging_config()
        self.assertFalse(config["loggers"]["uvicorn.access"]["propagate"])
        self.assertEqual(config["loggers"]["uvicorn.access"]["handlers"], [])
        self.assertEqual(config["handlers"]["safe"]["formatter"], "safe")

    def test_stream_exception_does_not_propagate_original_message(self):
        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            raise ValueError(PRIVATE)
        async def noop(*args):
            pass
        with self.assertRaisesRegex(RuntimeError, "Resposta interrompida") as caught:
            asyncio.run(SafeHttpBoundary(app)({"type": "http", "method": "GET"}, noop, noop))
        self.assertNotIn(PRIVATE, str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)


def production_settings(**changes):
    values = {"_env_file": None, "app_environment": "production", "database_password": "banco-" + "91ab" * 12,
              "redis_password": "redis-" + "27cd" * 12, "auth_rate_limit_key": "auth-" + "63ef" * 12}
    return Settings(**(values | changes))


class EnvironmentSecurityTests(unittest.TestCase):
    def tearDown(self):
        get_settings.cache_clear()

    def test_production_requires_debug_off_distinct_secrets_and_no_echo(self):
        self.assertEqual(production_settings().app_environment, "production")
        for changes in ({"app_debug": True}, {"database_echo": True}, {"redis_password": None},
                        {"auth_rate_limit_key": None}, {"database_password": "change_me"},
                        {"redis_password": "a" * 40}, {"redis_password": "auth-" + "63ef" * 12}):
            with self.subTest(fields=list(changes)), self.assertRaises(ValidationError) as error:
                production_settings(**changes)
            self.assertNotIn("91ab", str(error.exception))
            self.assertNotIn("63ef", str(error.exception))

    def test_staging_has_same_requirements(self):
        with self.assertRaises(ValidationError):
            production_settings(app_environment="staging", app_debug=True)

    def test_echo_and_blank_database_secret_rejected_in_development(self):
        for changes in ({"database_echo": True}, {"database_password": " "}):
            with self.assertRaises(ValidationError):
                Settings(_env_file=None, **({"database_password": "ficticia"} | changes))

    def test_prefix_cannot_include_query_fragment_or_trailing_slash(self):
        for prefix in ("/", "/api/", "/api?token=private", "/api#fragment", "api", "/api//v1"):
            with self.subTest(prefix=prefix), self.assertRaises(ValidationError):
                Settings(_env_file=None, database_password="ficticia", api_v1_prefix=prefix)

    def test_production_loader_ignores_local_dotenv(self):
        get_settings.cache_clear()
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "production"}, clear=True), patch("app.core.config.Settings", return_value=production_settings()) as constructor:
            get_settings()
            constructor.assert_called_once_with(_env_file=None)

    def test_production_without_external_secrets_fails_closed(self):
        get_settings.cache_clear()
        with patch.dict(os.environ, {"APP_ENVIRONMENT": "production"}, clear=True), self.assertRaises(ValidationError):
            get_settings()

    def test_launcher_hides_configuration_exception(self):
        with patch.object(serve, "get_settings", side_effect=RuntimeError(PRIVATE)), contextlib.redirect_stderr(io.StringIO()) as output:
            self.assertEqual(serve.main([]), 1)
        self.assertNotIn(PRIVATE, output.getvalue())

    def test_launcher_rejects_production_reload(self):
        with patch.object(serve, "get_settings", return_value=production_settings()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(serve.main(["--reload"]), 1)

    def test_launcher_uses_safe_options(self):
        with patch.object(serve, "get_settings", return_value=Settings(_env_file=None, database_password="ficticia")), patch("uvicorn.run") as run:
            self.assertEqual(serve.main([]), 0)
        self.assertFalse(run.call_args.kwargs["proxy_headers"])
        self.assertFalse(run.call_args.kwargs["access_log"])
        self.assertEqual(run.call_args.kwargs["loop"], "ops.serve:event_loop")
