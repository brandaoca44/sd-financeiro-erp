"""Implementa o acesso aos dados de organizações."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization


class OrganizationRepository:
    """Persiste organizações sem controlar transações ou autorizações."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, name: str) -> Organization:
        """Insere a organização e obtém os valores gerados, sem realizar commit."""

        organization = Organization(name=name)
        self._session.add(organization)
        await self._session.flush()
        return organization

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        """Busca pelo UUID; o chamador deve autorizar o contexto organizacional."""

        return await self._session.get(Organization, organization_id)
