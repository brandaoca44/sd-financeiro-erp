"""Contas empresariais: criptografia, isolamento, revisão e saldo inicial preservado."""
from datetime import date,timedelta
from decimal import Decimal
from uuid import UUID,uuid4
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select,update,delete
from sqlalchemy.exc import SQLAlchemyError
from app.modules.finance.accounts import FinancialAccount
from app.modules.audit.models import OperationEvent
from test_payable_http import PayableHttpFixture

class FinancialAccountTests(PayableHttpFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.app.state.settings=self.config.model_copy(update={'auth_identity_encryption_key':SecretStr(Fernet.generate_key().decode())})
        self.root=self.path().removesuffix('/payables');self.url=self.root+'/financial-accounts';self.owner_headers=self.headers[self.owner.id]

    def data(self,**changes):return dict(name='Conta operacional',kind='BANK',opening_balance='-123.45',opening_date='2026-01-01',bank_details=dict(institution='Banco confidencial',branch='12345',account='987654321')) | changes

    async def create_account(self,data=None,headers=None,key=None):
        return await self.client.post(self.url,headers={**(headers or self.owner_headers),'Idempotency-Key':key or str(uuid4())},json=data or self.data())

    async def test_bank_details_encrypted_and_absent_from_list_and_audit(self):
        result=await self.create_account();self.assertEqual(result.status_code,201,result.text);id=result.json()['id']
        listed=await self.client.get(self.url,headers=self.owner_headers);self.assertEqual(listed.status_code,200,listed.text)
        self.assertEqual(Decimal(listed.json()['items'][0]['opening_balance']),Decimal('-123.45'))
        for secret in ('987654321','12345','Banco confidencial','encrypted_bank','bank_details'):self.assertNotIn(secret,listed.text)
        details=await self.client.get(self.url+'/'+id+'/bank-details',headers=self.owner_headers)
        self.assertEqual(details.status_code,200,details.text);self.assertEqual(details.json()['account'],'987654321');self.assertEqual(details.headers['cache-control'],'no-store')
        async with self.factory() as session:
            row=await session.get(FinancialAccount,(self.org.id,self.a.id,UUID(id)))
            for secret in ('987654321','Banco confidencial'):self.assertNotIn(secret,row.encrypted_bank)
        history=await self.client.get(self.root+'/audit',headers=self.owner_headers,params={'domain':'ACCOUNTS'})
        self.assertEqual(history.status_code,200,history.text);self.assertEqual(history.json()['items'][0]['resource_type'],'ACCOUNT')
        for secret in ('987654321','Banco confidencial','123.45'):self.assertNotIn(secret,history.text)

    async def test_read_manage_bank_are_independent_and_company_scoped(self):
        result=await self.create_account();id=result.json()['id'];headers=self.headers[self.member.id]
        await self.grant('payables.read');await self.grant('billing.read');await self.grant('people.bank')
        self.assertEqual((await self.client.get(self.url,headers=headers)).status_code,404)
        await self.grant('accounts.read')
        self.assertEqual((await self.client.get(self.url,headers=headers)).status_code,200)
        self.assertEqual((await self.client.get(self.url+'/'+id+'/bank-details',headers=headers)).status_code,404)
        body=dict(name='Novo nome',status='ACTIVE',expected_revision=1)
        self.assertEqual((await self.client.put(self.url+'/'+id,headers=headers,json=body)).status_code,404)
        await self.grant('accounts.manage')
        result=await self.client.put(self.url+'/'+id,headers=headers,json=body);self.assertEqual(result.status_code,200,result.text)
        body.update(expected_revision=2,bank_details=dict(institution='Outro',branch='22',account='333'))
        self.assertEqual((await self.client.put(self.url+'/'+id,headers=headers,json=body)).status_code,404)
        private=await self.client.get(self.url+'/'+id+'/bank-details',headers=self.owner_headers);self.assertEqual(private.json()['account'],'987654321')
        await self.grant('accounts.bank')
        self.assertEqual((await self.client.get(self.url+'/'+id+'/bank-details',headers=headers)).status_code,200)
        other=self.path(company=self.b).removesuffix('/payables')+'/financial-accounts/'+id+'/bank-details'
        self.assertEqual((await self.client.get(other,headers=headers)).status_code,404)
        await self.grant('accounts.bank',status='INACTIVE',revision=1)
        self.assertEqual((await self.client.get(self.url+'/'+id+'/bank-details',headers=headers)).status_code,404)

    async def test_initial_position_immutable_no_deletion_and_stale_edit_conflict(self):
        result=await self.create_account();id=result.json()['id']
        invalid=dict(name='Novo',status='ACTIVE',expected_revision=1,opening_balance='999.00')
        self.assertEqual((await self.client.put(self.url+'/'+id,headers=self.owner_headers,json=invalid)).status_code,422)
        body=dict(name='Inativa',status='INACTIVE',expected_revision=1)
        self.assertEqual((await self.client.put(self.url+'/'+id,headers=self.owner_headers,json=body)).status_code,200)
        self.assertEqual((await self.client.put(self.url+'/'+id,headers=self.owner_headers,json=body)).status_code,409)
        self.assertEqual((await self.client.delete(self.url+'/'+id,headers=self.owner_headers)).status_code,405)
        for statement in (update(FinancialAccount).values(opening_balance=Decimal('0.00')),delete(FinancialAccount)):
            async with self.factory() as session:
                with self.assertRaises(SQLAlchemyError):
                    await session.execute(statement.where(FinancialAccount.id==UUID(id)));await session.commit()
                await session.rollback()
        listed=await self.client.get(self.url,headers=self.owner_headers,params={'status':'INACTIVE'})
        self.assertEqual(listed.json()['items'][0]['revision'],2)
        self.assertEqual(Decimal(listed.json()['items'][0]['opening_balance']),Decimal('-123.45'))

    async def test_idempotency_validation_cash_and_missing_encryption_key(self):
        key=str(uuid4());first=await self.create_account(key=key);second=await self.create_account(key=key)
        self.assertEqual(first.status_code,201,first.text);self.assertEqual(second.json(),first.json())
        changed=self.data();changed['opening_balance']='1.00'
        self.assertEqual((await self.create_account(changed,key=key)).status_code,409)
        for balance in ('NaN','1.001','+1','01.00',1.2):
            self.assertEqual((await self.create_account(self.data(opening_balance=balance))).status_code,422)
        self.assertEqual((await self.create_account(self.data(opening_date=(date.today()+timedelta(days=3)).isoformat()))).status_code,422)
        self.app.state.settings=self.config
        self.assertEqual((await self.create_account()).status_code,503)
        cash=dict(name='Caixa',kind='CASH',opening_balance='0',opening_date='2026-01-01')
        self.assertEqual((await self.create_account(cash)).status_code,201)
        self.assertEqual((await self.client.get(self.url)).status_code,401)

    async def test_manage_without_read_can_create_cash_but_not_read_private_data(self):
        await self.grant('accounts.manage');headers=self.headers[self.member.id]
        cash=dict(name='Caixa',kind='CASH',opening_balance='10.50',opening_date='2026-01-01')
        self.assertEqual((await self.create_account(cash,headers=headers)).status_code,201)
        self.assertEqual((await self.client.get(self.url,headers=headers)).status_code,404)
        self.assertEqual((await self.create_account(headers=headers)).status_code,404)
        await self.grant('accounts.bank')
        self.assertEqual((await self.create_account(headers=headers)).status_code,201)
        contexts=(await self.client.get('/api/v1/auth/workspaces',headers=headers)).json()['items']
        self.assertEqual(set(contexts[0]['permissions']),{'accounts.manage','accounts.bank'})
    async def test_encrypted_bank_payload_cannot_be_transplanted_to_another_account(self):
        first=await self.create_account();second=await self.create_account()
        self.assertEqual(first.status_code,201,first.text);self.assertEqual(second.status_code,201,second.text)
        a=UUID(first.json()['id']);b=UUID(second.json()['id'])
        async with self.factory() as session,session.begin():
            source=await session.get(FinancialAccount,(self.org.id,self.a.id,a))
            target=await session.get(FinancialAccount,(self.org.id,self.a.id,b))
            target.encrypted_bank=source.encrypted_bank
        result=await self.client.get(self.url+'/'+str(b)+'/bank-details',headers=self.owner_headers)
        self.assertEqual(result.status_code,503,result.text);self.assertNotIn('987654321',result.text)
        listed=await self.client.get(self.url,headers=self.owner_headers);self.assertEqual(listed.status_code,200)

    async def test_downgrade_preserves_accounts_and_audit(self):
        import asyncio
        result=await self.create_account();self.assertEqual(result.status_code,201,result.text)
        await self.session.close();await self.engine.dispose()
        with self.assertRaises(RuntimeError):
            await asyncio.to_thread(self.run_migration,'downgrade','b57329d81c04')
        listed=await self.client.get(self.url,headers=self.owner_headers)
        self.assertEqual(listed.status_code,200,listed.text);self.assertEqual(len(listed.json()['items']),1)

    async def test_contract_suspension_blocks_summary_and_bank_read(self):
        from app.modules.commercial.models import BusinessContract
        created=await self.create_account();self.assertEqual(created.status_code,201,created.text)
        async with self.factory() as session,session.begin():
            contract=await session.get(BusinessContract,self.org.id);contract.status='SUSPENDED'
        self.assertEqual((await self.client.get(self.url,headers=self.owner_headers)).status_code,404)
        self.assertEqual((await self.client.get(self.url+'/'+created.json()['id']+'/bank-details',headers=self.owner_headers)).status_code,404)
