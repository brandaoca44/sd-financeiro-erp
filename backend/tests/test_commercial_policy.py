"""Direitos de uso não concedem permissão e plano superior não libera segmentos."""
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from app.core.config import Settings
from app.main import create_app
from app.modules.commercial.catalog import CATALOG_VERSION, FEATURES, PLANS, Feature, Plan, Segment
from app.modules.commercial.policy import (
    AccessSnapshot, ContractSnapshot, ContractState, Denial, evaluate_access, evaluate_capacity,
)


class CommercialPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,2,tzinfo=timezone.utc)
        self.org,self.company,self.user=uuid4(),uuid4(),uuid4()
        self.access=AccessSnapshot(self.user,self.org,self.company,Segment.BUSINESS,
            active_user=True,active_membership=True,active_organization=True,active_company=True,
            company_authorized=True,permissions=frozenset({'payables.read'}))
        self.contract=ContractSnapshot(self.org,Segment.BUSINESS,Plan.ESSENTIAL,CATALOG_VERSION,
            ContractState.ACTIVE,self.now-timedelta(days=1),self.now+timedelta(days=30),frozenset({self.company}))

    def decide(self,access=None,contract=None,**changes):
        return evaluate_access(access or self.access,contract or self.contract,
            **{'feature':Feature.PAYABLES,'permission':'payables.read','now':self.now,**changes})

    def test_active_contract_scope_and_permission_allow_existing_operation(self):
        for plan in Plan:
            self.assertTrue(self.decide(contract=replace(self.contract,plan=plan)).allowed)

    def test_license_alone_does_not_grant_read(self):
        self.assertEqual(self.decide(access=replace(self.access,permissions=frozenset())).denial,Denial.PERMISSION_DENIED)

    def test_permission_alone_does_not_replace_contract(self):
        result=evaluate_access(self.access,None,feature=Feature.PAYABLES,permission='payables.read',now=self.now)
        self.assertEqual(result.denial,Denial.NO_CONTRACT)

    def test_each_operation_requires_its_own_permission(self):
        for action in ('payables.manage','payables.settle','payables.reverse','companies.read'):
            self.assertEqual(self.decide(permission=action).denial,Denial.PERMISSION_DENIED)

    def test_summary_never_accepts_write_permission_as_read(self):
        writer=replace(self.access,permissions=frozenset({'payables.manage'}))
        self.assertEqual(self.decide(access=writer,feature=Feature.PAYABLES_SUMMARY,permission='payables.manage').denial,Denial.PERMISSION_DENIED)

    def test_same_plan_name_in_another_segment_does_not_grant_business(self):
        for segment in (Segment.HEALTH,Segment.RETAIL,Segment.INDUSTRY):
            contract=replace(self.contract,segment=segment,plan=Plan.ENTERPRISE)
            self.assertEqual(self.decide(contract=contract).denial,Denial.CONTEXT_MISMATCH)

    def test_other_segments_remain_unavailable_even_with_enterprise(self):
        for segment in (Segment.HEALTH,Segment.RETAIL,Segment.INDUSTRY):
            access=replace(self.access,segment=segment)
            contract=replace(self.contract,segment=segment,plan=Plan.ENTERPRISE)
            self.assertEqual(self.decide(access=access,contract=contract).denial,Denial.SEGMENT_UNAVAILABLE)

    def test_cross_tenant_contract_is_denied(self):
        self.assertEqual(self.decide(contract=replace(self.contract,organization_id=uuid4())).denial,Denial.CONTEXT_MISMATCH)

    def test_company_must_be_explicitly_enabled(self):
        self.assertEqual(self.decide(contract=replace(self.contract,enabled_companies=frozenset({uuid4()}))).denial,Denial.COMPANY_DISABLED)

    def test_disabled_identity_membership_tenant_or_company_blocks(self):
        for key in ('active_user','active_membership','active_organization','active_company','company_authorized'):
            self.assertEqual(self.decide(access=replace(self.access,**{key:False})).denial,Denial.UNAUTHORIZED)

    def test_all_non_active_contract_states_deny(self):
        for state in (ContractState.SUSPENDED,ContractState.CANCELLED,ContractState.PENDING):
            self.assertEqual(self.decide(contract=replace(self.contract,state=state)).denial,Denial.INACTIVE_CONTRACT)

    def test_validity_start_inclusive_end_exclusive(self):
        self.assertTrue(self.decide(contract=replace(self.contract,valid_from=self.now)).allowed)
        for changes in ({'valid_from':self.now+timedelta(seconds=1)},{'valid_until':self.now}):
            self.assertEqual(self.decide(contract=replace(self.contract,**changes)).denial,Denial.CONTRACT_OUTSIDE_VALIDITY)

    def test_unknown_catalog_is_not_upgraded_silently(self):
        self.assertEqual(self.decide(contract=replace(self.contract,catalog_version='unknown')).denial,Denial.UNKNOWN_CATALOG)

    def test_higher_plan_does_not_enable_unimplemented_feature(self):
        for plan in Plan:
            self.assertEqual(self.decide(contract=replace(self.contract,plan=plan),feature=Feature.RECEIVABLES).denial,Denial.FEATURE_UNAVAILABLE)

    def test_unlicensed_feature_is_rejected(self):
        self.assertEqual(self.decide(feature=Feature.CONSOLIDATION).denial,Denial.FEATURE_NOT_INCLUDED)

    def test_immutable_catalog_and_snapshots(self):
        with self.assertRaises(TypeError): PLANS[Plan.ESSENTIAL]=PLANS[Plan.ENTERPRISE]
        with self.assertRaises(TypeError): FEATURES[Feature.PAYABLES]=None
        with self.assertRaises(FrozenInstanceError): self.contract.plan=Plan.ENTERPRISE
        self.assertTrue(PLANS[Plan.ESSENTIAL].features <= PLANS[Plan.PROFESSIONAL].features <= PLANS[Plan.ENTERPRISE].features)

    def test_plain_client_dictionaries_and_unknown_keys_are_not_trusted(self):
        result=evaluate_access({'active_user':True,'plan':'ENTERPRISE'},self.contract,feature=Feature.PAYABLES,permission='payables.read',now=self.now)
        self.assertEqual(result.denial,Denial.INVALID_CONTEXT)
        for changes in ({'feature':'business.payables'},{'permission':True},{'now':datetime(2026,11,2)}):
            self.assertEqual(self.decide(**changes).denial,Denial.INVALID_CONTEXT)

    def test_malformed_contract_or_access_is_denied(self):
        for changes in ({'plan':'ENTERPRISE'},{'enabled_companies':{self.company}}, {'valid_until':self.contract.valid_from}):
            self.assertEqual(self.decide(contract=replace(self.contract,**changes)).denial,Denial.INVALID_CONTEXT)
        self.assertEqual(self.decide(access=replace(self.access,active_user=1)).denial,Denial.INVALID_CONTEXT)

    def test_essential_limit_accepts_exact_capacity_and_rejects_excess(self):
        for resource,limit in (('companies',1),('users',3)):
            common={'resource':resource,'requested':1,'now':self.now}
            self.assertTrue(evaluate_capacity(self.access,self.contract,used=limit-1,**common).allowed)
            self.assertEqual(evaluate_capacity(self.access,self.contract,used=limit,**common).denial,Denial.LIMIT_EXCEEDED)

    def test_professional_limits_and_no_ad_hoc_override(self):
        contract=replace(self.contract,plan=Plan.PROFESSIONAL)
        self.assertTrue(evaluate_capacity(self.access,contract,resource='users',used=19,requested=1,now=self.now).allowed)
        self.assertEqual(evaluate_capacity(self.access,replace(contract,users_limit=100),resource='users',used=19,requested=1,now=self.now).denial,Denial.INVALID_CONTEXT)

    def test_enterprise_requires_defined_capacity(self):
        contract=replace(self.contract,plan=Plan.ENTERPRISE)
        self.assertEqual(evaluate_capacity(self.access,contract,resource='users',used=0,requested=1,now=self.now).denial,Denial.UNDEFINED_LIMIT)
        self.assertTrue(evaluate_capacity(self.access,replace(contract,users_limit=50),resource='users',used=49,requested=1,now=self.now).allowed)

    def test_negative_boolean_unknown_and_fractional_capacity_are_denied(self):
        base={'resource':'users','used':0,'requested':1,'now':self.now}
        for changes in ({'used':-1},{'used':True},{'requested':0},{'requested':1.2},{'resource':'employees'}):
            self.assertEqual(evaluate_capacity(self.access,self.contract,**{**base,**changes}).denial,Denial.INVALID_CONTEXT)

    def test_capacity_check_also_requires_valid_active_contract_and_scope(self):
        result=evaluate_capacity(self.access,replace(self.contract,state=ContractState.SUSPENDED),resource='users',used=0,requested=1,now=self.now)
        self.assertEqual(result.denial,Denial.INACTIVE_CONTRACT)


class ProductCatalogHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_exposes_only_public_definitions_and_never_checkout(self):
        settings=Settings(_env_file=None,database_password='ficticia',app_environment='test')
        app=create_app(settings)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            response=await client.get('/api/v1/catalog/plans')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['cache-control'],'no-store')
        data=response.json()
        self.assertFalse(data['published']);self.assertFalse(data['checkout_available'])
        self.assertEqual([plan['key'] for plan in data['plans']],['ESSENTIAL','PROFESSIONAL','ENTERPRISE'])
        self.assertEqual(set(data['available_features']),{'business.payables','business.payables.summary'})
        for private in ('organization_id','company_id','user_id','token','password','price','cpf'):
            self.assertNotIn(private,response.text)
