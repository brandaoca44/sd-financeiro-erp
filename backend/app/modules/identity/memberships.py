"""Altera o vínculo do tenant sem mudar identidade global ou deixar o tenant sem Master."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select, update

from app.modules.identity.access_models import OrganizationRoleAssignment, RoleAssignmentStatus
from app.modules.identity.authorization import OrganizationAccessPolicy
from app.modules.identity.company_access_models import CompanyPermissionGrant
from app.modules.identity.invitation_models import OrganizationInvitation
from app.modules.identity.membership_schemas import MembershipStatusResponse
from app.modules.identity.models import MembershipStatus, OrganizationMembership, UserStatus
from app.modules.identity.permission_models import OrganizationAccessDelegation
from app.modules.identity.permissions import PermissionKey
from app.modules.identity.roles import RoleService


class MembershipService(RoleService):
    """Reutiliza locks, confirmação de senha, conflitos e auditoria da gestão de acesso."""

    async def read_status(self, organization_id: UUID, actor_id: UUID, user_id: UUID):
        if not await OrganizationAccessPolicy(self.session).has_permission(actor_id, organization_id, PermissionKey.MEMBERS_READ):
            self.deny()
        member = await self.session.get(OrganizationMembership, (user_id, organization_id))
        if member is None:
            self.deny()
        return MembershipStatusResponse(user_id=user_id, status=member.status, revision=member.revision)

    async def set_status(self, organization_id: UUID, user_id: UUID, data, *, token):
        async with self.session.begin():
            actor_id, owner, users, members, _ = await self._authorize(
                organization_id, token, data.password, target_id=user_id)
            member = members[user_id]
            # Inclusive um pedido de ativação não altera o vínculo do proprietário atual.
            if user_id == owner.user_id:
                self.deny()
            self.check_revision(data.expected_revision, member.revision)
            if data.status == MembershipStatus.ACTIVE and users[user_id].status != UserStatus.ACTIVE:
                self.deny()
            before = {"status": member.status, "revision": member.revision,
                      "legacy_read": member.can_read_organization}
            reset_grants = data.status == MembershipStatus.INACTIVE or member.status == MembershipStatus.INACTIVE
            assignments_reset, invitations_revoked, company_grants_reset = 0, 0, 0
            delegation_before = None
            if reset_grants:
                member.can_read_organization = False
                changed_company_grants = await self.session.execute(update(CompanyPermissionGrant).where(
                    CompanyPermissionGrant.organization_id == organization_id, CompanyPermissionGrant.user_id == user_id,
                ).values(status="INACTIVE", revision=CompanyPermissionGrant.revision + 1, updated_by_user_id=actor_id))
                company_grants_reset = changed_company_grants.rowcount
                # Inativa tanto os perfis do alvo quanto concessões originadas de sua delegação.
                changed = await self.session.execute(update(OrganizationRoleAssignment).where(
                    OrganizationRoleAssignment.organization_id == organization_id,
                    or_(OrganizationRoleAssignment.user_id == user_id,
                        OrganizationRoleAssignment.delegated_by_user_id == user_id),
                ).values(status=RoleAssignmentStatus.INACTIVE, revision=OrganizationRoleAssignment.revision + 1))
                assignments_reset = changed.rowcount
                delegation = await self.session.get(OrganizationAccessDelegation, (organization_id, user_id))
                if delegation is not None:
                    delegation_before = {"status": delegation.status, "revision": delegation.revision}
                    delegation.status = "INACTIVE"
                    delegation.revision += 1
                now = datetime.now(timezone.utc)
                changed = await self.session.execute(update(OrganizationInvitation).where(
                    OrganizationInvitation.organization_id == organization_id,
                    OrganizationInvitation.accepted_at.is_(None), OrganizationInvitation.revoked_at.is_(None),
                    or_(OrganizationInvitation.issued_by_user_id == user_id,
                        OrganizationInvitation.email == users[user_id].email.lower()),
                ).values(revoked_at=now, revoked_by_user_id=actor_id))
                invitations_revoked = changed.rowcount
            member.status = data.status
            member.revision += 1
            after = {"status": member.status, "revision": member.revision, "legacy_read": member.can_read_organization,
                     "grants_reset": reset_grants, "assignments_reset": assignments_reset,
                     "invitations_revoked": invitations_revoked, "company_grants_reset": company_grants_reset}
            if delegation_before is not None:
                before["delegation"] = delegation_before
                after["delegation"] = {"status": "INACTIVE", "revision": delegation_before["revision"] + 1}
            self._audit(organization_id, actor_id, "MEMBERSHIP_SET", before, after, target_id=user_id)
            await self.session.flush()
            result = MembershipStatusResponse(user_id=user_id, status=member.status, revision=member.revision)
        return result
