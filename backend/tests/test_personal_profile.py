"""Perfil pessoal e Pix, com isolamento, criptografia e confirmação de alterações."""
import unittest
from uuid import uuid4

from cryptography.fernet import Fernet
from pydantic import SecretStr, ValidationError

from app.modules.identity.pix import PixDetails
from app.modules.identity.profile import UserProfile
from test_company_access import CompanyGrantHttpFixture


class PixValidationTests(unittest.TestCase):
    def test_pix_pair_and_formats(self):
        with self.assertRaises(ValidationError):
            PixDetails(pix_type="EMAIL", pix_key="invalido")
        with self.assertRaises(ValidationError):
            PixDetails(pix_type="CPF")
        with self.assertRaises(ValidationError):
            PixDetails(pix_type="PHONE", pix_key="11912345678")
        self.assertEqual(PixDetails(pix_type="PHONE", pix_key="+5511912345678").pix_key, "+5511912345678")
        self.assertIsNone(PixDetails().pix_key)
        key = str(uuid4())
        self.assertEqual(PixDetails(pix_type="RANDOM", pix_key=key).pix_key, key)


class PersonalProfileTests(CompanyGrantHttpFixture):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.app.state.settings = self.config.model_copy(update={
            "auth_identity_encryption_key": SecretStr(Fernet.generate_key().decode())})
        self.endpoint = "/api/v1/auth/profile"

    async def test_profile_is_private_encrypted_and_revision_protected(self):
        headers = self.headers[self.owner.id]
        first = await self.client.get(self.endpoint, headers=headers)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["revision"], 0)
        payload = dict(name="Pessoa Exemplo", cpf="52998224725", rg="1234567", phone="11912345678",
                       bank="Banco de teste", branch="1234", account="56789", account_type="CORRENTE",
                       pix_type="EMAIL", pix_key="pessoa@example.com", expected_revision=0, password=self.password)
        saved = await self.client.put(self.endpoint, headers=headers, json=payload)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertTrue(saved.json()["cpf_locked"])
        self.assertEqual(saved.headers["cache-control"], "no-store")
        self.assertNotIn("password", saved.json())
        async with self.factory() as session:
            row = await session.get(UserProfile, self.owner.id)
            self.assertNotIn("52998224725", row.encrypted_data)
            self.assertNotIn("pessoa@example.com", row.encrypted_data)
        other = await self.client.get(self.endpoint, headers=self.headers[self.member.id])
        self.assertEqual(other.status_code, 200, other.text)
        self.assertIsNone(other.json()["cpf"])
        self.assertIsNone(other.json()["account"])
        conflict = await self.client.put(self.endpoint, headers=headers, json=payload)
        self.assertEqual(conflict.status_code, 409, conflict.text)
        reread = await self.client.get(self.endpoint, headers=headers)
        self.assertEqual(reread.json()["revision"], 1)
        self.assertEqual(reread.json()["cpf"], payload["cpf"])

    async def test_collaborator_pix_is_saved_only_in_private_details(self):
        base = f"/api/v1/organizations/{self.org.id}/companies/{self.a.id}/collaborators"
        headers = {**self.headers[self.owner.id], "Idempotency-Key": str(uuid4())}
        details = dict(cpf="52998224725", phone="11912345678", bank="Banco de teste",
                       branch="1234", account="56789", account_type="CORRENTE",
                       pix_type="PHONE", pix_key="+5511912345678")
        created = await self.client.post(base, headers=headers,
            json=dict(name="Pessoa Exemplo", job_title="Analista financeiro", details=details))
        self.assertEqual(created.status_code, 201, created.text)
        self.assertNotIn("pix_key", created.json())
        listed = await self.client.get(base, headers=headers)
        self.assertNotIn("pix_key", listed.json()[0])
        private = await self.client.get(base + "/" + created.json()["id"] + "/details", headers=headers)
        self.assertEqual(private.status_code, 200, private.text)
        self.assertEqual(private.json()["pix_key"], details["pix_key"])
        invalid = await self.client.post(base, headers={**headers, "Idempotency-Key": str(uuid4())},
            json=dict(name="Pessoa Exemplo", job_title="Analista financeiro",
                      details={**details, "pix_key": "telefone errado"}))
        self.assertEqual(invalid.status_code, 422)

    async def test_password_required_and_cpf_immutable(self):
        headers = self.headers[self.owner.id]
        payload = dict(name="Pessoa Exemplo", cpf="52998224725", expected_revision=0, password="senha errada")
        denied = await self.client.put(self.endpoint, headers=headers, json=payload)
        self.assertEqual(denied.status_code, 403, denied.text)
        payload["password"] = self.password
        saved = await self.client.put(self.endpoint, headers=headers, json=payload)
        self.assertEqual(saved.status_code, 200, saved.text)
        payload.update(expected_revision=1, cpf=None)
        denied = await self.client.put(self.endpoint, headers=headers, json=payload)
        self.assertEqual(denied.status_code, 409, denied.text)
        anonymous = await self.client.get(self.endpoint)
        self.assertEqual(anonymous.status_code, 401)
