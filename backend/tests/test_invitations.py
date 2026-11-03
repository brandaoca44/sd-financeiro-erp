"""Valida onboarding e convites em infraestrutura isolada, sem enviar mensagens."""

import asyncio
import hashlib
import os
import secrets
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from cryptography.fernet import Fernet
import httpx
from pydantic import SecretStr, ValidationError
from redis.asyncio import Redis
from redis.exceptions import ConnectionError
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database_support import DatabaseTestCase
from app.core.config import Settings
from app.main import create_app
from app.modules.identity.access_models import OrganizationOwnership, OrganizationRoleAssignment, OwnershipChange
from app.modules.identity.invitation_models import OrganizationInvitation
from app.modules.identity.invitation_schemas import AcceptInvitationRequest, InviteMemberRequest, OnboardingRequest
from app.modules.identity.models import (
    MembershipStatus, OrganizationMembership, User, UserPasswordCredential, UserSession, UserStatus,
)
from app.modules.identity.passwords import hash_password
from app.modules.identity.rate_limit import LoginRateLimiter, LoginRateLimitPolicy
from app.modules.identity.sessions import SessionService
from app.modules.organizations.models import Organization, OrganizationStatus


class InvitationSchemaTests(unittest.TestCase):
    def test_normalizes_email_name_and_masks_secrets(self):
        data = OnboardingRequest(organization_name=" Empresa ", email=" PESSOA@EXAMPLE.COM ", password="segredo")
        self.assertEqual(data.organization_name, "Empresa")
        self.assertEqual(str(data.email), "pessoa@example.com")
        self.assertNotIn("segredo", repr(data))

    def test_rejects_extra_privileges_and_non_boolean_grants(self):
        for extra in ({"role": "CEO"}, {"can_provision_organizations": True}, {"can_read_organization": "true"}):
            with self.assertRaises(ValidationError):
                InviteMemberRequest(email="pessoa@example.com", password="segredo", **extra)

    def test_acceptance_requires_secret_token_and_eight_character_password(self):
        for data in ({"token": "invalido", "password": "senha longa"},
                     {"token": "a"*43, "password": "curta"},
                     {"token": "a"*43, "password": "senha longa", "email": "outra@example.com"}):
            with self.assertRaises(ValidationError):
                AcceptInvitationRequest(**data)


@unittest.skipUnless(os.environ.get("SD_RUN_DATABASE_TESTS") == "1" and os.environ.get("SD_RUN_REDIS_TESTS") == "1",
                     "Defina SD_RUN_DATABASE_TESTS=1 e SD_RUN_REDIS_TESTS=1.")
class InvitationHttpTests(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.redis = Redis(host="127.0.0.1", port=6379, db=15, socket_timeout=2, socket_connect_timeout=2)
        self.addAsyncCleanup(self.redis.aclose)
        self.namespace = "sd-financeiro:test:" + uuid4().hex
        self.addAsyncCleanup(self._clear_redis)
        config = Settings(_env_file=None, database_password="ficticia", app_environment="test", app_debug=True,
                          auth_rate_limit_key=SecretStr(secrets.token_urlsafe(32)),
                          auth_identity_encryption_key=SecretStr(Fernet.generate_key().decode()))
        self.config = config
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)
        self.app = create_app(config, session_factory=self.factory, redis_client=self.redis, rate_limit_namespace=self.namespace)
        context = self.app.router.lifespan_context(self.app)
        await context.__aenter__()
        self.addAsyncCleanup(context.__aexit__, None, None, None)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(
            app=self.app, client=("127.0.0.1", 12345), raise_app_exceptions=False), base_url="http://testserver")
        self.addAsyncCleanup(self.client.aclose)
        self.password = "Senha ficticia para teste @123"
        self.operator, self.owner, self.existing = [User(name=name, email=uuid4().hex+"@example.com",
            status=UserStatus.ACTIVE, can_provision_organizations=(name == "Operador"))
            for name in ("Operador", "Master", "Existente")]
        self.org, self.other = Organization(name="Empresa de teste"), Organization(name="Outra empresa")
        self.session.add_all([self.operator, self.owner, self.existing, self.org, self.other])
        await self.session.flush()
        hashed = (await hash_password(SecretStr(self.password))).get_secret_value()
        for user in (self.operator, self.owner, self.existing):
            self.session.add(UserPasswordCredential(user_id=user.id, password_hash=hashed))
        self.session.add(OrganizationMembership(user_id=self.owner.id, organization_id=self.org.id,
            status=MembershipStatus.ACTIVE, can_read_organization=True))
        await self.session.flush()
        self.session.add(OrganizationOwnership(organization_id=self.org.id, user_id=self.owner.id))
        await self.session.commit()
        self.headers = {}
        for user in (self.operator, self.owner, self.existing):
            issued = await SessionService(self.session).issue_for_authenticated_user(user.id)
            self.headers[user.id] = {"Authorization": "Bearer " + issued.token.get_secret_value()}
        self.email = uuid4().hex + "@example.com"

    async def _clear_redis(self):
        keys = [key async for key in self.redis.scan_iter(match="{"+self.namespace+":*")]
        if keys:
            await self.redis.delete(*keys)

    async def _onboard(self, *, actor=None, **changes):
        return await self.client.post("/api/v1/organizations/onboarding", headers=self.headers[actor or self.operator.id],
            json={"organization_name": "Nova empresa", "email": self.email, "password": self.password, **changes})

    async def _invite(self, *, owner=False, actor=None, org=None, **changes):
        return await self.client.post(f"/api/v1/organizations/{org or self.org.id}/" + ("owner-invitations" if owner else "invitations"),
            headers=self.headers[actor or (self.operator.id if owner else self.owner.id)],
            json={"email": self.email, "password": self.password, **changes})

    async def _issue(self, **kwargs):
        result = await self._invite(**kwargs)
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()

    async def _accept(self, issued, **changes):
        digits = str(secrets.randbelow(900000000) + 100000000)
        for size in (9, 10):
            check = (sum(int(digits[i]) * (size + 1 - i) for i in range(size)) * 10) % 11
            digits += str(0 if check == 10 else check)
        return await self.client.post("/api/v1/auth/invitations/accept", json={
            "token": issued["invitation_token"], "password": self.password, "name": "Pessoa convidada", "cpf": digits, **changes})

    async def _revoke(self, issued, *, actor=None, org=None):
        return await self.client.post(f"/api/v1/organizations/{org or issued['organization_id']}/invitations/{issued['invitation_id']}/revoke",
            headers=self.headers[actor or self.owner.id], json={"password": self.password})

    async def _user(self, email=None):
        async with self.factory() as reader:
            return await reader.scalar(select(User).where(User.email == (email or self.email)))

    async def test_onboarding_creates_pending_invitation_then_owner_with_read_only_baseline(self):
        result = await self._onboard()
        self.assertEqual(result.status_code, 201, result.text)
        issued = result.json()
        self.assertEqual(set(issued), {"organization_id", "invitation_id", "invitation_token", "expires_at"})
        self.assertEqual(result.headers["cache-control"], "no-store")
        self.assertIsNone(await self._user())
        self.assertIsNone(await self.session.scalar(select(OrganizationOwnership).where(
            OrganizationOwnership.organization_id == issued["organization_id"])))
        response = await self._accept(issued)
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(response.content, b"")
        user = await self._user()
        self.assertFalse(user.can_provision_organizations)
        self.assertEqual(await self.session.scalar(select(OrganizationOwnership.user_id).where(
            OrganizationOwnership.organization_id == issued["organization_id"])), user.id)
        member = await self.session.get(OrganizationMembership, (user.id, issued["organization_id"]))
        self.assertEqual(member.status, MembershipStatus.ACTIVE)
        self.assertTrue(member.can_read_organization)
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(UserSession).where(UserSession.user_id == user.id)), 0)
        history = await self.session.scalar(select(OwnershipChange).where(OwnershipChange.organization_id == issued["organization_id"]))
        self.assertEqual(history.actor_user_id, user.id)
        self.assertIsNone(history.previous_user_id)
        login = await self.client.post("/api/v1/auth/login", json={"email": self.email, "password": self.password})
        self.assertEqual(login.status_code, 200)
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        self.assertEqual((await self.client.get("/api/v1/organizations/"+issued["organization_id"], headers=headers)).status_code, 200)
        self.assertEqual((await self.client.get("/api/v1/organizations/"+issued["organization_id"], headers=self.headers[self.operator.id])).status_code, 404)

    async def test_onboarding_denials_do_not_create_tenants(self):
        before = await self.session.scalar(select(func.count()).select_from(Organization))
        for response in (await self._onboard(actor=self.owner.id), await self._onboard(password="incorreta")):
            self.assertEqual(response.status_code, 404)
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(Organization)), before)

    async def test_owner_invitation_supports_legacy_tenant_without_automatic_operator_membership(self):
        issued = await self._issue(owner=True, org=self.other.id)
        self.assertEqual((await self._accept(issued)).status_code, 204)
        self.assertIsNone(await self.session.get(OrganizationMembership, (self.operator.id, self.other.id)))
        self.assertEqual((await self._invite(owner=True, org=self.other.id)).status_code, 404)

    async def test_member_defaults_deny_read_and_never_assign_roles_or_master(self):
        issued = await self._issue()
        self.assertEqual((await self._accept(issued)).status_code, 204)
        user = await self._user()
        member = await self.session.get(OrganizationMembership, (user.id, self.org.id))
        self.assertFalse(member.can_read_organization)
        self.assertFalse(user.can_provision_organizations)
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(OrganizationRoleAssignment).where(
            OrganizationRoleAssignment.user_id == user.id)), 0)
        self.assertNotEqual(await self.session.scalar(select(OrganizationOwnership.user_id).where(
            OrganizationOwnership.organization_id == self.org.id)), user.id)

    async def test_explicit_read_grant_is_limited_to_invitation_tenant(self):
        issued = await self._issue(can_read_organization=True)
        self.assertEqual((await self._accept(issued)).status_code, 204)
        user = await self._user()
        self.assertTrue((await self.session.get(OrganizationMembership, (user.id, self.org.id))).can_read_organization)
        self.assertIsNone(await self.session.get(OrganizationMembership, (user.id, self.other.id)))

    async def test_existing_account_requires_own_password_and_preserves_name_credential(self):
        issued = await self._issue(email=self.existing.email)
        before = await self.session.scalar(select(UserPasswordCredential.password_hash).where(UserPasswordCredential.user_id == self.existing.id))
        bad = await self._accept(issued, password="senha incorreta")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual((await self._accept(issued, name="Não substituir nome")).status_code, 204)
        await self.session.refresh(self.existing)
        self.assertEqual(self.existing.name, "Existente")
        self.assertEqual(await self.session.scalar(select(UserPasswordCredential.password_hash).where(
            UserPasswordCredential.user_id == self.existing.id)), before)

    async def test_expired_revoked_unknown_and_used_tokens_share_generic_denial(self):
        issued = await self._issue()
        self.assertEqual((await self._revoke(issued)).status_code, 204)
        revoked = await self._accept(issued)
        unknown = await self._accept({"invitation_token": secrets.token_urlsafe(32)})
        expired = await self._issue()
        now = datetime.now(timezone.utc)
        await self.session.execute(update(OrganizationInvitation).where(OrganizationInvitation.id == expired["invitation_id"]).values(
            created_at=now-timedelta(days=2), expires_at=now-timedelta(days=1)))
        await self.session.commit()
        expired_result = await self._accept(expired)
        valid = await self._issue()
        self.assertEqual((await self._accept(valid)).status_code, 204)
        used = await self._accept(valid)
        self.assertTrue(all(r.status_code == 400 for r in (revoked, unknown, expired_result, used)))
        self.assertEqual(len({r.text for r in (revoked, unknown, expired_result, used)}), 1)

    async def test_reissue_revokes_previous_token_and_keeps_both_audit_records(self):
        first = await self._issue()
        second = await self._issue()
        self.assertNotEqual(first["invitation_token"], second["invitation_token"])
        self.assertEqual((await self._accept(first)).status_code, 400)
        self.assertEqual((await self._accept(second)).status_code, 204)
        old = await self.session.get(OrganizationInvitation, first["invitation_id"])
        self.assertEqual(old.revoked_by_user_id, self.owner.id)
        self.assertIsNotNone(old.revoked_at)

    async def test_only_one_pending_initial_owner_even_with_different_email(self):
        first = await self._issue(owner=True, org=self.other.id)
        second = await self._issue(owner=True, org=self.other.id, email=uuid4().hex+"@example.com")
        self.assertEqual((await self._accept(first)).status_code, 400)
        self.assertEqual((await self._accept(second)).status_code, 204)

    async def test_concurrent_acceptance_consumes_token_once(self):
        issued = await self._issue()
        responses = await asyncio.gather(self._accept(issued), self._accept(issued))
        self.assertEqual(sorted(r.status_code for r in responses), [204, 400])
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(User).where(User.email == self.email)), 1)

    async def test_owner_transfer_invalidates_invitations_from_previous_owner(self):
        issued = await self._issue()
        self.session.add(OrganizationMembership(user_id=self.existing.id, organization_id=self.org.id, status=MembershipStatus.ACTIVE))
        await self.session.flush()
        await self.session.execute(update(OrganizationOwnership).where(OrganizationOwnership.organization_id == self.org.id).values(user_id=self.existing.id))
        await self.session.commit()
        self.assertEqual((await self._accept(issued)).status_code, 400)
        self.assertIsNone(await self._user())
        self.assertEqual((await self._revoke(issued, actor=self.existing.id)).status_code, 204)

    async def test_inactive_issuer_membership_or_tenant_prevents_acceptance(self):
        issued = await self._issue()
        for model, clause, inactive, active in (
            (User, User.id == self.owner.id, UserStatus.INACTIVE, UserStatus.ACTIVE),
            (OrganizationMembership, OrganizationMembership.user_id == self.owner.id, MembershipStatus.INACTIVE, MembershipStatus.ACTIVE),
            (Organization, Organization.id == self.org.id, OrganizationStatus.INACTIVE, OrganizationStatus.ACTIVE),
        ):
            await self.session.execute(update(model).where(clause).values(status=inactive))
            await self.session.commit()
            self.assertEqual((await self._accept(issued)).status_code, 400)
            await self.session.execute(update(model).where(clause).values(status=active))
            await self.session.commit()
        self.assertIsNone(await self._user())

    async def test_revoked_provisioning_flag_invalidates_pending_owner_invite(self):
        issued = await self._issue(owner=True, org=self.other.id)
        await self.session.execute(update(User).where(User.id == self.operator.id).values(can_provision_organizations=False))
        await self.session.commit()
        self.assertEqual((await self._accept(issued)).status_code, 400)

    async def test_invitation_never_reactivates_existing_user_or_membership(self):
        issued = await self._issue(email=self.existing.email, can_read_organization=True)
        await self.session.execute(update(User).where(User.id == self.existing.id).values(status=UserStatus.INACTIVE))
        await self.session.commit()
        self.assertEqual((await self._accept(issued)).status_code, 400)
        await self.session.execute(update(User).where(User.id == self.existing.id).values(status=UserStatus.ACTIVE))
        self.session.add(OrganizationMembership(user_id=self.existing.id, organization_id=self.org.id, status=MembershipStatus.INACTIVE))
        await self.session.commit()
        self.assertEqual((await self._accept(issued)).status_code, 400)
        member = await self.session.get(OrganizationMembership, (self.existing.id, self.org.id))
        self.assertEqual(member.status, MembershipStatus.INACTIVE)
        self.assertFalse(member.can_read_organization)

    async def test_cross_tenant_creation_and_revocation_are_denied(self):
        issued = await self._issue()
        for response in (await self._invite(org=self.other.id), await self._invite(actor=self.existing.id),
                         await self._revoke(issued, org=self.other.id), await self._revoke(issued, actor=self.existing.id)):
            self.assertEqual(response.status_code, 404)
        self.assertEqual((await self._accept(issued)).status_code, 204)

    async def test_tokens_are_hashed_and_not_returned_by_other_endpoints(self):
        issued = await self._issue()
        stored = await self.session.scalar(select(OrganizationInvitation.token_hash).where(OrganizationInvitation.id == issued["invitation_id"]))
        self.assertEqual(stored, hashlib.sha256(issued["invitation_token"].encode()).hexdigest())
        self.assertNotEqual(stored, issued["invitation_token"])
        self.assertNotIn(issued["invitation_token"], repr(AcceptInvitationRequest(token=issued["invitation_token"], password=self.password)))
        revoked = await self._revoke(issued)
        self.assertEqual(revoked.status_code, 204)
        self.assertEqual(revoked.content, b"")
        self.assertEqual((await self._revoke(issued)).status_code, 204)

    async def test_rate_limit_management_is_shared_across_endpoints_and_sessions(self):
        for _ in range(5):
            self.assertEqual((await self._invite(owner=True, org=self.other.id, password="incorreta")).status_code, 404)
        with patch("app.modules.identity.invitations.verify_password", new_callable=AsyncMock) as verifier:
            response = await self._onboard()
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response.headers["retry-after"]), 0)
        verifier.assert_not_awaited()

    async def test_acceptance_limit_is_per_token_and_precedes_password_work(self):
        issued = await self._issue(email=self.existing.email)
        for _ in range(5):
            self.assertEqual((await self._accept(issued, password="incorreta")).status_code, 400)
        with patch("app.modules.identity.invitations.verify_password", new_callable=AsyncMock) as verifier:
            response = await self._accept(issued)
        self.assertEqual(response.status_code, 429)
        verifier.assert_not_awaited()

    async def test_origin_and_global_limits_block_rotating_invitation_tokens(self):
        for policy, origin in ((LoginRateLimitPolicy(origin_limit=1), "127.0.0.1"),
                               (LoginRateLimitPolicy(global_limit=1), "198.51.100.1")):
            namespace = self.namespace+"_"+uuid4().hex[:6]
            limiter = LoginRateLimiter(self.redis, key_secret=self.config.auth_rate_limit_key, namespace=namespace,
                                       operation="invitation_accept", policy=policy)
            self.app.state.invitation_accept_limiter = limiter
            try:
                await limiter.check(account_identifier=secrets.token_urlsafe(32), origin_ip=origin)
                response = await self._accept({"invitation_token": secrets.token_urlsafe(32)})
                self.assertEqual(response.status_code, 429)
            finally:
                keys = [key async for key in self.redis.scan_iter(match="{"+namespace+":*")]
                if keys:
                    await self.redis.delete(*keys)

    async def test_redis_failure_blocks_issue_accept_but_not_logout(self):
        issued = await self._issue()
        with patch.object(self.redis, "eval", side_effect=ConnectionError("segredo_redis")):
            for response in (await self._invite(), await self._accept(issued)):
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("segredo_redis", response.text)
            logout = await self.client.post("/api/v1/auth/logout", headers=self.headers[self.owner.id])
            self.assertEqual(logout.status_code, 204)

    async def test_shared_hash_capacity_and_cancellation_roll_back_acceptance(self):
        issued = await self._issue()
        self.app.state.auth_hash_slots = asyncio.Semaphore(1)
        entered, finish = asyncio.Event(), asyncio.Event()
        real_hash = hash_password

        async def delayed_hash(password):
            entered.set()
            await finish.wait()
            return await real_hash(password)

        with patch("app.modules.identity.invitations.hash_password", delayed_hash):
            first = asyncio.create_task(self._accept(issued))
            try:
                await asyncio.wait_for(entered.wait(), timeout=5)
                first.cancel()
                self.assertEqual((await self._accept(issued)).status_code, 503)
            finally:
                finish.set()
                await asyncio.gather(first, return_exceptions=True)
        self.assertIsNone(await self._user())
        async with self.factory() as reader:
            invitation = await reader.get(OrganizationInvitation, issued["invitation_id"])
            self.assertIsNone(invitation.accepted_at)

    async def test_validation_body_limits_and_no_secret_echo(self):
        headers = self.headers[self.operator.id]
        url = "/api/v1/organizations/onboarding"
        for data in ({"organization_name": "Empresa", "email": self.email, "password": self.password, "role": "CEO"},
                     {"organization_name": "Empresa", "email": "inválido", "password": self.password}):
            response = await self.client.post(url, json=data, headers=headers)
            self.assertEqual(response.status_code, 422)
            self.assertNotIn(self.password, response.text)
            self.assertNotIn(self.email, response.text)
        for path in (url, "/api/v1/auth/invitations/accept"):
            oversized = await self.client.post(path, content="x"*4097, headers={**headers, "Content-Type": "application/json"})
            wrong_type = await self.client.post(path, content="segredo", headers={**headers, "Content-Type": "text/plain"})
            self.assertEqual(oversized.status_code, 413)
            self.assertEqual(wrong_type.status_code, 415)
            self.assertEqual(oversized.headers["cache-control"], "no-store")

    async def test_management_requires_bearer_and_acceptance_requires_https_in_production(self):
        response = await self.client.post("/api/v1/organizations/onboarding", json={
            "organization_name": "Empresa", "email": self.email, "password": self.password})
        self.assertEqual(response.status_code, 401)
        issued = await self._issue()
        self.app.state.settings = self.config.model_copy(update={"app_environment": "production"})
        self.assertEqual((await self._accept(issued)).status_code, 503)

    async def test_database_and_unexpected_errors_are_sanitized_even_in_debug(self):
        for error, code in ((SQLAlchemyError("segredo_sql"), 503), (RuntimeError("segredo_app"), 500)):
            with patch("app.api.v1.invitations.InvitationService.onboard", side_effect=error):
                response = await self._onboard()
            self.assertEqual(response.status_code, code)
            self.assertNotIn("segredo", response.text)
            self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_new_user_requires_name_and_non_obvious_password_without_consuming_token(self):
        issued = await self._issue()
        for changes in ({"name": None}, {"password": "aaaaaaaa"}, {"password": "12345678"}):
            self.assertEqual((await self._accept(issued, **changes)).status_code, 400)
            self.assertIsNone(await self._user())
        self.assertEqual((await self._accept(issued)).status_code, 204)

    async def test_expiration_is_rechecked_after_password_work(self):
        issued = await self._issue()
        now = datetime.now(timezone.utc)
        with patch("app.modules.identity.invitations.datetime") as clock:
            clock.now.side_effect = [now, now+timedelta(days=2)]
            response = await self._accept(issued)
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(await self._user())

    async def test_logout_during_confirmation_prevents_invitation_and_activity_renewal(self):
        from app.modules.identity.passwords import verify_password as real_verify

        async def revoke_during_verification(password, stored_hash):
            self.assertEqual((await self.client.post("/api/v1/auth/logout", headers=self.headers[self.owner.id])).status_code, 204)
            return await real_verify(password, stored_hash)

        with patch("app.modules.identity.invitations.verify_password", revoke_during_verification):
            result = await self._invite()
        self.assertEqual(result.status_code, 404)
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == self.org.id)), 0)

    async def test_database_constraints_reject_double_terminal_state_and_duplicate_pending(self):
        issued = await self._issue()
        row = await self.session.get(OrganizationInvitation, issued["invitation_id"])
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                await self.session.execute(update(OrganizationInvitation).where(OrganizationInvitation.id == row.id).values(
                    accepted_at=datetime.now(timezone.utc), accepted_by_user_id=self.existing.id,
                    revoked_at=datetime.now(timezone.utc), revoked_by_user_id=self.owner.id))
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                self.session.add(OrganizationInvitation(organization_id=self.org.id, email=self.email, kind="MEMBER",
                    token_hash="a"*64, issued_by_user_id=self.owner.id, expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
                await self.session.flush()

    async def test_concurrent_invitations_for_same_email_across_tenants_create_one_identity(self):
        self.session.add(OrganizationMembership(user_id=self.owner.id, organization_id=self.other.id,
                                               status=MembershipStatus.ACTIVE))
        await self.session.flush()
        self.session.add(OrganizationOwnership(organization_id=self.other.id, user_id=self.owner.id))
        await self.session.commit()
        first, second = await self._issue(), await self._issue(org=self.other.id)
        responses = await asyncio.gather(self._accept(first), self._accept(second))
        self.assertEqual([r.status_code for r in responses], [204, 204])
        user = await self._user()
        self.assertEqual(await self.session.scalar(select(func.count()).select_from(User).where(User.email == self.email)), 1)
        for org in (self.org, self.other):
            self.assertIsNotNone(await self.session.get(OrganizationMembership, (user.id, org.id)))

    async def test_history_failure_rolls_back_account_membership_and_token_consumption(self):
        response = await self._onboard()
        self.assertEqual(response.status_code, 201)
        issued = response.json()
        real_flush = AsyncSession.flush

        async def fail_after_history(session, *args, **kwargs):
            if any(isinstance(item, OwnershipChange) for item in session.new):
                await real_flush(session, *args, **kwargs)
                raise SQLAlchemyError("falha simulada")
            return await real_flush(session, *args, **kwargs)

        with patch.object(AsyncSession, "flush", fail_after_history):
            result = await self._accept(issued)
        self.assertEqual(result.status_code, 503)
        self.assertIsNone(await self._user())
        async with self.factory() as reader:
            invitation = await reader.get(OrganizationInvitation, issued["invitation_id"])
            self.assertIsNone(invitation.accepted_at)
            self.assertIsNone(await reader.get(OrganizationOwnership, issued["organization_id"]))
        self.assertEqual((await self._accept(issued)).status_code, 204)

    async def test_database_rejects_acceptor_without_membership_in_exact_tenant(self):
        issued = await self._issue()
        with self.assertRaises(IntegrityError):
            async with self.session.begin_nested():
                await self.session.execute(update(OrganizationInvitation).where(
                    OrganizationInvitation.id == issued["invitation_id"]).values(
                        accepted_at=datetime.now(timezone.utc), accepted_by_user_id=self.existing.id))


class InvitationMigrationTests(DatabaseTestCase):
    async def test_migration_round_trip_preserves_identity_ownership_and_matches_metadata(self):
        self.owner=User(name="Responsável teste",email=uuid4().hex+"@example.com",status=UserStatus.ACTIVE)
        self.org=Organization(name="Empresa teste")
        self.session.add_all([self.owner,self.org]);await self.session.flush()
        self.session.add(OrganizationMembership(user_id=self.owner.id,organization_id=self.org.id,status=MembershipStatus.ACTIVE))
        await self.session.flush()
        self.session.add(OrganizationOwnership(organization_id=self.org.id,user_id=self.owner.id))
        await self.session.commit()
        await self.session.close()
        await self.engine.dispose()
        try:
            await asyncio.to_thread(self.run_migration, "downgrade", "e7b1c90a42d3")
            self.assertIsNotNone(await self.session.get(User, self.owner.id))
            self.assertEqual(await self.session.scalar(select(OrganizationOwnership.user_id).where(
                OrganizationOwnership.organization_id == self.org.id)), self.owner.id)
        finally:
            await self.session.close()
            await self.engine.dispose()
            await asyncio.to_thread(self.run_migration, "upgrade", "head")
        await self.session.close()
        await asyncio.to_thread(self.run_migration, "check")
