"""Limita admissões de login com contadores compartilhados e identificadores protegidos."""

import hashlib
import hmac
import ipaddress
import re

from pydantic import BaseModel, ConfigDict, Field, SecretStr
from redis.asyncio import Redis
from redis.exceptions import RedisError


class LoginRateLimitPolicy(BaseModel):
    """Define limites iniciais ajustáveis no servidor, nunca pelo cliente HTTP."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True, hide_input_in_errors=True)

    account_limit: int = Field(default=5, ge=1, le=1_000_000)
    account_window_seconds: int = Field(default=900, ge=1, le=86_400)
    origin_limit: int = Field(default=30, ge=1, le=1_000_000)
    origin_window_seconds: int = Field(default=60, ge=1, le=86_400)
    global_limit: int = Field(default=300, ge=1, le=1_000_000)
    global_window_seconds: int = Field(default=60, ge=1, le=86_400)


class LoginRateLimitExceededError(Exception):
    """Permite mapear a recusa para HTTP 429 e Retry-After sem expor a dimensão."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Muitas tentativas. Aguarde antes de tentar novamente.")
        self.retry_after_seconds = retry_after_seconds


class LoginRateLimitUnavailableError(Exception):
    """Interrompe o login se o armazenamento não puder aplicar a política."""


# Cada chave possui janela a partir da primeira admissão. Recusas não renovam TTL.
# O preflight evita consumir limites de outras dimensões quando uma já está bloqueada.
_CHECK_SCRIPT = """
local counts = {}
local retry_ms = 0
for i, key in ipairs(KEYS) do
    local raw = redis.call('GET', key)
    local count = 0
    local ttl = -2
    if raw then
        if not string.match(raw, '^%d+$') then
            return redis.error_reply('Invalid rate limit state')
        end
        count = tonumber(raw)
        ttl = redis.call('PTTL', key)
        if ttl < 0 then
            return redis.error_reply('Invalid rate limit expiration')
        end
    end
    counts[i] = count
    if count >= tonumber(ARGV[(i - 1) * 2 + 1]) then
        retry_ms = math.max(retry_ms, math.max(ttl, 1))
    end
end
if retry_ms > 0 then
    return {0, math.max(1, math.ceil(retry_ms / 1000))}
end
for i, key in ipairs(KEYS) do
    redis.call('INCR', key)
    if counts[i] == 0 then
        redis.call('PEXPIRE', key, ARGV[(i - 1) * 2 + 2])
    end
end
return {1, 0}
"""


class LoginRateLimiter:
    """Verifica origem, conta e limite geral antes da verificação de senha.

    Recebe cliente Redis gerenciado pelo chamador, com timeouts finitos. A origem
    deve vir da conexão validada pelo servidor; não recebe ou interpreta headers.
    Login, propriedade, convites e gestão de perfis usam contadores separados. Nunca limitar logout.
    """

    def __init__(
        self, client: Redis, *, key_secret: SecretStr, namespace: str,
        policy: LoginRateLimitPolicy | None = None,
        operation: str = "login",
    ) -> None:
        if not isinstance(key_secret, SecretStr) or len(key_secret.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("O segredo do limitador deve ter pelo menos 32 bytes.")
        if not isinstance(namespace, str) or re.fullmatch(
            r"sd-financeiro:(development|test|staging|production)(:[a-z0-9_-]{1,64})?", namespace,
        ) is None:
            raise ValueError("Namespace de rate limit inválido.")
        if policy is not None and not isinstance(policy, LoginRateLimitPolicy):
            raise ValueError("Política de rate limit inválida.")
        if operation not in ("login", "ownership", "invitation_manage", "invitation_accept", "access_manage", "payables_manage"):
            raise ValueError("Operação de rate limit inválida.")
        self._client = client
        self._key_secret = key_secret
        self._prefix = "{" + namespace + ":" + operation + ":v1}"
        self._policy = policy if policy is not None else LoginRateLimitPolicy()

    def _digest(self, purpose: str, value: str) -> str:
        return hmac.new(
            self._key_secret.get_secret_value().encode("utf-8"),
            (purpose + ":" + value).encode("utf-8"), hashlib.sha256,
        ).hexdigest()

    def _keys(self, account_identifier: str, origin_ip: str) -> list[str]:
        if not isinstance(account_identifier, str) or not 1 <= len(account_identifier) <= 512:
            raise ValueError("Identificador de conta inválido.")
        account = account_identifier.strip().lower()
        if not 1 <= len(account) <= 254 or any(ord(char) < 32 for char in account):
            raise ValueError("Identificador de conta inválido.")
        if not isinstance(origin_ip, str) or not 1 <= len(origin_ip) <= 64 or "%" in origin_ip:
            raise ValueError("Origem de conexão inválida.")
        try:
            address = ipaddress.ip_address(origin_ip)
        except ValueError:
            raise ValueError("Origem de conexão inválida.") from None
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        return [
            self._prefix + ":account:" + self._digest("account", account),
            self._prefix + ":origin:" + self._digest("origin", str(address)),
            self._prefix + ":global",
        ]

    async def check(self, *, account_identifier: str, origin_ip: str) -> None:
        """Consome uma admissão ou lança recusa/falha; não consulta existência de conta."""

        keys = self._keys(account_identifier, origin_ip)
        policy = self._policy
        try:
            result = await self._client.eval(
                _CHECK_SCRIPT, len(keys), *keys,
                policy.account_limit, policy.account_window_seconds * 1000,
                policy.origin_limit, policy.origin_window_seconds * 1000,
                policy.global_limit, policy.global_window_seconds * 1000,
            )
        except (RedisError, OSError, TimeoutError):
            raise LoginRateLimitUnavailableError("Autenticação temporariamente indisponível.") from None
        if (
            not isinstance(result, (list, tuple)) or len(result) != 2
            or any(type(value) is not int for value in result)
        ):
            raise LoginRateLimitUnavailableError("Autenticação temporariamente indisponível.")
        allowed, retry_after = result
        if allowed == 1 and retry_after == 0:
            return
        if allowed == 0 and 1 <= retry_after <= 86_400:
            raise LoginRateLimitExceededError(retry_after)
        raise LoginRateLimitUnavailableError("Autenticação temporariamente indisponível.")
