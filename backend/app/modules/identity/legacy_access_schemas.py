"""Revisão e conversão explícita da concessão antiga, sem privilégios no payload."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.identity.invitation_schemas import ConfirmPassword
from app.modules.identity.models import MembershipStatus, UserStatus


class LegacyReadRevokeRequest(ConfirmPassword):
    expected_revision: int = Field(ge=1, strict=True)


class LegacyReadConvertRequest(LegacyReadRevokeRequest):
    role_id: UUID
    expected_role_revision: int = Field(ge=1, strict=True)
    expected_assignment_revision: int = Field(ge=0, strict=True)


class ReadAccessReview(BaseModel):
    user_id: UUID
    revision: int
    membership_status: MembershipStatus
    user_status: UserStatus
    legacy_read: bool
    legacy_effective: bool
    profile_read: bool
    effective_read: bool


class LegacyReadConversionResponse(ReadAccessReview):
    role_id: UUID
    assignment_revision: int
