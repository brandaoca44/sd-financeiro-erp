from functools import lru_cache
import os
from pathlib import Path
import re
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from cryptography.fernet import Fernet


class Settings(BaseSettings):
    """Centraliza e valida as configurações utilizadas pela aplicação."""

    app_name: str = Field(default="SD Financeiro ERP API")
    app_version: str = Field(default="0.1.0")
    app_environment: Literal[
        "development",
        "test",
        "staging",
        "production",
    ] = Field(default="development")
    app_debug: bool = Field(default=False)

    api_v1_prefix: str = Field(default="/api/v1")

    database_host: str = Field(default="127.0.0.1")
    database_port: int = Field(default=5433, ge=1, le=65535)
    database_name: str = Field(default="sd_financeiro")
    database_user: str = Field(default="sd_admin")
    database_password: SecretStr
    database_echo: bool = Field(default=False)

    redis_host: str = "127.0.0.1"
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_db: int = Field(default=0, ge=0, le=15)
    redis_username: str | None = None
    redis_password: SecretStr | None = None
    auth_rate_limit_key: SecretStr | None = Field(default=None, repr=False)
    auth_idle_timeout_seconds: int = Field(default=1800, ge=1, le=86400)
    auth_mfa_encryption_key: SecretStr | None = Field(default=None, repr=False)
    auth_identity_encryption_key: SecretStr | None = Field(default=None, repr=False)
    auth_hash_concurrency: int = Field(default=2, ge=1, le=16)
    auth_account_limit: int = Field(default=5, ge=1, le=1000000)
    auth_account_window_seconds: int = Field(default=900, ge=1, le=86400)
    auth_origin_limit: int = Field(default=30, ge=1, le=1000000)
    auth_origin_window_seconds: int = Field(default=60, ge=1, le=86400)
    auth_global_limit: int = Field(default=300, ge=1, le=1000000)
    auth_global_window_seconds: int = Field(default=60, ge=1, le=86400)

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_api_prefix(cls, value):
        if not re.fullmatch(r"/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", value):
            raise ValueError("Prefixo da API inválido.")
        return value

    @model_validator(mode="after")
    def validate_operational_security(self):
        if self.auth_identity_encryption_key is not None:
            try:
                Fernet(self.auth_identity_encryption_key.get_secret_value().encode("ascii"))
            except (ValueError, UnicodeError):
                raise ValueError("Configure uma chave Fernet válida para identidade.") from None
            if any(secret and secret.get_secret_value() == self.auth_identity_encryption_key.get_secret_value()
                   for secret in (self.auth_mfa_encryption_key, self.auth_rate_limit_key, self.database_password, self.redis_password)):
                raise ValueError("A chave de identidade deve ser exclusiva.")
        if self.auth_mfa_encryption_key is not None:
            try:
                Fernet(self.auth_mfa_encryption_key.get_secret_value().encode("ascii"))
            except (ValueError, UnicodeError):
                raise ValueError("Configure uma chave Fernet válida para MFA.") from None
            if any(secret and secret.get_secret_value() == self.auth_mfa_encryption_key.get_secret_value()
                   for secret in (self.auth_rate_limit_key, self.database_password, self.redis_password)):
                raise ValueError("A chave de MFA deve ser exclusiva.")
        if self.database_echo:
            raise ValueError("SQL echo deve permanecer desativado.")
        if not self.database_password.get_secret_value().strip():
            raise ValueError("Credencial de banco ausente.")
        if self.app_environment in ("staging", "production"):
            if self.app_debug:
                raise ValueError("Debug não é permitido neste ambiente.")
            secrets_to_check = (self.database_password, self.redis_password, self.auth_rate_limit_key)
            for secret in secrets_to_check:
                value = secret.get_secret_value() if secret else ""
                if (len(value.encode("utf-8")) < 32 or len(set(value)) < 2
                        or value.lower().startswith(("change_me", "changeme", "example", "your_secret"))):
                    raise ValueError("Configure segredos distintos e fortes para banco, Redis e autenticação.")
            if len({secret.get_secret_value() for secret in secrets_to_check}) != 3:
                raise ValueError("Os segredos de banco, Redis e autenticação devem ser distintos.")
        return self

    @field_validator("auth_rate_limit_key", mode="before")
    @classmethod
    def validate_auth_key(cls, value):
        """Permite health check sem chave, mas nunca uma autenticação sem segredo."""

        if value is None or value == "":
            return None
        secret = value if isinstance(value, SecretStr) else SecretStr(value)
        if len(secret.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("A chave de autenticação deve ter pelo menos 32 bytes.")
        return secret

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        hide_input_in_errors=True,
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        """Monta a URL de conexão com PostgreSQL usando o driver Psycopg."""

        user = quote_plus(self.database_user)
        password = quote_plus(self.database_password.get_secret_value())
        database = quote_plus(self.database_name)

        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.database_host}:{self.database_port}/{database}"
        )


@lru_cache
def get_settings() -> Settings:
    """Retorna uma única instância das configurações durante a execução."""

    external = os.environ.get("APP_ENVIRONMENT", "development")
    settings = Settings(_env_file=None) if external in ("staging", "production") else Settings()
    if settings.app_environment in ("staging", "production") and external not in ("staging", "production"):
        raise ValueError("Defina o ambiente operacional externamente, sem depender do arquivo .env.")
    return settings
