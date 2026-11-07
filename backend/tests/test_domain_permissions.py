"""Autorizações por ação e omissão de dados sensíveis na resposta HTTP."""
from uuid import uuid4
from cryptography.fernet import Fernet
from pydantic import SecretStr
from test_payable_http import PayableHttpFixture

class DomainPermissionTests(PayableHttpFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.app.state.settings = self.config.model_copy(update={
            'auth_identity_encryption_key': SecretStr(Fernet.generate_key().decode())})
        self.root = self.path().removesuffix('/payables')
        self.people = self.root + '/collaborators'
        self.owner_headers = self.headers[self.owner.id]
        self.member_headers = self.headers[self.member.id]

    async def person(self):
        body = dict(name='Pessoa sintética', job_title='Analista financeiro', employment_type='CLT',
            admission_date='2026-01-01', details=dict(cpf='52998224725', phone='11912345678',
            bank='Banco sintético', branch='1234', account='56789', account_type='CORRENTE',
            monthly_compensation='5000.00', pix_type='EMAIL', pix_key='pessoa@example.com'))
        result = await self.client.post(self.people, headers={**self.owner_headers,
            'Idempotency-Key': str(uuid4())}, json=body)
        self.assertEqual(result.status_code, 201, result.text)
        return self.people + '/' + result.json()['id'], body

    async def test_payables_do_not_grant_billing_or_people(self):
        for key in ('payables.read', 'payables.manage', 'payables.settle', 'payables.reverse'):
            await self.grant(key)
        for url in (self.people, self.root + '/billing', self.root + '/customers'):
            self.assertEqual((await self.client.get(url, headers=self.member_headers)).status_code, 404)
        await self.grant('billing.read')
        self.assertEqual((await self.client.get(self.root + '/billing', headers=self.member_headers)).status_code, 200)
        other = self.path(company=self.b).removesuffix('/payables') + '/billing'
        self.assertEqual((await self.client.get(other, headers=self.member_headers)).status_code, 404)

    async def test_billing_actions_are_independent_and_revocable(self):
        await self.grant('billing.manage')
        headers = {**self.member_headers, 'Idempotency-Key': str(uuid4())}
        body = dict(customer='Cliente', service='Serviço', competence='2026-11-01',
            issue_date='2026-11-01', due_date='2026-11-10', amount='200.00')
        result = await self.client.post(self.root + '/billing', headers=headers, json=body)
        self.assertEqual(result.status_code, 201, result.text)
        url = self.root + '/billing/' + result.json()['id']
        self.assertEqual((await self.client.get(self.root + '/billing', headers=headers)).status_code, 404)
        payment = dict(amount='100.00', received_on='2026-11-05')
        self.assertEqual((await self.client.post(url + '/receipts', headers=headers, json=payment)).status_code, 404)
        await self.grant('billing.receive')
        result = await self.client.post(url + '/receipts', headers=headers, json=payment)
        self.assertEqual(result.status_code, 201, result.text)
        reverse = url + '/receipts/' + result.json()['id'] + '/reverse'
        self.assertEqual((await self.client.post(reverse, headers=headers, json={})).status_code, 404)
        await self.grant('billing.reverse')
        self.assertEqual((await self.client.post(reverse, headers=headers, json={})).status_code, 204)
        await self.grant('billing.reverse', status='INACTIVE', revision=1)
        self.assertEqual((await self.client.post(reverse, headers=headers, json={})).status_code, 404)

    async def test_private_groups_and_partial_update_preserve_hidden_values(self):
        url, body = await self.person()
        await self.grant('people.read')
        result = await self.client.get(url + '/details', headers=self.member_headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json(), {})
        await self.grant('people.compensation')
        self.assertEqual((await self.client.get(url + '/details', headers=self.member_headers)).json(), {'monthly_compensation':'5000.00'})
        await self.grant('people.update')
        update = {key:value for key,value in body.items() if key != 'details'}
        update.update(name='Pessoa atualizada', details={'monthly_compensation':'6000.00'})
        result = await self.client.put(url, headers=self.member_headers, json=update)
        self.assertEqual(result.status_code, 200, result.text)
        result = await self.client.get(url + '/details', headers=self.owner_headers)
        self.assertEqual(result.json()['account'], '56789')
        self.assertEqual(result.json()['cpf'], body['details']['cpf'])
        self.assertEqual(result.json()['monthly_compensation'], '6000.00')
        update['details'] = {'account':'99999'}
        self.assertEqual((await self.client.put(url, headers=self.member_headers, json=update)).status_code, 404)
        self.assertEqual((await self.client.get(url + '/details', headers=self.owner_headers)).json()['account'], '56789')
        await self.grant('people.compensation', status='INACTIVE', revision=1)
        self.assertEqual((await self.client.get(url + '/details', headers=self.member_headers)).json(), {})
        foreign = self.path(company=self.b).removesuffix('/payables') + '/collaborators/' + url.rsplit('/',1)[1] + '/details'
        self.assertEqual((await self.client.get(foreign, headers=self.member_headers)).status_code, 404)

    async def test_document_and_bank_groups_do_not_reveal_salary(self):
        url, body = await self.person()
        await self.grant('people.read')
        await self.grant('people.documents')
        result = await self.client.get(url + '/details', headers=self.member_headers)
        self.assertEqual(result.json()['cpf'], body['details']['cpf'])
        self.assertNotIn('account', result.json())
        self.assertNotIn('monthly_compensation', result.json())
        await self.grant('people.bank')
        result = await self.client.get(url + '/details', headers=self.member_headers)
        self.assertEqual(result.json()['pix_key'], 'pessoa@example.com')
        self.assertNotIn('monthly_compensation', result.json())
        result = await self.client.put(self._grant_path().replace('read-access','permissions/people.compensation'),
            headers=self.member_headers, json=dict(status='ACTIVE', expected_revision=0,
            expected_company_revision=1, expected_membership_revision=1, password=self.password))
        self.assertIn(result.status_code, (403,404))

    async def test_create_terminate_and_contract_are_independent(self):
        await self.grant('people.create')
        headers = {**self.member_headers, 'Idempotency-Key':str(uuid4())}
        basic = dict(name='Cadastro incompleto', job_title='Assistente')
        self.assertEqual((await self.client.post(self.people, headers=headers, json=basic)).status_code, 422)
        _, full = await self.person()
        result = await self.client.post(self.people, headers=headers, json=full)
        self.assertEqual(result.status_code, 404, result.text)
        await self.grant('people.documents')
        await self.grant('people.bank')
        full['details'].pop('monthly_compensation')
        result = await self.client.post(self.people, headers=headers, json=full)
        self.assertEqual(result.status_code, 201, result.text)
        url = self.people + '/' + result.json()['id']
        contexts = (await self.client.get('/api/v1/auth/workspaces', headers=headers)).json()['items']
        self.assertEqual(set(next(row for row in contexts if row['company_id'] == str(self.a.id))['permissions']),
            {'people.create', 'people.documents', 'people.bank'})
        payload = dict(date='2026-11-06', reason='SEM_JUSTA_CAUSA')
        self.assertEqual((await self.client.post(url + '/termination', headers=headers, json=payload)).status_code,404)
        await self.grant('people.terminate')
        self.assertEqual((await self.client.post(url + '/termination', headers=headers, json=payload)).status_code,200)
        from app.modules.commercial.models import BusinessContract
        async with self.factory() as session, session.begin():
            contract = await session.get(BusinessContract, self.org.id)
            contract.status = 'SUSPENDED'
        self.assertEqual((await self.client.post(url + '/termination', headers=headers, json=payload)).status_code,404)
