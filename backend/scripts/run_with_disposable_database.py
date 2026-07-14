"""Provision, guard, run, and safely remove an isolated PostgreSQL instance."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import secrets
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Iterator, Sequence
from urllib.parse import urlsplit

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import URL

from scripts.assert_disposable_database import (
    CONTAINER_ID_PATTERN,
    connect_and_verify,
    database_name_for_run,
    role_name_for_run,
    validate_run_id,
)


COMPOSE_FILE = pathlib.Path(__file__).with_name("docker-compose.disposable.yml")
SERVICE_NAME = "postgres"
POSTGRES_DATA_DIRECTORY = "/var/lib/postgresql/data"
PROJECT_PATTERN = re.compile(r"^jualin-test-[0-9a-f]{32}$")
TARGET_AUTHORITY_ENVIRONMENT = (
    "ENVIRONMENT",
    "JUALIN_TEST_RUN_ID",
    "JUALIN_TEST_CONTAINER_ID",
    "JUALIN_TEST_SERVER_ADDRESS",
    "DATABASE_URL",
    "TEST_DATABASE_URL",
)
DOCKER_OVERRIDE_ENVIRONMENT = frozenset(
    {
        "DOCKER_CERT_PATH",
        "DOCKER_CONTEXT",
        "DOCKER_HOST",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
    }
)


class SafetyError(RuntimeError):
    """Raised when isolated-resource authority cannot be proven."""


@dataclass(frozen=True)
class DisposableAuthority:
    run_id: str
    bootstrap_password: str = field(repr=False)
    role_password: str = field(repr=False)
    container_id: str = ""
    server_address: str = ""
    host_port: int = 0
    network_id: str = ""

    @property
    def token(self) -> str:
        return uuid.UUID(self.run_id).hex

    @property
    def project_name(self) -> str:
        return f"jualin-test-{self.token}"

    @property
    def bootstrap_role(self) -> str:
        return f"jualin_bootstrap_role_{self.token}"

    @property
    def bootstrap_database(self) -> str:
        return f"jualin_bootstrap_{self.token}"

    @property
    def database_name(self) -> str:
        return database_name_for_run(self.run_id)

    @property
    def role_name(self) -> str:
        return role_name_for_run(self.run_id)

    @property
    def dsn(self) -> str:
        if not self.container_id or not self.host_port:
            raise SafetyError("Disposable PostgreSQL runtime is not fully identified")
        return URL.create(
            "postgresql+asyncpg",
            username=self.role_name,
            password=self.role_password,
            host="127.0.0.1",
            port=self.host_port,
            database=self.database_name,
        ).render_as_string(hide_password=False)

    def with_runtime(
        self,
        *,
        container_id: str,
        server_address: str,
        host_port: int,
        network_id: str,
    ) -> "DisposableAuthority":
        return replace(
            self,
            container_id=container_id,
            server_address=server_address,
            host_port=host_port,
            network_id=network_id,
        )


def new_authority(run_id: str | None = None) -> DisposableAuthority:
    actual_run_id = run_id or str(uuid.uuid4())
    validate_run_id(actual_run_id)
    return DisposableAuthority(
        run_id=actual_run_id,
        bootstrap_password=secrets.token_urlsafe(32),
        role_password=secrets.token_urlsafe(32),
    )


def _compose_environment(authority: DisposableAuthority) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "JUALIN_TEST_RUN_ID": authority.run_id,
            "JUALIN_TEST_BOOTSTRAP_ROLE": authority.bootstrap_role,
            "JUALIN_TEST_BOOTSTRAP_PASSWORD": authority.bootstrap_password,
            "JUALIN_TEST_BOOTSTRAP_DATABASE": authority.bootstrap_database,
        }
    )
    return environment


def _is_local_docker_endpoint(endpoint: str) -> bool:
    parsed = urlsplit(endpoint)
    if parsed.netloc or parsed.query or parsed.fragment:
        return False
    if parsed.scheme == "unix":
        return parsed.path.startswith("/") and parsed.path != "/"
    if parsed.scheme == "npipe":
        return re.fullmatch(r"//\./pipe/[A-Za-z0-9_.-]+", parsed.path) is not None
    return False


def _local_docker_environment() -> dict[str, str]:
    if any(key in os.environ for key in DOCKER_OVERRIDE_ENVIRONMENT):
        raise SafetyError("Ambient Docker endpoint or TLS overrides are not allowed")

    environment = os.environ.copy()
    for key in DOCKER_OVERRIDE_ENVIRONMENT:
        environment.pop(key, None)
    try:
        result = subprocess.run(
            [
                "docker",
                "context",
                "inspect",
                "--format",
                "{{json .Endpoints.docker.Host}}",
            ],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            env=environment,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SafetyError("Docker context could not be inspected safely") from exc
    if result.returncode != 0:
        raise SafetyError("Docker context inspection failed; output withheld")
    try:
        endpoint = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise SafetyError("Docker context returned an invalid endpoint") from exc
    if not isinstance(endpoint, str) or not _is_local_docker_endpoint(endpoint):
        raise SafetyError("Docker context does not use an approved local endpoint")
    environment["DOCKER_HOST"] = endpoint
    return environment


def _docker(
    arguments: Sequence[str],
    *,
    environment: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    docker_environment = _local_docker_environment()
    endpoint = docker_environment["DOCKER_HOST"]
    if environment is not None:
        docker_environment.update(
            (key, value)
            for key, value in environment.items()
            if key not in DOCKER_OVERRIDE_ENVIRONMENT
        )
    docker_environment["DOCKER_HOST"] = endpoint
    try:
        result = subprocess.run(
            ["docker", *arguments],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            env=docker_environment,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SafetyError("Docker command could not be executed safely") from exc
    if result.returncode != 0:
        raise SafetyError("Docker command failed; output withheld to protect credentials")
    return result


def _compose(
    authority: DisposableAuthority, arguments: Sequence[str], *, timeout: int = 120
) -> subprocess.CompletedProcess[str]:
    return _docker(
        [
            "compose",
            "--project-name",
            authority.project_name,
            "--file",
            str(COMPOSE_FILE),
            *arguments,
        ],
        environment=_compose_environment(authority),
        timeout=timeout,
    )


def _json_object(result: subprocess.CompletedProcess[str]) -> dict:
    try:
        parsed = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise SafetyError("Docker returned invalid inspection data") from exc
    if not isinstance(parsed, list) or len(parsed) != 1 or not isinstance(parsed[0], dict):
        raise SafetyError("Docker inspection did not identify exactly one resource")
    return parsed[0]


def _inspect_container(container_id: str) -> dict:
    if CONTAINER_ID_PATTERN.fullmatch(container_id) is None:
        raise SafetyError("Container ID is not an exact full Docker identifier")
    return _json_object(_docker(["inspect", container_id]))


def _assert_ephemeral_storage(container: dict) -> None:
    tmpfs = container.get("HostConfig", {}).get("Tmpfs") or {}
    if set(tmpfs) != {POSTGRES_DATA_DIRECTORY}:
        raise SafetyError("PostgreSQL data directory is not the exact disposable tmpfs")
    options = set(str(tmpfs[POSTGRES_DATA_DIRECTORY]).split(","))
    if not {"rw", "nosuid", "noexec"}.issubset(options):
        raise SafetyError("PostgreSQL tmpfs is missing required safety options")

    mounts = container.get("Mounts") or []
    for mount in mounts:
        if (
            mount.get("Type") != "tmpfs"
            or mount.get("Destination") != POSTGRES_DATA_DIRECTORY
        ):
            raise SafetyError("Disposable PostgreSQL must not use bind or named mounts")


def _container_network_identity(
    authority: DisposableAuthority, container: dict
) -> tuple[str, str, str]:
    container_id = container.get("Id", "")
    if CONTAINER_ID_PATTERN.fullmatch(container_id) is None:
        raise SafetyError("Compose did not return a full container ID")
    if authority.container_id and container_id != authority.container_id:
        raise SafetyError("Container ID does not match disposable authority")

    config = container.get("Config", {})
    labels = config.get("Labels") or {}
    expected_labels = {
        "com.docker.compose.project": authority.project_name,
        "com.docker.compose.service": SERVICE_NAME,
        "com.jualin.disposable": "true",
        "com.jualin.test-run-id": authority.run_id,
    }
    if (
        config.get("Image") != "pgvector/pgvector:pg16"
        or any(labels.get(key) != value for key, value in expected_labels.items())
    ):
        raise SafetyError("Container labels do not match disposable authority")
    _assert_ephemeral_storage(container)

    expected_network_name = f"{authority.project_name}_default"
    networks = container.get("NetworkSettings", {}).get("Networks") or {}
    if set(networks) != {expected_network_name}:
        raise SafetyError("Container is attached to an unexpected network")
    network = networks[expected_network_name]
    server_address = network.get("IPAddress", "")
    network_id = network.get("NetworkID", "")
    if CONTAINER_ID_PATTERN.fullmatch(network_id) is None:
        raise SafetyError("Container network authority is incomplete")
    if authority.network_id and network_id != authority.network_id:
        raise SafetyError("Container network ID does not match disposable authority")
    if authority.server_address and server_address != authority.server_address:
        raise SafetyError("Container server address does not match disposable authority")
    return container_id, server_address, network_id


def _runtime_from_inspect(
    authority: DisposableAuthority, container: dict
) -> DisposableAuthority:
    container_id, server_address, network_id = _container_network_identity(
        authority, container
    )

    ports = container.get("NetworkSettings", {}).get("Ports", {}).get("5432/tcp")
    if not isinstance(ports, list) or len(ports) != 1:
        raise SafetyError("PostgreSQL must expose exactly one loopback port")
    binding = ports[0]
    if binding.get("HostIp") != "127.0.0.1":
        raise SafetyError("PostgreSQL port is not bound exclusively to loopback")
    try:
        host_port = int(binding.get("HostPort", ""))
    except (TypeError, ValueError) as exc:
        raise SafetyError("PostgreSQL host port is invalid") from exc
    if not 1 <= host_port <= 65535:
        raise SafetyError("PostgreSQL host port is invalid")

    if not server_address:
        raise SafetyError("Container network authority is incomplete")

    return authority.with_runtime(
        container_id=container_id,
        server_address=server_address,
        host_port=host_port,
        network_id=network_id,
    )


def assert_container_authority(
    authority: DisposableAuthority, container: dict
) -> None:
    identified = _runtime_from_inspect(authority, container)
    if identified != authority:
        raise SafetyError("Container runtime does not match captured disposable authority")
    state = container.get("State", {})
    if state.get("Status") != "running" or state.get("Health", {}).get("Status") != "healthy":
        raise SafetyError("Disposable PostgreSQL container is not running and healthy")


def _start_container(authority: DisposableAuthority) -> DisposableAuthority:
    if not COMPOSE_FILE.is_file() or PROJECT_PATTERN.fullmatch(authority.project_name) is None:
        raise SafetyError("Disposable compose authority is invalid")
    _compose(authority, ["config", "--quiet"])
    try:
        _compose(authority, ["up", "--detach"])

        deadline = time.monotonic() + 90
        container_id = ""
        while time.monotonic() < deadline:
            result = _compose(authority, ["ps", "--quiet", SERVICE_NAME])
            candidate = result.stdout.strip()
            if CONTAINER_ID_PATTERN.fullmatch(candidate):
                container_id = candidate
                container = _inspect_container(container_id)
                if container.get("State", {}).get("Health", {}).get("Status") == "healthy":
                    runtime = _runtime_from_inspect(authority, container)
                    assert_container_authority(runtime, container)
                    _assert_network_authority(runtime)
                    print(
                        "[DISPOSABLE DB] loopback-only PostgreSQL healthy: "
                        f"run_id={runtime.run_id} container={runtime.container_id[:12]}"
                    )
                    return runtime
            time.sleep(1)
        raise SafetyError("Disposable PostgreSQL did not become healthy within 90 seconds")
    except BaseException:
        _remove_preprovisioned_project(authority)
        raise


def _close_quietly(resource: object | None) -> None:
    if resource is not None:
        try:
            resource.close()  # type: ignore[attr-defined]
        except Exception:
            pass


def _provision_database(authority: DisposableAuthority) -> None:
    if not authority.container_id:
        raise SafetyError("Container authority is required before provisioning")

    admin_connection = None
    admin_cursor = None
    extension_connection = None
    extension_cursor = None
    role_connection = None
    role_cursor = None
    try:
        admin_connection = psycopg2.connect(
            host="127.0.0.1",
            port=authority.host_port,
            dbname=authority.bootstrap_database,
            user=authority.bootstrap_role,
            password=authority.bootstrap_password,
            connect_timeout=5,
            sslmode="disable",
            application_name="jualin-disposable-db-provisioner",
        )
        admin_connection.autocommit = True
        admin_cursor = admin_connection.cursor()
        admin_cursor.execute(
            sql.SQL(
                "CREATE ROLE {} WITH LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 20"
            ).format(sql.Identifier(authority.role_name), sql.Literal(authority.role_password))
        )
        admin_cursor.execute(
            sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8'").format(
                sql.Identifier(authority.database_name),
                sql.Identifier(authority.role_name),
            )
        )
        admin_cursor.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(
                sql.Identifier(authority.database_name)
            )
        )

        extension_connection = psycopg2.connect(
            host="127.0.0.1",
            port=authority.host_port,
            dbname=authority.database_name,
            user=authority.bootstrap_role,
            password=authority.bootstrap_password,
            connect_timeout=5,
            sslmode="disable",
            application_name="jualin-disposable-db-provisioner",
        )
        extension_connection.autocommit = True
        extension_cursor = extension_connection.cursor()
        extension_cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")

        role_connection = psycopg2.connect(
            host="127.0.0.1",
            port=authority.host_port,
            dbname=authority.database_name,
            user=authority.role_name,
            password=authority.role_password,
            connect_timeout=5,
            sslmode="disable",
            application_name="jualin-disposable-db-provisioner",
        )
        role_connection.autocommit = False
        role_cursor = role_connection.cursor()
        role_cursor.execute(
            """
            CREATE TABLE public.disposable_db_sentinel (
                sentinel_key boolean PRIMARY KEY DEFAULT TRUE CHECK (sentinel_key IS TRUE),
                run_id uuid NOT NULL UNIQUE,
                database_name text NOT NULL,
                role_name text NOT NULL,
                container_id char(64) NOT NULL,
                provisioned_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        role_cursor.execute(
            "REVOKE ALL ON public.disposable_db_sentinel FROM PUBLIC"
        )
        role_cursor.execute(
            """
            INSERT INTO public.disposable_db_sentinel
                (sentinel_key, run_id, database_name, role_name, container_id)
            VALUES (TRUE, %s, %s, %s, %s)
            """,
            (
                authority.run_id,
                authority.database_name,
                authority.role_name,
                authority.container_id,
            ),
        )
        role_connection.commit()
    except Exception as exc:
        raise SafetyError("Disposable PostgreSQL provisioning failed; details withheld") from exc
    finally:
        _close_quietly(role_cursor)
        _close_quietly(role_connection)
        _close_quietly(extension_cursor)
        _close_quietly(extension_connection)
        _close_quietly(admin_cursor)
        _close_quietly(admin_connection)


def _target_environment(authority: DisposableAuthority) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "ENVIRONMENT": "test",
            "JUALIN_TEST_RUN_ID": authority.run_id,
            "JUALIN_TEST_CONTAINER_ID": authority.container_id,
            "JUALIN_TEST_SERVER_ADDRESS": authority.server_address,
            "DATABASE_URL": authority.dsn,
            "TEST_DATABASE_URL": authority.dsn,
        }
    )
    return environment


@contextmanager
def _guard_environment(authority: DisposableAuthority) -> Iterator[dict[str, str]]:
    environment = _target_environment(authority)
    previous = {
        key: os.environ.get(key) for key in TARGET_AUTHORITY_ENVIRONMENT
    }
    os.environ.update(
        {key: environment[key] for key in TARGET_AUTHORITY_ENVIRONMENT}
    )
    try:
        yield environment
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_target(
    authority: DisposableAuthority,
    command: Sequence[str],
    *,
    cwd: pathlib.Path | None = None,
) -> int:
    if not command:
        raise SafetyError("A target command is required")
    with _guard_environment(authority) as environment:
        connect_and_verify(authority.dsn, authority.run_id)
        result = subprocess.run(
            list(command),
            cwd=cwd,
            env=environment,
            check=False,
            shell=False,
        )
    return result.returncode


def _project_resource_ids(authority: DisposableAuthority, kind: str) -> list[str]:
    if kind not in {"container", "network", "volume"}:
        raise SafetyError("Unsupported Docker resource kind")
    noun = "container" if kind == "container" else kind
    arguments = [noun, "ls"]
    if kind == "container":
        arguments.append("--all")
    if kind in {"container", "network"}:
        arguments.append("--no-trunc")
    arguments.extend(
        [
            "--quiet",
            "--filter",
            f"label=com.docker.compose.project={authority.project_name}",
        ]
    )
    output = _docker(arguments).stdout
    return [line.strip() for line in output.splitlines() if line.strip()]


def _assert_network_record(
    authority: DisposableAuthority,
    network: dict,
    *,
    network_id: str,
    container_ids: set[str],
) -> None:
    labels = network.get("Labels") or {}
    options = network.get("Options") or {}
    if (
        CONTAINER_ID_PATTERN.fullmatch(network_id) is None
        or network.get("Id") != network_id
        or network.get("Name") != f"{authority.project_name}_default"
        or network.get("Driver") != "bridge"
        or network.get("Scope") != "local"
        or network.get("Internal") is not False
        or network.get("Attachable") is not False
        or network.get("Ingress") is not False
        or labels.get("com.docker.compose.project") != authority.project_name
        or labels.get("com.docker.compose.network") != "default"
        or labels.get("com.jualin.disposable") != "true"
        or labels.get("com.jualin.test-run-id") != authority.run_id
        or options.get("com.docker.network.bridge.host_binding_ipv4") != "127.0.0.1"
    ):
        raise SafetyError("Docker network labels do not match disposable authority")
    attached = network.get("Containers") or {}
    if set(attached) != container_ids:
        raise SafetyError("Disposable network contains an unexpected endpoint")


def _inspect_network(network_id: str) -> dict:
    if CONTAINER_ID_PATTERN.fullmatch(network_id) is None:
        raise SafetyError("Network ID is not an exact full Docker identifier")
    return _json_object(_docker(["network", "inspect", network_id]))


def _assert_network_authority(authority: DisposableAuthority) -> None:
    network = _inspect_network(authority.network_id)
    _assert_network_record(
        authority,
        network,
        network_id=authority.network_id,
        container_ids={authority.container_id},
    )


def _remove_preprovisioned_project(authority: DisposableAuthority) -> None:
    containers = _project_resource_ids(authority, "container")
    networks = _project_resource_ids(authority, "network")
    volumes = _project_resource_ids(authority, "volume")
    if not containers and not networks and not volumes:
        return
    if len(containers) > 1 or len(networks) != 1 or volumes:
        raise SafetyError("Pre-provision project resources do not match disposable authority")

    network_id = networks[0]
    container_ids: set[str] = set()
    if containers:
        container_id = containers[0]
        container = _inspect_container(container_id)
        actual_container_id, _, actual_network_id = _container_network_identity(
            authority, container
        )
        if actual_container_id != container_id or actual_network_id != network_id:
            raise SafetyError("Pre-provision container does not match project resources")
        container_ids.add(container_id)

    network = _inspect_network(network_id)
    _assert_network_record(
        authority,
        network,
        network_id=network_id,
        container_ids=container_ids,
    )
    if container_ids:
        _docker(["container", "rm", "--force", next(iter(container_ids))])

    network = _inspect_network(network_id)
    _assert_network_record(
        authority,
        network,
        network_id=network_id,
        container_ids=set(),
    )
    _docker(["network", "rm", network_id])

    if any(
        _project_resource_ids(authority, kind)
        for kind in ("container", "network", "volume")
    ):
        raise SafetyError("Pre-provision project cleanup left disposable resources")
    print(f"[DISPOSABLE DB] verified pre-provision cleanup: run_id={authority.run_id}")


def verify_and_remove(authority: DisposableAuthority) -> None:
    container = _inspect_container(authority.container_id)
    assert_container_authority(authority, container)

    containers = _project_resource_ids(authority, "container")
    networks = _project_resource_ids(authority, "network")
    volumes = _project_resource_ids(authority, "volume")
    if containers != [authority.container_id]:
        raise SafetyError("Compose project contains unexpected containers")
    if networks != [authority.network_id] or volumes:
        raise SafetyError("Compose project contains unexpected network or volume resources")
    _assert_network_authority(authority)

    with _guard_environment(authority):
        connect_and_verify(authority.dsn, authority.run_id)

    _docker(["container", "rm", "--force", authority.container_id])
    network = _inspect_network(authority.network_id)
    _assert_network_record(
        authority,
        network,
        network_id=authority.network_id,
        container_ids=set(),
    )
    _docker(["network", "rm", authority.network_id])
    if any(
        _project_resource_ids(authority, kind)
        for kind in ("container", "network", "volume")
    ):
        raise SafetyError("Verified teardown left disposable project resources")
    print(f"[DISPOSABLE DB] verified teardown complete: run_id={authority.run_id}")


def run_command(
    command: Sequence[str], *, cwd: pathlib.Path | None = None
) -> int:
    if not command:
        raise SafetyError("A target command is required")
    authority = new_authority()
    runtime: DisposableAuthority | None = None
    provisioned = False
    try:
        runtime = _start_container(authority)
        _provision_database(runtime)
        provisioned = True
        print(
            "[DISPOSABLE DB] exact database/role/sentinel provisioned: "
            f"run_id={runtime.run_id}"
        )
        return run_target(runtime, command, cwd=cwd)
    finally:
        if runtime is not None:
            if provisioned:
                verify_and_remove(runtime)
            else:
                _remove_preprovisioned_project(runtime)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one command behind an isolated disposable PostgreSQL guard"
    )
    parser.add_argument("--cwd", type=pathlib.Path, default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        result = run_command(command, cwd=args.cwd)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except SafetyError as exc:
        print(f"[DISPOSABLE DB FAIL] {exc}", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(result)


if __name__ == "__main__":
    main()
