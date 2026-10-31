"""Administra perfis e delegações em transações auditadas e sem privilégios implícitos."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.access_models import (
    OrganizationOwnership, OrganizationRole, OrganizationRoleAssignment, RoleAssignmentStatus, RoleStatus,
)
from app.modules.identity.authorization import OrganizationAccessPolicy
from app.modules.identity.models import (
    MembershipStatus, OrganizationMembership, User, UserPasswordCredential, UserSession, UserStatus,
)
from app.modules.identity.passwords import run_password_work, verify_password
from app.modules.identity.permission_models import (
    OrganizationAccessChange, OrganizationAccessDelegation, OrganizationDelegationPermission, OrganizationRolePermission,
)
from app.modules.identity.permissions import PermissionKey
from app.modules.identity.role_schemas import AssignmentResponse, DelegationResponse, RoleResponse
from app.modules.identity.sessions import SessionService
from app.modules.organizations.models import Organization, OrganizationStatus


class AccessManagementDeniedError(Exception):
    """Nega sem informar existência de conta, perfil ou tenant."""


class AccessRevisionConflictError(Exception):
    """Exige revisão atual antes de substituir uma concessão."""


class RoleService:
    def __init__(self, session: AsyncSession, *, idle_timeout: timedelta = timedelta(minutes=30)):
        if not timedelta(0) < idle_timeout <= timedelta(days=1):
            raise ValueError("Prazo de inatividade inválido.")
        self.session, self.idle_timeout = session, idle_timeout

    @staticmethod
    def deny():
        raise AccessManagementDeniedError("Operação de acesso não permitida.")

    @staticmethod
    def check_revision(expected, current):
        if expected != current:
            raise AccessRevisionConflictError("Concessão alterada. Atualize os dados antes de tentar novamente.")

    async def _authorize(self, organization_id, token, password, *, target_id=None, assignment=False):
        await self.session.execute(text("SET LOCAL lock_timeout = '5s'"))
        organization = await self.session.scalar(select(Organization).where(
            Organization.id == organization_id).with_for_update())
        if organization is None or organization.status != OrganizationStatus.ACTIVE:
            self.deny()
        owner = await self.session.scalar(select(OrganizationOwnership).where(
            OrganizationOwnership.organization_id == organization_id).with_for_update())
        if owner is None:
            self.deny()
        token_hash = SessionService._token_hash(token)
        actor_id = await self.session.scalar(select(UserSession.user_id).where(UserSession.token_hash == token_hash))
        if actor_id is None:
            self.deny()
        ids = {actor_id, owner.user_id} | ({target_id} if target_id is not None else set())
        users = {user.id: user for user in (await self.session.scalars(select(User).where(
            User.id.in_(ids)).order_by(User.id).with_for_update())).all()}
        members = {member.user_id: member for member in (await self.session.scalars(select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id.in_(ids)).order_by(OrganizationMembership.user_id).with_for_update())).all()}
        actor = users.get(actor_id)
        if actor is None or actor.status != UserStatus.ACTIVE or actor_id not in members or members[actor_id].status != MembershipStatus.ACTIVE:
            self.deny()
        if target_id is not None and (target_id not in users or target_id not in members):
            self.deny()
        is_owner = owner.user_id == actor_id
        if not is_owner:
            if not assignment or not await OrganizationAccessPolicy(self.session).has_permission(
                actor_id, organization_id, PermissionKey.ASSIGNMENTS_MANAGE,
            ):
                self.deny()
            if target_id in (actor_id, owner.user_id):
                self.deny()
            target_delegation = await self.session.get(OrganizationAccessDelegation, (organization_id, target_id))
            if target_delegation is not None:
                self.deny()
        credential = await self.session.scalar(select(UserPasswordCredential.password_hash).where(
            UserPasswordCredential.user_id == actor_id).with_for_update())
        if credential is None or not (await run_password_work(verify_password(password, credential)))[0]:
            self.deny()
        login = await self.session.scalar(select(UserSession).where(UserSession.token_hash == token_hash).with_for_update())
        now = datetime.now(timezone.utc)
        if login is None or login.revoked_at is not None or not login.created_at <= now < login.expires_at:
            self.deny()
        login.expires_at = max(login.expires_at, now + self.idle_timeout)
        return actor_id, owner, users, members, is_owner

    def _audit(self, organization_id, actor_id, action, before, after, *, role_id=None, target_id=None):
        self.session.add(OrganizationAccessChange(organization_id=organization_id, actor_user_id=actor_id,
            role_id=role_id, target_user_id=target_id, action=action, before_state=before, after_state=after))

    async def _permissions(self, organization_id, role_id):
        return sorted((await self.session.scalars(select(OrganizationRolePermission.permission_key).where(
            OrganizationRolePermission.organization_id == organization_id, OrganizationRolePermission.role_id == role_id))).all())

    async def _replace_permissions(self, organization_id, role_id, permissions):
        await self.session.execute(delete(OrganizationRolePermission).where(
            OrganizationRolePermission.organization_id == organization_id, OrganizationRolePermission.role_id == role_id))
        self.session.add_all([OrganizationRolePermission(organization_id=organization_id, role_id=role_id,
            permission_key=permission) for permission in permissions])

    @staticmethod
    def _role_response(role, permissions):
        return RoleResponse(id=role.id, name=role.name, category=role.category, status=role.status,
                            revision=role.revision, permissions=permissions)

    async def create(self, organization_id: UUID, data, *, token):
        async with self.session.begin():
            actor_id, *_ = await self._authorize(organization_id, token, data.password)
            role = OrganizationRole(organization_id=organization_id, name=data.name, category=data.category, status=data.status)
            self.session.add(role)
            await self.session.flush()
            await self._replace_permissions(organization_id, role.id, data.permissions)
            after = {"revision": role.revision, "status": role.status, "permissions": list(data.permissions)}
            self._audit(organization_id, actor_id, "ROLE_CREATED", {}, after, role_id=role.id)
            await self.session.flush()
            result = self._role_response(role, data.permissions)
        return result

    async def update(self, organization_id: UUID, role_id: UUID, data, *, token):
        async with self.session.begin():
            actor_id, *_ = await self._authorize(organization_id, token, data.password)
            role = await self.session.scalar(select(OrganizationRole).where(
                OrganizationRole.organization_id == organization_id, OrganizationRole.id == role_id).with_for_update())
            if role is None:
                self.deny()
            self.check_revision(data.expected_revision, role.revision)
            before = {"revision": role.revision, "status": role.status, "permissions": await self._permissions(organization_id, role.id)}
            role.name, role.category, role.status = data.name, data.category, data.status
            role.revision += 1
            await self._replace_permissions(organization_id, role.id, data.permissions)
            after = {"revision": role.revision, "status": role.status, "permissions": list(data.permissions)}
            self._audit(organization_id, actor_id, "ROLE_UPDATED", before, after, role_id=role.id)
            await self.session.flush()
            result = self._role_response(role, data.permissions)
        return result

    async def assign(self, organization_id: UUID, user_id: UUID, role_id: UUID, data, *, token):
        async with self.session.begin():
            actor_id, owner, users, members, is_owner = await self._authorize(
                organization_id, token, data.password, target_id=user_id, assignment=True)
            role = await self.session.scalar(select(OrganizationRole).where(
                OrganizationRole.organization_id == organization_id, OrganizationRole.id == role_id).with_for_update())
            if role is None:
                self.deny()
            self.check_revision(data.expected_role_revision, role.revision)
            if data.status == RoleAssignmentStatus.ACTIVE and (
                role.status != RoleStatus.ACTIVE or users[user_id].status != UserStatus.ACTIVE or members[user_id].status != MembershipStatus.ACTIVE
            ):
                self.deny()
            delegation = None
            if not is_owner:
                delegation = await self.session.get(OrganizationAccessDelegation, (organization_id, actor_id))
                ceiling = set((await self.session.scalars(select(OrganizationDelegationPermission.permission_key).where(
                    OrganizationDelegationPermission.organization_id == organization_id,
                    OrganizationDelegationPermission.user_id == actor_id))).all())
                if not set(await self._permissions(organization_id, role_id)) <= ceiling:
                    self.deny()
            assignment = await self.session.get(OrganizationRoleAssignment, (organization_id, user_id, role_id))
            self.check_revision(data.expected_revision, assignment.revision if assignment else 0)
            before = {} if assignment is None else {"revision": assignment.revision, "status": assignment.status,
                "delegated_by_user_id": str(assignment.delegated_by_user_id) if assignment.delegated_by_user_id else None,
                "delegation_revision": assignment.delegation_revision}
            if assignment is None:
                assignment = OrganizationRoleAssignment(organization_id=organization_id, user_id=user_id, role_id=role_id)
                self.session.add(assignment)
                assignment.revision = 1
            else:
                assignment.revision += 1
            assignment.status = data.status
            assignment.delegated_by_user_id = None if is_owner else actor_id
            assignment.delegation_revision = None if is_owner else delegation.revision
            after = {"revision": assignment.revision, "status": assignment.status,
                "delegated_by_user_id": str(assignment.delegated_by_user_id) if assignment.delegated_by_user_id else None,
                "delegation_revision": assignment.delegation_revision}
            self._audit(organization_id, actor_id, "ASSIGNMENT_SET", before, after, role_id=role_id, target_id=user_id)
            await self.session.flush()
            result = AssignmentResponse(user_id=user_id, role_id=role_id, status=assignment.status, revision=assignment.revision)
        return result

    async def set_delegation(self, organization_id: UUID, user_id: UUID, data, *, token):
        async with self.session.begin():
            actor_id, owner, users, members, _ = await self._authorize(organization_id, token, data.password, target_id=user_id)
            if actor_id == user_id:
                self.deny()
            if data.status == RoleAssignmentStatus.ACTIVE and (
                users[user_id].status != UserStatus.ACTIVE or members[user_id].status != MembershipStatus.ACTIVE
            ):
                self.deny()
            delegation = await self.session.get(OrganizationAccessDelegation, (organization_id, user_id))
            self.check_revision(data.expected_revision, delegation.revision if delegation else 0)
            previous_permissions = sorted((await self.session.scalars(select(OrganizationDelegationPermission.permission_key).where(
                OrganizationDelegationPermission.organization_id == organization_id,
                OrganizationDelegationPermission.user_id == user_id))).all())
            before = {} if delegation is None else {"revision": delegation.revision, "status": delegation.status,
                "permissions": previous_permissions, "owner_revision": delegation.owner_revision}
            if delegation is None:
                delegation = OrganizationAccessDelegation(organization_id=organization_id, user_id=user_id,
                    granted_by_user_id=actor_id, owner_revision=owner.revision, revision=1)
                self.session.add(delegation)
            else:
                delegation.revision += 1
                delegation.granted_by_user_id, delegation.owner_revision = actor_id, owner.revision
            delegation.status = data.status
            await self.session.flush()
            await self.session.execute(delete(OrganizationDelegationPermission).where(
                OrganizationDelegationPermission.organization_id == organization_id,
                OrganizationDelegationPermission.user_id == user_id))
            self.session.add_all([OrganizationDelegationPermission(organization_id=organization_id, user_id=user_id,
                permission_key=permission) for permission in data.permissions])
            self._audit(organization_id, actor_id, "DELEGATION_SET", before,
                {"revision": delegation.revision, "status": delegation.status, "permissions": list(data.permissions),
                 "owner_revision": owner.revision}, target_id=user_id)
            await self.session.flush()
            result = DelegationResponse(user_id=user_id, status=delegation.status, revision=delegation.revision,
                                        permissions=data.permissions, effective=delegation.status == RoleAssignmentStatus.ACTIVE)
        return result

    async def list_roles(self, organization_id, actor_id, *, cursor=None, limit=50):
        if not await OrganizationAccessPolicy(self.session).has_permission(actor_id, organization_id, PermissionKey.ROLES_READ):
            self.deny()
        query = select(OrganizationRole).where(OrganizationRole.organization_id == organization_id).order_by(OrganizationRole.id).limit(limit+1)
        if cursor is not None:
            query = query.where(OrganizationRole.id > cursor)
        roles = (await self.session.scalars(query)).all()
        page = roles[:limit]
        permissions = (await self.session.execute(select(OrganizationRolePermission.role_id, OrganizationRolePermission.permission_key).where(
            OrganizationRolePermission.organization_id == organization_id,
            OrganizationRolePermission.role_id.in_([role.id for role in page])))).all()
        by_role = {role.id: [] for role in page}
        for role_id, key in permissions:
            by_role[role_id].append(key)
        return {"items": [self._role_response(role, sorted(by_role[role.id])) for role in page],
                "next_cursor": page[-1].id if len(roles) > limit else None}

    async def member_access(self, organization_id, actor_id, user_id, *, delegation=False, cursor=None, limit=50):
        # Leitura administrativa mínima; não entrega nome, e-mail ou credenciais.
        policy = OrganizationAccessPolicy(self.session)
        owner_access = await policy.has_permission(actor_id, organization_id, PermissionKey.DELEGATIONS_MANAGE)
        if not owner_access and (delegation or not await policy.has_permission(actor_id, organization_id, PermissionKey.ASSIGNMENTS_MANAGE)):
            self.deny()
        if await self.session.get(OrganizationMembership, (user_id, organization_id)) is None:
            self.deny()
        if not owner_access:
            owner_id = await self.session.scalar(select(OrganizationOwnership.user_id).where(
                OrganizationOwnership.organization_id == organization_id))
            if user_id in (actor_id, owner_id) or await self.session.get(OrganizationAccessDelegation, (organization_id, user_id)) is not None:
                self.deny()
        if delegation:
            row = await self.session.get(OrganizationAccessDelegation, (organization_id, user_id))
            if row is None:
                return None
            permissions = sorted((await self.session.scalars(select(OrganizationDelegationPermission.permission_key).where(
                OrganizationDelegationPermission.organization_id == organization_id,
                OrganizationDelegationPermission.user_id == user_id))).all())
            effective = await OrganizationAccessPolicy(self.session).has_permission(user_id, organization_id, PermissionKey.ASSIGNMENTS_MANAGE)
            return DelegationResponse(user_id=user_id, status=row.status, revision=row.revision, permissions=permissions, effective=effective)
        query = select(OrganizationRoleAssignment).where(
            OrganizationRoleAssignment.organization_id == organization_id, OrganizationRoleAssignment.user_id == user_id,
        ).order_by(OrganizationRoleAssignment.role_id).limit(limit+1)
        if not owner_access:
            ceiling = (await self.session.scalars(select(OrganizationDelegationPermission.permission_key).where(
                OrganizationDelegationPermission.organization_id == organization_id,
                OrganizationDelegationPermission.user_id == actor_id))).all()
            outside = select(OrganizationRolePermission.role_id).where(
                OrganizationRolePermission.organization_id == organization_id,
                OrganizationRolePermission.role_id == OrganizationRoleAssignment.role_id,
                OrganizationRolePermission.permission_key.not_in(ceiling),
            ).correlate(OrganizationRoleAssignment).exists()
            query = query.where(~outside)
        if cursor is not None:
            query = query.where(OrganizationRoleAssignment.role_id > cursor)
        rows = (await self.session.scalars(query)).all()
        return {"items": [AssignmentResponse(user_id=user_id, role_id=row.role_id, status=row.status, revision=row.revision) for row in rows[:limit]],
                "next_cursor": rows[limit-1].role_id if len(rows) > limit else None}

    async def list_members(self, organization_id, actor_id, *, cursor=None, limit=50):
        if not await OrganizationAccessPolicy(self.session).has_permission(actor_id, organization_id, PermissionKey.MEMBERS_READ):
            self.deny()
        query = select(OrganizationMembership.user_id, User.name, User.email, OrganizationMembership.status,
                       OrganizationMembership.can_read_organization, OrganizationMembership.revision).join(User).where(
            OrganizationMembership.organization_id == organization_id).order_by(OrganizationMembership.user_id).limit(limit+1)
        if cursor is not None:
            query = query.where(OrganizationMembership.user_id > cursor)
        rows = (await self.session.execute(query)).all()
        return {"items": [{"user_id": row.user_id, "name": row.name, "email": row.email, "status": row.status,
                           "legacy_read": row.can_read_organization, "revision": row.revision} for row in rows[:limit]],
                "next_cursor": rows[limit-1].user_id if len(rows) > limit else None}
