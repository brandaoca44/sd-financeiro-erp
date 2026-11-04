"""Validação compartilhada de dados de chave Pix."""
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, SecretStr, TypeAdapter, model_validator

from app.modules.identity.account_security import RegisterRequest
from app.modules.organizations.cnpj import normalize_cnpj


class PixDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    pix_type: Literal["CPF", "CNPJ", "EMAIL", "PHONE", "RANDOM"] | None = None
    pix_key: str | None = None

    @model_validator(mode="after")
    def validate_pix(self):
        if self.pix_type is None and self.pix_key is None:
            return self
        if not self.pix_type or not self.pix_key:
            raise ValueError("Informe o tipo e a chave Pix.")
        value = self.pix_key.strip()
        if len(value) > 254:
            raise ValueError("Chave Pix inválida.")
        if self.pix_type == "CPF":
            value = RegisterRequest.cpf_valid(SecretStr(value)).get_secret_value()
        elif self.pix_type == "CNPJ":
            value = normalize_cnpj(value)
        elif self.pix_type == "EMAIL":
            value = str(TypeAdapter(EmailStr).validate_python(value))
        elif self.pix_type == "PHONE":
            if re.fullmatch(r"\+[1-9][0-9]{7,14}", value) is None:
                raise ValueError("Informe o telefone com +, código do país e DDD.")
        else:
            try:
                value = str(UUID(value))
            except ValueError:
                raise ValueError("Chave aleatória inválida.") from None
        self.pix_key = value
        return self


def normalize_passport(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if re.fullmatch(r"[A-Z0-9]{6,20}", normalized) is None or not any(char.isdigit() for char in normalized):
        raise ValueError("Informe letras e números conforme o passaporte.")
    return normalized
