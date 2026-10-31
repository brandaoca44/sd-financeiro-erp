"""Define os contratos de criação e resposta de organizações."""

from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints

from app.modules.organizations.models import OrganizationStatus


class OrganizationCreate(BaseModel):
    """Recebe apenas o nome da organização; demais campos pertencem ao sistema."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=150),
    ]


class OrganizationResponse(BaseModel):
    """Expõe os dados públicos da organização a partir de atributos ORM."""

    model_config = ConfigDict(from_attributes=True, hide_input_in_errors=True)

    id: UUID
    name: str
    status: OrganizationStatus
    created_at: AwareDatetime
    updated_at: AwareDatetime
