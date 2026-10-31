"""Autoriza escritas administrativas com locks e reautenticação, sem lógica de perfis."""

from datetime import datetime, timezone

from sqlalchemy import select, text

from app.modules.identity.access_models import OrganizationOwnership
from app.modules.identity.authorization import OrganizationAccessPolicy
from app.modules.identity.models import MembershipStatus, OrganizationMembership, User, UserPasswordCredential, UserSession, UserStatus
from app.modules.identity.passwords import run_password_work, verify_password
from app.modules.identity.permission_models import OrganizationAccessDelegation
from app.modules.identity.permissions import PermissionKey
from app.modules.identity.sessions import SessionService
from app.modules.organizations.models import Organization, OrganizationStatus


class AccessManagementDeniedError(Exception):
    """Nega sem informar existência de conta, recurso ou tenant."""


class AccessRevisionConflictError(Exception):
    """Exige revisão atual antes de substituir uma configuração."""


async def authorize_access_change(session, organization_id, token, password, *, idle_timeout,
                                  target_id=None, assignment=False, verifier=None):
    """Executa dentro da transação do serviço; reavalia autoridade no banco.

    `verifier` é uma dependência interna para testes, nunca parâmetro do cliente.
    O adaptador aplica rate limit e capacidade antes de chamar este fluxo.
    """
    def deny():
        raise AccessManagementDeniedError("Operação de acesso não permitida.")

    await session.execute(text("SET LOCAL lock_timeout = '5s'"))
    organization = await session.scalar(select(Organization).where(Organization.id == organization_id).with_for_update())
    if organization is None or organization.status != OrganizationStatus.ACTIVE:
        deny()
    owner = await session.scalar(select(OrganizationOwnership).where(
        OrganizationOwnership.organization_id == organization_id).with_for_update())
    if owner is None:
        deny()
    token_hash = SessionService._token_hash(token)
    actor_id = await session.scalar(select(UserSession.user_id).where(UserSession.token_hash == token_hash))
    if actor_id is None:
        deny()
    ids = {actor_id, owner.user_id} | ({target_id} if target_id is not None else set())
    users = {user.id: user for user in (await session.scalars(select(User).where(
        User.id.in_(ids)).order_by(User.id).with_for_update())).all()}
    members = {member.user_id: member for member in (await session.scalars(select(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.user_id.in_(ids)).order_by(OrganizationMembership.user_id).with_for_update())).all()}
    actor = users.get(actor_id)
    if actor is None or actor.status != UserStatus.ACTIVE or actor_id not in members or members[actor_id].status != MembershipStatus.ACTIVE:
        deny()
    if target_id is not None and (target_id not in users or target_id not in members):
        deny()
    is_owner = owner.user_id == actor_id
    if not is_owner:
        if not assignment or not await OrganizationAccessPolicy(session).has_permission(actor_id, organization_id, PermissionKey.ASSIGNMENTS_MANAGE):
            deny()
        if target_id in (actor_id, owner.user_id):
            deny()
        if await session.get(OrganizationAccessDelegation, (organization_id, target_id)) is not None:
            deny()
    credential = await session.scalar(select(UserPasswordCredential.password_hash).where(
        UserPasswordCredential.user_id == actor_id).with_for_update())
    check_password = verifier if verifier is not None else verify_password
    if credential is None or not (await run_password_work(check_password(password, credential)))[0]:
        deny()
    login = await session.scalar(select(UserSession).where(UserSession.token_hash == token_hash).with_for_update())
    now = datetime.now(timezone.utc)
    if login is None or login.revoked_at is not None or not login.created_at <= now < login.expires_at:
        deny()
    login.expires_at = max(login.expires_at, now + idle_timeout)
    return actor_id, owner, users, members, is_owner
