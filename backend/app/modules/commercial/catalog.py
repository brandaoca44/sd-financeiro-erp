"""Catálogo imutável de trabalho. Inclusão no plano não indica disponibilidade."""
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class Segment(StrEnum):
    BUSINESS = "BUSINESS"
    HEALTH = "HEALTH"
    RETAIL = "RETAIL"
    INDUSTRY = "INDUSTRY"


class Plan(StrEnum):
    ESSENTIAL = "ESSENTIAL"
    PROFESSIONAL = "PROFESSIONAL"
    ENTERPRISE = "ENTERPRISE"


class Feature(StrEnum):
    PAYABLES = "business.payables"
    PAYABLES_SUMMARY = "business.payables.summary"
    RECEIVABLES = "business.receivables"
    PARTIES = "business.parties"
    PRODUCTS = "business.products"
    SERVICES = "business.services"
    EXPENSES = "business.expenses"
    BOLETOS = "business.boletos"
    DUE_ALERTS = "business.due_alerts"
    DOCUMENTS = "business.documents"
    BASIC_RESULTS = "business.results.basic"
    STAFF_COSTS = "business.staff_costs"
    TAX_BASIC = "business.tax.basic"
    CASHFLOW = "business.cashflow"
    IMPORT_STANDARD = "business.import.standard"
    IMPORT_MAPPING = "business.import.mapping"
    CONSOLIDATION = "business.consolidation"
    CONTRACTS = "business.contracts"
    PLANNING = "business.planning"
    OPPORTUNITIES = "business.opportunities"
    APPROVALS = "business.approvals"
    EXPENSE_ALLOCATION = "business.expenses.allocation"
    STAFF_ANALYSIS = "business.staff_analysis"
    TAX_REVIEW = "business.tax.review"
    GOVERNANCE = "business.governance"
    INTEGRATIONS = "business.integrations"
    TAX_GOVERNANCE = "business.tax.governance"
    PRODUCT_ASSISTANCE = "assistance.product"
    COMPANY_ASSISTANCE = "assistance.company"
    PRIVATE_KNOWLEDGE = "assistance.private_knowledge"
    LANGUAGES = "interface.languages"


@dataclass(frozen=True)
class FeatureDefinition:
    key: Feature
    available: bool = False
    permissions: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PlanDefinition:
    key: Plan
    features: frozenset[Feature]
    companies: int | None
    users: int | None


CATALOG_VERSION = "business-v1-draft"
CATALOG_PUBLISHED = False
ACTIVE_SEGMENTS = frozenset({Segment.BUSINESS})
_essential = frozenset({Feature.PAYABLES, Feature.PAYABLES_SUMMARY, Feature.RECEIVABLES, Feature.PARTIES,
    Feature.PRODUCTS, Feature.SERVICES, Feature.EXPENSES, Feature.BOLETOS, Feature.DUE_ALERTS,
    Feature.DOCUMENTS, Feature.BASIC_RESULTS, Feature.STAFF_COSTS, Feature.TAX_BASIC, Feature.CASHFLOW,
    Feature.IMPORT_STANDARD, Feature.PRODUCT_ASSISTANCE, Feature.LANGUAGES})
_professional = _essential | frozenset({Feature.IMPORT_MAPPING, Feature.CONSOLIDATION, Feature.CONTRACTS,
    Feature.PLANNING, Feature.OPPORTUNITIES, Feature.APPROVALS, Feature.EXPENSE_ALLOCATION,
    Feature.STAFF_ANALYSIS, Feature.TAX_REVIEW, Feature.COMPANY_ASSISTANCE})
_enterprise = _professional | frozenset({Feature.GOVERNANCE, Feature.INTEGRATIONS,
    Feature.TAX_GOVERNANCE, Feature.PRIVATE_KNOWLEDGE})
PLANS = MappingProxyType({
    Plan.ESSENTIAL: PlanDefinition(Plan.ESSENTIAL, _essential, companies=1, users=3),
    Plan.PROFESSIONAL: PlanDefinition(Plan.PROFESSIONAL, _professional, companies=5, users=20),
    Plan.ENTERPRISE: PlanDefinition(Plan.ENTERPRISE, _enterprise, companies=None, users=None),
})
_definitions = {feature: FeatureDefinition(feature) for feature in Feature}
_definitions[Feature.PAYABLES] = FeatureDefinition(Feature.PAYABLES, available=True,
    permissions=frozenset({"payables.read", "payables.manage", "payables.settle", "payables.reverse"}))
_definitions[Feature.PAYABLES_SUMMARY] = FeatureDefinition(Feature.PAYABLES_SUMMARY, available=True,
    permissions=frozenset({"payables.read"}))
FEATURES = MappingProxyType(_definitions)
# Remover referências mutáveis de construção. Nenhuma API altera este catálogo.
del _definitions
