"""Valida a persistência inicial de hierarquia sem ampliar permissões existentes."""

import asyncio
from uuid import uuid4

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError

from database_support import DatabaseTestCase
from app.modules.identity.access_models import (
    OrganizationOwnership, OrganizationRole, OrganizationRoleAssignment,
    RoleAssignmentStatus, RoleCategory, RoleStatus,
)
from app.modules.identity.authorization import OrganizationAccessPolicy
from app.modules.identity.models import MembershipStatus, OrganizationMembership, User, UserStatus
from app.modules.organizations.models import Organization


class AccessModelsTests(DatabaseTestCase):
    async def _tenant(self):
        user = User(name="Pessoa de teste", email=uuid4().hex + "@example.com", status=UserStatus.ACTIVE)
        organization = Organization(name="Organização de teste")
        self.session.add_all([user, organization])
        await self.session.flush()
        membership = OrganizationMembership(
            user_id=user.id, organization_id=organization.id, status=MembershipStatus.ACTIVE,
        )
        self.session.add(membership)
        await self.session.flush()
        return user, organization

    async def _role(self, organization, *, name="Auxiliar de Cadastro", **kwargs):
        role = OrganizationRole(organization_id=organization.id, name=name, **kwargs)
        self.session.add(role)
        await self.session.flush()
        return role

    async def test_defaults_are_inactive_custom_and_timezone_aware(self):
        user, organization = await self._tenant()
        role = await self._role(organization)
        assignment = OrganizationRoleAssignment(organization_id=organization.id, user_id=user.id, role_id=role.id)
        self.session.add(assignment)
        await self.session.flush()
        self.assertEqual(role.category, RoleCategory.CUSTOM)
        self.assertEqual(role.status, RoleStatus.INACTIVE)
        self.assertEqual(assignment.status, RoleAssignmentStatus.INACTIVE)
        self.assertIsNotNone(role.created_at.tzinfo)
        self.assertIsNotNone(assignment.created_at.tzinfo)

    async def test_database_defaults_are_also_restrictive(self):
        user, organization = await self._tenant()
        role_id = uuid4()
        row = (await self.session.execute(text(
            "INSERT INTO organization_roles (id, organization_id, name) VALUES (:id, :org, :name) "
            "RETURNING category, status"
        ), dict(id=role_id, org=organization.id, name="Perfil SQL"))).one()
        self.assertEqual(tuple(row), ("CUSTOM", "INACTIVE"))
        status = await self.session.scalar(text(
            "INSERT INTO organization_role_assignments (organization_id, user_id, role_id) "
            "VALUES (:org, :user, :role) RETURNING status"
        ), dict(org=organization.id, user=user.id, role=role_id))
        self.assertEqual(status, "INACTIVE")

    async def test_profile_name_is_unique_ignoring_case_only_within_tenant(self):
        _, first = await self._tenant()
        _, second = await self._tenant()
        await self._role(first, name="Analista Fiscal")
        await self._role(second, name="Analista Fiscal")
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                await self._role(first, name="ANALISTA FISCAL")

    async def test_rejects_blank_and_untrimmed_profile_names(self):
        _, organization = await self._tenant()
        for name in ("", "   ", " Perfil "):
            with self.subTest(name=name), self.assertRaises(IntegrityError):
                async with self.session.begin_nested():
                    await self._role(organization, name=name)

    async def test_owner_requires_membership_in_the_exact_tenant(self):
        user, first = await self._tenant()
        _, second = await self._tenant()
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                self.session.add(OrganizationOwnership(organization_id=second.id, user_id=user.id))
                await self.session.flush()
        owner = OrganizationOwnership(organization_id=first.id, user_id=user.id)
        self.session.add(owner)
        await self.session.flush()
        self.assertIsNotNone(owner.created_at.tzinfo)

    async def test_organization_cannot_have_two_owners(self):
        first_user, organization = await self._tenant()
        second_user = User(name="Outra pessoa", email=uuid4().hex + "@example.com")
        self.session.add(second_user)
        await self.session.flush()
        self.session.add(OrganizationMembership(user_id=second_user.id, organization_id=organization.id))
        await self.session.flush()
        self.session.add(OrganizationOwnership(organization_id=organization.id, user_id=first_user.id))
        await self.session.flush()
        self.session.expunge_all()
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                self.session.add(OrganizationOwnership(organization_id=organization.id, user_id=second_user.id))
                await self.session.flush()

    async def test_assignments_reject_foreign_profile_and_foreign_membership(self):
        first_user, first = await self._tenant()
        second_user, second = await self._tenant()
        role = await self._role(first)
        for organization_id, user_id, role_id in (
            (second.id, second_user.id, role.id),
            (first.id, second_user.id, role.id),
            (first.id, first_user.id, uuid4()),
        ):
            with self.subTest(org=organization_id), self.assertRaises(IntegrityError):
                async with self.session.begin_nested():
                    self.session.add(OrganizationRoleAssignment(
                        organization_id=organization_id, user_id=user_id, role_id=role_id,
                    ))
                    await self.session.flush()

    async def test_same_assignment_cannot_be_duplicated(self):
        user, organization = await self._tenant()
        role = await self._role(organization)
        self.session.add(OrganizationRoleAssignment(organization_id=organization.id, user_id=user.id, role_id=role.id))
        await self.session.flush()
        self.session.expunge_all()
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                self.session.add(OrganizationRoleAssignment(organization_id=organization.id, user_id=user.id, role_id=role.id))
                await self.session.flush()

    async def test_linked_profile_membership_and_organization_cannot_be_deleted(self):
        user, organization = await self._tenant()
        role = await self._role(organization)
        self.session.add_all([
            OrganizationOwnership(organization_id=organization.id, user_id=user.id),
            OrganizationRoleAssignment(organization_id=organization.id, user_id=user.id, role_id=role.id),
        ])
        other = Organization(name="Outro tenant para verificar a FK composta")
        self.session.add(other)
        await self.session.flush()
        for statement in (
            delete(OrganizationRole).where(OrganizationRole.id == role.id),
            delete(OrganizationMembership).where(OrganizationMembership.user_id == user.id),
            delete(Organization).where(Organization.id == organization.id),
            update(OrganizationRole).where(OrganizationRole.id == role.id).values(organization_id=other.id),
        ):
            with self.assertRaises(IntegrityError):
                async with self.session.begin_nested():
                    await self.session.execute(statement)

    async def test_owner_and_ceo_category_do_not_bypass_existing_authorization(self):
        user, organization = await self._tenant()
        role = await self._role(organization, name="Direção", category=RoleCategory.CEO, status=RoleStatus.ACTIVE)
        self.session.add_all([
            OrganizationOwnership(organization_id=organization.id, user_id=user.id),
            OrganizationRoleAssignment(organization_id=organization.id, user_id=user.id, role_id=role.id,
                                       status=RoleAssignmentStatus.ACTIVE),
        ])
        await self.session.flush()
        policy = OrganizationAccessPolicy(self.session)
        self.assertFalse(await policy.can_provision_organizations(user.id))
        self.assertFalse(await policy.can_read_organization(user.id, organization.id))
        self.assertFalse(await policy.can_read_organization(user.id, uuid4()))

    async def test_all_categories_can_be_persisted_without_numeric_rank(self):
        _, organization = await self._tenant()
        for category in RoleCategory:
            role = await self._role(organization, name=category.value, category=category)
            self.assertEqual(role.category, category)
            self.assertEqual(role.status, RoleStatus.INACTIVE)

    async def test_migration_round_trip_preserves_previous_identity_and_does_not_seed_grants(self):
        user, organization = await self._tenant()
        user_id, organization_id = user.id, organization.id
        role = await self._role(organization)
        self.session.add_all([
            OrganizationOwnership(organization_id=organization_id, user_id=user_id),
            OrganizationRoleAssignment(organization_id=organization_id, user_id=user_id, role_id=role.id),
        ])
        await self.session.commit()
        await self.session.close()
        await self.engine.dispose()
        try:
            await asyncio.to_thread(self.run_migration, "downgrade", "c418d69a02be")
            self.assertIsNotNone(await self.session.get(User, user_id))
            self.assertIsNotNone(await self.session.get(Organization, organization_id))
            self.assertIsNotNone(await self.session.get(OrganizationMembership, (user_id, organization_id)))
            enum_count = await self.session.scalar(text(
                "SELECT count(*) FROM pg_type WHERE typname IN "
                "('organization_role_category', 'organization_role_status', 'organization_role_assignment_status')"
            ))
            self.assertEqual(enum_count, 0)
        finally:
            await self.session.close()
            await self.engine.dispose()
            await asyncio.to_thread(self.run_migration, "upgrade", "head")
        for model in (OrganizationOwnership, OrganizationRole, OrganizationRoleAssignment):
            self.assertEqual(await self.session.scalar(select(func.count()).select_from(model)), 0)
        self.assertFalse(await OrganizationAccessPolicy(self.session).can_provision_organizations(user_id))
        await self.session.close()
        await asyncio.to_thread(self.run_migration, "check")
