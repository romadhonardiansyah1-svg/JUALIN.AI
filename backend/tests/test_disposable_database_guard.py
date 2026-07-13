"""
Test for disposable database guard — P0.0a
Red tests: ambient, non-test env, forged name without sentinel, wrong role/run ID,
production host, unreachable DB, sentinel of other run.
Green: explicit provisioned DB/role/sentinel exact passes (mocked).

The guard itself is imported as module; we test its validation functions
without needing real Postgres, plus one mocked successful path.
"""
import os
import unittest
from unittest.mock import patch, MagicMock

# Import guard module
from scripts.assert_disposable_database import (
    validate_run_id,
    validate_environment,
    parse_dsn,
    validate_url,
    connect_and_verify,
    RUN_ID_PATTERN,
    SENTINEL_TABLES,
)


class DisposableGuardValidationTests(unittest.TestCase):
    def setUp(self):
        # Ensure clean env for each test
        self.env_patcher = patch.dict(os.environ, {}, clear=False)
        self.env_patcher.start()
        os.environ["ENVIRONMENT"] = "test"
        os.environ["JUALIN_TEST_RUN_ID"] = "test-run-abc123XYZ-7890"

    def tearDown(self):
        self.env_patcher.stop()

    # ── ENVIRONMENT checks ──
    def test_non_test_environment_fails(self):
        os.environ["ENVIRONMENT"] = "production"
        with self.assertRaises(SystemExit) as cm:
            validate_environment()
        self.assertNotEqual(cm.exception.code, 0)

    def test_missing_environment_fails(self):
        os.environ.pop("ENVIRONMENT", None)
        with self.assertRaises(SystemExit):
            validate_environment()

    # ── RUN ID checks ──
    def test_empty_run_id_fails(self):
        with self.assertRaises(SystemExit):
            validate_run_id("")

    def test_short_run_id_fails(self):
        with self.assertRaises(SystemExit):
            validate_run_id("short")

    def test_invalid_run_id_format_fails(self):
        with self.assertRaises(SystemExit):
            validate_run_id("!!! not valid ###")

    def test_valid_run_id_passes(self):
        # Should not raise
        validate_run_id("test-run-abc123XYZ-7890")
        validate_run_id("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

    # ── DSN parsing and allowlist/blocklist ──
    def test_ambient_default_dsn_blocked(self):
        # This is the default from config.py — should be blocked
        dsn = "postgresql+asyncpg://postgres:postgres@localhost:5432/jualin_ai"
        url = parse_dsn(dsn)
        with self.assertRaises(SystemExit):
            validate_url(url, "test-run-abc123XYZ-7890")

    def test_production_host_blocked(self):
        dsn = "postgresql+asyncpg://user:pass@prod-db.example.com:5432/jualin_test_abc123"
        url = parse_dsn(dsn)
        with self.assertRaises(SystemExit):
            validate_url(url, "test-run-abc123")

    def test_rds_host_blocked(self):
        dsn = "postgresql+asyncpg://user:pass@mydb.c9akciqbd.rds.amazonaws.com:5432/jualin_test_xyz"
        url = parse_dsn(dsn)
        with self.assertRaises(SystemExit):
            validate_url(url, "test-run-abc123")

    def test_supabase_host_blocked(self):
        dsn = "postgresql+asyncpg://user:pass@db.supabase.co:5432/jualin_test_abc"
        url = parse_dsn(dsn)
        with self.assertRaises(SystemExit):
            validate_url(url, "test-run-abc123")

    def test_blocked_db_name_exact(self):
        dsn = "postgresql+asyncpg://postgres:postgres@localhost:5432/jualin_ai"
        url = parse_dsn(dsn)
        with self.assertRaises(SystemExit):
            validate_url(url, "test-run-abc123XYZ-7890")

    def test_generic_test_db_too_short_blocked(self):
        # jualin_test_ without random suffix should be blocked
        dsn = "postgresql+asyncpg://postgres:postgres@localhost:5432/jualin_test_"
        url = parse_dsn(dsn)
        with self.assertRaises(SystemExit):
            validate_url(url, "test-run-abc123XYZ-7890")

    def test_allowed_test_db_passes(self):
        dsn = "postgresql+asyncpg://postgres:postgres@localhost:5432/jualin_test_abc123XYZ-7890-456"
        url = parse_dsn(dsn)
        # Should not raise
        validate_url(url, "test-run-abc123XYZ-7890")

    def test_allowed_db_with_test_prefix(self):
        dsn = "postgresql+asyncpg://jualin_test_user:pass@localhost:5432/jualin_test_run-abc123XYZ-7890"
        url = parse_dsn(dsn)
        validate_url(url, "run-abc123XYZ-7890")

    def test_blocked_user(self):
        dsn = "postgresql+asyncpg://prod_user:pass@localhost:5432/jualin_test_abc123XYZ-7890"
        url = parse_dsn(dsn)
        with self.assertRaises(SystemExit):
            validate_url(url, "test-run-abc123XYZ-7890")

    def test_unknown_host_not_allowed(self):
        dsn = "postgresql+asyncpg://postgres:postgres@some-random-host:5432/jualin_test_abc123XYZ-7890"
        url = parse_dsn(dsn)
        with self.assertRaises(SystemExit):
            validate_url(url, "test-run-abc123XYZ-7890")

    # ── Connect and sentinel verification (mocked) ──

    @patch("scripts.assert_disposable_database.psycopg2")
    def test_connect_success_with_sentinel(self, mock_psycopg2):
        # Setup mock connection that returns expected current_database and sentinel row
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        # First call: current_database, current_user
        # Second call: sentinel lookup returns row
        # Third call: server addr/port (optional)
        mock_cur.fetchone.side_effect = [
            ("jualin_test_run-abc123", "postgres"),  # current_database, current_user
            ("run-abc123XYZ-7890",),  # sentinel row found
            ("127.0.0.1", 5432),  # server addr/port
        ]
        # fetchall for existing ids not needed in success path
        dsn = "postgresql+asyncpg://postgres:postgres@localhost:5432/jualin_test_run-abc123"
        # Should not raise
        current_db, current_user = connect_and_verify(dsn, "run-abc123XYZ-7890")
        self.assertEqual(current_db, "jualin_test_run-abc123")

    @patch("scripts.assert_disposable_database.psycopg2")
    def test_connect_fails_when_sentinel_missing(self, mock_psycopg2):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur

        # Simulate table not existing for first tables, then exists but row missing for last
        # We'll make fetchone return None for sentinel check and raise undefined_table for others?
        # Simpler: simulate all tables exist but row missing → guard should fail via SystemExit
        def execute_side_effect(query, params=None):
            # Store query for fetch behavior
            mock_cur._last_query = query

        mock_cur.execute.side_effect = execute_side_effect

        def fetchone_side_effect():
            q = getattr(mock_cur, "_last_query", "")
            if "current_database" in q:
                return ("jualin_test_run-abc123", "postgres")
            if "run_id" in q and "WHERE" in q:
                return None  # row not found -> should trigger fail inside
            if "inet_server" in q:
                return ("127.0.0.1", 5432)
            # For SELECT run_id LIMIT 5 after not found, return some other ids
            if "LIMIT 5" in q:
                return [("other-run-id",)]
            return None

        mock_cur.fetchone.side_effect = fetchone_side_effect
        mock_cur.fetchall.return_value = [("other-run-id",)]

        dsn = "postgresql+asyncpg://postgres:postgres@localhost:5432/jualin_test_run-abc123"
        with self.assertRaises(SystemExit):
            connect_and_verify(dsn, "run-abc123XYZ-7890")

    @patch("scripts.assert_disposable_database.psycopg2")
    def test_connect_fails_when_unreachable(self, mock_psycopg2):
        mock_psycopg2.connect.side_effect = Exception("connection refused")
        dsn = "postgresql+asyncpg://postgres:postgres@localhost:5432/jualin_test_run-abc123"
        with self.assertRaises(SystemExit):
            connect_and_verify(dsn, "run-abc123XYZ-7890")

    @patch("scripts.assert_disposable_database.psycopg2")
    def test_connect_fails_when_db_mismatch(self, mock_psycopg2):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_psycopg2.connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = ("other_db", "postgres")
        dsn = "postgresql+asyncpg://postgres:postgres@localhost:5432/jualin_test_run-abc123"
        with self.assertRaises(SystemExit):
            connect_and_verify(dsn, "run-abc123XYZ-7890")

    def test_production_identifiers_in_dsn_blocked(self):
        dsn = "postgresql+asyncpg://user:pass@db.neon.tech:5432/jualin_test_abc"
        url = parse_dsn(dsn)
        with self.assertRaises(SystemExit):
            validate_url(url, "test-run-abc123XYZ-7890")


class GuardScriptIntegrationTests(unittest.TestCase):
    """Ensure script does not create schema itself."""

    def test_script_does_not_create_tables(self):
        # Import source and check it does not contain CREATE TABLE or INSERT for sentinel
        import pathlib
        p = pathlib.Path("scripts/assert_disposable_database.py")
        if not p.exists():
            p = pathlib.Path(__file__).parent.parent / "scripts" / "assert_disposable_database.py"
        content = p.read_text(encoding="utf-8")
        # Guard must not CREATE TABLE or INSERT sentinel
        self.assertNotIn("CREATE TABLE", content)
        # It should only SELECT from sentinel, not INSERT
        # Allow SELECT ... FROM sentinel, but not INSERT INTO sentinel
        self.assertNotIn("INSERT INTO", content.upper() if "sentinel" in content.lower() else content)


if __name__ == "__main__":
    unittest.main()
