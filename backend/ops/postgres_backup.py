"""Backup cifrado e ensaio de restauração em contêiner descartável."""

import argparse
import base64
import getpass
import hashlib
import importlib
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from cryptography.fernet import Fernet, InvalidToken


MAGIC = b"SDFBACKUP\x01"
SALT_BYTES = 16
ITERATIONS = 1_200_000
MAX_DUMP = 128 * 1024 * 1024
MAX_FILE = len(MAGIC) + SALT_BYTES + 4 * ((MAX_DUMP + 128 + 2) // 3)
IMAGE = "postgres:18.4-alpine"
BACKEND = Path(__file__).resolve().parents[1]


class BackupError(Exception):
    """Mensagem operacional sem conteúdo do banco ou stderr de ferramentas."""


def _cipher(password: str, salt: bytes) -> Fernet:
    if not 16 <= len(password) <= 1024:
        raise BackupError("Use uma senha de backup entre 16 e 1024 caracteres.")
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS, 32)
    return Fernet(base64.urlsafe_b64encode(key))


def seal(dump: bytes, password: str) -> bytes:
    if not dump.startswith(b"PGDMP") or len(dump) > MAX_DUMP:
        raise BackupError("Dump inválido ou acima do limite de 128 MiB.")
    salt = secrets.token_bytes(SALT_BYTES)
    return MAGIC + salt + _cipher(password, salt).encrypt(dump)


def unseal(data: bytes, password: str) -> bytes:
    if len(data) > MAX_FILE or not data.startswith(MAGIC):
        raise BackupError("Formato de backup inválido ou acima do limite.")
    offset = len(MAGIC) + SALT_BYTES
    salt, token = data[len(MAGIC):offset], data[offset:]
    try:
        # Rejeita também dados anexados que um decoder base64 permissivo ignoraria.
        if base64.urlsafe_b64encode(base64.b64decode(token, altchars=b"-_", validate=True)) != token:
            raise ValueError
        dump = _cipher(password, salt).decrypt(token)
    except (InvalidToken, ValueError):
        raise BackupError("Senha incorreta ou backup corrompido.") from None
    if not dump.startswith(b"PGDMP") or len(dump) > MAX_DUMP:
        raise BackupError("Conteúdo de backup inválido.")
    return dump


def _docker(*args: str, input_data=None, timeout=60) -> bytes:
    try:
        result = subprocess.run(
            ["docker", *args], input=input_data, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise BackupError("Docker indisponível ou operação excedeu o tempo limite.") from None
    if result.returncode:
        raise BackupError("Falha na operação Docker/PostgreSQL; detalhes sensíveis foram omitidos.")
    return result.stdout


def read_dump(container: str, database: str | None = None) -> bytes:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", container):
        raise BackupError("Identificador de contêiner inválido.")
    if database is not None and not re.fullmatch(r"[a-zA-Z0-9_]{1,63}", database):
        raise BackupError("Identificador de banco inválido.")
    options = ["--env", "PGOPTIONS=-c statement_timeout=120000"]
    if database is not None:
        options += ["--env", "POSTGRES_DB=" + database]
    command = 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges --lock-wait-timeout=10s'
    try:
        process = subprocess.Popen(
            ["docker", "exec", *options, container, "sh", "-c", command],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
    except OSError:
        raise BackupError("Docker indisponível.") from None
    timer = threading.Timer(120, process.kill)
    timer.start()
    try:
        with process.stdout:
            dump = process.stdout.read(MAX_DUMP + 1)
        if len(dump) > MAX_DUMP:
            raise BackupError("Dump acima de 128 MiB; use uma solução de backup de maior capacidade.")
        if process.wait(timeout=10):
            raise BackupError("pg_dump falhou; nenhum backup foi publicado.")
        return dump
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
        process.wait()


def create_backup(path: Path, password: str, container="sd-financeiro-postgres") -> None:
    if path.suffix != ".sdfbackup" or path.exists():
        raise BackupError("Informe um arquivo novo com extensão .sdfbackup; sobrescrita bloqueada.")
    _cipher(password, b"\0" * SALT_BYTES)  # Valida antes de ler o banco.
    encrypted = seal(read_dump(container), password)
    # Só bytes cifrados chegam ao disco. Publicação atômica sem sobrescrever destino.
    fd, temporary = tempfile.mkstemp(suffix=".sdfbackup.partial", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(encrypted)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _head() -> str:
    config = Config()
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    head = ScriptDirectory.from_config(config).get_current_head()
    if not head or not re.fullmatch(r"[a-z0-9]+", head):
        raise BackupError("Não foi possível determinar a migration atual.")
    return head


def _sql(container: str, query: str) -> bytes:
    return _docker("exec", container, "psql", "-X", "-U", "postgres", "-d", "recovery",
                   "-v", "ON_ERROR_STOP=1", "-At", "-c", query)


def _expected_columns() -> set[str]:
    for module in ("organizations.models", "identity.models", "identity.access_models",
                   "identity.invitation_models", "identity.permission_models", "identity.company_access_models", "finance.models"):
        importlib.import_module("app.modules." + module)
    from app.database.base import Base
    return {f"{table.name}|{column.name}" for table in Base.metadata.tables.values() for column in table.columns}


def verify_backup(path: Path, password: str) -> dict:
    with path.open("rb") as source:
        dump = unseal(source.read(MAX_FILE + 1), password)
    # A autenticação termina antes de iniciar qualquer contêiner ou executar SQL.
    name = "sd-restore-check-" + uuid4().hex
    created = False
    started = time.monotonic()
    try:
        created = True  # Mesmo um timeout no docker run exige tentativa de limpeza pelo nome exclusivo.
        _docker(
            "run", "--detach", "--name", name, "--network", "none",
            "--memory", "1g", "--cpus", "1", "--pids-limit", "128",
            "--tmpfs", "/var/lib/postgresql:rw,nosuid,noexec,size=512m",
            "--env", "POSTGRES_HOST_AUTH_METHOD=trust", "--env", "POSTGRES_DB=recovery",
            IMAGE,
        )
        for attempt in range(40):
            try:
                _sql(name, "SELECT 1")
                break
            except BackupError:
                if attempt == 39:
                    raise BackupError("PostgreSQL descartável não ficou disponível.") from None
                time.sleep(0.5)
        _docker(
            "exec", "-i", name, "pg_restore", "-U", "postgres", "-d", "recovery",
            "--single-transaction", "--exit-on-error", "--no-owner", "--no-privileges",
            input_data=dump, timeout=180,
        )
        revision = _sql(name, "SELECT version_num FROM public.alembic_version").decode().strip()
        if revision != _head():
            raise BackupError("Backup restaurado possui migration diferente da versão atual do código.")
        invalid = _sql(name, "SELECT count(*) FROM pg_constraint WHERE NOT convalidated").strip()
        if invalid != b"0":
            raise BackupError("Restauração contém constraints não validadas.")
        columns = _sql(name, "SELECT table_name || '|' || column_name FROM information_schema.columns WHERE table_schema='public'").decode().splitlines()
        if not _expected_columns().issubset(set(columns)):
            raise BackupError("Restauração não contém todas as tabelas e colunas esperadas.")
        # Força leitura de todas as tabelas públicas, sem imprimir conteúdo ou contagens individuais.
        tables = _sql(name, "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").decode().splitlines()
        for table in tables:
            identifier = '"' + table.replace('"', '""') + '"'
            _sql(name, f"SELECT count(*) FROM public.{identifier}")
        return {"revision": revision, "tables_checked": len(tables),
                "seconds": round(time.monotonic() - started, 2)}
    finally:
        if created:
            try:
                _docker("rm", "--force", "--volumes", name)
            except BackupError:
                raise BackupError(f"Remoção do contêiner descartável falhou. Remova apenas {name}.") from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "verify"))
    parser.add_argument("file", type=Path)
    args = parser.parse_args(argv)
    try:
        if not sys.stdin.isatty():
            raise BackupError("Execute em terminal interativo; senha não é aceita por argumento ou variável de ambiente.")
        password = getpass.getpass("Senha do backup (mínimo 16 caracteres): ")
        if args.action == "create":
            if password != getpass.getpass("Confirme a senha: "):
                raise BackupError("As senhas não coincidem.")
            create_backup(args.file, password)
            print("Backup cifrado criado. Execute verify para ensaiar a recuperação.")
        else:
            result = verify_backup(args.file, password)
            print(f"Recuperação validada: migration {result['revision']}, {result['tables_checked']} tabelas; contêiner removido.")
        return 0
    except BackupError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, EOFError, KeyboardInterrupt, subprocess.SubprocessError):
        # Sem traceback, stderr externo, nomes de usuários, SQL ou conteúdo de arquivos.
        print("Operação não concluída. Verifique senha, arquivo, espaço e Docker; nenhuma base existente foi substituída.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
