"""Fail-closed authority check for P0.0a disposable PostgreSQL execution.

The guard is intentionally read-only. Provisioning and teardown live in a
separate runner so this module can never make an ambient database look safe.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import sys
import uuid
from typing import NoReturn

import psycopg2
from sqlalchemy.engine.url import URL, make_url


ALLOWED_DRIVERS = frozenset(
    {"postgresql", "postgresql+asyncpg", "postgresql+psycopg2"}
)
LOOPBACK_CLIENT_HOSTS = frozenset({"127.0.0.1", "::1"})
SAFE_SERVER_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
        "fc00::/7",
    )
)
KNOWN_DEPLOYMENT_IDENTIFIERS = (
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
)
CONTAINER_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def fail(message: str, code: int = 2) -> NoReturn:
    print(f"[GUARD FAIL] {message}", file=sys.stderr)
    raise SystemExit(code)


def _run_uuid(run_id: str) -> uuid.UUID:
    if not run_id:
        fail("JUALIN_TEST_RUN_ID is required")
    try:
        parsed = uuid.UUID(run_id)
    except (AttributeError, TypeError, ValueError):
        fail("JUALIN_TEST_RUN_ID must be a canonical UUIDv4")
    if parsed.version != 4 or str(parsed) != run_id:
        fail("JUALIN_TEST_RUN_ID must be a canonical lowercase UUIDv4")
    return parsed


def validate_run_id(run_id: str) -> None:
    _run_uuid(run_id)


def database_name_for_run(run_id: str) -> str:
    return f"jualin_test_{_run_uuid(run_id).hex}"


def role_name_for_run(run_id: str) -> str:
    return f"jualin_test_role_{_run_uuid(run_id).hex}"


def validate_environment() -> None:
    environment = os.getenv("ENVIRONMENT", "")
    if environment != "test":
        fail(f"ENVIRONMENT must be exactly 'test', got {environment!r}")


def parse_dsn(dsn: str) -> URL:
    if not dsn:
        fail("DATABASE_URL is required")
    try:
        return make_url(dsn)
    except Exception:
        # SQLAlchemy parse errors may echo userinfo; never forward them to logs.
        fail("DATABASE_URL is not a valid SQLAlchemy URL")


def validate_url(url: URL, run_id: str) -> None:
    run_uuid = _run_uuid(run_id)
    expected_database = f"jualin_test_{run_uuid.hex}"
    expected_role = f"jualin_test_role_{run_uuid.hex}"
    expected_container = f"jualin-test-db-{run_uuid.hex}"

    if url.drivername not in ALLOWED_DRIVERS:
        fail("DATABASE_URL must use an approved PostgreSQL driver")

    host = (url.host or "").lower()
    if any(identifier in host for identifier in KNOWN_DEPLOYMENT_IDENTIFIERS):
        fail("DATABASE_URL host contains a known deployment identifier")
    if host not in LOOPBACK_CLIENT_HOSTS and host != expected_container:
        fail("DATABASE_URL host is not the exact disposable endpoint")

    try:
        port = url.port
    except ValueError:
        fail("DATABASE_URL port is invalid")
    if port is None or not 1 <= port <= 65535:
        fail("DATABASE_URL must include an explicit valid port")

    if url.database != expected_database:
        fail("DATABASE_URL database is not bound to JUALIN_TEST_RUN_ID")
    if url.username != expected_role:
        fail("DATABASE_URL role is not bound to JUALIN_TEST_RUN_ID")

    password = url.password or ""
    if len(password) < 24:
        fail("DATABASE_URL requires a random test-only credential of at least 24 characters")

    if url.query:
        fail("DATABASE_URL contains an SSL target or connection override")

    sanitized = url.render_as_string(hide_password=True).lower()
    if any(
        identifier in sanitized
        for identifier in KNOWN_DEPLOYMENT_IDENTIFIERS
        if identifier not in {"prod", "production"}
    ):
        fail("DATABASE_URL contains a known deployment identifier")

    print(
        "[GUARD] URL authority OK: "
        f"host={host} port={port} db={url.database} role={url.username}"
    )


def _server_endpoint_is_disposable(
    address: object, port: object, expected_address: str
) -> bool:
    if address is None or port != 5432:
        return False
    try:
        parsed = ipaddress.ip_address(str(address))
        expected = ipaddress.ip_address(expected_address)
    except ValueError:
        return False
    return parsed == expected and any(parsed in network for network in SAFE_SERVER_NETWORKS)


def _resource_authority_from_environment() -> tuple[str, str]:
    container_id = os.getenv("JUALIN_TEST_CONTAINER_ID", "")
    server_address = os.getenv("JUALIN_TEST_SERVER_ADDRESS", "")
    if CONTAINER_ID_PATTERN.fullmatch(container_id) is None:
        fail("JUALIN_TEST_CONTAINER_ID must be the exact 64-character container ID")
    try:
        parsed_address = ipaddress.ip_address(server_address)
    except ValueError:
        fail("JUALIN_TEST_SERVER_ADDRESS must be an exact IP address")
    if not any(parsed_address in network for network in SAFE_SERVER_NETWORKS):
        fail("JUALIN_TEST_SERVER_ADDRESS is not an approved local container address")
    return container_id, str(parsed_address)


def connect_and_verify(dsn: str, run_id: str) -> tuple[str, str]:
    """Connect read-only and prove runtime identity, scope, and sentinel."""

    url = parse_dsn(dsn)
    validate_url(url, run_id)
    expected_database = database_name_for_run(run_id)
    expected_role = role_name_for_run(run_id)
    expected_container_id, expected_server_address = (
        _resource_authority_from_environment()
    )

    host = url.host
    database = url.database
    role = url.username
    password = url.password
    port = url.port
    if (
        host is None
        or database is None
        or role is None
        or password is None
        or port is None
    ):
        fail("DATABASE_URL authority became incomplete after validation")

    connection = None
    cursor = None
    try:
        try:
            connection = psycopg2.connect(
                host=host,
                dbname=database,
                user=role,
                password=password,
                port=port,
                connect_timeout=5,
                sslmode="disable",
                application_name="jualin-disposable-db-guard",
            )
            connection.set_session(readonly=True, autocommit=True)
        except Exception:
            fail("Unable to establish a read-only disposable database session")

        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT current_database(),
                   current_user,
                   session_user,
                   host(inet_server_addr()),
                   inet_server_port()
            """
        )
        identity = cursor.fetchone()
        if not identity or len(identity) != 5:
            fail("PostgreSQL did not return complete runtime identity")
        current_database, current_user, session_user, server_address, server_port = (
            identity
        )
        if current_database != expected_database:
            fail("Actual PostgreSQL database does not match the disposable authority")
        if current_user != expected_role or session_user != expected_role:
            fail("Actual PostgreSQL role does not match the disposable authority")
        if not _server_endpoint_is_disposable(
            server_address, server_port, expected_server_address
        ):
            fail("Actual PostgreSQL server endpoint does not match provisioned authority")

        cursor.execute(
            """
            SELECT rolcanlogin,
                   rolsuper,
                   rolcreatedb,
                   rolcreaterole,
                   rolreplication,
                   rolbypassrls,
                   rolinherit
            FROM pg_catalog.pg_roles
            WHERE rolname = current_user
            """
        )
        capabilities = cursor.fetchone()
        if capabilities != (True, False, False, False, False, False, False):
            fail("Disposable PostgreSQL role has unsafe capabilities")

        cursor.execute(
            """
            SELECT pg_get_userbyid(datdba)
            FROM pg_catalog.pg_database
            WHERE datname = current_database()
            """
        )
        owner = cursor.fetchone()
        if owner != (expected_role,):
            fail("Disposable PostgreSQL role does not own the exact test database")

        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_catalog.pg_auth_members
                WHERE roleid = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = current_user)
                   OR member = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = current_user)
            )
            """
        )
        membership = cursor.fetchone()
        if membership != (False,):
            fail("Disposable PostgreSQL role must not inherit or grant role membership")

        cursor.execute(
            """
            SELECT pg_get_userbyid(c.relowner), c.relkind
            FROM pg_catalog.pg_class AS c
            JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = 'disposable_db_sentinel'
              AND c.relkind = 'r'
            """
        )
        sentinel_owner = cursor.fetchone()
        if sentinel_owner != (expected_role, "r"):
            fail("Provisioning sentinel is missing or has the wrong owner")

        cursor.execute(
            """
            SELECT run_id::text,
                   database_name,
                   role_name,
                   container_id,
                   count(*) OVER ()
            FROM public.disposable_db_sentinel
            WHERE sentinel_key IS TRUE
            """
        )
        sentinel = cursor.fetchone()
        if not sentinel or len(sentinel) != 5:
            fail("Provisioning sentinel row is missing")
        (
            sentinel_run_id,
            sentinel_database,
            sentinel_role,
            container_id,
            sentinel_count,
        ) = sentinel
        if (
            sentinel_run_id != run_id
            or sentinel_database != expected_database
            or sentinel_role != expected_role
            or container_id != expected_container_id
            or sentinel_count != 1
        ):
            fail("Provisioning sentinel does not match the disposable authority")

        print(
            "[GUARD PASS] read-only authority verified: "
            f"run_id={run_id} db={current_database} role={current_user} "
            f"server={server_address}:{server_port}"
        )
        return str(current_database), str(current_user)
    except SystemExit:
        raise
    except Exception:
        # Query/permission errors can include SQL or connection fields; keep output redacted.
        fail("Disposable database authority verification query failed")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Assert disposable PostgreSQL authority")
    parser.add_argument(
        "--run-id",
        default="",
        help="canonical UUIDv4; defaults to JUALIN_TEST_RUN_ID",
    )
    parser.add_argument(
        "--dsn",
        default="",
        help="explicit disposable DSN; defaults to DATABASE_URL",
    )
    args = parser.parse_args()

    validate_environment()
    run_id = os.getenv("JUALIN_TEST_RUN_ID", "")
    dsn = os.getenv("DATABASE_URL", "")
    if args.run_id and args.run_id != run_id:
        fail("--run-id must exactly match JUALIN_TEST_RUN_ID")
    if args.dsn and args.dsn != dsn:
        fail("--dsn must exactly match DATABASE_URL")
    validate_run_id(run_id)
    connect_and_verify(dsn, run_id)


if __name__ == "__main__":
    main()
