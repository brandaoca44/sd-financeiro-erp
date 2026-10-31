"""Contratos empresariais sem CPF, alteração de tenant ou mudança de CNPJ na edição."""

from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, field_validator

from app.modules.identity.invitation_schemas import ConfirmPassword
from app.modules.organizations.cnpj import normalize_cnpj
from app.modules.organizations.models import CompanyStatus

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
CNPJ = Annotated[str, BeforeValidator(normalize_cnpj), Field(min_length=14, max_length=14)]


class CompanyNames(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    legal_name: Name
    trade_name: Name | None = None

    @field_validator("trade_name", mode="before")
    @classmethod
    def blank_trade_name(cls, value):
        return None if isinstance(value, str) and not value.strip() else value


class CompanyCreate(ConfirmPassword, CompanyNames):
    tax_id: CNPJ


class CompanyUpdate(ConfirmPassword, CompanyNames):
    status: CompanyStatus
    expected_revision: int = Field(ge=1, strict=True)


class CompanyResponse(CompanyNames):
    model_config = ConfigDict(from_attributes=True, hide_input_in_errors=True)
    id: UUID
    organization_id: UUID
    tax_id: CNPJ
    status: CompanyStatus
    revision: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class CompanyPage(BaseModel):
    items: list[CompanyResponse]
    next_cursor: UUID | None
