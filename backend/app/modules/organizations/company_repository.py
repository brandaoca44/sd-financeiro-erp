"""Persistência de empresas sempre limitada ao tenant, sem autorização ou commit."""

from sqlalchemy import select

from app.modules.organizations.models import Company


class CompanyRepository:
    def __init__(self, session):
        self.session = session

    async def create(self, organization_id, *, legal_name, trade_name, tax_id):
        company = Company(organization_id=organization_id, legal_name=legal_name, trade_name=trade_name, tax_id=tax_id)
        self.session.add(company)
        await self.session.flush()
        return company

    async def get(self, organization_id, company_id, *, lock=False, visibility=None):
        query = select(Company).where(Company.organization_id == organization_id, Company.id == company_id)
        if visibility is not None:
            query = query.where(visibility)
        if lock:
            query = query.with_for_update()
        return await self.session.scalar(query)

    async def list(self, organization_id, *, cursor=None, limit=50, visibility=None):
        query = select(Company).where(Company.organization_id == organization_id).order_by(Company.id).limit(limit + 1)
        if visibility is not None:
            query = query.where(visibility)
        if cursor is not None:
            query = query.where(Company.id > cursor)
        return (await self.session.scalars(query)).all()
