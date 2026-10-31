"""Contratos de perfis sem campos de plataforma ou escopos implícitos."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.modules.identity.access_models import RoleAssignmentStatus, RoleCategory, RoleStatus
from app.modules.identity.invitation_schemas import ConfirmPassword
from app.modules.identity.permissions import PermissionKey, ROLE_PERMISSIONS

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class PermissionList(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    permissions: list[PermissionKey] = Field(default_factory=list, max_length=16)

    @field_validator("permissions")
    @classmethod
    def restrict_permissions(cls, value):
        if len(set(value)) != len(value) or not set(value) <= ROLE_PERMISSIONS:
            raise ValueError("Concessão de permissão inválida.")
        return sorted(value)


class RoleCreateRequest(ConfirmPassword, PermissionList):
    name: Name
    category: RoleCategory = RoleCategory.CUSTOM
    status: RoleStatus = RoleStatus.INACTIVE


class RoleUpdateRequest(RoleCreateRequest):
    expected_revision: int = Field(ge=1, strict=True)


class RoleResponse(PermissionList):
    id: UUID
    name: str
    category: RoleCategory
    status: RoleStatus
    revision: int


class AssignmentRequest(ConfirmPassword):
    status: RoleAssignmentStatus
    expected_revision: int = Field(ge=0, strict=True)
    expected_role_revision: int = Field(ge=1, strict=True)


class AssignmentResponse(BaseModel):
    user_id: UUID
    role_id: UUID
    status: RoleAssignmentStatus
    revision: int


class DelegationRequest(ConfirmPassword, PermissionList):
    status: RoleAssignmentStatus
    expected_revision: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def require_ceiling(self):
        if self.status == RoleAssignmentStatus.ACTIVE and not self.permissions:
            raise ValueError("Delegação ativa exige teto explícito.")
        return self


class DelegationResponse(PermissionList):
    user_id: UUID
    status: RoleAssignmentStatus
    revision: int
    effective: bool


class RolePage(BaseModel):
    items: list[RoleResponse]
    next_cursor: UUID | None


class AssignmentPage(BaseModel):
    items: list[AssignmentResponse]
    next_cursor: UUID | None


class MemberResponse(BaseModel):
    user_id: UUID
    name: str
    email: str
    status: str
    legacy_read: bool
    revision: int


class MemberPage(BaseModel):
    items: list[MemberResponse]
    next_cursor: UUID | None
