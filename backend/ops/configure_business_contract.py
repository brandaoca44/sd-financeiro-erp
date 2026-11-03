"""Configura contratos Empresarial por meio de acesso administrativo ao banco."""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.modules.commercial.catalog import CATALOG_VERSION, PLANS, Plan
from app.modules.commercial.models import BusinessCompanyActivation, BusinessContract
from app.modules.organizations.models import Company, CompanyStatus, Organization, OrganizationStatus
from ops.serve import event_loop


def aware_datetime(value):
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Informe data e hora ISO 8601 com fuso.") from error
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("Informe data e hora ISO 8601 com fuso.")
    return parsed.astimezone(timezone.utc)


async def configure(session, organization_id, plan, valid_from, valid_until, companies, enterprise_limit=None):
    """Substitui a configuração e a lista de empresas na transação do chamador."""
    if valid_until <= valid_from:
        raise ValueError("O fim da vigência deve ser posterior ao início.")
    limit = PLANS[plan].companies
    if limit is None:
        if enterprise_limit is None or enterprise_limit < 1:
            raise ValueError("Informe o limite de empresas acordado no contrato Enterprise.")
        limit = enterprise_limit
    elif enterprise_limit is not None:
        raise ValueError("O limite negociado é exclusivo do Enterprise.")
    requested = set(companies)
    if not requested or len(requested) != len(companies) or len(requested) > limit:
        raise ValueError("Informe empresas distintas dentro do limite do plano.")

    await session.execute(text("SET LOCAL lock_timeout = '5s'"))
    organization = await session.scalar(select(Organization).where(
        Organization.id == organization_id,
    ).with_for_update())
    if organization is None or organization.status != OrganizationStatus.ACTIVE:
        raise ValueError("A organização precisa existir e estar ativa.")

    eligible = set(await session.scalars(select(Company.id).where(
        Company.organization_id == organization_id,
        Company.id.in_(requested),
        Company.status == CompanyStatus.ACTIVE,
    )))
    if eligible != requested:
        raise ValueError("Todas as empresas precisam estar ativas na organização informada.")

    contract = await session.get(BusinessContract, organization_id, with_for_update=True)
    if contract is None:
        contract = BusinessContract(organization_id=organization_id)
        session.add(contract)
    contract.plan = plan.value
    contract.catalog_version = CATALOG_VERSION
    contract.status = "ACTIVE"
    contract.valid_from = valid_from
    contract.valid_until = valid_until
    await session.flush()

    activations = await session.scalars(select(BusinessCompanyActivation).where(
        BusinessCompanyActivation.organization_id == organization_id,
    ))
    current = {activation.company_id: activation for activation in activations}
    for company_id in current.keys() - requested:
        await session.delete(current[company_id])
    for company_id in requested - current.keys():
        session.add(BusinessCompanyActivation(organization_id=organization_id, company_id=company_id))


async def run(args):
    from app.database.session import async_session_factory, close_database_engine

    try:
        async with async_session_factory.begin() as session:
            await configure(session, args.organization, Plan(args.plan), args.valid_from,
                            args.valid_until, args.company, args.enterprise_company_limit)
    finally:
        await close_database_engine()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization", type=UUID, required=True)
    parser.add_argument("--plan", choices=[plan.value for plan in Plan], required=True)
    parser.add_argument("--valid-from", type=aware_datetime, required=True)
    parser.add_argument("--valid-until", type=aware_datetime, required=True)
    parser.add_argument("--company", type=UUID, action="append", required=True,
                        help="Repita para cada empresa da lista completa de habilitações.")
    parser.add_argument("--enterprise-company-limit", type=int)
    args = parser.parse_args()

    try:
        with asyncio.Runner(loop_factory=event_loop) as runner:
            runner.run(run(args))
    except ValueError as error:
        print(f"Configuração rejeitada: {error}", file=sys.stderr)
        return 2
    except SQLAlchemyError:
        print("Falha ao gravar o contrato. Confira a conexão e a migração do banco.", file=sys.stderr)
        return 1
    print("Contrato e empresas habilitadas gravados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
