"""Entrada de concessão de leitura sem campo para privilégios ou escopo curinga."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.identity.invitation_schemas import ConfirmPassword
from app.modules.identity.models import MembershipStatus
from app.modules.identity.permissions import FinancialPermissionKey


class CompanyReadGrantRequest(ConfirmPassword):
    status: MembershipStatus
    expected_revision: int = Field(ge=0, strict=True)
    expected_company_revision: int = Field(ge=1, strict=True)
    expected_membership_revision: int = Field(ge=1, strict=True)


class CompanyReadGrantResponse(BaseModel):
    company_id: UUID
    user_id: UUID
    permission_key: Literal["companies.read"] = "companies.read"
    status: MembershipStatus
    revision: int
    company_revision: int
    membership_revision: int
    effective: bool


class CompanyFinancialGrantResponse(BaseModel):
    company_id: UUID
    user_id: UUID
    permission_key: FinancialPermissionKey
    status: MembershipStatus
    revision: int
    company_revision: int
    membership_revision: int
    effective: bool


class CompanyFinancialGrantRequest(CompanyReadGrantRequest):
    """Status e revisões; a chave financeira vem exclusivamente da rota fechada."""
