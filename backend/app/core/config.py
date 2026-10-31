from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    return Settings()
