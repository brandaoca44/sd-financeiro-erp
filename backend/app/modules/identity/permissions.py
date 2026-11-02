"""Catálogo fechado das ações existentes; cargos não são concessões."""

from enum import StrEnum


class PermissionKey(StrEnum):
    ORGANIZATION_READ = "organizations.read"
    ROLES_READ = "identity.roles.read"
    ROLES_MANAGE = "identity.roles.manage"
    ASSIGNMENTS_MANAGE = "identity.assignments.manage"
    DELEGATIONS_MANAGE = "identity.delegations.manage"
    MEMBERS_READ = "identity.members.read"
    MEMBERS_MANAGE = "identity.members.manage"
    COMPANIES_READ = "companies.read"
    COMPANIES_MANAGE = "companies.manage"
    COMPANY_ACCESS_MANAGE = "companies.access.manage"
    PAYABLES_READ = "payables.read"
    PAYABLES_MANAGE = "payables.manage"
    PAYABLES_SETTLE = "payables.settle"
    PAYABLES_REVERSE = "payables.reverse"


class FinancialPermissionKey(StrEnum):
    READ = "payables.read"
    MANAGE = "payables.manage"
    SETTLE = "payables.settle"
    REVERSE = "payables.reverse"


FINANCIAL_PERMISSIONS = frozenset(FinancialPermissionKey)


ROLE_PERMISSIONS = frozenset({PermissionKey.ORGANIZATION_READ, PermissionKey.ROLES_READ})
PERMISSION_CATALOG = (
    {"key": PermissionKey.ORGANIZATION_READ, "description": "Consultar metadados da organização",
     "scope": "ORGANIZATION", "grant_source": "ROLE_OR_LEGACY"},
    {"key": PermissionKey.ROLES_READ, "description": "Consultar perfis e suas permissões",
     "scope": "ORGANIZATION", "grant_source": "ROLE_OR_OWNER"},
    {"key": PermissionKey.ROLES_MANAGE, "description": "Criar, editar e inativar perfis",
     "scope": "ORGANIZATION", "grant_source": "OWNER"},
    {"key": PermissionKey.ASSIGNMENTS_MANAGE, "description": "Atribuir ou revogar perfis de vínculos existentes",
     "scope": "ORGANIZATION", "grant_source": "OWNER_OR_BOUNDED_DELEGATION"},
    {"key": PermissionKey.DELEGATIONS_MANAGE, "description": "Definir e revogar tetos de delegação",
     "scope": "ORGANIZATION", "grant_source": "OWNER"},
    {"key": PermissionKey.MEMBERS_READ, "description": "Consultar diretório mínimo de vínculos da organização",
     "scope": "ORGANIZATION", "grant_source": "OWNER"},
    {"key": PermissionKey.MEMBERS_MANAGE, "description": "Administrar status do vínculo e revisar a leitura antiga",
     "scope": "ORGANIZATION", "grant_source": "OWNER"},
    {"key": PermissionKey.COMPANIES_READ, "description": "Consultar cadastro jurídico de empresa autorizada",
     "scope": "COMPANY", "grant_source": "OWNER_OR_COMPANY_GRANT"},
    {"key": PermissionKey.COMPANIES_MANAGE, "description": "Cadastrar e atualizar empresas do tenant",
     "scope": "ORGANIZATION", "grant_source": "OWNER"},
    {"key": PermissionKey.COMPANY_ACCESS_MANAGE, "description": "Administrar concessões conhecidas por empresa para um vínculo",
     "scope": "COMPANY", "grant_source": "OWNER"},
)
PERMISSION_CATALOG += tuple({"key": key, "description": description,
    "scope": "COMPANY", "grant_source": "OWNER_OR_COMPANY_GRANT"} for key, description in (
    (PermissionKey.PAYABLES_READ, "Consultar títulos de contas a pagar"),
    (PermissionKey.PAYABLES_MANAGE, "Criar, editar e cancelar títulos de contas a pagar"),
    (PermissionKey.PAYABLES_SETTLE, "Registrar baixa manual de contas a pagar"),
    (PermissionKey.PAYABLES_REVERSE, "Estornar baixa de contas a pagar"),
))
