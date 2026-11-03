"""Contratos do segmento Empresarial e habilitações por empresa."""
import sqlalchemy as sa
from sqlalchemy.orm import mapped_column

from app.database.base import Base


class BusinessContract(Base):
    __tablename__ = "business_contracts"
    __table_args__ = (
        sa.CheckConstraint("plan IN ('ESSENTIAL','PROFESSIONAL','ENTERPRISE')", name="ck_business_contract_plan"),
        sa.CheckConstraint("status IN ('PENDING','ACTIVE','SUSPENDED','CANCELLED')", name="ck_business_contract_status"),
        sa.CheckConstraint("valid_until > valid_from", name="ck_business_contract_period"),
    )

    organization_id = mapped_column(sa.Uuid, sa.ForeignKey("organizations.id", ondelete="RESTRICT"), primary_key=True)
    plan = mapped_column(sa.String(20), nullable=False)
    catalog_version = mapped_column(sa.String(40), nullable=False)
    status = mapped_column(sa.String(20), nullable=False)
    valid_from = mapped_column(sa.DateTime(timezone=True), nullable=False)
    valid_until = mapped_column(sa.DateTime(timezone=True), nullable=False)


class BusinessCompanyActivation(Base):
    __tablename__ = "business_company_activations"
    __table_args__ = (
        sa.ForeignKeyConstraint(
            ("organization_id", "company_id"), ("companies.organization_id", "companies.id"),
            ondelete="RESTRICT", name="fk_business_activation_company",
        ),
    )

    organization_id = mapped_column(sa.Uuid, sa.ForeignKey("business_contracts.organization_id", ondelete="RESTRICT"), primary_key=True)
    company_id = mapped_column(sa.Uuid, primary_key=True)
