"""Inicialização local com logs seguros e sem confiança em proxy headers."""

import argparse
import asyncio
import selectors
import sys

from app.core.config import get_settings
from app.core.observability import logging_config


def event_loop():
    # Psycopg assíncrono não aceita o Proactor padrão no Windows.
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())
    return asyncio.new_event_loop()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(argv)
    try:
        settings = get_settings()
    except Exception:
        print("Configuração inválida. Revise as variáveis obrigatórias e as regras de segurança do ambiente.", file=sys.stderr)
        return 1
    if args.reload and settings.app_environment not in ("development", "test"):
        print("Reload é permitido somente em desenvolvimento e testes.", file=sys.stderr)
        return 1
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=args.reload,
                proxy_headers=False, access_log=False, log_config=logging_config(),
                loop="ops.serve:event_loop")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
