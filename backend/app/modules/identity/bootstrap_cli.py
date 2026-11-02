"""Comando interativo para inicializar o primeiro operador, sem aceitar senhas por argumentos."""

import asyncio
import getpass
import secrets
import selectors
import sys
import warnings

from pydantic import SecretStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings, get_settings
from app.modules.identity.bootstrap import (
    BootstrapAccountConflictError,
    BootstrapAlreadyInitializedError,
    BootstrapOperatorInput,
    PlatformBootstrapService,
)


async def _create_operator(settings: Settings, data: BootstrapOperatorInput):
    engine = create_async_engine(
        settings.database_url, echo=False, hide_parameters=True, connect_args={"connect_timeout": 5},
    )
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            return await PlatformBootstrapService(session).create_operator(data)
    finally:
        await engine.dispose()


def _validation_message(error: ValidationError) -> str:
    """Explica regras por campo sem refletir valores, mensagens ou contexto do erro."""

    if error.title != BootstrapOperatorInput.__name__:
        return "Configuração inválida. Confira backend/.env, sem compartilhar os valores secretos."
    messages = []
    for issue in error.errors(include_input=False, include_context=False, include_url=False):
        location = issue.get("loc", ())
        field = location[0] if location else None
        if field == "name":
            message = "Nome: informe entre 1 e 150 caracteres, sem deixar apenas espaços."
        elif field == "email":
            message = "E-mail: informe um endereço válido, com até 254 caracteres."
        elif field == "password":
            if issue.get("type") in {"too_short", "too_long", "string_too_short", "string_too_long"}:
                message = "Senha: use entre 8 e 128 caracteres. Caracteres especiais são permitidos."
            else:
                message = "Senha: escolha uma frase menos previsível, sem repetir apenas um caractere."
        else:
            message = "Dados de cadastro inválidos. Confira os campos solicitados."
        if message not in messages:
            messages.append(message)
    return "Dados inválidos:\n" + "\n".join("- " + message for message in messages)


def main(argv: list[str] | None = None) -> int:
    """Executa somente em terminal interativo, sem imprimir credenciais ou exceções."""

    arguments = sys.argv[1:] if argv is None else argv
    if arguments == ["--help"]:
        print("Uso: uv run python -m app.modules.identity.bootstrap_cli")
        print("Comando interativo; não aceita senhas ou outros dados por argumentos.")
        return 0
    if arguments:
        print("Argumentos não são aceitos. Use --help para consultar o comando.", file=sys.stderr)
        return 2
    if not sys.stdin.isatty():
        print("É necessário um terminal interativo com entrada de senha oculta.", file=sys.stderr)
        return 2
    try:
        settings = get_settings()
        print(f"Destino: {settings.database_host}:{settings.database_port} / {settings.database_name}")
        if input("Digite CRIAR para inicializar o primeiro operador neste banco: ").strip() != "CRIAR":
            print("Operação cancelada.")
            return 1
        name = input("Nome: ")
        email = input("E-mail: ")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = SecretStr(getpass.getpass("Senha (8 a 128 caracteres): "))
            confirmation = SecretStr(getpass.getpass("Confirme a senha: "))
        if not secrets.compare_digest(
            password.get_secret_value().encode("utf-8"), confirmation.get_secret_value().encode("utf-8"),
        ):
            print("As senhas não coincidem.", file=sys.stderr)
            return 2
        data = BootstrapOperatorInput(name=name, email=email, password=password)
        runner_options = {}
        if sys.platform == "win32":
            runner_options["loop_factory"] = lambda: asyncio.SelectorEventLoop(selectors.SelectSelector())
        user_id = asyncio.run(_create_operator(settings, data), **runner_options)
        print(f"Primeiro operador criado. Identificador: {user_id}")
        return 0
    except (KeyboardInterrupt, EOFError):
        print("Operação cancelada.", file=sys.stderr)
        return 130
    except getpass.GetPassWarning:
        print("Não foi possível ocultar a senha. Operação interrompida.", file=sys.stderr)
        return 2
    except ValidationError as error:
        print(_validation_message(error), file=sys.stderr)
        return 2
    except (BootstrapAlreadyInitializedError, BootstrapAccountConflictError):
        print("Bootstrap recusado: inicialização concluída, operador ou conta já existente.", file=sys.stderr)
        return 1
    except Exception:
        # Exceções de infraestrutura podem incluir parâmetros; não exibi-las neste comando.
        print("Não foi possível concluir. Confira o banco de destino, a conexão e as migrations.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
