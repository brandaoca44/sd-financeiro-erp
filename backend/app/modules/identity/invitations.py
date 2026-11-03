"""Onboarding e concessão por convite com autoridade revalidada e transações próprias."""

import asyncio
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from pydantic import SecretStr
from cryptography.fernet import Fernet
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.access_models import OrganizationOwnership, OwnershipChange
from app.modules.identity.account_models import AccountSecurity
from app.modules.identity.account_security import RegisterRequest
from app.modules.identity.invitation_models import OrganizationInvitation
from app.modules.identity.invitation_schemas import AcceptInvitationRequest
from app.modules.identity.models import (
    MembershipStatus, OrganizationMembership, User, UserPasswordCredential, UserSession, UserStatus,
)
from app.modules.identity.passwords import hash_password, validate_new_password, verify_password
from app.modules.identity.sessions import SessionService
from app.modules.organizations.models import Organization, OrganizationStatus


class InvitationDeniedError(Exception):
    """Não distingue conta, credencial, autoridade ou estado do convite."""


@dataclass(frozen=True)
class IssuedInvitation:
    organization_id: UUID
    invitation_id: UUID
    token: SecretStr
    expires_at: datetime


async def _password_work(work):
    task = asyncio.create_task(work)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.shield(task)
        raise


class InvitationService:
    """Sessão nova por chamada; HTTP limita admissões e concorrência antes do serviço."""

    def __init__(self, session: AsyncSession, *, idle_timeout: timedelta = timedelta(minutes=30), identity_key: SecretStr | None = None):
        if not timedelta(0) < idle_timeout <= timedelta(days=1):
            raise ValueError("Prazo de inatividade inválido.")
        self.session = session
        self.idle_timeout = idle_timeout
        self.identity_key = identity_key

    @staticmethod
    def deny():
        raise InvitationDeniedError("Operação de convite não permitida.")

    async def _begin(self):
        await self.session.execute(text("SET LOCAL lock_timeout = '5s'"))

    async def _organization(self, organization_id):
        organization = await self.session.scalar(select(Organization).where(
            Organization.id == organization_id).with_for_update())
        if organization is None or organization.status != OrganizationStatus.ACTIVE:
            self.deny()
        return organization

    async def _owner(self, organization_id):
        return await self.session.scalar(select(OrganizationOwnership.user_id).where(
            OrganizationOwnership.organization_id == organization_id).with_for_update())

    async def _active_membership(self, user_id, organization_id):
        member = await self.session.scalar(select(OrganizationMembership).where(
            OrganizationMembership.user_id == user_id, OrganizationMembership.organization_id == organization_id,
        ).with_for_update())
        if member is None or member.status != MembershipStatus.ACTIVE:
            self.deny()
        return member

    async def _authenticate(self, token, password, *, organization_id=None, kind="OWNER"):
        token_hash = SessionService._token_hash(token)
        if token_hash is None:
            self.deny()
        actor_id = await self.session.scalar(select(UserSession.user_id).where(UserSession.token_hash == token_hash))
        actor = await self.session.scalar(select(User).where(User.id == actor_id).with_for_update())
        if actor is None or actor.status != UserStatus.ACTIVE:
            self.deny()
        if kind == "OWNER":
            if not actor.can_provision_organizations:
                self.deny()
            if organization_id is not None and await self._owner(organization_id) is not None:
                self.deny()
        else:
            if await self._owner(organization_id) != actor.id:
                self.deny()
            await self._active_membership(actor.id, organization_id)
        credential = await self.session.scalar(select(UserPasswordCredential.password_hash).where(
            UserPasswordCredential.user_id == actor.id).with_for_update())
        if credential is None or not (await _password_work(verify_password(password, credential)))[0]:
            self.deny()
        login = await self.session.scalar(select(UserSession).where(UserSession.token_hash == token_hash).with_for_update())
        now = datetime.now(timezone.utc)
        if login is None or login.revoked_at is not None or not login.created_at <= now < login.expires_at:
            self.deny()
        login.expires_at = max(login.expires_at, now + self.idle_timeout)
        return actor

    async def _issue(self, organization_id, email, kind, actor_id, can_read):
        now = datetime.now(timezone.utc)
        # Substituição explícita: convite anterior deixa de ser utilizável, mesmo expirado.
        replacement = OrganizationInvitation.email == email
        if kind == "OWNER":
            replacement = or_(replacement, OrganizationInvitation.kind == "OWNER")
        pending = (await self.session.scalars(select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == organization_id,
            OrganizationInvitation.accepted_at.is_(None), OrganizationInvitation.revoked_at.is_(None),
            replacement,
        ).with_for_update())).all()
        for old in pending:
            old.revoked_at, old.revoked_by_user_id = now, actor_id
        await self.session.flush()
        token = SecretStr(secrets.token_urlsafe(32))
        invitation = OrganizationInvitation(
            organization_id=organization_id, email=email, kind=kind, can_read_organization=can_read,
            token_hash=SessionService._token_hash(token), issued_by_user_id=actor_id,
            created_at=now, expires_at=now + timedelta(hours=24),
        )
        self.session.add(invitation)
        await self.session.flush()
        return IssuedInvitation(organization_id, invitation.id, token, invitation.expires_at)

    async def onboard(self, data, *, token: SecretStr) -> IssuedInvitation:
        async with self.session.begin():
            await self._begin()
            actor = await self._authenticate(token, data.password)
            organization = Organization(name=data.organization_name)
            self.session.add(organization)
            await self.session.flush()
            issued = await self._issue(organization.id, str(data.email), "OWNER", actor.id, True)
        return issued

    async def issue(self, organization_id: UUID, data, *, token: SecretStr, owner: bool) -> IssuedInvitation:
        async with self.session.begin():
            await self._begin()
            await self._organization(organization_id)
            kind = "OWNER" if owner else "MEMBER"
            actor = await self._authenticate(token, data.password, organization_id=organization_id, kind=kind)
            issued = await self._issue(organization_id, str(data.email), kind, actor.id,
                                       True if owner else data.can_read_organization)
        return issued

    async def revoke(self, organization_id: UUID, invitation_id: UUID, *, token: SecretStr, password: SecretStr):
        async with self.session.begin():
            await self._begin()
            await self._organization(organization_id)
            invitation = await self.session.scalar(select(OrganizationInvitation).where(
                OrganizationInvitation.id == invitation_id,
                OrganizationInvitation.organization_id == organization_id).with_for_update())
            if invitation is None:
                self.deny()
            actor = await self._authenticate(token, password, organization_id=organization_id, kind=invitation.kind)
            if invitation.accepted_at is not None:
                self.deny()
            if invitation.revoked_at is None:
                invitation.revoked_at = datetime.now(timezone.utc)
                invitation.revoked_by_user_id = actor.id
            await self.session.flush()

    async def accept(self, data: AcceptInvitationRequest):
        token_hash = SessionService._token_hash(data.token)
        if token_hash is None:
            self.deny()
        async with self.session.begin():
            await self._begin()
            organization_id = await self.session.scalar(select(OrganizationInvitation.organization_id).where(
                OrganizationInvitation.token_hash == token_hash))
            if organization_id is None:
                self.deny()
            await self._organization(organization_id)
            invitation = await self.session.scalar(select(OrganizationInvitation).where(
                OrganizationInvitation.token_hash == token_hash).with_for_update())
            now = datetime.now(timezone.utc)
            if invitation is None or invitation.accepted_at is not None or invitation.revoked_at is not None or not (
                invitation.created_at <= now < invitation.expires_at
            ):
                self.deny()
            owner_id = await self._owner(organization_id)
            if invitation.kind == "OWNER" and owner_id is not None:
                self.deny()
            if invitation.kind == "MEMBER" and owner_id != invitation.issued_by_user_id:
                self.deny()
            # Serializa criação da mesma identidade por convites de tenants diferentes.
            email_lock = int.from_bytes(hashlib.sha256(("sd:invite-email:" + invitation.email).encode()).digest()[:8],
                                        byteorder="big", signed=True)
            await self.session.execute(select(func.pg_advisory_xact_lock(email_lock)))
            target_id = await self.session.scalar(select(User.id).where(func.lower(User.email) == invitation.email))
            ids = {invitation.issued_by_user_id} | ({target_id} if target_id else set())
            users = (await self.session.scalars(select(User).where(User.id.in_(ids)).order_by(User.id).with_for_update())).all()
            by_id = {user.id: user for user in users}
            issuer = by_id.get(invitation.issued_by_user_id)
            if issuer is None or issuer.status != UserStatus.ACTIVE:
                self.deny()
            if invitation.kind == "OWNER":
                if not issuer.can_provision_organizations:
                    self.deny()
            else:
                await self._active_membership(issuer.id, organization_id)
            user = by_id.get(target_id)
            if user is not None:
                if user.status != UserStatus.ACTIVE:
                    self.deny()
                credential = await self.session.scalar(select(UserPasswordCredential.password_hash).where(
                    UserPasswordCredential.user_id == user.id).with_for_update())
                if credential is None or not (await _password_work(verify_password(data.password, credential)))[0]:
                    self.deny()
            else:
                if data.name is None or data.cpf is None or self.identity_key is None:
                    self.deny()
                try:
                    full_name = RegisterRequest.name_valid(data.name)
                    validate_new_password(data.password)
                except ValueError:
                    self.deny()
                hashed = await _password_work(hash_password(data.password))
                key = self.identity_key.get_secret_value().encode()
                cpf = data.cpf.get_secret_value()
                cpf_digest = hmac.new(key, ("cpf:" + cpf).encode(), hashlib.sha256).hexdigest()
                if await self.session.scalar(select(AccountSecurity.user_id).where(AccountSecurity.cpf_digest == cpf_digest)):
                    self.deny()
                user = User(name=full_name, email=invitation.email, status=UserStatus.ACTIVE)
                self.session.add(user)
                await self.session.flush()
                self.session.add(UserPasswordCredential(user_id=user.id, password_hash=hashed.get_secret_value()))
                self.session.add(AccountSecurity(user_id=user.id, cpf_encrypted=Fernet(key).encrypt(cpf.encode()).decode(),
                    cpf_digest=cpf_digest))
            member = await self.session.scalar(select(OrganizationMembership).where(
                OrganizationMembership.user_id == user.id, OrganizationMembership.organization_id == organization_id,
            ).with_for_update())
            # Um convite não altera concessões nem reativa vínculo anterior.
            if member is not None:
                self.deny()
            now = datetime.now(timezone.utc)
            if now >= invitation.expires_at:
                self.deny()
            self.session.add(OrganizationMembership(user_id=user.id, organization_id=organization_id,
                status=MembershipStatus.ACTIVE, can_read_organization=invitation.can_read_organization))
            await self.session.flush()
            if invitation.kind == "OWNER":
                self.session.add(OrganizationOwnership(organization_id=organization_id, user_id=user.id))
                self.session.add(OwnershipChange(organization_id=organization_id, actor_user_id=user.id,
                                                previous_user_id=None, new_user_id=user.id))
            invitation.accepted_at, invitation.accepted_by_user_id = now, user.id
            await self.session.flush()
