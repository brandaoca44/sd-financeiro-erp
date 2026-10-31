"""Protege senhas com Argon2id sem bloquear o event loop da aplicação."""

import asyncio

from pydantic import SecretStr
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError


_password_hash = PasswordHash.recommended()
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
_COMMON_PASSWORDS = frozenset({
    "12345678", "password", "senha123", "qwertyui", "123456789012345",
    "12345678901234567890", "password123456789", "senha12345678901",
    "administrador123", "qwertyuiop123456",
})


async def run_password_work(work):
    """Mantém a vaga do chamador até a thread terminar, inclusive no cancelamento."""
    task = asyncio.create_task(work)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.shield(task)
        raise


def validate_new_password(password: SecretStr) -> SecretStr:
    """Bloqueio local mínimo compartilhado pelo bootstrap e aceite de novos usuários."""
    plain = password.get_secret_value()
    if not MIN_PASSWORD_LENGTH <= len(plain) <= MAX_PASSWORD_LENGTH:
        raise ValueError("A senha deve conter entre 8 e 128 caracteres.")
    if plain.lower() in _COMMON_PASSWORDS or len(set(plain)) == 1:
        raise ValueError("Escolha uma senha menos previsível.")
    return password


async def hash_password(password: SecretStr) -> SecretStr:
    """Gera hash com salt aleatório; não remove espaços ou normaliza a senha."""

    if not isinstance(password, SecretStr):
        raise TypeError("A senha deve ser fornecida como SecretStr.")
    value = password.get_secret_value()
    if not MIN_PASSWORD_LENGTH <= len(value) <= MAX_PASSWORD_LENGTH:
        raise ValueError("A senha deve conter entre 8 e 128 caracteres.")
    return SecretStr(await asyncio.to_thread(_password_hash.hash, value))


async def verify_password(
    password: SecretStr, stored_hash: str,
) -> tuple[bool, SecretStr | None]:
    """Verifica e sugere rehash quando necessário, sem persistir ou registrar dados."""

    if not isinstance(password, SecretStr) or not isinstance(stored_hash, str):
        return False, None
    value = password.get_secret_value()
    if not 1 <= len(value) <= MAX_PASSWORD_LENGTH or not 1 <= len(stored_hash) <= 512:
        return False, None
    try:
        valid, replacement = await asyncio.to_thread(
            _password_hash.verify_and_update, value, stored_hash,
        )
    except UnknownHashError:
        return False, None
    return valid, SecretStr(replacement) if replacement is not None else None
