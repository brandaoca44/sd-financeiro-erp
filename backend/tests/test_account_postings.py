"""Vínculos de movimentos, estornos e saldo calculado por conta."""
from decimal import Decimal
from uuid import uuid4
from app.modules.finance.billing import Receipt
from sqlalchemy import select
from test_payable_http import PayableHttpFixture

class AccountPostingTests(PayableHttpFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp();self.root=self.path().removesuffix('/payables');self.accounts=self.root+'/financial-accounts';self.h=self.headers[self.owner.id]
    async def account(self,day='2026-01-01',root=None):
        result=await self.client.post((root or self.root)+'/financial-accounts',headers={**self.h,'Idempotency-Key':str(uuid4())},json=dict(name='Caixa',kind='CASH',opening_date=day,opening_balance='1000.00'))
        self.assertEqual(result.status_code,201,result.text);return result.json()['id']
    async def payment(self,title,account=None,day='2026-11-05',revision=1,key=None,headers=None):
        return await self.client.post(self.path(title)+'/payments',headers={**(headers or self.h),'Idempotency-Key':key or str(uuid4())},json=dict(amount='100.00',occurred_on=day,expected_revision=revision,**({'financial_account_id':account} if account else {})))
    async def bill(self):
        result=await self.client.post(self.root+'/billing',headers={**self.h,'Idempotency-Key':str(uuid4())},json=dict(customer='Cliente',service='Serviço',amount='300.00',competence='2026-11-01',issue_date='2026-11-01',due_date='2026-11-10'))
        self.assertEqual(result.status_code,201,result.text);return result.json()['id']
    async def receipt(self,bill,account=None):
        return await self.client.post(self.root+'/billing/'+bill+'/receipts',headers={**self.h,'Idempotency-Key':str(uuid4())},json=dict(amount='200.00',received_on='2026-11-05',**({'financial_account_id':account} if account else {})))
    async def balance(self,account):
        result=await self.client.get(self.accounts+'/'+account+'/position',headers=self.h)
        self.assertEqual(result.status_code,200,result.text);return result.json()
    async def test_native_movements_and_inactive_account_reversals(self):
        account=await self.account();title=await self.title_id();key=str(uuid4())
        paid=await self.payment(title,account,key=key);self.assertEqual(paid.status_code,201,paid.text)
        retry=await self.payment(title,account,key=key);self.assertEqual(retry.json(),paid.json())
        bill=await self.bill();receipt=await self.receipt(bill,account);self.assertEqual(receipt.status_code,201,receipt.text)
        self.assertEqual(Decimal((await self.balance(account))['current_balance']),1100)
        inactive=await self.client.put(self.accounts+'/'+account,headers=self.h,json=dict(name='Caixa',status='INACTIVE',expected_revision=1));self.assertEqual(inactive.status_code,200,inactive.text)
        title2=await self.title_id();self.assertEqual((await self.payment(title2,account)).status_code,409)
        reverse=await self.client.post(self.path(title)+'/payments/'+paid.json()['movement_id']+'/reverse',headers={**self.h,'Idempotency-Key':str(uuid4())},json=dict(expected_revision=2,occurred_on='2026-11-06',reason='Correção'))
        self.assertEqual(reverse.status_code,201,reverse.text)
        reverse=await self.client.post(self.root+'/billing/'+bill+'/receipts/'+receipt.json()['id']+'/reverse',headers=self.h,json={'reversed_on':'2026-11-06'})
        self.assertEqual(reverse.status_code,204,reverse.text)
        data=await self.balance(account);self.assertEqual(Decimal(data['current_balance']),1000);self.assertEqual(Decimal(data['receipt_reversals_amount']),200)
        movements=await self.client.get(self.path(title)+'/movements',headers=self.h)
        self.assertTrue(all(row['financial_account_id']==account for row in movements.json()['items']))
    async def test_dates_cross_company_and_permissions(self):
        account=await self.account('2026-11-06');title=await self.title_id()
        self.assertEqual((await self.payment(title,account)).status_code,409)
        otherroot=self.path(company=self.b).removesuffix('/payables');foreign=await self.account(root=otherroot)
        self.assertEqual((await self.payment(title,foreign)).status_code,404)
        await self.grant('payables.settle');headers=self.headers[self.member.id]
        self.assertEqual((await self.payment(title,account,day='2026-11-06',headers=headers)).status_code,404)
        await self.grant('accounts.read')
        self.assertEqual((await self.payment(title,account,day='2026-11-06',headers=headers)).status_code,201)
        self.assertEqual((await self.client.get(self.accounts+'/'+account+'/position',headers=headers)).status_code,404)
    async def test_explicit_legacy_links_and_reassignment_rejected(self):
        account=await self.account();title=await self.title_id();paid=await self.payment(title);self.assertEqual(paid.status_code,201,paid.text)
        bill=await self.bill();receipt=await self.receipt(bill);self.assertEqual(receipt.status_code,201,receipt.text)
        before=await self.balance(account);self.assertEqual(Decimal(before['current_balance']),1000);self.assertEqual(before['unassigned_payments'],1);self.assertEqual(before['unassigned_receipts'],1)
        url=self.path(title)+'/payments/'+paid.json()['movement_id']+'/account';body=dict(financial_account_id=account,expected_revision=2)
        for _ in range(2):
            result=await self.client.post(url,headers=self.h,json=body);self.assertEqual(result.status_code,200,result.text)
        receipturl=self.root+'/billing/'+bill+'/receipts/'+receipt.json()['id']+'/account'
        result=await self.client.post(receipturl,headers=self.h,json=dict(financial_account_id=account,expected_reversed=False));self.assertEqual(result.status_code,200,result.text)
        data=await self.balance(account);self.assertEqual(Decimal(data['current_balance']),1100);self.assertEqual(data['unassigned_payments'],0)
        other=await self.account();body['financial_account_id']=other
        self.assertEqual((await self.client.post(url,headers=self.h,json=body)).status_code,409)
    async def test_old_receipt_reversal_requires_real_date(self):
        account=await self.account();bill=await self.bill();receipt=await self.receipt(bill)
        async with self.factory() as session,session.begin():
            row=await session.scalar(select(Receipt).where(Receipt.id==receipt.json()['id'],Receipt.company_id==self.a.id));row.reversed=True
        url=self.root+'/billing/'+bill+'/receipts/'+receipt.json()['id']+'/account';body=dict(financial_account_id=account,expected_reversed=True)
        self.assertEqual((await self.client.post(url,headers=self.h,json=body)).status_code,422)
        result=await self.client.post(url,headers=self.h,json={**body,'reversed_on':'2026-11-06'});self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(Decimal((await self.balance(account))['current_balance']),1000)
    async def test_legacy_payment_link_also_links_existing_reversal(self):
        account=await self.account();title=await self.title_id();paid=await self.payment(title)
        reversed_=await self.client.post(self.path(title)+'/payments/'+paid.json()['movement_id']+'/reverse',headers={**self.h,'Idempotency-Key':str(uuid4())},json=dict(expected_revision=2,occurred_on='2026-11-06',reason='Correção'))
        self.assertEqual(reversed_.status_code,201,reversed_.text)
        linked=await self.client.post(self.path(title)+'/payments/'+paid.json()['movement_id']+'/account',headers=self.h,json=dict(financial_account_id=account,expected_revision=3))
        self.assertEqual(linked.status_code,200,linked.text)
        data=await self.balance(account);self.assertEqual(Decimal(data['current_balance']),1000)
        self.assertEqual(Decimal(data['payment_reversals_amount']),100)
        rows=await self.client.get(self.path(title)+'/movements',headers=self.h)
        self.assertTrue(all(row['financial_account_id']==account for row in rows.json()['items']))
    async def test_database_disallows_reassignment_of_posted_movement(self):
        from uuid import UUID
        from sqlalchemy import update
        from sqlalchemy.exc import SQLAlchemyError
        from app.modules.finance.models import PayableMovement
        account=await self.account();other=await self.account();title=await self.title_id();paid=await self.payment(title,account)
        self.assertEqual(paid.status_code,201,paid.text)
        async with self.factory() as session:
            with self.assertRaises(SQLAlchemyError):
                await session.execute(update(PayableMovement).where(PayableMovement.id==UUID(paid.json()['movement_id'])).values(financial_account_id=UUID(other)))
                await session.commit()
            await session.rollback()
        self.assertEqual(Decimal((await self.balance(account))['current_balance']),900)
        self.assertEqual(Decimal((await self.balance(other))['current_balance']),1000)
    async def test_missing_legacy_reversal_date_requires_reversal_permission(self):
        account=await self.account();bill=await self.bill();receipt=await self.receipt(bill)
        async with self.factory() as session,session.begin():
            row=await session.scalar(select(Receipt).where(Receipt.id==receipt.json()['id'],Receipt.company_id==self.a.id));row.reversed=True
        for key in ('accounts.read','accounts.manage','billing.receive'):await self.grant(key)
        url=self.root+'/billing/'+bill+'/receipts/'+receipt.json()['id']+'/account';body=dict(financial_account_id=account,expected_reversed=True,reversed_on='2026-11-06')
        headers=self.headers[self.member.id]
        self.assertEqual((await self.client.post(url,headers=headers,json=body)).status_code,404)
        await self.grant('billing.reverse')
        response=await self.client.post(url,headers=headers,json=body);self.assertEqual(response.status_code,200,response.text)
    async def test_receipt_write_confirmation_does_not_expose_read_fields(self):
        bill=await self.bill();await self.grant('billing.receive');headers=self.headers[self.member.id]
        result=await self.client.post(self.root+'/billing/'+bill+'/receipts',headers={**headers,'Idempotency-Key':str(uuid4())},json=dict(amount='10.00',received_on='2026-11-05'))
        self.assertEqual(result.status_code,201,result.text);self.assertEqual(set(result.json()),{'id'})
        self.assertEqual((await self.client.get(self.root+'/billing/'+bill+'/position',headers=headers)).status_code,404)
