"""Metadados de auditoria; nunca armazenar payloads ou valores pessoais."""
from uuid import uuid4
from sqlalchemy import CheckConstraint, DateTime, Index, String, Uuid, func
from sqlalchemy.orm import mapped_column
from app.database.base import Base
from app.modules.finance.models import actor_member, scope_company


class OperationEvent(Base):
    __tablename__ = 'operation_events'
    __table_args__ = (
        scope_company('fk_operation_events_company'),
        actor_member('actor_user_id', 'fk_operation_events_actor'),
        CheckConstraint("domain IN ('BILLING', 'PEOPLE', 'ACCOUNTS')", name='ck_operation_events_domain'),
        CheckConstraint("action IN ('CREATED', 'UPDATED', 'RECEIVED', 'REVERSAL', 'TERMINATED')", name='ck_operation_events_action'),
        CheckConstraint("resource_type IN ('BILLING', 'CUSTOMER', 'RECEIPT', 'COLLABORATOR', 'ACCOUNT')", name='ck_operation_events_resource'),
        Index('ix_operation_events_scope_time', 'organization_id', 'company_id', 'created_at', 'id'),
    )
    id = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id = mapped_column(Uuid, nullable=False)
    company_id = mapped_column(Uuid, nullable=False)
    actor_user_id = mapped_column(Uuid, nullable=False)
    domain = mapped_column(String(12), nullable=False)
    resource_type = mapped_column(String(16), nullable=False)
    resource_id = mapped_column(Uuid, nullable=False)
    action = mapped_column(String(12), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def record_event(session, organization_id, company_id, actor, domain, resource_type, resource_id, action):
    session.add(OperationEvent(organization_id=organization_id, company_id=company_id,
        actor_user_id=actor, domain=domain, resource_type=resource_type, resource_id=resource_id, action=action))
