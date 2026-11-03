"""Integrações isoladas de ciclo da conta e MFA, sem transporte de e-mails real."""
import asyncio
import base64
import os
import secrets
import unittest
from datetime import timedelta
from uuid import uuid4
from cryptography.fernet import Fernet
import httpx
from pydantic import SecretStr, ValidationError
from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker
from database_support import DatabaseTestCase
from app.core.config import Settings
from app.main import create_app
from app.modules.identity.account_models import AccountAction, AccountSecurity
from app.modules.identity.account_security import RegisterRequest, digest, now, totp
from app.modules.identity.models import User, UserPasswordCredential, UserSession, UserStatus
from app.modules.identity.passwords import hash_password
from app.modules.identity.sessions import SessionIssueDeniedError, SessionService


class TotpTests(unittest.TestCase):
    def test_registration_requires_full_name_and_valid_cpf_without_leaking_input(self):
        for extra in ({'cpf':'11111111111'}, {'cpf':'00000000190'}, {'name':'Nome'}, {'cpf':None}):
            data={'name':'Pessoa Teste','email':'ficticio@example.com','password':'Senha de teste @123','cpf':'00000000191',**extra}
            with self.assertRaises(ValidationError): RegisterRequest(**data)
        request=RegisterRequest(name='Pessoa Teste',email='ficticio@example.com',password='Senha de teste @123',cpf='000.000.001-91')
        self.assertNotIn('00000000191',repr(request))

    def test_rfc_6238_sha1_vectors(self):
        secret = base64.b32encode(b"12345678901234567890").decode()
        for timestamp, expected in [(59,"94287082"),(1111111109,"07081804"),(1111111111,"14050471"),
                                    (1234567890,"89005924"),(2000000000,"69279037"),(20000000000,"65353130")]:
            self.assertEqual(totp(secret, timestamp//30, digits=8), expected)


class TestDelivery:
    def __init__(self): self.messages = []
    async def send_account_action(self, **message): self.messages.append(message)


@unittest.skipUnless(os.environ.get("SD_RUN_DATABASE_TESTS")=="1" and os.environ.get("SD_RUN_REDIS_TESTS")=="1", "Infraestrutura isolada opt-in.")
class AccountSecurityTests(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.redis = Redis(host="127.0.0.1", port=6379, db=15, socket_timeout=2, socket_connect_timeout=2)
        self.addAsyncCleanup(self.redis.aclose)
        self.namespace = "sd-financeiro:test:"+uuid4().hex
        self.addAsyncCleanup(self.clear_redis)
        self.config = Settings(_env_file=None, database_password="ficticia", app_environment="test",
            auth_rate_limit_key=SecretStr(secrets.token_urlsafe(32)), auth_mfa_encryption_key=SecretStr(Fernet.generate_key().decode()),
            auth_identity_encryption_key=SecretStr(Fernet.generate_key().decode()), auth_account_limit=100, auth_origin_limit=200, auth_global_limit=300)
        self.factory=async_sessionmaker(self.engine,expire_on_commit=False,autoflush=False)
        self.app=create_app(self.config,session_factory=self.factory,redis_client=self.redis,rate_limit_namespace=self.namespace)
        context=self.app.router.lifespan_context(self.app)
        await context.__aenter__()
        self.addAsyncCleanup(context.__aexit__,None,None,None)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app,client=("127.0.0.1",12345),raise_app_exceptions=False),base_url="http://testserver")
        self.addAsyncCleanup(self.client.aclose)
        self.delivery=TestDelivery()
        self.password="Senha exclusiva @ de teste"

    async def clear_redis(self):
        keys=[key async for key in self.redis.scan_iter(match="{"+self.namespace+":*")]
        if keys: await self.redis.delete(*keys)

    async def post(self,path,body,token=None):
        return await self.client.post('/api/v1/auth/'+path,json=body,headers={"Authorization":"Bearer "+token} if token else {})

    async def user(self):
        user=User(name="Pessoa fictícia",email=uuid4().hex+"@example.com",status=UserStatus.ACTIVE)
        self.session.add(user);await self.session.flush()
        self.session.add(UserPasswordCredential(user_id=user.id,password_hash=(await hash_password(SecretStr(self.password))).get_secret_value()))
        await self.session.commit()
        result=await self.post('login',{'email':user.email,'password':self.password})
        self.assertEqual(result.status_code,200,result.text)
        return user,result.json()['access_token']

    async def enroll(self,user,token):
        setup=await self.post('mfa/setup',{'password':self.password},token)
        self.assertEqual(setup.status_code,200,setup.text)
        secret=setup.json()['secret']
        code=totp(secret,int(now().timestamp())//30)
        result=await self.post('mfa/enable',{'code':code},token)
        self.assertEqual(result.status_code,200,result.text)
        return secret,result.json()['recovery_codes']

    async def test_email_disabled_has_no_side_effects_or_false_success(self):
        email=uuid4().hex+'@example.com'
        result=await self.post('register',{'name':'Pessoa teste','cpf':'00000000191','email':email,'password':self.password})
        self.assertEqual(result.status_code,503)
        self.assertIsNone(await self.session.scalar(select(User.id).where(User.email==email)))
        self.assertEqual((await self.post('password/forgot',{'email':email})).status_code,503)
        self.assertFalse((await self.client.get('/api/v1/auth/capabilities')).json()['email_flows_available'])

    async def test_register_verify_single_use_no_permissions_or_login_before_verify(self):
        self.app.state.accounts.delivery=self.delivery
        email=uuid4().hex+'@example.com'
        result=await self.post('register',{'name':'Pessoa teste','cpf':'00000000191','email':email,'password':self.password})
        self.assertEqual(result.status_code,202,result.text)
        self.assertEqual((await self.post('login',{'email':email,'password':self.password})).status_code,401)
        token=self.delivery.messages[-1]['token'].get_secret_value()
        self.assertNotIn(token,result.text)
        action=await self.session.scalar(select(AccountAction).where(AccountAction.token_hash==digest(token)))
        self.assertNotEqual(action.token_hash,token)
        confirmed=await self.post('email/confirm',{'token':token})
        self.assertEqual(confirmed.status_code,200,confirmed.text)
        self.assertEqual((await self.post('email/confirm',{'token':token})).status_code,400)
        login=await self.post('login',{'email':email,'password':self.password})
        self.assertEqual(login.status_code,200)
        user=await self.session.scalar(select(User).where(User.email==email))
        self.assertFalse(user.can_provision_organizations)
        security=await self.session.get(AccountSecurity,user.id)
        self.assertNotIn('00000000191',security.cpf_encrypted)
        self.assertNotEqual(security.cpf_digest,digest('00000000191'))
        workspaces=await self.client.get('/api/v1/auth/workspaces',headers={'Authorization':'Bearer '+login.json()['access_token']})
        self.assertEqual(workspaces.status_code,200)
        self.assertEqual(workspaces.json()['items'],[])

    async def test_duplicate_cpf_is_generic_and_does_not_create_another_identity(self):
        self.app.state.accounts.delivery=self.delivery
        # CPF gerado só para este teste, evitando colisão com outros casos.
        digits=str(secrets.randbelow(900000000)+100000000)
        for size in (9,10):
            check=(sum(int(digits[i])*(size+1-i) for i in range(size))*10)%11
            digits+=str(0 if check==10 else check)
        emails=[uuid4().hex+'@example.com' for _ in range(2)]
        results=[await self.post('register',{'name':'Pessoa Teste','cpf':digits,'email':email,'password':self.password}) for email in emails]
        self.assertEqual([r.status_code for r in results],[202,202])
        self.assertEqual(results[0].text,results[1].text)
        self.assertIsNone(await self.session.scalar(select(User.id).where(User.email==emails[1])))

    async def test_expired_and_wrong_purpose_links_rejected(self):
        user,_=await self.user()
        token=secrets.token_urlsafe(32)
        self.session.add(AccountAction(user_id=user.id,purpose='RESET',token_hash=digest(token),created_at=now()-timedelta(hours=2),expires_at=now()-timedelta(hours=1)))
        await self.session.commit()
        self.assertEqual((await self.post('email/confirm',{'token':token})).status_code,400)
        self.assertEqual((await self.post('password/reset',{'token':token,'password':self.password+'2'})).status_code,400)

    async def test_unknown_and_existing_reset_return_same_public_response(self):
        self.app.state.accounts.delivery=self.delivery
        user,_=await self.user()
        existing=await self.post('password/forgot',{'email':user.email})
        unknown=await self.post('password/forgot',{'email':uuid4().hex+'@example.com'})
        self.assertEqual(existing.status_code,202)
        self.assertEqual(existing.text,unknown.text)
        self.assertEqual(len(self.delivery.messages),1)

    async def test_reset_revokes_sessions_challenges_keeps_mfa_and_single_use(self):
        self.app.state.accounts.delivery=self.delivery
        user,token=await self.user()
        await self.enroll(user,token)
        challenge=await self.post('login',{'email':user.email,'password':self.password})
        await self.post('password/forgot',{'email':user.email})
        action_token=self.delivery.messages[-1]['token'].get_secret_value()
        changed=await self.post('password/reset',{'token':action_token,'password':self.password+' nova'})
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertEqual((await self.post('password/reset',{'token':action_token,'password':self.password+' outra'})).status_code,400)
        self.assertEqual((await self.client.get('/api/v1/auth/mfa/status',headers={'Authorization':'Bearer '+token})).status_code,401)
        self.assertEqual((await self.post('login',{'email':user.email,'password':self.password})).status_code,401)
        self.assertTrue((await self.post('login',{'email':user.email,'password':self.password+' nova'})).json()['mfa_required'])
        self.assertEqual((await self.post('mfa/login',{'challenge_token':challenge.json()['challenge_token'],'code':'000000'})).status_code,400)

    async def test_mfa_challenge_not_bearer_and_recovery_single_use(self):
        user,token=await self.user()
        _,codes=await self.enroll(user,token)
        login=await self.post('login',{'email':user.email,'password':self.password})
        self.assertTrue(login.json()['mfa_required'])
        self.assertNotIn('access_token',login.json())
        challenge=login.json()['challenge_token']
        self.assertEqual((await self.client.get('/api/v1/auth/workspaces',headers={'Authorization':'Bearer '+challenge})).status_code,401)
        result=await self.post('mfa/login',{'challenge_token':challenge,'code':codes[0]})
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual((await self.post('mfa/login',{'challenge_token':challenge,'code':codes[0]})).status_code,400)
        next_challenge=(await self.post('login',{'email':user.email,'password':self.password})).json()['challenge_token']
        self.assertEqual((await self.post('mfa/login',{'challenge_token':next_challenge,'code':codes[0]})).status_code,400)
        self.assertEqual((await self.post('mfa/login',{'challenge_token':next_challenge,'code':codes[1]})).status_code,200)

    async def test_mfa_secret_encrypted_and_totp_replay_rejected(self):
        user,token=await self.user()
        secret,_=await self.enroll(user,token)
        security=await self.session.get(AccountSecurity,user.id)
        self.assertNotIn(secret,security.mfa_secret)
        login=await self.post('login',{'email':user.email,'password':self.password})
        code=totp(secret,int(now().timestamp())//30)
        self.assertEqual((await self.post('mfa/login',{'challenge_token':login.json()['challenge_token'],'code':code})).status_code,400)

    async def test_mfa_disable_needs_password_and_second_factor(self):
        user,token=await self.user()
        _,codes=await self.enroll(user,token)
        self.assertEqual((await self.post('mfa/disable',{'password':'errada','code':codes[0]},token)).status_code,400)
        self.assertEqual((await self.post('mfa/disable',{'password':self.password,'code':'000000'},token)).status_code,400)
        disabled=await self.post('mfa/disable',{'password':self.password,'code':codes[0]},token)
        self.assertEqual(disabled.status_code,200,disabled.text)
        self.assertIn('access_token',(await self.post('login',{'email':user.email,'password':self.password})).json())

    async def test_direct_session_issuance_cannot_bypass_mfa(self):
        user,token=await self.user()
        await self.enroll(user,token)
        async with self.factory() as writer:
            with self.assertRaises(SessionIssueDeniedError):
                await SessionService(writer).issue_for_authenticated_user(user.id)

    async def test_mfa_key_missing_fails_closed_for_enrolled_user(self):
        user,token=await self.user()
        await self.enroll(user,token)
        self.app.state.accounts.key=None
        result=await self.post('login',{'email':user.email,'password':self.password})
        self.assertEqual(result.status_code,503)
        self.assertNotIn('access_token',result.text)

    async def test_mfa_challenge_rate_limit_and_no_store(self):
        user,token=await self.user()
        _,codes=await self.enroll(user,token)
        challenge=(await self.post('login',{'email':user.email,'password':self.password})).json()['challenge_token']
        for _ in range(5):
            self.assertEqual((await self.post('mfa/login',{'challenge_token':challenge,'code':'not-a-code'})).status_code,400)
        refused=await self.post('mfa/login',{'challenge_token':challenge,'code':codes[0]})
        self.assertEqual(refused.status_code,429)
        self.assertEqual(refused.headers['cache-control'],'no-store')
        self.assertNotIn(challenge,refused.text)

    async def test_concurrent_challenge_consumption_only_one_session(self):
        user,token=await self.user()
        _,codes=await self.enroll(user,token)
        challenge=(await self.post('login',{'email':user.email,'password':self.password})).json()['challenge_token']
        results=await asyncio.gather(*(self.post('mfa/login',{'challenge_token':challenge,'code':codes[0]}) for _ in range(2)))
        self.assertEqual(sorted(result.status_code for result in results),[200,400])
