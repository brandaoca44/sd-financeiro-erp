"""Entradas de onboarding/convites sem campos de promoção ou identidade do autor."""

import re
from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field, SecretStr, StringConstraints, field_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class SecureInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ConfirmPassword(SecureInput):
    password: SecretStr = Field(min_length=1, max_length=128)


class InviteOwnerRequest(ConfirmPassword):
    email: EmailStr = Field(max_length=254)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class OnboardingRequest(InviteOwnerRequest):
    organization_name: Name


class InviteMemberRequest(InviteOwnerRequest):
    can_read_organization: bool = Field(default=False, strict=True)


class AcceptInvitationRequest(SecureInput):
    token: SecretStr = Field(min_length=43, max_length=43)
    password: SecretStr = Field(min_length=8, max_length=128)
    name: Name | None = None

    @field_validator("token")
    @classmethod
    def validate_token(cls, value):
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", value.get_secret_value()) is None:
            raise ValueError("Convite inválido.")
        return value


class InvitationResponse(BaseModel):
    organization_id: UUID
    invitation_id: UUID
    invitation_token: str = Field(repr=False)
    expires_at: AwareDatetime
