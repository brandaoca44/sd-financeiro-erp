"""Bootstrap do frontend sem conceder leitura de cadastros ou revelar clientes."""

from test_company_access import CompanyGrantHttpFixture


class WorkspaceHttpTests(CompanyGrantHttpFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.enable_business_contracts()

    async def contexts(self, user=None, **params):
        return await self.client.get("/api/v1/auth/workspaces",headers=self.headers[user or self.member.id],params=params)

    async def financial_grant(self):
        response=await self.client.put(self._grant_path().replace("read-access","permissions/payables.read"),headers=self.headers[self.owner.id],
            json={"status":"ACTIVE","expected_revision":0,"expected_company_revision":1,"expected_membership_revision":1,"password":self.password})
        self.assertEqual(response.status_code,200,response.text)

    async def test_no_financial_permission_means_no_company_directory(self):
        for user in (self.member,self.operator,self.colleague):
            response=await self.contexts(user.id)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json(),{"items":[],"next_cursor":None})

    async def test_financial_scope_does_not_expose_company_name_without_cadastral_read(self):
        await self.financial_grant()
        response=await self.contexts()
        self.assertEqual(len(response.json()["items"]),1)
        item=response.json()["items"][0]
        self.assertEqual(item["company_id"],str(self.a.id))
        self.assertIsNone(item["company_name"])
        self.assertEqual(item["permissions"],["payables.read"])
        self.assertEqual(set(item),{"organization_id","company_id","company_name","permissions"})
        self.assertEqual((await self._set()).status_code,200)
        self.assertEqual((await self.contexts()).json()["items"][0]["company_name"],self.a.legal_name)

    async def test_master_contexts_are_scoped_and_paginated_before_limit(self):
        first=await self.contexts(self.owner.id,limit=1)
        self.assertEqual(len(first.json()["items"]),1)
        self.assertIsNotNone(first.json()["next_cursor"])
        second=await self.contexts(self.owner.id,limit=100,cursor=first.json()["next_cursor"])
        ids={row["company_id"] for row in first.json()["items"]+second.json()["items"]}
        self.assertEqual(ids,{str(company.id) for company in (self.a,self.b,self.d,self.foreign)})

    async def test_revocation_and_inactivity_remove_workspace(self):
        await self.financial_grant()
        self.assertEqual((await self._member_status("INACTIVE",1)).status_code,200)
        self.assertEqual((await self.contexts()).json()["items"],[])

    async def test_auth_https_no_store_and_no_private_fields(self):
        response=await self.client.get("/api/v1/auth/workspaces")
        self.assertEqual(response.status_code,401)
        response=await self.contexts(self.owner.id)
        self.assertEqual(response.headers["cache-control"],"no-store")
        for private in ("email","tax_id","token","can_provision"):
            self.assertNotIn(private,response.text)
        self.app.state.settings=self.config.model_copy(update={"app_environment":"production"})
        self.assertEqual((await self.contexts()).status_code,503)
