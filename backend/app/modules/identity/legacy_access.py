"""Substitui a flag antiga por leitura direta em perfil, com revisão e auditoria."""

from uuid import UUID

from sqlalchemy import select

from app.modules.identity.access_models import OrganizationRole, OrganizationRoleAssignment, RoleAssignmentStatus, RoleStatus
from app.modules.identity.authorization import OrganizationAccessPolicy
from app.modules.identity.legacy_access_schemas import LegacyReadConversionResponse, ReadAccessReview
from app.modules.identity.models import MembershipStatus, UserStatus
from app.modules.identity.permissions import PermissionKey
from app.modules.identity.roles import AccessRevisionConflictError, RoleService


class LegacyReadService(RoleService):
    async def _review(self, organization_id, user_id):
        row = (await self.session.execute(OrganizationAccessPolicy(self.session).read_access_query(user_id, organization_id))).one_or_none()
        if row is None:
            self.deny()
        member, user_status, profile_read = row
        legacy_effective = bool(member.can_read_organization and member.status == MembershipStatus.ACTIVE and user_status == UserStatus.ACTIVE)
        return ReadAccessReview(user_id=user_id, revision=member.revision, membership_status=member.status,
            user_status=user_status, legacy_read=member.can_read_organization, legacy_effective=legacy_effective,
            profile_read=profile_read, effective_read=legacy_effective or profile_read)

    async def review(self, organization_id: UUID, actor_id: UUID, user_id: UUID):
        if not await OrganizationAccessPolicy(self.session).has_permission(actor_id, organization_id, PermissionKey.MEMBERS_READ):
            self.deny()
        return await self._review(organization_id, user_id)

    @staticmethod
    def _require_legacy(member, expected_revision):
        RoleService.check_revision(expected_revision, member.revision)
        if not member.can_read_organization:
            raise AccessRevisionConflictError("Concessão alterada. Atualize os dados antes de tentar novamente.")

    async def convert(self, organization_id: UUID, user_id: UUID, data, *, token):
        async with self.session.begin():
            actor_id, _, users, members, _ = await self._authorize(organization_id, token, data.password, target_id=user_id)
            member = members[user_id]
            self._require_legacy(member, data.expected_revision)
            if member.status != MembershipStatus.ACTIVE or users[user_id].status != UserStatus.ACTIVE:
                self.deny()
            role = await self.session.scalar(select(OrganizationRole).where(
                OrganizationRole.id == data.role_id, OrganizationRole.organization_id == organization_id).with_for_update())
            if role is None or role.status != RoleStatus.ACTIVE:
                self.deny()
            self.check_revision(data.expected_role_revision, role.revision)
            if set(await self._permissions(organization_id, role.id)) != {PermissionKey.ORGANIZATION_READ}:
                self.deny()
            assignment = await self.session.get(OrganizationRoleAssignment, (organization_id, user_id, role.id))
            self.check_revision(data.expected_assignment_revision, assignment.revision if assignment else 0)
            before = {"revision": member.revision, "legacy_read": True, "role_revision": role.revision,
                "assignment": {} if assignment is None else {"revision": assignment.revision, "status": assignment.status,
                    "delegated_by_user_id": str(assignment.delegated_by_user_id) if assignment.delegated_by_user_id else None,
                    "delegation_revision": assignment.delegation_revision}}
            if assignment is None:
                assignment = OrganizationRoleAssignment(organization_id=organization_id, user_id=user_id, role_id=role.id, revision=1)
                self.session.add(assignment)
            else:
                assignment.revision += 1
            assignment.status = RoleAssignmentStatus.ACTIVE
            # A flag anterior era direta; sua substituição não depende de um delegado.
            assignment.delegated_by_user_id, assignment.delegation_revision = None, None
            member.can_read_organization = False
            member.revision += 1
            after = {"revision": member.revision, "legacy_read": False, "role_revision": role.revision,
                "assignment": {"revision": assignment.revision, "status": assignment.status,
                               "delegated_by_user_id": None, "delegation_revision": None}}
            self._audit(organization_id, actor_id, "LEGACY_READ_CONVERTED", before, after, role_id=role.id, target_id=user_id)
            await self.session.flush()
            review = await self._review(organization_id, user_id)
            result = LegacyReadConversionResponse(**review.model_dump(), role_id=role.id, assignment_revision=assignment.revision)
        return result

    async def revoke(self, organization_id: UUID, user_id: UUID, data, *, token):
        async with self.session.begin():
            actor_id, _, users, members, _ = await self._authorize(organization_id, token, data.password, target_id=user_id)
            member = members[user_id]
            self._require_legacy(member, data.expected_revision)
            before = {"revision": member.revision, "legacy_read": True}
            member.can_read_organization = False
            member.revision += 1
            self._audit(organization_id, actor_id, "LEGACY_READ_REVOKED", before,
                {"revision": member.revision, "legacy_read": False}, target_id=user_id)
            await self.session.flush()
            result = await self._review(organization_id, user_id)
        return result
