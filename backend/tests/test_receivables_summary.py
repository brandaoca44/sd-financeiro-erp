"""Indicadores de recebimentos sem confundir receita e saldo a receber."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4
from app.modules.finance.billing import ServiceBilling
from test_payable_http import PayableHttpFixture

class ReceivableSummaryTests(PayableHttpFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.root=self.path().removesuffix('/payables')
        self.url=self.root+'/receivables-summary'
        self.owner_headers=self.headers[self.owner.id]
        clock=patch('app.modules.finance.receivables_summary.PayableMovementService._today',return_value=date(2026,11,6))
        clock.start();self.addCleanup(clock.stop)

    async def bill(self,amount,due):
        result=await self.client.post(self.root+'/billing',headers={**self.owner_headers,'Idempotency-Key':str(uuid4())},
            json=dict(customer='Cliente privado',service='Serviço reservado',competence='2026-10-01',issue_date='2026-10-01',amount=str(amount),due_date=due))
        self.assertEqual(result.status_code,201,result.text)
        return result.json()['id']

    async def receive(self,billing,amount,day='2026-11-06'):
        result=await self.client.post(self.root+'/billing/'+billing+'/receipts',headers={**self.owner_headers,'Idempotency-Key':str(uuid4())},
            json=dict(amount=str(amount),received_on=day))
        self.assertEqual(result.status_code,201,result.text)
        return result.json()['id']

    async def summary(self,month='2026-11',headers=None):
        result=await self.client.get(self.url,headers=headers or self.owner_headers,params={'month':month})
        self.assertEqual(result.status_code,200,result.text)
        return result.json()

    def amount(self,data,key,expected):self.assertEqual(Decimal(data[key]),Decimal(str(expected)))

    async def test_partial_settled_overdue_current_month_and_reversal(self):
        late=await self.bill(100,'2026-11-05');await self.receive(late,40)
        current=await self.bill(200,'2026-11-06');await self.receive(current,50)
        soon=await self.bill(300,'2026-11-13');receipt=await self.receive(soon,25)
        await self.bill(400,'2026-11-14')
        settled=await self.bill(500,'2026-11-06');await self.receive(settled,500)
        old=await self.bill(100,'2026-10-31');await self.receive(old,20,'2026-10-31')
        await self.bill(999,None)
        data=await self.summary()
        for key,expected in [('outstanding_amount',965),('overdue_amount',140),('due_today_amount',150),('upcoming_amount',275),('received_amount',615)]:self.amount(data,key,expected)
        self.assertEqual([data[key] for key in ('outstanding_count','overdue_count','due_today_count','upcoming_count','received_count')],[5,2,1,1,4])
        october=await self.summary('2026-10');self.amount(october,'received_amount',20)
        self.assertEqual(october['outstanding_amount'],data['outstanding_amount'])
        result=await self.client.post(self.root+'/billing/'+soon+'/receipts/'+receipt+'/reverse',headers=self.owner_headers,json={})
        self.assertEqual(result.status_code,204,result.text)
        after=await self.summary();self.amount(after,'outstanding_amount',990);self.amount(after,'received_amount',590);self.amount(after,'upcoming_amount',300)
        self.assertNotIn('Cliente privado',str(after));self.assertNotIn('Serviço reservado',str(after))

    async def test_read_permission_is_independent_and_scoped_to_exact_company(self):
        await self.bill(200,'2026-11-06')
        await self.grant('payables.read');await self.grant('billing.manage')
        headers=self.headers[self.member.id]
        self.assertEqual((await self.client.get(self.url,headers=headers)).status_code,404)
        await self.grant('billing.read')
        data=await self.summary(headers=headers);self.amount(data,'outstanding_amount',200)
        other=self.path(company=self.b).removesuffix('/payables')+'/receivables-summary'
        self.assertEqual((await self.client.get(other,headers=headers)).status_code,404)
        self.assertEqual((await self.client.get(self.url)).status_code,401)
        await self.grant('billing.read',status='INACTIVE',revision=1)
        self.assertEqual((await self.client.get(self.url,headers=headers)).status_code,404)

    async def test_all_records_are_aggregated_not_just_billing_list_limit(self):
        async with self.factory() as session,session.begin():
            session.add_all([ServiceBilling(organization_id=self.org.id,company_id=self.a.id,id=uuid4(),customer='Cliente',service='Serviço',
                competence=date(2026,11,1),issue_date=date(2026,11,1),due_date=date(2026,11,6),amount=Decimal('1.01')) for _ in range(125)])
        data=await self.summary();self.amount(data,'outstanding_amount','126.25');self.assertEqual(data['outstanding_count'],125)
        self.assertEqual(data['due_today_count'],125)

    async def test_empty_month_validation_and_inactive_contract(self):
        data=await self.summary();self.amount(data,'outstanding_amount',0);self.amount(data,'received_amount',0)
        result=await self.client.get(self.url,headers=self.owner_headers)
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.headers['cache-control'],'no-store')
        for month in ('0000-01','2026-13','2026-1','bad'):
            self.assertEqual((await self.client.get(self.url,headers=self.owner_headers,params={'month':month})).status_code,422)
        from app.modules.commercial.models import BusinessContract
        async with self.factory() as session,session.begin():
            row=await session.get(BusinessContract,self.org.id);row.status='SUSPENDED'
        self.assertEqual((await self.client.get(self.url,headers=self.owner_headers)).status_code,404)
