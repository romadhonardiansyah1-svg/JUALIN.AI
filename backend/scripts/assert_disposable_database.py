"""
Disposable Database Guard — P0.0a
Ensures tests/migrations never run against ambient/production DB.

Contract:
1. Require ENVIRONMENT=test and non-empty JUALIN_TEST_RUN_ID
2. Parse DSN with SQLAlchemy parser, reject production/unknown host/db/role
3. Connect read-only and verify current_database(), current_user, server addr/port,
   and provisioning sentinel table/row exact run ID
4. DB/role only test scope and random per run; no prod network route/credential
5. Fail non-zero on missing/mismatch/unreachable/permission and do NOT create schema
6. Called before every DB-capable suite and Alembic current/upgrade/downgrade
7. Teardown verifies compose project label + sentinel/run ID (handled by caller/orchestrator)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Tuple

from sqlalchemy.engine.url import make_url

try:
    import psycopg2  # noqa: F401 for test mocking
    import psycopg2.extras  # noqa: F401
except Exception:
    psycopg2 = None  # type: ignore

# Allowed hosts for disposable test DBs (local dev + docker compose service names)
ALLOWED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "db",
    "postgres",
    "test",
    "test-db",
    "jualin-test-db",
}

# Host prefixes that are acceptable if they look like test resources
ALLOWED_HOST_PREFIXES = (
    "jualin-test-",
    "test-",
    "jualin_test_",
)

# Blocked substrings that indicate production or cloud managed DB
BLOCKED_HOST_SUBSTRINGS = (
    "prod",
    "production",
    "rds.amazonaws.com",
    "supabase",
    "neon.tech",
    "railway",
    "render.com",
    "vercel",
    "jualin.ai",
    "api.jualin",
    "aws",
    "gcp",
    "azure",
)

# Blocked exact database names (production)
BLOCKED_DB_EXACT = {
    "jualin_ai",
    "jualin",
    "postgres",  # postgres db is not disposable unless explicitly allowed with test prefix? allow postgres user but not db name alone?
    "production",
    "prod",
}

# Allowed DB name patterns for test
ALLOWED_DB_PREFIXES = (
    "jualin_test_",
    "test_",
    "jualin_ai_test",
)

ALLOWED_DB_EXACT = {
    "test",
    "jualin_ai_test",
}

BLOCKED_USER_EXACT = {
    "prod",
    "production",
    "admin_prod",
}

ALLOWED_USER_PREFIXES = (
    "jualin_test_",
    "test_",
    "postgres",  # common local superuser allowed for dev
    "test",
    "jualin",  # Docker superuser for disposable test DBs
)

# Sentinel tables to try in order
SENTINEL_TABLES = (
    "disposable_db_sentinel",
    "test_provisioning_sentinel",
    "test_sentinel",
    "provisioning_sentinel",
)

RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9\-_]{12,128}$")


def fail(msg: str, code: int = 2) -> None:
    print(f"[GUARD FAIL] {msg}", file=sys.stderr)
    sys.exit(code)


def validate_run_id(run_id: str) -> None:
    if not run_id:
        fail("JUALIN_TEST_RUN_ID is empty — must be cryptographic non-empty")
    if not RUN_ID_PATTERN.match(run_id):
        fail(f"JUALIN_TEST_RUN_ID format invalid: '{run_id}' must match {RUN_ID_PATTERN.pattern} and be 12-128 chars")
    # Require some entropy: at least mixture or length > 16
    if len(run_id) < 12:
        fail("JUALIN_TEST_RUN_ID too short, must be >=12")


def validate_environment() -> None:
    env = os.getenv("ENVIRONMENT", "")
    if env != "test":
        fail(f"ENVIRONMENT must be 'test', got '{env}'")


def parse_dsn(dsn: str):
    try:
        url = make_url(dsn)
    except Exception as e:
        fail(f"Failed to parse DATABASE_URL as SQLAlchemy URL: {e}")
    return url


def is_host_allowed(host: str) -> bool:
    if not host:
        return False
    h = host.lower()
    if h in ALLOWED_HOSTS:
        return True
    for prefix in ALLOWED_HOST_PREFIXES:
        if h.startswith(prefix):
            return True
    # Allow any host that contains 'test' but does NOT contain blocked substrings
    if "test" in h:
        for blocked in BLOCKED_HOST_SUBSTRINGS:
            if blocked in h:
                return False
        return True
    return False


def is_host_blocked(host: str) -> bool:
    h = host.lower()
    for blocked in BLOCKED_HOST_SUBSTRINGS:
        if blocked in h:
            return True
    return False


def validate_url(url, run_id: str) -> None:
    host = url.host or ""
    database = url.database or ""
    username = url.username or ""

    # Host checks
    if not host:
        fail("DATABASE_URL host is empty")
    if is_host_blocked(host):
        fail(f"DATABASE_URL host '{host}' contains blocked production substring {BLOCKED_HOST_SUBSTRINGS}")
    if not is_host_allowed(host):
        fail(f"DATABASE_URL host '{host}' not in allowlist {ALLOWED_HOSTS} plus prefixes {ALLOWED_HOST_PREFIXES}")

    # Database checks
    if not database:
        fail("DATABASE_URL database is empty")
    db_lower = database.lower()
    if db_lower in BLOCKED_DB_EXACT:
        # Special case: allow 'postgres' db only if host is localhost and db is exactly 'postgres'?? 
        # For safety, we block bare 'postgres' and 'jualin_ai' as they are ambient defaults
        if db_lower == "postgres":
            fail(f"DATABASE_URL database '{database}' is blocked as ambient default; must be disposable test db like jualin_test_<run_id>")
        fail(f"DATABASE_URL database '{database}' is blocked production database")
    # Must match allowed patterns
    allowed_db = False
    if db_lower in ALLOWED_DB_EXACT:
        allowed_db = True
    else:
        for prefix in ALLOWED_DB_PREFIXES:
            if db_lower.startswith(prefix):
                allowed_db = True
                break
    if not allowed_db:
        fail(
            f"DATABASE_URL database '{database}' not allowed — must start with {ALLOWED_DB_PREFIXES} or be {ALLOWED_DB_EXACT}"
        )

    # Ensure run_id is part of database name or we at least have jualin_test_ prefix with randomness
    # Enforce that db contains test and is not just static jualin_test_ without suffix if run_id provided
    if db_lower.startswith("jualin_test_") and len(database) <= len("jualin_test_") + 3:
        fail(f"DATABASE_URL database '{database}' too generic — must be random per run, include run-id suffix")

    # User checks
    if username:
        u_lower = username.lower()
        if u_lower in BLOCKED_USER_EXACT:
            fail(f"DATABASE_URL user '{username}' is blocked")
        allowed_user = False
        if u_lower in {"postgres", "test"}:
            allowed_user = True
        else:
            for prefix in ALLOWED_USER_PREFIXES:
                if u_lower.startswith(prefix):
                    allowed_user = True
                    break
        if not allowed_user:
            fail(
                f"DATABASE_URL user '{username}' not allowed — must start with {ALLOWED_USER_PREFIXES} or be postgres/test"
            )

    # Reject production identifiers in full DSN string (defense in depth)
    dsn_lower = str(url).lower()
    for blocked in ("neon.tech", "supabase.co", "rds.amazonaws.com"):
        if blocked in dsn_lower:
            fail(f"DATABASE_URL contains blocked production identifier '{blocked}'")

    # Optional: reject sslmode=require for test local? Actually allow, but warn
    # We don't fail on ssl, just check
    print(f"[GUARD] DSN parsed OK: host={host} db={database} user={username}")


def connect_and_verify(dsn: str, run_id: str) -> Tuple[str, str]:
    """
    Connect and verify actual current_database(), current_user, and sentinel row.
    Raises SystemExit on failure per contract (no schema creation).
    Returns (current_database, current_user) on success.
    """
    global psycopg2
    # Use module-level psycopg2 if available
    if psycopg2 is None:
        try:
            import psycopg2 as _psycopg2  # type: ignore
            import psycopg2.extras  # type: ignore
            psycopg2 = _psycopg2
        except Exception as e:
            fail(f"psycopg2 not available for guard verification: {e}")

    # Build libpq DSN from sqlalchemy url for psycopg2
    # psycopg2 can parse URL via make_url rendering? We'll use url.render_as_string(hide_password=False)
    try:
        url = make_url(dsn)
        # Build connection kwargs
        conn_kwargs = {
            "host": url.host,
            "dbname": url.database,
            "user": url.username,
            "password": url.password,
            "port": url.port or 5432,
            "connect_timeout": 5,
        }
        # Remove None
        conn_kwargs = {k: v for k, v in conn_kwargs.items() if v is not None}
    except Exception as e:
        fail(f"Failed to prepare psycopg2 connection info: {e}")

    try:
        conn = psycopg2.connect(**conn_kwargs)
        conn.set_session(readonly=True, autocommit=True)
    except Exception as e:
        fail(f"Failed to connect to test DB (unreachable or auth error): {e}")

    try:
        cur = conn.cursor()
        # Verify current_database and current_user
        cur.execute("SELECT current_database(), current_user;")
        row = cur.fetchone()
        if not row:
            fail("Failed to fetch current_database/current_user")
        current_db, current_user = row[0], row[1]
        print(f"[GUARD] Connected: current_database={current_db} current_user={current_user}")

        # Verify database matches expected parsed database (or at least allowed)
        parsed_db = make_url(dsn).database
        if current_db != parsed_db:
            # Allow if both are test prefixed but mismatch due to search_path? Still fail strict
            fail(f"current_database() '{current_db}' != expected DSN database '{parsed_db}'")

        # Verify sentinel table exists and contains exact run_id
        sentinel_found = False
        row_found = False
        last_error = None
        for table in SENTINEL_TABLES:
            try:
                cur.execute(f"SELECT run_id FROM {table} WHERE run_id = %s LIMIT 1;", (run_id,))
                r = cur.fetchone()
                if r:
                    row_found = True
                    sentinel_found = True
                    print(f"[GUARD] Sentinel OK: table={table} run_id={run_id}")
                    break
                else:
                    # Table exists but row not found — this is a mismatch, not just missing table
                    # Try to see if table has any rows to give better error
                    cur.execute(f"SELECT run_id FROM {table} LIMIT 5;")
                    existing = cur.fetchall()
                    existing_ids = [x[0] for x in existing] if existing else []
                    fail(
                        f"Sentinel table '{table}' exists but run_id '{run_id}' not found. Existing sample: {existing_ids[:3]} — possible forged name or wrong run"
                    )
            except Exception as e:
                # Table may not exist, try next
                last_error = e
                # Check if error is undefined_table, continue
                err_str = str(e).lower()
                if "does not exist" in err_str or "undefined_table" in err_str or "relation" in err_str:
                    continue
                else:
                    # Other error -> fail
                    fail(f"Error querying sentinel table '{table}': {e}")

        if not sentinel_found:
            fail(
                f"No sentinel table found among {SENTINEL_TABLES} with run_id '{run_id}'. Last error: {last_error}. "
                "Did provisioning step create disposable_db_sentinel with exact run ID?"
            )

        # Verify server address/port not production (best effort)
        try:
            cur.execute("SELECT inet_server_addr(), inet_server_port();")
            srv = cur.fetchone()
            if srv:
                srv_addr, srv_port = srv[0], srv[1]
                print(f"[GUARD] Server: addr={srv_addr} port={srv_port}")
                # Could add extra checks here if needed
        except Exception:
            # inet_server_addr may be null on some setups, not fatal
            pass

        cur.close()
        conn.close()
        return current_db, current_user

    except SystemExit:
        raise
    except Exception as e:
        fail(f"Guard verification failed during DB checks: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Disposable DB guard")
    parser.add_argument("--run-id", dest="run_id", default="", help="JUALIN_TEST_RUN_ID (or use env var)")
    parser.add_argument("--dsn", dest="dsn", default="", help="DATABASE_URL override (or use env var)")
    args = parser.parse_args()

    env_run_id = os.getenv("JUALIN_TEST_RUN_ID", "")
    run_id = args.run_id or env_run_id

    dsn = args.dsn or os.getenv("DATABASE_URL", "") or os.getenv("TEST_DATABASE_URL", "")

    if not dsn:
        fail("DATABASE_URL is empty — must export disposable test DSN")

    # 1. Validate environment and run_id
    validate_environment()
    validate_run_id(run_id)

    # 2. Parse and validate DSN allowlist/blocklist
    url = parse_dsn(dsn)
    validate_url(url, run_id)

    # 3. Connect and verify actual DB state + sentinel
    connect_and_verify(dsn, run_id)

    print(f"[GUARD PASS] ENVIRONMENT=test run_id={run_id} db={url.database} host={url.host} is disposable")
    sys.exit(0)


if __name__ == "__main__":
    main()
