"""Valida hash e verificação com senhas exclusivamente fictícias."""

import unittest

from pydantic import SecretStr
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.modules.identity.passwords import hash_password, verify_password


class PasswordTests(unittest.IsolatedAsyncioTestCase):
    """Exercita Argon2id real e proteção dos valores em representações textuais."""

    async def test_hash_uses_argon2id_and_random_salt(self):
        password = SecretStr("uma senha ficticia longa")
        first = await hash_password(password)
        second = await hash_password(password)
        self.assertTrue(first.get_secret_value().startswith("$argon2id$"))
        self.assertNotEqual(first.get_secret_value(), second.get_secret_value())
        self.assertNotIn(password.get_secret_value(), first.get_secret_value())
        self.assertNotIn(first.get_secret_value(), repr(first))

    async def test_correct_password_verifies_without_rehash(self):
        password = SecretStr("outra senha ficticia longa")
        hashed = await hash_password(password)
        self.assertEqual(await verify_password(password, hashed.get_secret_value()), (True, None))

    async def test_wrong_password_is_rejected(self):
        hashed = await hash_password(SecretStr("senha correta apenas de teste"))
        self.assertEqual(
            await verify_password(SecretStr("senha incorreta de teste"), hashed.get_secret_value()),
            (False, None),
        )

    async def test_unicode_and_surrounding_spaces_are_preserved(self):
        password = SecretStr("  frase fictícia com ação 🔐  ")
        hashed = await hash_password(password)
        self.assertTrue((await verify_password(password, hashed.get_secret_value()))[0])
        self.assertFalse((await verify_password(
            SecretStr(password.get_secret_value().strip()), hashed.get_secret_value(),
        ))[0])

    async def test_new_password_length_limits(self):
        for length in (8, 128):
            with self.subTest(length=length):
                password = SecretStr("á" * length)
                hashed = await hash_password(password)
                self.assertTrue((await verify_password(password, hashed.get_secret_value()))[0])
        for length in (0, 7, 129):
            with self.subTest(length=length), self.assertRaises(ValueError):
                await hash_password(SecretStr("a" * length))

    async def test_hash_requires_secretstr(self):
        with self.assertRaises(TypeError) as caught:
            await hash_password("senha ficticia exposta")
        self.assertNotIn("senha ficticia exposta", str(caught.exception))

    async def test_invalid_inputs_and_hashes_are_rejected(self):
        password = SecretStr("senha ficticia longa")
        for stored_hash in ("", "invalido", "$argon2id$v=19$m=65536,t=3,p=4$ruim$ruim", "a" * 513, None):
            with self.subTest(hash_type=type(stored_hash).__name__):
                self.assertEqual(await verify_password(password, stored_hash), (False, None))
        for invalid_password in (None, "texto sem SecretStr", SecretStr(""), SecretStr("a" * 129)):
            self.assertEqual(await verify_password(invalid_password, "invalido"), (False, None))

    async def test_successful_verification_proposes_parameter_upgrade(self):
        password = SecretStr("senha antiga apenas ficticia")
        old_hash = PasswordHash((Argon2Hasher(time_cost=2),)).hash(password.get_secret_value())
        valid, replacement = await verify_password(password, old_hash)
        self.assertTrue(valid)
        self.assertIsInstance(replacement, SecretStr)
        self.assertEqual(await verify_password(password, replacement.get_secret_value()), (True, None))
        self.assertEqual(await verify_password(SecretStr("incorreta"), old_hash), (False, None))
