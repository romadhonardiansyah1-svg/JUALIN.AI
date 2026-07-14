"""Regression tests for the P0.0a disposable PostgreSQL guard.

These tests are DB-free. Database state is represented by a strict cursor fake so
the guard contract can be tested before any real PostgreSQL operation is legal.
"""

from __future__ import annotations

import io
import os
import pathlib
import unittest
from contextlib import redirect_stderr
from unittest.mock import MagicMock, patch

from scripts.assert_disposable_database import (
    connect_and_verify,
    main,
    parse_dsn,
    validate_environment,
    validate_run_id,
    validate_url,
)


RUN_ID = "3f2504e0-4f89-4d3a-9a0c-0305e82c3301"
TOKEN = RUN_ID.replace("-", "")
DATABASE_NAME = f"jualin_test_{TOKEN}"
ROLE_NAME = f"jualin_test_role_{TOKEN}"
CONTAINER_NAME = f"jualin-test-db-{TOKEN}"
CONTAINER_ID = "a" * 64
PASSWORD = "test-only-password-with-32-characters"


def disposable_dsn(
    *,
    host: str = "127.0.0.1",
    database: str = DATABASE_NAME,
    role: str = ROLE_NAME,
    password: str = PASSWORD,
    query: str = "",
) -> str:
    suffix = f"?{query}" if query else ""
    return (
        f"postgresql+asyncpg://{role}:{password}@{host}:55432/"
        f"{database}{suffix}"
    )


class DisposableGuardValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patcher = patch.dict(
            os.environ,
            {"ENVIRONMENT": "test", "JUALIN_TEST_RUN_ID": RUN_ID},
            clear=False,
        )
        self.env_patcher.start()

    def tearDown(self) -> None:
        self.env_patcher.stop()

    def test_requires_exact_test_environment(self) -> None:
        os.environ["ENVIRONMENT"] = "production"
        with self.assertRaises(SystemExit):
            validate_environment()

        os.environ.pop("ENVIRONMENT")
        with self.assertRaises(SystemExit):
            validate_environment()

    def test_requires_canonical_uuid4_run_id(self) -> None:
        validate_run_id(RUN_ID)

        invalid_ids = (
            "",
            "predictable-test-run-1234567890",
            "6ba7b810-9dad-11d1-80b4-00c04fd430c8",  # UUIDv1
            RUN_ID.upper(),
        )
        for invalid in invalid_ids:
            with self.subTest(run_id=invalid), self.assertRaises(SystemExit):
                validate_run_id(invalid)

    def test_accepts_only_exact_run_bound_database_and_role(self) -> None:
        validate_url(parse_dsn(disposable_dsn()), RUN_ID)
        validate_url(parse_dsn(disposable_dsn(host=CONTAINER_NAME)), RUN_ID)

        mismatches = (
            disposable_dsn(database=f"{DATABASE_NAME}0"),
            disposable_dsn(role=f"{ROLE_NAME}0"),
            disposable_dsn(role="postgres"),
            "postgresql+asyncpg://postgres:postgres@localhost:5432/jualin_ai",
        )
        for dsn in mismatches:
            with self.subTest(dsn=dsn), self.assertRaises(SystemExit):
                validate_url(parse_dsn(dsn), RUN_ID)

    def test_rejects_unknown_or_deployment_hosts(self) -> None:
        for host in (
            "db",
            "postgres",
            "some-test-host",
            "prod-db.example.com",
            "db.supabase.co",
            "cluster.rds.amazonaws.com",
            "db.neon.tech",
        ):
            with self.subTest(host=host), self.assertRaises(SystemExit):
                validate_url(parse_dsn(disposable_dsn(host=host)), RUN_ID)

    def test_rejects_missing_or_short_credentials(self) -> None:
        invalid = (
            disposable_dsn(password=""),
            disposable_dsn(password="password"),
            f"postgresql+asyncpg://{ROLE_NAME}@127.0.0.1:55432/{DATABASE_NAME}",
        )
        for dsn in invalid:
            with self.subTest(dsn=dsn), self.assertRaises(SystemExit):
                validate_url(parse_dsn(dsn), RUN_ID)

    def test_rejects_all_query_parameters_and_connection_overrides(self) -> None:
        unsafe_queries = (
            "sslmode=require",
            "sslmode=disable",
            "sslrootcert=%2Ftmp%2Fca.pem",
            "hostaddr=10.0.0.4",
            "target_session_attrs=read-write",
        )
        for query in unsafe_queries:
            with self.subTest(query=query), self.assertRaises(SystemExit):
                validate_url(parse_dsn(disposable_dsn(query=query)), RUN_ID)

    def test_rejects_non_postgresql_driver_and_missing_explicit_port(self) -> None:
        with self.assertRaises(SystemExit):
            validate_url(
                parse_dsn(
                    f"mysql://{ROLE_NAME}:{PASSWORD}@127.0.0.1:3306/{DATABASE_NAME}"
                ),
                RUN_ID,
            )

        with self.assertRaises(SystemExit):
            validate_url(
                parse_dsn(
                    f"postgresql+asyncpg://{ROLE_NAME}:{PASSWORD}@127.0.0.1/"
                    f"{DATABASE_NAME}"
                ),
                RUN_ID,
            )


class DisposableGuardDatabaseStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patcher = patch.dict(
            os.environ,
            {
                "JUALIN_TEST_CONTAINER_ID": CONTAINER_ID,
                "JUALIN_TEST_SERVER_ADDRESS": "172.18.0.2",
            },
            clear=False,
        )
        self.env_patcher.start()

    def tearDown(self) -> None:
        self.env_patcher.stop()

    def _connection(
        self,
        mock_psycopg2: MagicMock,
        *,
        current_database: str = DATABASE_NAME,
        current_user: str = ROLE_NAME,
        session_user: str = ROLE_NAME,
        server_address: str | None = "172.18.0.2",
        server_port: int | None = 5432,
        role_capabilities: tuple[bool, ...] = (
            True,
            False,
            False,
            False,
            False,
            False,
            False,
        ),
        database_owner: str = ROLE_NAME,
        has_role_membership: bool = False,
        sentinel_owner: tuple[str, str] | None = (ROLE_NAME, "r"),
        sentinel: tuple[str, str, str, str, int] | None = (
            RUN_ID,
            DATABASE_NAME,
            ROLE_NAME,
            CONTAINER_ID,
            1,
        ),
    ) -> tuple[MagicMock, MagicMock]:
        connection = MagicMock()
        cursor = MagicMock()
        mock_psycopg2.connect.return_value = connection
        connection.cursor.return_value = cursor

        def execute(query: str, params=None) -> None:
            cursor.last_query = " ".join(str(query).lower().split())
            if "inet_server_addr()" in cursor.last_query:
                self.assertIn("host(inet_server_addr())", cursor.last_query)

        def fetchone():
            query = cursor.last_query
            if "from pg_catalog.pg_database" in query:
                return (database_owner,)
            if "from pg_catalog.pg_auth_members" in query:
                return (has_role_membership,)
            if "from pg_catalog.pg_class" in query:
                if sentinel_owner is None or sentinel_owner[1] != "r":
                    return None
                if ", c.relkind" in query:
                    return sentinel_owner
                return (sentinel_owner[0],)
            if "from public.disposable_db_sentinel" in query or (
                "from disposable_db_sentinel" in query
            ):
                if sentinel is None or "count(*) over" in query:
                    return sentinel
                return sentinel[:4]
            if "from pg_catalog.pg_roles" in query:
                return role_capabilities
            if "current_database()" in query:
                return (
                    current_database,
                    current_user,
                    session_user,
                    server_address,
                    server_port,
                )
            if "inet_server_addr()" in query:
                return (server_address, server_port)
            raise AssertionError(f"Unexpected guard query: {query}")

        cursor.execute.side_effect = execute
        cursor.fetchone.side_effect = fetchone
        cursor.fetchall.return_value = []
        return connection, cursor

    @patch("scripts.assert_disposable_database.psycopg2")
    def test_exact_provisioned_identity_passes_read_only(self, mock_psycopg2) -> None:
        connection, _ = self._connection(mock_psycopg2)

        actual = connect_and_verify(disposable_dsn(), RUN_ID)

        self.assertEqual(actual, (DATABASE_NAME, ROLE_NAME))
        connection.set_session.assert_called_once_with(readonly=True, autocommit=True)
        mock_psycopg2.connect.assert_called_once_with(
            host="127.0.0.1",
            dbname=DATABASE_NAME,
            user=ROLE_NAME,
            password=PASSWORD,
            port=55432,
            connect_timeout=5,
            sslmode="disable",
            application_name="jualin-disposable-db-guard",
        )

    @patch("scripts.assert_disposable_database.psycopg2")
    def test_wrong_actual_role_fails(self, mock_psycopg2) -> None:
        self._connection(mock_psycopg2, current_user="postgres", session_user="postgres")
        with self.assertRaises(SystemExit):
            connect_and_verify(disposable_dsn(), RUN_ID)

    @patch("scripts.assert_disposable_database.psycopg2")
    def test_session_role_switch_fails(self, mock_psycopg2) -> None:
        self._connection(mock_psycopg2, session_user="bootstrap_admin")
        with self.assertRaises(SystemExit):
            connect_and_verify(disposable_dsn(), RUN_ID)

    @patch("scripts.assert_disposable_database.psycopg2")
    def test_privileged_or_inherited_role_fails(self, mock_psycopg2) -> None:
        unsafe_capabilities = (True, True, False, False, False, False, False)
        self._connection(mock_psycopg2, role_capabilities=unsafe_capabilities)
        with self.assertRaises(SystemExit):
            connect_and_verify(disposable_dsn(), RUN_ID)

        inheriting_capabilities = (True, False, False, False, False, False, True)
        self._connection(mock_psycopg2, role_capabilities=inheriting_capabilities)
        with self.assertRaises(SystemExit):
            connect_and_verify(disposable_dsn(), RUN_ID)

        self._connection(mock_psycopg2, has_role_membership=True)
        with self.assertRaises(SystemExit):
            connect_and_verify(disposable_dsn(), RUN_ID)

    @patch("scripts.assert_disposable_database.psycopg2")
    def test_wrong_database_or_sentinel_owner_fails(self, mock_psycopg2) -> None:
        self._connection(mock_psycopg2, database_owner="bootstrap_admin")
        with self.assertRaises(SystemExit):
            connect_and_verify(disposable_dsn(), RUN_ID)

        self._connection(mock_psycopg2, sentinel_owner=("bootstrap_admin", "r"))
        with self.assertRaises(SystemExit):
            connect_and_verify(disposable_dsn(), RUN_ID)

    @patch("scripts.assert_disposable_database.psycopg2")
    def test_missing_or_foreign_sentinel_fails(self, mock_psycopg2) -> None:
        self._connection(mock_psycopg2, sentinel=None)
        with self.assertRaises(SystemExit):
            connect_and_verify(disposable_dsn(), RUN_ID)

        foreign = (
            "d9428888-122b-4d74-99f1-cd520f4f0c64",
            DATABASE_NAME,
            ROLE_NAME,
            CONTAINER_ID,
            1,
        )
        self._connection(mock_psycopg2, sentinel=foreign)
        with self.assertRaises(SystemExit):
            connect_and_verify(disposable_dsn(), RUN_ID)

        foreign_container = (RUN_ID, DATABASE_NAME, ROLE_NAME, "b" * 64, 1)
        self._connection(mock_psycopg2, sentinel=foreign_container)
        with self.assertRaises(SystemExit):
            connect_and_verify(disposable_dsn(), RUN_ID)

    @patch("scripts.assert_disposable_database.psycopg2")
    def test_public_or_missing_server_endpoint_fails(self, mock_psycopg2) -> None:
        self._connection(mock_psycopg2, server_address="203.0.113.10")
        with self.assertRaises(SystemExit):
            connect_and_verify(disposable_dsn(), RUN_ID)

        self._connection(mock_psycopg2, server_address=None, server_port=None)
        with self.assertRaises(SystemExit):
            connect_and_verify(disposable_dsn(), RUN_ID)

        self._connection(mock_psycopg2, server_address="172.18.0.3")
        with self.assertRaises(SystemExit):
            connect_and_verify(disposable_dsn(), RUN_ID)

    @patch("scripts.assert_disposable_database.psycopg2")
    def test_sentinel_must_be_one_owned_ordinary_table(self, mock_psycopg2) -> None:
        self._connection(mock_psycopg2, sentinel_owner=(ROLE_NAME, "v"))
        with self.assertRaises(SystemExit):
            connect_and_verify(disposable_dsn(), RUN_ID)

        duplicate = (RUN_ID, DATABASE_NAME, ROLE_NAME, CONTAINER_ID, 2)
        self._connection(mock_psycopg2, sentinel=duplicate)
        with self.assertRaises(SystemExit):
            connect_and_verify(disposable_dsn(), RUN_ID)

    @patch("scripts.assert_disposable_database.psycopg2")
    def test_unreachable_error_does_not_leak_credentials(self, mock_psycopg2) -> None:
        mock_psycopg2.connect.side_effect = RuntimeError(
            f"connection failed with password={PASSWORD}"
        )
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            connect_and_verify(disposable_dsn(), RUN_ID)
        self.assertNotIn(PASSWORD, stderr.getvalue())


class GuardSourceSafetyTests(unittest.TestCase):
    def test_guard_does_not_provision_or_mutate_database(self) -> None:
        path = pathlib.Path(__file__).parent.parent / "scripts" / "assert_disposable_database.py"
        content = path.read_text(encoding="utf-8").upper()
        self.assertNotIn("CREATE TABLE", content)
        self.assertNotIn("INSERT INTO", content)
        self.assertNotIn("SENTINEL_TABLES", content)

    @patch("scripts.assert_disposable_database.connect_and_verify")
    def test_cli_rejects_authority_overrides_that_differ_from_environment(
        self, mock_connect
    ) -> None:
        other_run_id = "d9428888-122b-4d74-99f1-cd520f4f0c64"
        env = {
            "ENVIRONMENT": "test",
            "JUALIN_TEST_RUN_ID": RUN_ID,
            "DATABASE_URL": disposable_dsn(),
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "sys.argv", ["guard", "--run-id", other_run_id]
        ), self.assertRaises(SystemExit):
            main()
        mock_connect.assert_not_called()

        with patch.dict(os.environ, env, clear=True), patch(
            "sys.argv", ["guard", "--dsn", disposable_dsn(host=CONTAINER_NAME)]
        ), self.assertRaises(SystemExit):
            main()
        mock_connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
