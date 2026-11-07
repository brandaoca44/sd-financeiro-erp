"""Auditoria transacional, isolamento, paginação e ausência de dados sensíveis."""
from uuid import UUID, uuid4
from unittest.mock import patch
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import SQLAlchemyError
from app.modules.audit.models import OperationEvent
from app.modules.finance.billing import ServiceBilling
from test_payable_http import PayableHttpFixture

class OperationAuditTests(PayableHttpFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.app.state.settings=self.config.model_copy(update={'auth_identity_encryption_key':SecretStr(Fernet.generate_key().decode())})
        self.root=self.path().removesuffix('/payables')
        self.audit=self.root+'/audit'
        self.owner_headers=self.headers[self.owner.id]

    async def bill(self, key=None):
        key=key or str(uuid4())
        body=dict(customer='Cliente reservado',service='Descrição reservada',competence='2026-11-01',
            issue_date='2026-11-01',due_date='2026-11-10',amount='123.45',invoice_reference='NF-PRIVADA')
        result=await self.client.post(self.root+'/billing',headers={**self.owner_headers,'Idempotency-Key':key},json=body)
        return result,key,body

    async def test_billing_creation_receipt_reversal_are_transactional_and_idempotent(self):
        result,key,body=await self.bill()
        self.assertEqual(result.status_code,201,result.text)
        url=self.root+'/billing/'+result.json()['id']
        replay=await self.client.post(self.root+'/billing',headers={**self.owner_headers,'Idempotency-Key':key},json=body)
        self.assertEqual(replay.status_code,201,replay.text)
        headers={**self.owner_headers,'Idempotency-Key':str(uuid4())}
        receipt_body=dict(amount='50.00',received_on='2026-11-06')
        receipt=await self.client.post(url+'/receipts',headers=headers,json=receipt_body)
        self.assertEqual(receipt.status_code,201,receipt.text)
        self.assertEqual((await self.client.post(url+'/receipts',headers=headers,json=receipt_body)).status_code,201)
        reverse=url+'/receipts/'+receipt.json()['id']+'/reverse'
        for _ in range(2):self.assertEqual((await self.client.post(reverse,headers=headers,json={})).status_code,204)
        result=await self.client.get(self.audit,headers=self.owner_headers,params={'domain':'BILLING'})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual([item['action'] for item in result.json()['items']],['REVERSAL','RECEIVED','CREATED'])
        self.assertEqual(result.headers['cache-control'],'no-store')
        for secret in ('Cliente reservado','Descrição reservada','123.45','NF-PRIVADA','before_state','after_state','email'):
            self.assertNotIn(secret,result.text)
        for item in result.json()['items']:self.assertEqual(item['actor_user_id'],str(self.owner.id))

    async def test_audit_failure_rolls_back_the_business_operation(self):
        with patch('app.modules.finance.billing.record_event',side_effect=RuntimeError('forced')):
            result,key,_=await self.bill()
        self.assertEqual(result.status_code,500)
        async with self.factory() as session:
            self.assertIsNone(await session.get(ServiceBilling,(self.org.id,self.a.id,UUID(key))))
            self.assertEqual(await session.scalar(select(func.count()).select_from(OperationEvent).where(OperationEvent.company_id==self.a.id)),0)

    async def test_people_history_never_copies_private_payload(self):
        base=self.root+'/collaborators';key=str(uuid4());headers={**self.owner_headers,'Idempotency-Key':key}
        body=dict(name='Pessoa reservada',job_title='Analista financeiro',admission_date='2026-01-01',details=dict(
            cpf='52998224725',phone='11912345678',bank='Banco privado',branch='1234',account='56789',account_type='CORRENTE',monthly_compensation='9876.54'))
        for _ in range(2):self.assertEqual((await self.client.post(base,headers=headers,json=body)).status_code,201)
        updated={k:v for k,v in body.items() if k!='details'};updated['job_title']='Assistente financeiro'
        self.assertEqual((await self.client.put(base+'/'+key,headers=headers,json=updated)).status_code,200)
        end=dict(date='2026-11-06',reason='SEM_JUSTA_CAUSA')
        for _ in range(2):self.assertEqual((await self.client.post(base+'/'+key+'/termination',headers=headers,json=end)).status_code,200)
        result=await self.client.get(self.audit,headers=headers,params={'domain':'PEOPLE'})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual([row['action'] for row in result.json()['items']],['TERMINATED','UPDATED','CREATED'])
        for secret in ('52998224725','9876.54','56789','11912345678','Pessoa reservada','Banco privado','SEM_JUSTA_CAUSA'):
            self.assertNotIn(secret,result.text)

    async def test_history_is_master_only_and_exact_company_scoped(self):
        await self.bill()
        for key in ('billing.read','people.read','payables.read'):await self.grant(key)
        denied=await self.client.get(self.audit,headers=self.headers[self.member.id])
        self.assertEqual(denied.status_code,404)
        self.assertEqual((await self.client.get(self.audit)).status_code,401)
        other=self.path(company=self.b).removesuffix('/payables')+'/audit'
        self.assertEqual((await self.client.get(other,headers=self.owner_headers)).json()['items'],[])
        forged=f'/api/v1/organizations/{self.other.id}/companies/{self.a.id}/audit'
        self.assertEqual((await self.client.get(forged,headers=self.owner_headers)).status_code,404)
        self.assertEqual((await self.client.get(self.audit,headers=self.headers[self.colleague.id])).status_code,404)

    async def test_existing_history_filters_and_keyset_pagination(self):
        title=await self.title_id()
        self.assertEqual((await self.edit(title,description='Alterada')).status_code,200)
        self.assertEqual((await self.cancel(title,revision=2)).status_code,200)
        await self.bill()
        params={'domain':'PAYABLE','limit':1};seen=[]
        while True:
            result=await self.client.get(self.audit,headers=self.owner_headers,params=params)
            self.assertEqual(result.status_code,200,result.text)
            seen.extend(result.json()['items'])
            if not result.json()['next_cursor']:break
            params['cursor']=result.json()['next_cursor']
        self.assertEqual(len(seen),3)
        self.assertEqual(len({row['id'] for row in seen}),3)
        self.assertEqual([row['action'] for row in seen],['CANCELLED','UPDATED','CREATED'])
        filtered=await self.client.get(self.audit,headers=self.owner_headers,params={'action':'CREATED','actor_id':str(self.member.id)})
        self.assertEqual(filtered.json()['items'],[])
        for params in ({'cursor':'bad'},{'start':'2026-01-01','end':'2026-12-31'},{'domain':'OTHER'},{'limit':101}):
            self.assertEqual((await self.client.get(self.audit,headers=self.owner_headers,params=params)).status_code,422)

    async def test_database_rejects_event_update_and_delete(self):
        result,_,_=await self.bill();self.assertEqual(result.status_code,201,result.text)
        for mutation in (update(OperationEvent).values(action='UPDATED'),delete(OperationEvent)):
            async with self.factory() as session:
                with self.assertRaises(SQLAlchemyError):
                    await session.execute(mutation.where(OperationEvent.company_id==self.a.id))
                    await session.commit()
                await session.rollback()
        result=await self.client.get(self.audit,headers=self.owner_headers)
        self.assertEqual(len(result.json()['items']),1)
    async def test_expense_history_includes_changes_without_disclosing_snapshots(self):
        payload=self.data(category='INTERNET',supplier='Fornecedor privado',document_type='BOLETO',document_reference='REFERENCIA-PRIVADA')
        created=await self.client.post(self.root+'/expenses',headers={**self.owner_headers,'Idempotency-Key':str(uuid4())},json=payload)
        self.assertEqual(created.status_code,201,created.text)
        expense=created.json()['id']
        result=await self.client.post(self.root+'/expenses/'+expense+'/cancel',headers=self.owner_headers,
            json={'expected_revision':1,'expected_payable_revision':1})
        self.assertEqual(result.status_code,200,result.text)
        history=await self.client.get(self.audit,headers=self.owner_headers,params={'domain':'EXPENSE'})
        self.assertEqual(history.status_code,200,history.text)
        self.assertEqual([row['action'] for row in history.json()['items']],['CANCELLED','CREATED'])
        for text in ('Fornecedor privado','REFERENCIA-PRIVADA','123.45','before_state','after_state'):
            self.assertNotIn(text,history.text)
    async def test_former_master_loses_audit_access_after_ownership_transfer(self):
        from app.modules.identity.access_models import OrganizationOwnership
        result,_,_=await self.bill();self.assertEqual(result.status_code,201,result.text)
        async with self.factory() as session,session.begin():
            owner=await session.get(OrganizationOwnership,self.org.id)
            owner.user_id=self.member.id
            owner.revision+=1
        self.assertEqual((await self.client.get(self.audit,headers=self.owner_headers)).status_code,404)
        result=await self.client.get(self.audit,headers=self.headers[self.member.id])
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(len(result.json()['items']),1)

    async def test_downgrade_does_not_remove_new_audit_history(self):
        import asyncio
        result,_,_=await self.bill();self.assertEqual(result.status_code,201,result.text)
        await self.session.close()
        await self.engine.dispose()
        with self.assertRaises(RuntimeError):
            await asyncio.to_thread(self.run_migration,'downgrade','a14c5e93b207')
        result=await self.client.get(self.audit,headers=self.owner_headers)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(len(result.json()['items']),1)
