"""Valida autoridade, reautenticação, atomicidade e concorrência de propriedade."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database_support import DatabaseTestCase
from app.modules.identity.access_models import OrganizationOwnership, OwnershipChange
from app.modules.identity.models import (
    MembershipStatus, OrganizationMembership, User, UserPasswordCredential, UserSession, UserStatus,
)
from app.modules.identity.ownership import OrganizationOwnershipService, OwnershipChangeDeniedError
from app.modules.identity.passwords import hash_password
from app.modules.identity.sessions import SessionService
from app.modules.organizations.models import Organization, OrganizationStatus


class OwnershipTests(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.password = SecretStr("Senha de teste @123")
        hashed = (await hash_password(self.password)).get_secret_value()
        self.operator = User(name="Operador", email=uuid4().hex + "@example.com",
                             status=UserStatus.ACTIVE, can_provision_organizations=True)
        self.first = User(name="Primeiro", email=uuid4().hex + "@example.com", status=UserStatus.ACTIVE)
        self.second = User(name="Segundo", email=uuid4().hex + "@example.com", status=UserStatus.ACTIVE)
        self.org = Organization(name="Empresa de teste")
        self.session.add_all([self.operator, self.first, self.second, self.org])
        await self.session.flush()
        for user in (self.operator, self.first, self.second):
            self.session.add(UserPasswordCredential(user_id=user.id, password_hash=hashed))
        for user in (self.first, self.second):
            self.session.add(OrganizationMembership(user_id=user.id, organization_id=self.org.id,
                                                    status=MembershipStatus.ACTIVE))
        await self.session.commit()
        self.tokens = {}
        for user in (self.operator, self.first, self.second):
            self.tokens[user.id] = (await SessionService(self.session).issue_for_authenticated_user(user.id)).token

    async def _change(self, actor=None, target=None, *, initial=False, password=None, organization_id=None):
        async with AsyncSession(self.engine, expire_on_commit=False) as writer:
            method = OrganizationOwnershipService(writer).designate if initial else OrganizationOwnershipService(writer).transfer
            await method(organization_id=organization_id or self.org.id,
                         new_owner_id=target or self.second.id, token=self.tokens[actor or self.first.id],
                         password=password or self.password)

    async def _designate(self):
        await self._change(self.operator.id, self.first.id, initial=True)

    async def _owner(self):
        async with AsyncSession(self.engine) as reader:
            return await reader.scalar(select(OrganizationOwnership.user_id).where(
                OrganizationOwnership.organization_id == self.org.id))

    async def test_designation_and_transfer_record_exact_history_without_implicit_grants(self):
        await self._designate()
        await self._change()
        self.assertEqual(await self._owner(), self.second.id)
        rows = (await self.session.scalars(select(OwnershipChange).where(
            OwnershipChange.organization_id == self.org.id).order_by(OwnershipChange.created_at))).all()
        self.assertEqual([(r.actor_user_id, r.previous_user_id, r.new_user_id) for r in rows],
                         [(self.operator.id, None, self.first.id), (self.first.id, self.first.id, self.second.id)])
        self.assertFalse((await self.session.get(OrganizationMembership, (self.second.id, self.org.id))).can_read_organization)
        self.assertFalse(self.second.can_provision_organizations)

    async def test_only_provisioner_can_designate_and_cannot_replace_existing_owner(self):
        with self.assertRaises(OwnershipChangeDeniedError):
            await self._change(initial=True)
        await self._designate()
        with self.assertRaises(OwnershipChangeDeniedError):
            await self._change(self.operator.id, initial=True)
        with self.assertRaises(OwnershipChangeDeniedError):
            await self._change(self.operator.id)
        self.assertEqual(await self._owner(), self.first.id)

    async def test_non_owner_previous_owner_and_self_transfer_are_denied(self):
        await self._designate()
        for actor, target in ((self.second.id, self.first.id), (self.first.id, self.first.id)):
            with self.assertRaises(OwnershipChangeDeniedError):
                await self._change(actor, target)
        await self._change()
        with self.assertRaises(OwnershipChangeDeniedError):
            await self._change()

    async def test_wrong_password_does_not_change_owner_or_history(self):
        await self._designate()
        with self.assertRaises(OwnershipChangeDeniedError):
            await self._change(password=SecretStr("incorreta"))
        self.assertEqual(await self._owner(), self.first.id)
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(OwnershipChange).where(
            OwnershipChange.organization_id == self.org.id)), 1)

    async def test_inactive_actor_target_and_memberships_are_denied(self):
        await self._designate()
        for model, criteria, field, inactive, active in (
            (User, User.id == self.first.id, "status", UserStatus.INACTIVE, UserStatus.ACTIVE),
            (User, User.id == self.second.id, "status", UserStatus.INACTIVE, UserStatus.ACTIVE),
            (OrganizationMembership, OrganizationMembership.user_id == self.first.id,
             "status", MembershipStatus.INACTIVE, MembershipStatus.ACTIVE),
            (OrganizationMembership, OrganizationMembership.user_id == self.second.id,
             "status", MembershipStatus.INACTIVE, MembershipStatus.ACTIVE),
            (Organization, Organization.id == self.org.id,
             "status", OrganizationStatus.INACTIVE, OrganizationStatus.ACTIVE),
        ):
            await self.session.execute(update(model).where(criteria).values(**{field: inactive}))
            await self.session.commit()
            with self.assertRaises(OwnershipChangeDeniedError):
                await self._change()
            await self.session.execute(update(model).where(criteria).values(**{field: active}))
            await self.session.commit()

    async def test_target_from_other_tenant_and_missing_tenant_are_denied(self):
        await self._designate()
        with self.assertRaises(OwnershipChangeDeniedError):
            await self._change(target=self.operator.id)
        with self.assertRaises(OwnershipChangeDeniedError):
            await self._change(organization_id=uuid4())

    async def test_revoked_and_expired_sessions_are_denied(self):
        await self._designate()
        await SessionService(self.session).revoke(self.tokens[self.first.id])
        with self.assertRaises(OwnershipChangeDeniedError):
            await self._change()
        self.tokens[self.first.id] = (await SessionService(self.session).issue_for_authenticated_user(self.first.id)).token
        now = datetime.now(timezone.utc)
        await self.session.execute(update(UserSession).where(UserSession.user_id == self.first.id).values(
            created_at=now - timedelta(hours=2), expires_at=now - timedelta(hours=1)))
        await self.session.commit()
        with self.assertRaises(OwnershipChangeDeniedError):
            await self._change()

    async def test_history_failure_rolls_back_ownership(self):
        await self._designate()
        real_flush = AsyncSession.flush

        async def fail_history(session, *args, **kwargs):
            if any(isinstance(item, OwnershipChange) for item in session.new):
                await real_flush(session, *args, **kwargs)
                raise RuntimeError("Falha simulada de auditoria")
            return await real_flush(session, *args, **kwargs)

        with patch.object(AsyncSession, "flush", fail_history), self.assertRaises(RuntimeError):
            await self._change()
        self.assertEqual(await self._owner(), self.first.id)

    async def test_concurrent_designations_have_one_winner_and_one_history_entry(self):
        results = await asyncio.gather(
            self._change(self.operator.id, self.first.id, initial=True),
            self._change(self.operator.id, self.second.id, initial=True), return_exceptions=True)
        self.assertEqual(sum(result is None for result in results), 1)
        self.assertEqual(sum(isinstance(result, OwnershipChangeDeniedError) for result in results), 1)

    async def test_concurrent_transfers_cannot_reuse_previous_owner_authority(self):
        await self._designate()
        results = await asyncio.gather(self._change(), self._change(), return_exceptions=True)
        self.assertEqual(sum(result is None for result in results), 1)
        self.assertEqual(sum(isinstance(result, OwnershipChangeDeniedError) for result in results), 1)
        self.assertEqual(await self._owner(), self.second.id)

    async def test_migration_matches_metadata(self):
        await self.session.close()
        await asyncio.to_thread(self.run_migration, "check")

    async def test_logout_during_password_verification_prevents_transfer(self):
        await self._designate()
        from app.modules.identity.passwords import verify_password as real_verify

        async def revoke_then_verify(password, stored_hash):
            async with AsyncSession(self.engine) as writer:
                await SessionService(writer).revoke(self.tokens[self.first.id])
            return await real_verify(password, stored_hash)

        with patch("app.modules.identity.ownership.verify_password", revoke_then_verify):
            with self.assertRaises(OwnershipChangeDeniedError):
                await self._change()
        self.assertEqual(await self._owner(), self.first.id)

    async def test_designation_does_not_create_or_activate_membership(self):
        await self.session.execute(update(OrganizationMembership).where(
            OrganizationMembership.user_id == self.first.id).values(status=MembershipStatus.INACTIVE))
        await self.session.commit()
        with self.assertRaises(OwnershipChangeDeniedError):
            await self._designate()
        self.assertIsNone(await self._owner())

    async def test_migration_round_trip_preserves_owner(self):
        await self._designate()
        await self.session.close()
        await self.engine.dispose()
        try:
            await asyncio.to_thread(self.run_migration, "downgrade", "d2a6f09b84c1")
            self.assertEqual(await self._owner(), self.first.id)
        finally:
            await self.session.close()
            await self.engine.dispose()
            await asyncio.to_thread(self.run_migration, "upgrade", "head")
        self.assertEqual(await self._owner(), self.first.id)
