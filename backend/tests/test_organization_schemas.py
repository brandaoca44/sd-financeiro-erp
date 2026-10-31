"""Valida os contratos de organização sem conexão com banco de dados."""

import json
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from app.modules.organizations.models import Organization, OrganizationStatus
from app.modules.organizations.schemas import OrganizationCreate, OrganizationResponse


class OrganizationCreateTests(unittest.TestCase):
    """Verifica o nome e impede a entrada de campos controlados pelo sistema."""

    def test_normalizes_name_preserving_internal_spaces(self):
        schema = OrganizationCreate(name=" \tEmpresa  Exemplo\n")
        self.assertEqual(schema.name, "Empresa  Exemplo")
        self.assertEqual(schema.model_dump(), {"name": "Empresa  Exemplo"})

    def test_accepts_limit_after_trimming(self):
        schema = OrganizationCreate(name=" " + "á" * 150 + " ")
        self.assertEqual(schema.name, "á" * 150)

    def test_rejects_invalid_names(self):
        for name in ("", " \t\n", "a" * 151, None, 123, [], {}):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                OrganizationCreate(name=name)

    def test_requires_name(self):
        with self.assertRaises(ValidationError):
            OrganizationCreate()

    def test_rejects_system_and_unknown_fields(self):
        for field, value in {
            "id": str(uuid4()),
            "status": "INACTIVE",
            "created_at": "2026-10-30T12:00:00Z",
            "updated_at": "2026-10-30T12:00:00Z",
            "companies": [],
            "unknown": "valor",
        }.items():
            with self.subTest(field=field), self.assertRaises(ValidationError):
                OrganizationCreate.model_validate({"name": "Empresa", field: value})


class OrganizationResponseTests(unittest.TestCase):
    """Valida serialização ORM e o contrato explícito de saída."""

    def test_serializes_orm_without_relationships(self):
        now = datetime.now(timezone.utc)
        organization = Organization(
            id=uuid4(),
            name="Empresa Exemplo",
            status=OrganizationStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        response = OrganizationResponse.model_validate(organization)
        payload = json.loads(response.model_dump_json())
        self.assertEqual(
            set(payload), {"id", "name", "status", "created_at", "updated_at"}
        )
        self.assertEqual(payload["id"], str(organization.id))
        self.assertEqual(payload["name"], organization.name)
        self.assertEqual(payload["status"], "ACTIVE")
        self.assertEqual(response.created_at, now)
        self.assertEqual(response.updated_at, now)

    def test_accepts_inactive_status(self):
        now = datetime.now(timezone.utc)
        response = OrganizationResponse(
            id=uuid4(), name="Empresa", status=OrganizationStatus.INACTIVE,
            created_at=now, updated_at=now,
        )
        self.assertEqual(response.status, OrganizationStatus.INACTIVE)

    def test_rejects_invalid_response_data(self):
        now = datetime.now(timezone.utc)
        valid = dict(
            id=uuid4(), name="Empresa", status="ACTIVE",
            created_at=now, updated_at=now,
        )
        for field, value in (
            ("id", "invalido"), ("status", "UNKNOWN"),
            ("created_at", now.replace(tzinfo=None)),
            ("updated_at", now.replace(tzinfo=None)),
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                OrganizationResponse.model_validate({**valid, field: value})

    def test_requires_system_fields_in_response(self):
        with self.assertRaises(ValidationError):
            OrganizationResponse.model_validate({"name": "Empresa"})


if __name__ == "__main__":
    unittest.main()
