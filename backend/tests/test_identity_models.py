"""Valida identidade e integridade relacional em PostgreSQL temporário exclusivo."""

import asyncio
from uuid import uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from database_support import DatabaseTestCase
from app.modules.identity.models import MembershipStatus, OrganizationMembership, User, UserStatus
from app.modules.organizations.models import Organization


class IdentityModelsTests(DatabaseTestCase):
    """Verifica defaults restritivos, unicidade e chaves estrangeiras."""

    async def _user_and_organization(self):
        user = User(name="Pessoa de teste", email=f"{uuid4().hex}@example.invalid")
        organization = Organization(name="Tenant de teste")
        self.session.add_all([user, organization])
        await self.session.flush()
        return user, organization

    async def test_user_and_membership_start_without_privileges(self):
        user, organization = await self._user_and_organization()
        membership = OrganizationMembership(user_id=user.id, organization_id=organization.id)
        self.session.add(membership)
        await self.session.flush()
        self.assertEqual(user.status, UserStatus.INACTIVE)
        self.assertFalse(user.can_provision_organizations)
        self.assertEqual(membership.status, MembershipStatus.INACTIVE)
        self.assertFalse(membership.can_read_organization)
        self.assertIsNotNone(user.created_at.tzinfo)
        self.assertIsNotNone(membership.created_at.tzinfo)

    async def test_server_defaults_deny_privileges_without_orm(self):
        user_id = uuid4()
        row = (await self.session.execute(text(
            "INSERT INTO users (id, name, email) VALUES (:id, :name, :email) "
            "RETURNING status, can_provision_organizations"
        ), dict(id=user_id, name="Usuário SQL", email=f"{user_id.hex}@example.invalid"))).one()
        self.assertEqual(tuple(row), ("INACTIVE", False))
        organization = Organization(name="Tenant SQL")
        self.session.add(organization)
        await self.session.flush()
        row = (await self.session.execute(text(
            "INSERT INTO organization_memberships (user_id, organization_id) "
            "VALUES (:user_id, :organization_id) RETURNING status, can_read_organization"
        ), dict(user_id=user_id, organization_id=organization.id))).one()
        self.assertEqual(tuple(row), ("INACTIVE", False))

    async def test_email_is_unique_ignoring_case(self):
        user, _ = await self._user_and_organization()
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                self.session.add(User(name="Duplicado", email=user.email.upper()))
                await self.session.flush()

    async def test_rejects_blank_name_and_untrimmed_email(self):
        for name, email in (
            ("   ", "pessoa@example.invalid"),
            ("Pessoa", " pessoa@example.invalid "),
            ("Pessoa", ""),
        ):
            with self.subTest(name=name, email=email), self.assertRaises(IntegrityError):
                async with self.session.begin_nested():
                    self.session.add(User(name=name, email=email))
                    await self.session.flush()

    async def test_membership_requires_existing_user_and_organization(self):
        user, organization = await self._user_and_organization()
        for user_id, organization_id in ((uuid4(), organization.id), (user.id, uuid4())):
            with self.subTest(user_id=user_id), self.assertRaises(IntegrityError):
                async with self.session.begin_nested():
                    self.session.add(OrganizationMembership(
                        user_id=user_id, organization_id=organization_id,
                    ))
                    await self.session.flush()

    async def test_membership_is_unique_and_scoped_to_each_organization(self):
        user, organization = await self._user_and_organization()
        second = Organization(name="Segundo tenant")
        self.session.add(second)
        await self.session.flush()
        self.session.add_all([
            OrganizationMembership(
                user_id=user.id, organization_id=organization.id,
                status=MembershipStatus.ACTIVE, can_read_organization=True,
            ),
            OrganizationMembership(user_id=user.id, organization_id=second.id),
        ])
        await self.session.flush()
        self.session.expunge_all()
        memberships = (await self.session.scalars(select(OrganizationMembership).where(
            OrganizationMembership.user_id == user.id
        ))).all()
        grants = {m.organization_id: m.can_read_organization for m in memberships}
        self.assertEqual(grants, {organization.id: True, second.id: False})
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                # SQL direto evita colisão de identidade no cache do ORM.
                await self.session.execute(text(
                    "INSERT INTO organization_memberships (user_id, organization_id) "
                    "VALUES (:user_id, :organization_id)"
                ), dict(user_id=user.id, organization_id=organization.id))

    async def test_restricts_deletion_of_linked_entities(self):
        user, organization = await self._user_and_organization()
        self.session.add(OrganizationMembership(user_id=user.id, organization_id=organization.id))
        await self.session.flush()
        for statement in (delete(User).where(User.id == user.id),
                          delete(Organization).where(Organization.id == organization.id)):
            with self.assertRaises(IntegrityError):
                async with self.session.begin_nested():
                    await self.session.execute(statement)

    async def test_migration_round_trip_preserves_organization_and_removes_identity_enums(self):
        organization = Organization(name="Preservada no downgrade de identidade")
        self.session.add(organization)
        await self.session.commit()
        organization_id = organization.id
        await self.session.close()
        await self.engine.dispose()
        try:
            await asyncio.to_thread(self.run_migration, "downgrade", "ed92b41e1e71")
            tables = (await self.session.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ))).scalars().all()
            self.assertIn("organizations", tables)
            self.assertNotIn("users", tables)
            self.assertNotIn("organization_memberships", tables)
            enum_count = await self.session.scalar(text(
                "SELECT count(*) FROM pg_type WHERE typname IN ('user_status', 'membership_status')"
            ))
            self.assertEqual(enum_count, 0)
            self.assertIsNotNone(await self.session.get(Organization, organization_id))
        finally:
            await self.session.close()
            await self.engine.dispose()
            await asyncio.to_thread(self.run_migration, "upgrade", "head")
        await asyncio.to_thread(self.run_migration, "check")
