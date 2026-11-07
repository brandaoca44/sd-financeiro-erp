"""Extrato por conta com saldo anterior, paginação e autorização exata."""
from decimal import Decimal
from uuid import uuid4
from test_payable_http import PayableHttpFixture
import test_account_postings as posting_helpers

class AccountStatementTests(PayableHttpFixture):
    account=posting_helpers.AccountPostingTests.account
    payment=posting_helpers.AccountPostingTests.payment
    bill=posting_helpers.AccountPostingTests.bill
    receipt=posting_helpers.AccountPostingTests.receipt
    async def asyncSetUp(self):
        await super().asyncSetUp();self.root=self.path().removesuffix('/payables');self.accounts=self.root+'/financial-accounts';self.h=self.headers[self.owner.id]
    async def statement(self,account,headers=None,**params):
        return await self.client.get(self.accounts+'/'+account+'/statement',headers=headers or self.h,params={'start':'2026-11-01','end':'2026-11-06',**params})
    async def seed(self):
        account=await self.account();title=await self.title_id();paid=await self.payment(title,account)
        self.assertEqual(paid.status_code,201,paid.text);bill=await self.bill();receipt=await self.receipt(bill,account)
        self.assertEqual(receipt.status_code,201,receipt.text)
        reversed_=await self.client.post(self.path(title)+'/payments/'+paid.json()['movement_id']+'/reverse',headers={**self.h,'Idempotency-Key':str(uuid4())},json={'expected_revision':2,'occurred_on':'2026-11-06','reason':'Correção'})
        self.assertEqual(reversed_.status_code,201,reversed_.text)
        reversed_=await self.client.post(self.root+'/billing/'+bill+'/receipts/'+receipt.json()['id']+'/reverse',headers=self.h,json={'reversed_on':'2026-11-06'})
        self.assertEqual(reversed_.status_code,204,reversed_.text);return account
    async def test_opening_closing_reversals_and_stable_pagination(self):
        account=await self.seed();full=await self.statement(account)
        self.assertEqual(full.status_code,200,full.text);data=full.json()
        self.assertEqual(Decimal(data['opening_balance']),1000);self.assertEqual(Decimal(data['incoming']),300)
        self.assertEqual(Decimal(data['outgoing']),300);self.assertEqual(Decimal(data['closing_balance']),1000)
        self.assertEqual([Decimal(row['balance']) for row in data['items']],[Decimal(900),Decimal(1100),Decimal(1200),Decimal(1000)])
        seen=[];cursor=None
        for _ in range(6):
            page=await self.statement(account,limit=1,**({'cursor':cursor} if cursor else {}));self.assertEqual(page.status_code,200,page.text)
            seen.extend(page.json()['items']);self.assertEqual(page.json()['incoming'],data['incoming']);cursor=page.json()['next_cursor']
            if cursor is None:break
        self.assertEqual(seen,data['items']);self.assertEqual(full.headers['cache-control'],'no-store')
        for field in ('bank_details','institution','encrypted_bank','created_by_user_id'):self.assertNotIn(field,data)
    async def test_period_opening_includes_earlier_movements_and_empty_period(self):
        account=await self.seed();result=await self.statement(account,start='2026-11-06')
        self.assertEqual(result.status_code,200,result.text);data=result.json()
        self.assertEqual(Decimal(data['opening_balance']),1100);self.assertEqual(Decimal(data['closing_balance']),1000)
        self.assertEqual(len(data['items']),2)
        empty=await self.statement(account,start='2026-11-01',end='2026-11-04')
        self.assertEqual(empty.status_code,200,empty.text);self.assertEqual(empty.json()['items'],[]);self.assertEqual(Decimal(empty.json()['closing_balance']),1000)
    async def test_permissions_cross_company_and_revocation(self):
        account=await self.account();headers=self.headers[self.member.id]
        for key in ('accounts.read','payables.read'):
            await self.grant(key);self.assertEqual((await self.statement(account,headers)).status_code,404)
        await self.grant('billing.read');self.assertEqual((await self.statement(account,headers)).status_code,200)
        other=self.path(company=self.b).removesuffix('/payables')+'/financial-accounts/'+account+'/statement'
        self.assertEqual((await self.client.get(other,headers=self.h,params={'start':'2026-11-01','end':'2026-11-06'})).status_code,404)
        await self.grant('billing.read',status='INACTIVE',revision=1);self.assertEqual((await self.statement(account,headers)).status_code,404)
    async def test_invalid_periods_and_cursors(self):
        account=await self.account()
        for params in ({'start':'2025-12-31'},{'start':'2026-11-06','end':'2026-11-05'},
                       {'start':'2026-01-01'},{'end':'9999-01-01'},{'cursor':'bad'},{'limit':101}):
            result=await self.statement(account,**params);self.assertEqual(result.status_code,422,result.text)
    async def test_reused_receipt_key_in_different_bills_does_not_skip_rows(self):
        account=await self.account();bills=[await self.bill(),await self.bill()];key=str(uuid4())
        for bill in bills:
            result=await self.client.post(self.root+'/billing/'+bill+'/receipts',headers={**self.h,'Idempotency-Key':key},json=dict(amount='100.00',received_on='2026-11-05',financial_account_id=account))
            self.assertEqual(result.status_code,201,result.text)
        full=await self.statement(account);self.assertEqual(full.status_code,200,full.text)
        seen=[];cursor=None
        for _ in range(3):
            page=await self.statement(account,limit=1,**({'cursor':cursor} if cursor else {}));self.assertEqual(page.status_code,200,page.text)
            seen.extend(page.json()['items']);cursor=page.json()['next_cursor']
            if cursor is None:break
        self.assertEqual(len(seen),2);self.assertEqual({row['reference_id'] for row in seen},set(bills))
        self.assertEqual(seen,full.json()['items']);self.assertEqual(Decimal(full.json()['closing_balance']),1200)
