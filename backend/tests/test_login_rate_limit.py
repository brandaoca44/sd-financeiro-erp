"""Valida decisões de rate limit e integração Redis em namespace exclusivo."""

import asyncio
import os
import secrets
import unittest
from unittest.mock import AsyncMock
from uuid import uuid4

from pydantic import SecretStr, ValidationError
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, ResponseError

from app.modules.identity.rate_limit import (
    LoginRateLimitExceededError,
    LoginRateLimitPolicy,
    LoginRateLimiter,
    LoginRateLimitUnavailableError,
)


class LoginRateLimiterTests(unittest.IsolatedAsyncioTestCase):
    """Testa validação e falhas sem depender do Redis."""

    def setUp(self):
        self.client = AsyncMock(spec=Redis)
        self.client.eval = AsyncMock(return_value=[1, 0])
        self.secret = SecretStr("segredo-exclusivo-ficticio-para-testes")
        self.limiter = LoginRateLimiter(
            self.client, key_secret=self.secret, namespace="sd-financeiro:test:unit",
        )

    async def test_allowed_request_returns_without_error(self):
        self.assertIsNone(await self.limiter.check(account_identifier="pessoa@example.invalid", origin_ip="127.0.0.1"))

    async def test_denial_provides_generic_message_and_retry_after(self):
        self.client.eval.return_value = [0, 12]
        with self.assertRaises(LoginRateLimitExceededError) as caught:
            await self.limiter.check(account_identifier="pessoa@example.invalid", origin_ip="127.0.0.1")
        self.assertEqual(caught.exception.retry_after_seconds, 12)
        self.assertNotIn("pessoa@example.invalid", str(caught.exception))
        self.assertNotIn("127.0.0.1", str(caught.exception))

    async def test_storage_failure_never_allows_login_or_exposes_details(self):
        for error in (ConnectionError("credencial_ficticia_privada"), ResponseError("detalhe_privado"), TimeoutError()):
            self.client.eval.side_effect = error
            with self.assertRaises(LoginRateLimitUnavailableError) as caught:
                await self.limiter.check(account_identifier="pessoa@example.invalid", origin_ip="127.0.0.1")
            self.assertNotIn("privad", str(caught.exception))
            self.assertTrue(caught.exception.__suppress_context__)

    async def test_malformed_storage_responses_are_rejected(self):
        for response in (None, [], [1], [True, 0], [1, -1], [0, 0], [0, 100_000], [2, 1], [b"1", b"0"]):
            self.client.eval.return_value = response
            with self.subTest(response=response), self.assertRaises(LoginRateLimitUnavailableError):
                await self.limiter.check(account_identifier="pessoa@example.invalid", origin_ip="127.0.0.1")

    def test_policy_requires_positive_bounded_integer_limits(self):
        for update in ({"account_limit": 0}, {"origin_limit": True}, {"global_limit": 1.5},
                       {"account_window_seconds": -1}, {"origin_window_seconds": 86_401}):
            with self.subTest(update=update), self.assertRaises(ValidationError):
                LoginRateLimitPolicy(**update)

    def test_secret_and_namespace_are_required(self):
        for secret in (None, "texto sem SecretStr", SecretStr("curto")):
            with self.assertRaises(ValueError):
                LoginRateLimiter(self.client, key_secret=secret, namespace="sd-financeiro:test")
        for namespace in ("", "arbitrario", "sd-financeiro:test:{outra-chave}"):
            with self.assertRaises(ValueError):
                LoginRateLimiter(self.client, key_secret=self.secret, namespace=namespace)

    def test_keys_protect_identifiers_and_normalize_account_and_ip(self):
        first = self.limiter._keys(" Pessoa@Example.Invalid ", "::ffff:127.0.0.1")
        second = self.limiter._keys("pessoa@example.invalid", "127.0.0.1")
        self.assertEqual(first, second)
        for key in first:
            self.assertNotIn("pessoa", key)
            self.assertNotIn("127.0.0.1", key)
        other = LoginRateLimiter(self.client, key_secret=SecretStr("outro-segredo-ficticio-de-32-bytes-extra"), namespace="sd-financeiro:test:unit")
        self.assertNotEqual(first[0], other._keys("pessoa@example.invalid", "127.0.0.1")[0])

    async def test_invalid_identifiers_and_forwarded_header_values_do_not_reach_redis(self):
        for account, origin in (("", "127.0.0.1"), ("a" * 513, "127.0.0.1"),
                                ("a\nb", "127.0.0.1"), ("pessoa", "127.0.0.1, 10.0.0.1"),
                                ("pessoa", "for=127.0.0.1"), ("pessoa", "fe80::1%eth0")):
            with self.assertRaises(ValueError):
                await self.limiter.check(account_identifier=account, origin_ip=origin)
        self.client.eval.assert_not_awaited()


@unittest.skipUnless(os.environ.get("SD_RUN_REDIS_TESTS") == "1", "Defina SD_RUN_REDIS_TESTS=1 para testar Redis local.")
class LoginRateLimiterRedisTests(unittest.IsolatedAsyncioTestCase):
    """Usa DB 15 do Redis local e remove somente chaves com namespace aleatório próprio."""

    async def asyncSetUp(self):
        self.client = Redis(host="127.0.0.1", port=6379, db=15, socket_timeout=2, socket_connect_timeout=2)
        self.addAsyncCleanup(self.client.aclose)
        self.namespace = "sd-financeiro:test:" + uuid4().hex
        self.secret = SecretStr(secrets.token_urlsafe(32))
        self.policy = LoginRateLimitPolicy(
            account_limit=2, account_window_seconds=60,
            origin_limit=20, origin_window_seconds=60,
            global_limit=100, global_window_seconds=60,
        )
        self.limiter = self._limiter()
        self.addAsyncCleanup(self._cleanup)
        await self.client.ping()

    def _limiter(self, *, client=None, namespace=None, **policy):
        return LoginRateLimiter(
            client if client is not None else self.client, key_secret=self.secret,
            namespace=namespace or self.namespace,
            policy=LoginRateLimitPolicy(**{**self.policy.model_dump(), **policy}),
        )

    async def _cleanup(self):
        keys = [key async for key in self.client.scan_iter(match="{" + self.namespace + ":login:v1}:*")]
        if keys:
            await self.client.delete(*keys)

    async def _check(self, *, limiter=None, account="pessoa@example.invalid", origin="127.0.0.1"):
        await (limiter or self.limiter).check(account_identifier=account, origin_ip=origin)

    async def test_account_limit_applies_across_origins_including_nonexistent_account(self):
        await self._check(origin="127.0.0.1")
        await self._check(origin="127.0.0.2")
        with self.assertRaises(LoginRateLimitExceededError):
            await self._check(origin="127.0.0.3")

    async def test_origin_limit_applies_across_accounts(self):
        limiter = self._limiter(origin_limit=2)
        await self._check(limiter=limiter, account="primeiro@example.invalid")
        await self._check(limiter=limiter, account="segundo@example.invalid")
        with self.assertRaises(LoginRateLimitExceededError):
            await self._check(limiter=limiter, account="terceiro@example.invalid")

    async def test_global_limit_applies_across_accounts_and_origins(self):
        limiter = self._limiter(global_limit=2)
        await self._check(limiter=limiter, account="primeiro", origin="127.0.0.1")
        await self._check(limiter=limiter, account="segundo", origin="127.0.0.2")
        with self.assertRaises(LoginRateLimitExceededError):
            await self._check(limiter=limiter, account="terceiro", origin="127.0.0.3")

    async def test_denied_attempt_does_not_extend_ttl_or_consume_other_keys(self):
        await self._check()
        await self._check()
        keys = self.limiter._keys("pessoa@example.invalid", "127.0.0.1")
        await self.client.pexpire(keys[0], 5_000)
        before = await self.client.pttl(keys[0])
        with self.assertRaises(LoginRateLimitExceededError) as caught:
            await self._check(origin="127.0.0.2")
        self.assertGreaterEqual(caught.exception.retry_after_seconds, 1)
        self.assertLessEqual(caught.exception.retry_after_seconds, 5)
        self.assertLessEqual(await self.client.pttl(keys[0]), before)
        new_origin = self.limiter._keys("pessoa@example.invalid", "127.0.0.2")[1]
        self.assertFalse(await self.client.exists(new_origin))

    async def test_expiration_reopens_window_without_sleep_or_flush(self):
        await self._check()
        await self._check()
        with self.assertRaises(LoginRateLimitExceededError):
            await self._check()
        account_key = self.limiter._keys("pessoa@example.invalid", "127.0.0.1")[0]
        await self.client.pexpire(account_key, 0)
        await self._check()
        self.assertGreater(await self.client.pttl(account_key), 0)
        self.assertLessEqual(await self.client.pttl(account_key), 60_000)

    async def test_concurrent_workers_share_atomic_limit(self):
        second_client = Redis(host="127.0.0.1", port=6379, db=15, socket_timeout=2, socket_connect_timeout=2)
        self.addAsyncCleanup(second_client.aclose)
        workers = [self.limiter, self._limiter(client=second_client)]
        results = await asyncio.gather(*[
            self._check(limiter=workers[i % 2]) for i in range(30)
        ], return_exceptions=True)
        self.assertEqual(sum(result is None for result in results), 2)
        self.assertTrue(all(result is None or isinstance(result, LoginRateLimitExceededError) for result in results))

    async def test_namespaces_are_independent(self):
        await self._check()
        await self._check()
        other_namespace = self.namespace + "_other"
        other = self._limiter(namespace=other_namespace)
        try:
            await self._check(limiter=other)
            with self.assertRaises(LoginRateLimitExceededError):
                await self._check()
        finally:
            keys = [key async for key in self.client.scan_iter(match="{" + other_namespace + ":login:v1}:*")]
            if keys:
                await self.client.delete(*keys)

    async def test_corrupted_counter_without_ttl_fails_closed(self):
        key = self.limiter._keys("pessoa@example.invalid", "127.0.0.1")[0]
        await self.client.set(key, "1")
        with self.assertRaises(LoginRateLimitUnavailableError):
            await self._check()
