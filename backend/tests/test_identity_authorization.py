"""Testa políticas de acesso com permissões reais em PostgreSQL temporário."""

from itertools import product
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from database_support import DatabaseTestCase
from app.modules.identity.authorization import OrganizationAccessPolicy
from app.modules.identity.models import MembershipStatus, OrganizationMembership, User, UserStatus
from app.modules.organizations.models import Organization, OrganizationStatus


class OrganizationAccessPolicyTests(DatabaseTestCase):
    """Garante negação por padrão e concessões independentes por tenant."""

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.policy = OrganizationAccessPolicy(self.session)

    async def _user(self, *, active=True, provision=False):
        user = User(
            name="Pessoa de teste", email=f"{uuid4().hex}@example.invalid",
            status=UserStatus.ACTIVE if active else UserStatus.INACTIVE,
            can_provision_organizations=provision,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def _organization(self, *, status=OrganizationStatus.ACTIVE):
        organization = Organization(name="Tenant de teste", status=status)
        self.session.add(organization)
        await self.session.flush()
        return organization

    async def _membership(self, user, organization, *, active=True, read=True):
        membership = OrganizationMembership(
            user_id=user.id, organization_id=organization.id,
            status=MembershipStatus.ACTIVE if active else MembershipStatus.INACTIVE,
            can_read_organization=read,
        )
        self.session.add(membership)
        await self.session.flush()
        return membership

    async def test_provision_requires_active_user_and_explicit_grant(self):
        for active, provision in product((False, True), repeat=2):
            with self.subTest(active=active, provision=provision):
                user = await self._user(active=active, provision=provision)
                self.assertEqual(
                    await self.policy.can_provision_organizations(user.id), active and provision,
                )

    async def test_read_requires_all_three_conditions(self):
        for active_user, active_membership, read in product((False, True), repeat=3):
            with self.subTest(user=active_user, membership=active_membership, read=read):
                user = await self._user(active=active_user)
                organization = await self._organization()
                await self._membership(user, organization, active=active_membership, read=read)
                self.assertEqual(
                    await self.policy.can_read_organization(user.id, organization.id),
                    active_user and active_membership and read,
                )

    async def test_absent_or_invalid_identity_is_denied(self):
        organization = await self._organization()
        for user_id in (None, uuid4(), "identidade-nao-autenticada"):
            with self.subTest(user_id=user_id):
                self.assertFalse(await self.policy.can_provision_organizations(user_id))
                self.assertFalse(await self.policy.can_read_organization(user_id, organization.id))

    async def test_missing_membership_or_organization_is_denied(self):
        user = await self._user()
        organization = await self._organization()
        self.assertFalse(await self.policy.can_read_organization(user.id, organization.id))
        self.assertFalse(await self.policy.can_read_organization(user.id, uuid4()))
        self.assertFalse(await self.policy.can_read_organization(user.id, "uuid-invalido"))

    async def test_memberships_do_not_grant_access_to_other_tenants_or_users(self):
        first_user = await self._user()
        second_user = await self._user()
        first_tenant = await self._organization()
        second_tenant = await self._organization()
        await self._membership(first_user, first_tenant)
        await self._membership(second_user, second_tenant)
        self.assertTrue(await self.policy.can_read_organization(first_user.id, first_tenant.id))
        self.assertFalse(await self.policy.can_read_organization(first_user.id, second_tenant.id))
        self.assertFalse(await self.policy.can_read_organization(second_user.id, first_tenant.id))

    async def test_provisioning_does_not_grant_read_access(self):
        user = await self._user(provision=True)
        organization = await self._organization()
        self.assertTrue(await self.policy.can_provision_organizations(user.id))
        self.assertFalse(await self.policy.can_read_organization(user.id, organization.id))

    async def test_tenant_read_does_not_grant_provisioning(self):
        user = await self._user()
        organization = await self._organization()
        await self._membership(user, organization)
        self.assertTrue(await self.policy.can_read_organization(user.id, organization.id))
        self.assertFalse(await self.policy.can_provision_organizations(user.id))

    async def test_authorized_read_of_inactive_tenant_metadata_is_allowed(self):
        user = await self._user()
        organization = await self._organization(status=OrganizationStatus.INACTIVE)
        await self._membership(user, organization)
        self.assertTrue(await self.policy.can_read_organization(user.id, organization.id))

    async def test_committed_revocation_is_seen_despite_cached_orm_objects(self):
        user = await self._user(provision=True)
        organization = await self._organization()
        membership = await self._membership(user, organization)
        await self.session.commit()
        self.assertTrue(await self.policy.can_provision_organizations(user.id))
        self.assertTrue(await self.policy.can_read_organization(user.id, organization.id))
        async with AsyncSession(self.engine) as writer:
            async with writer.begin():
                await writer.execute(update(User).where(User.id == user.id).values(
                    can_provision_organizations=False,
                ))
                await writer.execute(update(OrganizationMembership).where(
                    OrganizationMembership.user_id == user.id,
                    OrganizationMembership.organization_id == organization.id,
                ).values(can_read_organization=False))
        self.assertTrue(user.can_provision_organizations)
        self.assertTrue(membership.can_read_organization)
        self.assertFalse(await self.policy.can_provision_organizations(user.id))
        self.assertFalse(await self.policy.can_read_organization(user.id, organization.id))

    async def test_policy_does_not_flush_or_commit_pending_grants(self):
        user = await self._user()
        organization = await self._organization()
        membership = await self._membership(user, organization, read=False)
        await self.session.commit()
        user.can_provision_organizations = True
        membership.can_read_organization = True
        self.session.autoflush = True
        self.assertFalse(await self.policy.can_provision_organizations(user.id))
        self.assertFalse(await self.policy.can_read_organization(user.id, organization.id))
        self.assertIn(user, self.session.dirty)
        self.assertIn(membership, self.session.dirty)
        await self.session.rollback()

    async def test_database_failure_propagates_without_granting_access(self):
        with patch.object(self.session, "scalar", side_effect=SQLAlchemyError("falha simulada")):
            with self.assertRaises(SQLAlchemyError):
                await self.policy.can_provision_organizations(uuid4())
            with self.assertRaises(SQLAlchemyError):
                await self.policy.can_read_organization(uuid4(), uuid4())
