"""Contratos mínimos para o ciclo de vida do vínculo, sem privilégios no payload."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.identity.invitation_schemas import ConfirmPassword
from app.modules.identity.models import MembershipStatus


class MembershipStatusRequest(ConfirmPassword):
    status: MembershipStatus
    expected_revision: int = Field(ge=1, strict=True)


class MembershipStatusResponse(BaseModel):
    user_id: UUID
    status: MembershipStatus
    revision: int
