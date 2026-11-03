"""Decisões puras sobre snapshots internos confiáveis, sem ler dados do navegador.

Esta camada ainda não persiste contratos nem protege rotas existentes. O adaptador
futuro deve carregar e revalidar os snapshots no banco na mesma transação da escrita.
Uma decisão de cota não reserva capacidade nem substitui lock/transação.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.modules.commercial.catalog import ACTIVE_SEGMENTS, CATALOG_VERSION, FEATURES, PLANS, Feature, Plan, Segment


class ContractState(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CANCELLED = "CANCELLED"
    PENDING = "PENDING"


class Denial(StrEnum):
    INVALID_CONTEXT = "INVALID_CONTEXT"
    UNAUTHORIZED = "UNAUTHORIZED"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
    SEGMENT_UNAVAILABLE = "SEGMENT_UNAVAILABLE"
    NO_CONTRACT = "NO_CONTRACT"
    INACTIVE_CONTRACT = "INACTIVE_CONTRACT"
    CONTRACT_OUTSIDE_VALIDITY = "CONTRACT_OUTSIDE_VALIDITY"
    UNKNOWN_CATALOG = "UNKNOWN_CATALOG"
    COMPANY_DISABLED = "COMPANY_DISABLED"
    FEATURE_NOT_INCLUDED = "FEATURE_NOT_INCLUDED"
    FEATURE_UNAVAILABLE = "FEATURE_UNAVAILABLE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    UNDEFINED_LIMIT = "UNDEFINED_LIMIT"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"


@dataclass(frozen=True)
class Decision:
    allowed: bool
    denial: Denial | None = None


@dataclass(frozen=True)
class AccessSnapshot:
    """Produzido pela autorização do servidor, nunca desserializado de requisição."""
    user_id: UUID
    organization_id: UUID
    company_id: UUID
    segment: Segment
    active_user: bool = False
    active_membership: bool = False
    active_organization: bool = False
    active_company: bool = False
    company_authorized: bool = False
    permissions: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ContractSnapshot:
    organization_id: UUID
    segment: Segment
    plan: Plan
    catalog_version: str
    state: ContractState
    valid_from: datetime
    valid_until: datetime
    enabled_companies: frozenset[UUID] = field(default_factory=frozenset)
    # Enterprise exige dimensionamento explícito; None não significa ilimitado.
    companies_limit: int | None = None
    users_limit: int | None = None


def _aware(value):
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _contract_problem(access, contract, now):
    if type(access) is not AccessSnapshot or not _aware(now):
        return Denial.INVALID_CONTEXT
    if (not all(type(value) is UUID for value in (access.user_id, access.organization_id, access.company_id))
        or type(access.segment) is not Segment or type(access.permissions) is not frozenset
        or not all(type(permission) is str for permission in access.permissions)):
        return Denial.INVALID_CONTEXT
    flags = (access.active_user, access.active_membership, access.active_organization,
             access.active_company, access.company_authorized)
    if not all(type(value) is bool for value in flags):
        return Denial.INVALID_CONTEXT
    if not all(flags):
        return Denial.UNAUTHORIZED
    if access.segment not in ACTIVE_SEGMENTS:
        return Denial.SEGMENT_UNAVAILABLE
    if contract is None:
        return Denial.NO_CONTRACT
    if (type(contract) is not ContractSnapshot or type(contract.organization_id) is not UUID
        or type(contract.segment) is not Segment or type(contract.plan) is not Plan
        or type(contract.state) is not ContractState or type(contract.catalog_version) is not str
        or type(contract.enabled_companies) is not frozenset
        or not all(type(company) is UUID for company in contract.enabled_companies)
        or not _aware(contract.valid_from) or not _aware(contract.valid_until)
        or contract.valid_until <= contract.valid_from):
        return Denial.INVALID_CONTEXT
    if access.organization_id != contract.organization_id or access.segment != contract.segment:
        return Denial.CONTEXT_MISMATCH
    if contract.state != ContractState.ACTIVE:
        return Denial.INACTIVE_CONTRACT
    if not contract.valid_from <= now < contract.valid_until:
        return Denial.CONTRACT_OUTSIDE_VALIDITY
    if contract.catalog_version != CATALOG_VERSION:
        return Denial.UNKNOWN_CATALOG
    if access.company_id not in contract.enabled_companies:
        return Denial.COMPANY_DISABLED
    return None


def evaluate_access(access: AccessSnapshot, contract: ContractSnapshot | None, *,
                    feature: Feature, permission: str, now: datetime) -> Decision:
    """Interseção de contrato, disponibilidade e permissão para uma operação."""
    problem = _contract_problem(access, contract, now)
    if problem:
        return Decision(False, problem)
    if type(feature) is not Feature or type(permission) is not str:
        return Decision(False, Denial.INVALID_CONTEXT)
    if feature not in PLANS[contract.plan].features:
        return Decision(False, Denial.FEATURE_NOT_INCLUDED)
    definition = FEATURES[feature]
    if not definition.available:
        return Decision(False, Denial.FEATURE_UNAVAILABLE)
    if permission not in definition.permissions or permission not in access.permissions:
        return Decision(False, Denial.PERMISSION_DENIED)
    return Decision(True)


def evaluate_capacity(access: AccessSnapshot, contract: ContractSnapshot | None, *,
                      resource: str, used: int, requested: int, now: datetime) -> Decision:
    """Preflight de cota. O futuro writer precisa revalidar e reservar sob lock."""
    problem = _contract_problem(access, contract, now)
    if problem:
        return Decision(False, problem)
    if resource not in ("companies", "users") or type(used) is not int or type(requested) is not int or used < 0 or requested < 1:
        return Decision(False, Denial.INVALID_CONTEXT)
    limit = getattr(PLANS[contract.plan], resource)
    override = contract.companies_limit if resource == "companies" else contract.users_limit
    if contract.plan == Plan.ENTERPRISE:
        limit = override
    elif override is not None:
        # Aditivos ainda não estão modelados; não ampliar uma cota por campo arbitrário.
        return Decision(False, Denial.INVALID_CONTEXT)
    if limit is None:
        return Decision(False, Denial.UNDEFINED_LIMIT)
    if type(limit) is not int or limit < 1:
        return Decision(False, Denial.INVALID_CONTEXT)
    if used + requested > limit:
        return Decision(False, Denial.LIMIT_EXCEEDED)
    return Decision(True)
