"""Integridade do backup e recuperação real sem tocar o banco principal."""

import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ops import postgres_backup as backup
from database_support import DatabaseTestCase


PASSWORD = "senha-exclusiva-apenas-do-teste-7391"
DUMP = b"PGDMP\x00dados sinteticos, nunca credenciais reais"


class BackupFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.encrypted = backup.seal(DUMP, PASSWORD)

    def test_roundtrip_and_no_plaintext(self):
        self.assertEqual(backup.unseal(self.encrypted, PASSWORD), DUMP)
        self.assertNotIn(DUMP, self.encrypted)

    def test_random_salt_and_ciphertext(self):
        self.assertNotEqual(backup.seal(DUMP, PASSWORD), self.encrypted)

    def test_wrong_password_rejected(self):
        with self.assertRaises(backup.BackupError):
            backup.unseal(self.encrypted, PASSWORD + "x")

    def test_corruption_truncation_and_appended_bytes_rejected(self):
        changed = bytearray(self.encrypted)
        changed[-10] ^= 1
        for value in (bytes(changed), self.encrypted[:-8], self.encrypted + b"ignored",
                      self.encrypted[:len(backup.MAGIC)], b"SQL: secret"):
            with self.subTest(length=len(value)), self.assertRaises(backup.BackupError):
                backup.unseal(value, PASSWORD)

    def test_salt_tampering_rejected(self):
        changed = bytearray(self.encrypted)
        changed[len(backup.MAGIC)] ^= 1
        with self.assertRaises(backup.BackupError):
            backup.unseal(bytes(changed), PASSWORD)

    def test_size_limits_and_non_dump_rejected(self):
        with self.assertRaises(backup.BackupError):
            backup.seal(b"plain SQL", PASSWORD)
        with patch.object(backup, "MAX_DUMP", 2), self.assertRaises(backup.BackupError):
            backup.seal(DUMP, PASSWORD)
        with patch.object(backup, "MAX_FILE", 2), self.assertRaises(backup.BackupError):
            backup.unseal(self.encrypted, PASSWORD)

    def test_short_password_rejected_before_dump(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(backup, "read_dump") as dump:
            with self.assertRaises(backup.BackupError):
                backup.create_backup(Path(folder) / "test.sdfbackup", "curta")
            dump.assert_not_called()

    def test_publication_encrypted_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(backup, "read_dump", return_value=DUMP):
            target = Path(folder) / "test.sdfbackup"
            backup.create_backup(target, PASSWORD)
            original = target.read_bytes()
            self.assertEqual(backup.unseal(original, PASSWORD), DUMP)
            with self.assertRaises(backup.BackupError):
                backup.create_backup(target, PASSWORD)
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(list(Path(folder).iterdir()), [target])

    def test_dump_failure_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(backup, "read_dump", side_effect=backup.BackupError("falha")):
            with self.assertRaises(backup.BackupError):
                backup.create_backup(Path(folder) / "test.sdfbackup", PASSWORD)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_publication_failure_removes_partial_file(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(backup, "read_dump", return_value=DUMP), patch.object(backup.os, "link", side_effect=OSError("falha simulada")):
            with self.assertRaises(OSError):
                backup.create_backup(Path(folder) / "test.sdfbackup", PASSWORD)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_untrusted_identifiers_rejected_before_subprocess(self):
        with patch.object(backup.subprocess, "Popen") as process:
            for container, database in (("--privileged", None), ("ok", "db; DROP DATABASE erp")):
                with self.assertRaises(backup.BackupError):
                    backup.read_dump(container, database)
            process.assert_not_called()

    def test_authentication_precedes_any_docker_call(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(backup, "_docker") as docker:
            target = Path(folder) / "test.sdfbackup"
            target.write_bytes(self.encrypted)
            with self.assertRaises(backup.BackupError):
                backup.verify_backup(target, PASSWORD + "wrong")
            docker.assert_not_called()

    def test_restore_failure_always_removes_only_own_container(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(backup, "_docker") as docker, patch.object(backup, "_sql", return_value=b"1"):
            target = Path(folder) / "test.sdfbackup"
            target.write_bytes(self.encrypted)
            docker.side_effect = [b"containerid", backup.BackupError("restore failed"), b""]
            with self.assertRaises(backup.BackupError):
                backup.verify_backup(target, PASSWORD)
            run_args = docker.call_args_list[0].args
            name = run_args[run_args.index("--name") + 1]
            self.assertRegex(name, r"^sd-restore-check-[0-9a-f]{32}$")
            self.assertEqual(docker.call_args_list[-1].args, ("rm", "--force", "--volumes", name))
            self.assertIn("none", run_args)
            self.assertNotIn("--publish", run_args)
            self.assertNotIn("--volume", run_args)

    def test_cli_does_not_accept_password_in_noninteractive_input(self):
        with patch("sys.stdin.isatty", return_value=False), patch.object(backup.getpass, "getpass") as prompt, contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(backup.main(["create", "test.sdfbackup"]), 1)
            prompt.assert_not_called()
            self.assertNotIn("Traceback", errors.getvalue())

    def test_wrong_revision_and_missing_schema_are_rejected_with_cleanup(self):
        for revision, columns in ((b"old_revision", b""), (backup._head().encode(), b"")):
            with self.subTest(revision=revision), tempfile.TemporaryDirectory() as folder:
                target = Path(folder) / "test.sdfbackup"
                target.write_bytes(self.encrypted)
                def query(container, sql):
                    if "version_num" in sql:
                        return revision
                    if "pg_constraint" in sql:
                        return b"0"
                    return columns
                with patch.object(backup, "_docker", return_value=b"" ) as docker, patch.object(backup, "_sql", side_effect=query):
                    with self.assertRaises(backup.BackupError):
                        backup.verify_backup(target, PASSWORD)
                    self.assertEqual(docker.call_args.args[:3], ("rm", "--force", "--volumes"))


@unittest.skipUnless(os.environ.get("SD_RUN_BACKUP_TESTS") == "1", "Defina SD_RUN_BACKUP_TESTS=1 para usar Docker na recuperação isolada.")
class BackupRecoveryTests(DatabaseTestCase):
    async def test_real_dump_restores_full_migrations_and_reads_tables(self):
        from sqlalchemy import text
        from uuid import uuid4
        organization_id = uuid4()
        await self.session.execute(text("INSERT INTO organizations (id, name, status) VALUES (:id, 'Empresa sintética do ensaio', 'ACTIVE')"), {"id": organization_id})
        await self.session.commit()
        dump = backup.read_dump("sd-financeiro-postgres", self.test_database)
        recovered = []
        actual_sql = backup._sql
        def inspect_recovered_data(container, query):
            result = actual_sql(container, query)
            if query == 'SELECT count(*) FROM public."organizations"':
                name = actual_sql(container, f"SELECT name FROM organizations WHERE id='{organization_id}'").decode().strip()
                self.assertEqual(name, "Empresa sintética do ensaio")
                recovered.append(organization_id)
            return result
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.sdfbackup"
            path.write_bytes(backup.seal(dump, PASSWORD))
            with patch.object(backup, "_sql", side_effect=inspect_recovered_data):
                result = backup.verify_backup(path, PASSWORD)
        self.assertEqual(recovered, [organization_id])
        self.assertEqual(result["revision"], backup._head())
        self.assertGreater(result["tables_checked"], 10)
        self.assertEqual((await self.session.execute(text("SELECT name FROM organizations WHERE id=:id"), {"id": organization_id})).scalar_one(), "Empresa sintética do ensaio")
        self.assertFalse(backup._docker("ps", "-aq", "--filter", "name=sd-restore-check-").strip())

    async def test_invalid_archive_cleans_up_real_container(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "invalid.sdfbackup"
            path.write_bytes(backup.seal(DUMP, PASSWORD))
            with self.assertRaises(backup.BackupError):
                backup.verify_backup(path, PASSWORD)
        self.assertFalse(backup._docker("ps", "-aq", "--filter", "name=sd-restore-check-").strip())
