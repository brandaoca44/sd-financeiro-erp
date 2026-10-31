"""Protege senhas com Argon2id sem bloquear o event loop da aplicação."""

import asyncio

from pydantic import SecretStr
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError


_password_hash = PasswordHash.recommended()
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


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
