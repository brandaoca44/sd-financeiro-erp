"""Logs por campos permitidos; nunca serializa requisições ou exceções."""

import json
import logging
import re
import time
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse


class SafeJsonFormatter(logging.Formatter):
    def format(self, record):
        # Mensagem, args, extras arbitrários, exc_info e stack_info são ignorados.
        data = {"event": "runtime_message", "level": record.levelname
                if record.levelname in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} else "UNKNOWN"}
        if record.name == "sd_financeiro.http" and getattr(record, "safe_http", False) is True:
            data["event"] = "http_request"
            for key, pattern in (("request_id", r"[0-9a-f]{32}"),
                                 ("method", r"GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|OTHER"),
                                 ("outcome", r"completed|internal_error|unavailable|interrupted")):
                value = getattr(record, key, None)
                if isinstance(value, str) and re.fullmatch(pattern, value):
                    data[key] = value
            for key, low, high in (("status", 100, 599), ("duration_ms", 0, 86_400_000)):
                value = getattr(record, key, None)
                if type(value) is int and low <= value <= high:
                    data[key] = value
        return json.dumps(data, ensure_ascii=True, separators=(",", ":"))


http_logger = logging.getLogger("sd_financeiro.http")
if not http_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJsonFormatter())
    http_logger.addHandler(handler)
http_logger.setLevel(logging.INFO)
http_logger.propagate = False


class SafeHttpBoundary:
    """Correlaciona erros sem confiar em IDs recebidos nem expor caminhos/valores."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        start = time.monotonic()
        status, started, complete = 500, False, False
        outcome = "completed"

        async def safe_send(message):
            nonlocal status, started, complete
            if message["type"] == "http.response.start":
                status, started = message["status"], True
                headers = [(k, v) for k, v in message.get("headers", [])
                           if k.lower() not in (b"x-request-id", b"cache-control", b"pragma")]
                message = {**message, "headers": headers + [
                    (b"x-request-id", request_id.encode("ascii")),
                    (b"cache-control", b"no-store"), (b"pragma", b"no-cache"),
                ]}
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                complete = True
            await send(message)

        try:
            await self.app(scope, receive, safe_send)
        except Exception as error:
            if started:
                outcome = "interrupted"
                # Após headers não é possível trocar o status. Nunca propagar a exceção original.
                raise RuntimeError("Resposta interrompida.") from None
            status = 503 if isinstance(error, SQLAlchemyError) else 500
            outcome = "unavailable" if status == 503 else "internal_error"
            detail = "Serviço temporariamente indisponível." if status == 503 else "Erro interno."
            await JSONResponse({"detail": detail}, status)(scope, receive, safe_send)
        finally:
            if not complete and outcome == "completed":
                outcome = "interrupted"
            raw_method = scope.get("method", "")
            method = raw_method if raw_method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"} else "OTHER"
            http_logger.info("http_request", extra={
                "safe_http": True, "request_id": request_id, "method": method,
                "status": status, "outcome": outcome,
                "duration_ms": min(86_400_000, max(0, int((time.monotonic() - start) * 1000))),
            })


def logging_config():
    """Configuração do launcher; logs externos também não imprimem valores livres."""
    return {
        "version": 1, "disable_existing_loggers": False,
        "formatters": {"safe": {"()": "app.core.observability.SafeJsonFormatter"}},
        "handlers": {"safe": {"class": "logging.StreamHandler", "formatter": "safe", "stream": "ext://sys.stderr"}},
        "root": {"level": "WARNING", "handlers": ["safe"]},
        "loggers": {
            "uvicorn": {"handlers": ["safe"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["safe"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": [], "level": "CRITICAL", "propagate": False},
            "sqlalchemy": {"handlers": ["safe"], "level": "WARNING", "propagate": False},
            "sd_financeiro.http": {"handlers": ["safe"], "level": "INFO", "propagate": False},
        },
    }
