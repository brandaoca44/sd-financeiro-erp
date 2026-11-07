"""Validação transacional dos vínculos financeiros, sem ler dados bancários."""
from fastapi import HTTPException
from sqlalchemy import select
from app.modules.identity.company_authorization import CompanyAccessPolicy
from app.modules.identity.permissions import PermissionKey

async def posting_account(session,org,company,actor,account_id,day,*,reversal=False):
    if account_id is None:return None
    from app.modules.finance.accounts import FinancialAccount
    if not await CompanyAccessPolicy(session).has_operation_permission(actor,org,company,PermissionKey.ACCOUNTS_READ):
        raise HTTPException(404,'Conta financeira indisponível.')
    row=await session.scalar(select(FinancialAccount).where(FinancialAccount.organization_id==org,
        FinancialAccount.company_id==company,FinancialAccount.id==account_id).with_for_update())
    if row is None:raise HTTPException(404,'Conta financeira indisponível.')
    if row.currency!='BRL' or (row.status!='ACTIVE' and not reversal) or day<row.opening_date:
        raise HTTPException(409,'Confira a situação da conta e sua data inicial.')
    return row.id
