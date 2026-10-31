"""Coordena os casos de uso iniciais de organizações."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import OrganizationCreate, OrganizationResponse


class OrganizationService:
    """Coordena persistência e contratos, sem decisões HTTP ou autorização."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repository = OrganizationRepository(session)

    async def create(self, data: OrganizationCreate) -> OrganizationResponse:
        """Cria e confirma a organização; reverte a transação se houver falha.

        A sessão recebida não deve ter uma transação já iniciada pelo chamador.
        """

        async with self._session.begin():
            organization = await self._repository.create(name=data.name)
            response = OrganizationResponse.model_validate(organization)
        return response

    async def get_by_id(self, organization_id: UUID) -> OrganizationResponse | None:
        """Consulta uma organização em contexto previamente autorizado pelo chamador."""

        organization = await self._repository.get_by_id(organization_id)
        if organization is None:
            return None
        return OrganizationResponse.model_validate(organization)
