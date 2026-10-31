"""Testes opt-in em banco temporário exclusivo no PostgreSQL local do ERP."""

from uuid import UUID, uuid4
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession

from database_support import DatabaseTestCase
from app.modules.organizations.models import OrganizationStatus
from app.modules.organizations.repository import OrganizationRepository
from app.modules.organizations.schemas import OrganizationCreate, OrganizationResponse
from app.modules.organizations.service import OrganizationService


class OrganizationRepositoryTests(DatabaseTestCase):
    """Aplica migrations no banco temporário e o remove ao concluir a suíte."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.repository = OrganizationRepository(self.session)

    async def test_create_returns_generated_fields(self):
        organization = await self.repository.create(name="Empresa de teste")
        self.assertIsInstance(organization.id, UUID)
        self.assertEqual(organization.status, OrganizationStatus.ACTIVE)
        self.assertIsNotNone(organization.created_at.tzinfo)
        self.assertIsNotNone(organization.updated_at.tzinfo)
        response = OrganizationResponse.model_validate(organization)
        self.assertEqual(response.name, "Empresa de teste")

    async def test_commit_by_caller_persists_for_another_session(self):
        organization = await self.repository.create(name="Organização persistida")
        await self.session.commit()
        async with AsyncSession(self.engine) as reader:
            found = await OrganizationRepository(reader).get_by_id(organization.id)
            self.assertIsNotNone(found)
            self.assertEqual(found.name, "Organização persistida")

    async def test_create_does_not_commit_and_can_be_rolled_back(self):
        organization = await self.repository.create(name="Organização temporária")
        organization_id = organization.id
        async with AsyncSession(self.engine) as reader:
            self.assertIsNone(
                await OrganizationRepository(reader).get_by_id(organization_id)
            )
        await self.session.rollback()
        self.assertIsNone(await self.repository.get_by_id(organization_id))

    async def test_get_by_id_returns_only_requested_organization(self):
        first = await self.repository.create(name="Primeira")
        second = await self.repository.create(name="Segunda")
        self.session.expunge_all()
        found = await self.repository.get_by_id(first.id)
        self.assertEqual(found.id, first.id)
        self.assertEqual(found.name, "Primeira")
        self.assertNotEqual(found.id, second.id)

    async def test_get_by_id_returns_none_when_missing(self):
        self.assertIsNone(await self.repository.get_by_id(uuid4()))

    async def test_service_create_commits_and_returns_response(self):
        response = await OrganizationService(self.session).create(
            OrganizationCreate(name="  Empresa do service  ")
        )
        self.assertIsInstance(response, OrganizationResponse)
        self.assertEqual(response.name, "Empresa do service")
        self.assertEqual(response.status, OrganizationStatus.ACTIVE)
        async with AsyncSession(self.engine) as reader:
            found = await OrganizationService(reader).get_by_id(response.id)
            self.assertEqual(found, response)

    async def test_service_missing_organization_returns_none(self):
        self.assertIsNone(await OrganizationService(self.session).get_by_id(uuid4()))

    async def test_service_rolls_back_when_response_conversion_fails(self):
        from pydantic import ValidationError

        created_ids = []
        original_create = OrganizationRepository.create

        async def create_invalid_response(repository, *, name):
            organization = await original_create(repository, name=name)
            created_ids.append(organization.id)
            organization.created_at = None
            return organization

        with patch.object(OrganizationRepository, "create", create_invalid_response):
            with self.assertRaises(ValidationError):
                await OrganizationService(self.session).create(OrganizationCreate(name="Reverter"))
        async with AsyncSession(self.engine) as reader:
            self.assertIsNone(
                await OrganizationRepository(reader).get_by_id(created_ids[0])
            )
        self.assertFalse(self.session.in_transaction())

    async def test_service_propagates_persistence_failure_and_releases_transaction(self):
        from sqlalchemy.exc import SQLAlchemyError

        with patch.object(OrganizationRepository, "create", side_effect=SQLAlchemyError("falha simulada")):
            with self.assertRaises(SQLAlchemyError):
                await OrganizationService(self.session).create(OrganizationCreate(name="Reverter"))
        self.assertFalse(self.session.in_transaction())
        response = await OrganizationService(self.session).create(OrganizationCreate(name="Recuperada"))
        self.assertEqual(response.name, "Recuperada")
