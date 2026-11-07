"""Fluxo consolidado exato, com estornos, baixas parciais e dupla autorização."""
from datetime import date
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
from test_payable_http import PayableHttpFixture

class CashflowTests(PayableHttpFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.root=self.path().removesuffix('/payables');self.url=self.root+'/cashflow'
        self.owner_headers=self.headers[self.owner.id]
        clock=patch('app.modules.finance.cashflow.PayableMovementService._today',return_value=date(2026,11,10))
        clock.start();self.addCleanup(clock.stop)

    async def flow(self,headers=None,**params):
        return await self.client.get(self.url,headers=headers or self.owner_headers,
            params={'start':'2026-11-01','end':'2026-11-10',**params})

    async def bill(self):
        response=await self.client.post(self.root+'/billing',headers={**self.owner_headers,'Idempotency-Key':str(uuid4())},
            json=dict(customer='Cliente privado',service='Descrição privada',competence='2026-11-01',issue_date='2026-11-01',due_date='2026-11-08',amount='200.00'))
        self.assertEqual(response.status_code,201,response.text)
        return response.json()['id']

    async def test_realized_pending_and_accumulation_do_not_double_count(self):
        bill=await self.bill();receipt=await self.client.post(self.root+'/billing/'+bill+'/receipts',headers={**self.owner_headers,'Idempotency-Key':str(uuid4())},json=dict(amount='50.00',received_on='2026-11-05'))
        self.assertEqual(receipt.status_code,201,receipt.text)
        title=await self.create(amount='100.00',due_date='2026-11-08');self.assertEqual(title.status_code,201,title.text);title=title.json()['id']
        payment=await self.client.post(self.path(title)+'/payments',headers={**self.owner_headers,'Idempotency-Key':str(uuid4())},json=dict(amount='40.00',occurred_on='2026-11-05',expected_revision=1))
        self.assertEqual(payment.status_code,201,payment.text)
        reversal=await self.client.post(self.path(title)+'/payments/'+payment.json()['movement_id']+'/reverse',headers={**self.owner_headers,'Idempotency-Key':str(uuid4())},json=dict(occurred_on='2026-11-06',expected_revision=2,reason='Correção'))
        self.assertEqual(reversal.status_code,201,reversal.text)
        payment=await self.client.post(self.path(title)+'/payments',headers={**self.owner_headers,'Idempotency-Key':str(uuid4())},json=dict(amount='25.00',occurred_on='2026-11-07',expected_revision=3))
        self.assertEqual(payment.status_code,201,payment.text)
        result=await self.flow();self.assertEqual(result.status_code,200,result.text);data=result.json()
        for key,value in dict(realized_in=50,realized_out=25,pending_in=150,pending_out=75,realized_net=25,projected_net=100).items():self.assertEqual(Decimal(data['totals'][key]),Decimal(value))
        days={row['day']:row for row in data['days']};self.assertEqual(len(days),10)
        self.assertEqual(Decimal(days['2026-11-06']['realized_out']),Decimal(-40))
        self.assertEqual(Decimal(days['2026-11-10']['cumulative_projected']),Decimal(100))
        self.assertEqual(result.headers['cache-control'],'no-store')
        self.assertNotIn('Cliente privado',result.text);self.assertNotIn('Descrição privada',result.text)
        reverse=await self.client.post(self.root+'/billing/'+bill+'/receipts/'+receipt.json()['id']+'/reverse',headers=self.owner_headers,json={})
        self.assertEqual(reverse.status_code,204,reverse.text)
        after=(await self.flow()).json();self.assertEqual(Decimal(after['totals']['realized_in']),0);self.assertEqual(Decimal(after['totals']['pending_in']),200)

    async def test_requires_both_reads_in_same_company_and_revocation_is_immediate(self):
        headers=self.headers[self.member.id]
        self.assertEqual((await self.flow(headers)).status_code,404)
        await self.grant('billing.read');self.assertEqual((await self.flow(headers)).status_code,404)
        await self.grant('payables.read');self.assertEqual((await self.flow(headers)).status_code,200)
        other=self.path(company=self.b).removesuffix('/payables')+'/cashflow'
        self.assertEqual((await self.client.get(other,headers=headers,params={'start':'2026-11-01','end':'2026-11-10'})).status_code,404)
        await self.grant('billing.read',status='INACTIVE',revision=1)
        self.assertEqual((await self.flow(headers)).status_code,404)
        self.assertEqual((await self.client.get(self.url,params={'start':'2026-11-01','end':'2026-11-10'})).status_code,401)

    async def test_empty_period_bounds_cancelled_and_future_outside_interval(self):
        result=await self.flow();self.assertEqual(result.status_code,200,result.text)
        self.assertTrue(all(Decimal(v)==0 for v in result.json()['totals'].values()))
        cancelled=await self.create(amount='100.00',due_date='2026-11-08');self.assertEqual((await self.cancel(cancelled.json()['id'])).status_code,200)
        await self.create(amount='200.00',due_date='2026-11-20')
        result=await self.flow();self.assertEqual(Decimal(result.json()['totals']['pending_out']),0)
        one=await self.flow(start='2026-11-20',end='2026-11-20');self.assertEqual(len(one.json()['days']),1);self.assertEqual(Decimal(one.json()['totals']['pending_out']),200)
        for params in ({'start':'2026-11-10','end':'2026-11-01'},{'start':'2026-01-01','end':'2026-12-31'}):self.assertEqual((await self.flow(**params)).status_code,422)

    async def test_all_records_and_contract_suspension(self):
        from app.modules.finance.billing import ServiceBilling
        from app.modules.commercial.models import BusinessContract
        async with self.factory() as session,session.begin():
            session.add_all([ServiceBilling(organization_id=self.org.id,company_id=self.a.id,id=uuid4(),customer='Cliente',service='Serviço',competence=date(2026,11,1),issue_date=date(2026,11,1),due_date=date(2026,11,8),amount=Decimal('1.01')) for _ in range(125)])
        result=await self.flow();self.assertEqual(result.status_code,200,result.text);self.assertEqual(Decimal(result.json()['totals']['pending_in']),Decimal('126.25'))
        async with self.factory() as session,session.begin():
            contract=await session.get(BusinessContract,self.org.id);contract.status='SUSPENDED'
        self.assertEqual((await self.flow()).status_code,404)
