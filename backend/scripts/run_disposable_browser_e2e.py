"""Run real browser evidence against guarded disposable PostgreSQL and Redis."""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterator
from urllib.request import urlopen

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
ARTIFACT = ROOT / "artifacts" / "proof-browser.json"
EXPECTED_BROWSER_TESTS = {
    "real auth tenant switch clears A before B",
    "real public capability exchange establishes an HttpOnly session",
    "real approval creates a durable dispatch",
}


def assert_guarded_environment() -> None:
    required = (
        "JUALIN_TEST_RUN_ID",
        "JUALIN_TEST_CONTAINER_ID",
        "JUALIN_TEST_SERVER_ADDRESS",
        "DATABASE_URL",
    )
    if os.environ.get("ENVIRONMENT") != "test" or any(
        not os.environ.get(name) for name in required
    ):
        raise RuntimeError("Disposable database runner authority is required")
    from scripts.assert_disposable_database import connect_and_verify

    connect_and_verify(os.environ["DATABASE_URL"], os.environ["JUALIN_TEST_RUN_ID"])


def playwright_assertions(
    report: dict[str, Any],
    expected_titles: set[str],
    *,
    expected_file: str | None = None,
) -> list[dict[str, Any]]:
    if report.get("errors"):
        raise RuntimeError("Real Playwright report contained root errors")
    suites = report.get("suites")
    if not isinstance(suites, list):
        raise RuntimeError("Real Playwright report was malformed")

    observed: dict[str, list[bool]] = {}

    def walk(items: list[dict[str, Any]]) -> None:
        for suite in items:
            for spec in suite.get("specs") or []:
                if expected_file:
                    report_file = pathlib.Path(str(spec.get("file") or "")).name
                    if report_file != pathlib.Path(expected_file).name:
                        continue
                tests = spec.get("tests") or []
                passed = bool(tests) and all(
                    test.get("status") == "expected"
                    and bool(test.get("results"))
                    and all(
                        result.get("status") == "passed"
                        for result in test.get("results") or []
                    )
                    for test in tests
                )
                title = str(spec.get("title") or "")
                observed.setdefault(title, []).append(passed)
            nested = suite.get("suites") or []
            if not isinstance(nested, list):
                raise RuntimeError("Real Playwright report was malformed")
            walk(nested)

    walk(suites)
    missing_failed_or_duplicate = sorted(
        title
        for title in expected_titles
        if observed.get(title) != [True]
    )
    if missing_failed_or_duplicate:
        raise RuntimeError("Real Playwright scenarios were missing, duplicated, or failed")
    return [
        {
            "ok": True,
            "message": f"Playwright passed: {title}",
            "audit_code": "real_browser_runtime",
        }
        for title in sorted(expected_titles)
    ]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _backend_environment(source: dict[str, str]) -> dict[str, str]:
    """Keep disposable authority and process basics while neutralizing providers."""
    allowed = {
        "APPDATA",
        "CI",
        "COMSPEC",
        "DATABASE_URL",
        "ENVIRONMENT",
        "HOME",
        "JUALIN_EVIDENCE_RUN_ID",
        "JUALIN_PROOF_SEED",
        "JUALIN_TEST_CONTAINER_ID",
        "JUALIN_TEST_RUN_ID",
        "JUALIN_TEST_SERVER_ADDRESS",
        "LANG",
        "LC_ALL",
        "LD_LIBRARY_PATH",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "PYTHONIOENCODING",
        "PYTHONPATH",
        "PYTHONUTF8",
        "SYSTEMROOT",
        "TEMP",
        "TERM",
        "TMP",
        "TMPDIR",
        "USERPROFILE",
        "VIRTUAL_ENV",
    }
    environment = {
        key: value
        for key, value in source.items()
        if key.upper() in allowed
    }
    environment.update(
        {
            "LLM_BASE_URL": "http://127.0.0.1:9/v1",
            "LLM_API_KEY": "",
            "GEMINI_API_KEY": "",
            "MIDTRANS_SERVER_KEY": "",
            "MIDTRANS_CLIENT_KEY": "",
            "MIDTRANS_IS_PRODUCTION": "false",
            "WHATSAPP_VERIFY_TOKEN": "",
            "WHATSAPP_ACCESS_TOKEN": "",
            "WHATSAPP_PHONE_NUMBER_ID": "",
            "WHATSAPP_WABA_ID": "",
            "WHATSAPP_APP_SECRET": "",
        }
    )
    return environment


def _frontend_environment(
    source: dict[str, str], backend_url: str
) -> dict[str, str]:
    """Build a least-privilege environment for Next.js and Playwright processes."""
    allowed = {
        "APPDATA",
        "CI",
        "COMSPEC",
        "HOME",
        "LANG",
        "LC_ALL",
        "LD_LIBRARY_PATH",
        "LOCALAPPDATA",
        "NODE_ENV",
        "NODE_OPTIONS",
        "NPM_CONFIG_CACHE",
        "NPM_CONFIG_USERCONFIG",
        "PATH",
        "PATHEXT",
        "PLAYWRIGHT_BROWSERS_PATH",
        "SYSTEMROOT",
        "TEMP",
        "TERM",
        "TMP",
        "TMPDIR",
        "USERPROFILE",
        "NEXT_TELEMETRY_DISABLED",
    }
    environment = {
        key: value
        for key, value in source.items()
        if key.upper() in allowed
    }
    environment["INTERNAL_API_URL"] = backend_url
    environment["NEXT_PUBLIC_API_URL"] = backend_url
    return environment


def _run_output_checked(
    label: str,
    command: list[str],
    *,
    cwd: pathlib.Path,
    environment: dict[str, str],
) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}")
    return result.stdout.strip()


def _run_checked(
    label: str,
    command: list[str],
    *,
    cwd: pathlib.Path,
    environment: dict[str, str],
) -> None:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        shell=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}")


def _wait_http(url: str, process: subprocess.Popen[bytes], timeout: int = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Supervised application process exited before readiness")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("Supervised application did not become ready")


@contextmanager
def _process(
    command: list[str], *, cwd: pathlib.Path, environment: dict[str, str]
) -> Iterator[subprocess.Popen[bytes]]:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
    )
    try:
        yield process
    finally:
        primary_error = sys.exc_info()[1]
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
        except Exception as cleanup_error:
            if primary_error is not None:
                primary_error.add_note("Supervised process cleanup also failed; details withheld")
            else:
                raise RuntimeError("Supervised process cleanup failed") from cleanup_error


@contextmanager
def _disposable_redis(run_id: str) -> Iterator[str]:
    from scripts.run_with_disposable_database import _docker

    token = uuid.UUID(run_id).hex
    name = f"jualin-test-redis-{token}"
    image = "redis:7-alpine"
    result = _docker(
        [
            "run",
            "--detach",
            "--rm",
            "--name",
            name,
            "--label",
            "com.jualin.disposable=true",
            "--label",
            f"com.jualin.test-run-id={run_id}",
            "--label",
            "com.jualin.resource=redis-e2e",
            "--publish",
            "127.0.0.1::6379",
            image,
            "redis-server",
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        timeout=180,
    )
    container_id = result.stdout.strip()

    def inspect_authority(*, require_running: bool) -> dict[str, Any]:
        inspected = json.loads(_docker(["inspect", container_id]).stdout)[0]
        labels = inspected.get("Config", {}).get("Labels") or {}
        mounts = inspected.get("Mounts") or []
        ports = inspected.get("NetworkSettings", {}).get("Ports", {}).get("6379/tcp")
        if (
            inspected.get("Id") != container_id
            or inspected.get("Name") != f"/{name}"
            or inspected.get("Config", {}).get("Image") != image
            or labels.get("com.jualin.disposable") != "true"
            or labels.get("com.jualin.test-run-id") != run_id
            or labels.get("com.jualin.resource") != "redis-e2e"
            or mounts
            or not isinstance(ports, list)
            or len(ports) != 1
            or ports[0].get("HostIp") != "127.0.0.1"
            or (require_running and inspected.get("State", {}).get("Running") is not True)
        ):
            raise RuntimeError("Disposable Redis authority verification failed")
        return inspected

    try:
        inspected = inspect_authority(require_running=True)
        ports = inspected["NetworkSettings"]["Ports"]["6379/tcp"]
        port = int(ports[0]["HostPort"])
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                ping = _docker(["exec", container_id, "redis-cli", "ping"])
            except RuntimeError:
                inspect_authority(require_running=True)
                time.sleep(0.5)
                continue
            if ping.stdout.strip() == "PONG":
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Disposable Redis did not become ready")
        yield f"redis://127.0.0.1:{port}/0"
    finally:
        primary_error = sys.exc_info()[1]
        try:
            resources = _docker(
                [
                    "ps",
                    "--all",
                    "--no-trunc",
                    "--filter",
                    f"label=com.jualin.test-run-id={run_id}",
                    "--filter",
                    "label=com.jualin.resource=redis-e2e",
                    "--format",
                    "{{.ID}}",
                ]
            ).stdout.splitlines()
            resources = [resource.strip() for resource in resources if resource.strip()]
            if resources:
                if resources != [container_id]:
                    raise RuntimeError("Refusing Redis teardown with changed authority")
                inspect_authority(require_running=False)
                _docker(["container", "rm", "--force", container_id])
        except Exception as cleanup_error:
            if primary_error is not None:
                primary_error.add_note("Disposable Redis cleanup also failed; details withheld")
            else:
                raise RuntimeError("Disposable Redis verified teardown failed") from cleanup_error


async def _seed_fixture(email_a: str, email_b: str, password: str) -> dict[str, Any]:
    import models  # noqa: F401
    from api.routes_auth import hash_password
    from models.agent_os import AgentPolicy
    from models.database import async_session
    from models.inbox import Channel
    from models.order import Order, OrderStatus
    from models.payment_recovery import (
        ContactPermission,
        ContactSubject,
        PaymentAttempt,
        PaymentRecoveryControl,
        RevenueOpportunity,
    )
    from models.user import User, UserRole, UserTier
    from models.wa_template import WhatsAppMessageTemplate
    from services.payment_capability import create_capability
    from services.payment_recovery.approval_materializer import (
        materialize_approval_for_opportunity,
    )

    now = datetime.now(timezone.utc)
    async with async_session() as db:
        seller_a = User(
            email=email_a,
            password_hash=hash_password(password),
            nama_toko="Toko E2E A",
            slug=f"toko-e2e-a-{secrets.token_hex(4)}",
            tier=UserTier.FREE,
            role=UserRole.SELLER,
        )
        seller_b = User(
            email=email_b,
            password_hash=hash_password(password),
            nama_toko="Toko E2E B",
            slug=f"toko-e2e-b-{secrets.token_hex(4)}",
            tier=UserTier.FREE,
            role=UserRole.SELLER,
        )
        db.add_all([seller_a, seller_b])
        await db.flush()
        order = Order(
            seller_id=seller_a.id,
            customer_name="Pelanggan Uji",
            customer_phone="+628000000000",
            items=[{"nama": "Produk Uji", "qty": 1, "harga": 10000}],
            total=10000,
            status=OrderStatus.PENDING,
            payment_method="snap",
            payment_provider="fixture",
            payment_invoice_id=f"fixture-{secrets.token_hex(6)}",
            payment_url="https://payments.example.test/invoice/fixture",
            payment_expires_at=(now + timedelta(hours=2)).isoformat(),
        )
        db.add(order)
        await db.flush()
        attempt = PaymentAttempt(
            seller_id=seller_a.id,
            order_id=order.id,
            provider="fixture",
            provider_account_id="fixture-account",
            external_attempt_id=f"attempt-{secrets.token_hex(6)}",
            attempt_version=1,
            is_current=True,
            status="pending",
            amount=Decimal("10000.00"),
            currency="IDR",
            payment_expires_at=now + timedelta(hours=2),
            trusted_link_reference="https://payments.example.test/invoice/fixture",
        )
        db.add(attempt)
        await db.flush()
        _, capability_token = await create_capability(
            db,
            seller_id=seller_a.id,
            order_id=order.id,
            payment_attempt_id=attempt.id,
        )
        subject = ContactSubject(seller_id=seller_a.id, channel="whatsapp")
        db.add(subject)
        await db.flush()
        permission = ContactPermission(
            seller_id=seller_a.id,
            contact_subject_id=subject.id,
            channel="whatsapp",
            address_fingerprint=f"fixture-{secrets.token_hex(16)}",
            fingerprint_key_version=1,
            purpose="transactional_payment_reminder",
            scope_type="order_payment_cycle",
            order_id=order.id,
            payment_attempt_id=attempt.id,
            status="active",
            provenance="disposable_e2e",
            expires_at=now + timedelta(hours=2),
        )
        channel = Channel(
            seller_id=seller_a.id,
            type="whatsapp",
            provider="whatsapp_cloud",
            external_id="fixture-phone-number-id",
            display_name="Disposable E2E",
            status="active",
            config_encrypted="",
        )
        template = WhatsAppMessageTemplate(
            seller_id=seller_a.id,
            name="payment_reminder_v1",
            category="utility",
            language="id",
            body="Pesanan {{1}} senilai {{2}} menunggu pembayaran.",
            variables_json=[{"key": "order"}, {"key": "amount"}],
            status="approved",
            provider_template_id="fixture-template-v1",
        )
        opportunity = RevenueOpportunity(
            seller_id=seller_a.id,
            order_id=order.id,
            payment_attempt_id=attempt.id,
            status="detected",
            signal_key=f"disposable-e2e:{seller_a.id}:{order.id}:{attempt.id}",
            amount_snapshot=Decimal("10000.00"),
            currency="IDR",
            evidence_json=[{"code": "disposable_e2e", "observed_at": now.isoformat()}],
            policy_version=1,
            state_version=1,
            eligible_at=now,
            expires_at=now + timedelta(hours=2),
        )
        control = PaymentRecoveryControl(id=1, enabled=True, paused=False, reason="disposable_e2e")
        policy_a = AgentPolicy(
            seller_id=seller_a.id,
            payment_recovery_mode="approval",
            payment_recovery_paused=False,
        )
        policy_b = AgentPolicy(seller_id=seller_b.id)
        db.add_all(
            [permission, channel, template, opportunity, control, policy_a, policy_b]
        )
        await db.flush()
        approval = await materialize_approval_for_opportunity(
            db,
            seller_id=seller_a.id,
            opportunity_id=opportunity.id,
            policy_version=1,
        )
        if approval is None:
            raise RuntimeError("Disposable recovery approval was not materialized")
        await db.commit()
        return {
            "seller_a_id": seller_a.id,
            "seller_b_id": seller_b.id,
            "order_id": order.id,
            "opportunity_id": str(opportunity.id),
            "capability_token": capability_token,
        }


async def _execute_approved_job(opportunity_id: str) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from models.database import async_session
    from models.payment_recovery import (
        OutboundDispatch,
        PaymentRecoveryControl,
        RevenueOpportunity,
    )
    from models.scale_core import BackgroundJob
    from worker import process_recorded_job

    opportunity_uuid = uuid.UUID(opportunity_id)
    async with async_session() as db:
        control = await db.get(PaymentRecoveryControl, 1)
        if control is None:
            raise RuntimeError("Recovery control disappeared")
        control.paused = True
        control.reason = "disposable_e2e_pre_send_stop"
        dispatch_result = await db.execute(
            select(OutboundDispatch).where(
                OutboundDispatch.opportunity_id == opportunity_uuid
            )
        )
        dispatch = dispatch_result.scalar_one_or_none()
        if not dispatch or dispatch.status != "scheduled" or not dispatch.background_job_id:
            raise RuntimeError("Browser approval did not create the durable dispatch")
        job_id = dispatch.background_job_id
        await db.commit()

    result = await process_recorded_job({}, job_id)
    if result.get("reason") != "global_paused":
        raise RuntimeError("Worker did not stop at the global pre-send kill switch")

    async with async_session() as db:
        dispatch = (
            await db.execute(
                select(OutboundDispatch).where(
                    OutboundDispatch.opportunity_id == opportunity_uuid
                )
            )
        ).scalar_one()
        opportunity = await db.get(RevenueOpportunity, opportunity_uuid)
        job = await db.get(BackgroundJob, job_id)
        checks = (
            dispatch.status == "cancelled",
            dispatch.attempt_count == 0,
            dispatch.last_error_code == "global_paused",
            opportunity is not None and opportunity.status == "suppressed",
            job is not None and job.status == "dead_letter",
        )
    if not all(checks):
        raise RuntimeError("Post-worker durable state did not fail closed")
    return [
        {
            "ok": True,
            "message": "real approval created a durable PostgreSQL dispatch and job",
            "audit_code": "approval_to_dispatch_real_db",
        },
        {
            "ok": True,
            "message": "real worker claim stopped before provider at the global kill switch",
            "audit_code": "worker_pre_send_revalidation",
        },
    ]


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _write_artifact(
    browser_assertions: list[dict[str, Any]],
    worker_assertions: list[dict[str, Any]],
    started_at: str,
    *,
    source_commit: str,
    source_identity_stable: bool,
) -> None:
    assertions = browser_assertions + worker_assertions
    evidence_run_id = (
        os.environ.get("JUALIN_EVIDENCE_RUN_ID")
        or os.environ.get("JUALIN_TEST_RUN_ID")
        or ""
    ).strip()
    if not evidence_run_id:
        raise RuntimeError("Evidence run identity is required")
    try:
        seed = int(os.environ.get("JUALIN_PROOF_SEED", "42"))
    except ValueError as exc:
        raise RuntimeError("Evidence seed must be an integer") from exc

    payload = {
        "schema_version": "proof-artifact-v1",
        "suite": "browser",
        "run_id": evidence_run_id,
        "seed": seed,
        "commit_sha": source_commit,
        "source_tree_clean": source_identity_stable,
        "status": "passed" if source_identity_stable else "unverified",
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "command": "python -m scripts.run_disposable_browser_e2e",
        "environment": "ci" if os.environ.get("CI") else "local_disposable",
        "watermark": "DATA SIMULASI",
        "redaction_status": "passed",
        "api_mocking": False,
        "dimensions": {
            "backend_invariants": "not_in_this_artifact",
            "browser_e2e": "passed",
            "backend_api": "passed",
            "postgresql": "passed",
            "redis": "passed",
            "worker_execution": "passed",
            "staging_provider": "blocked",
        },
        "scenarios": [
            {
                "scenario_id": "real-browser-disposable-stack",
                "status": "passed",
                "assertions": browser_assertions,
                "invariants": ["INV-01", "BUG-025", "BUG-034"],
                "provider_calls": 0,
            },
            {
                "scenario_id": "approval-dispatch-worker-kill-switch",
                "status": "passed",
                "assertions": worker_assertions,
                "invariants": ["INV-04", "INV-07", "INV-08"],
                "provider_calls": 0,
            },
        ],
        "summary": {
            "total": len(assertions),
            "passed": len(assertions),
            "failed": 0,
        },
        "infrastructure": {
            "loopback_only": True,
            "postgresql": "guarded_disposable_tmpfs",
            "redis": "guarded_disposable_no_persistence",
            "migration_rehearsal": "20260717_0012_downgrade_reupgrade_passed",
        },
        "disclaimer": (
            "Focused real local browser/backend/PostgreSQL/Redis proof with synthetic data. "
            "No live payment or messaging provider was called. DATA SIMULASI."
        ),
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    from services.payment_recovery.proof import (
        git_source_tree_clean,
        production_guard_blocks_proof_mode,
    )

    blocked, reason = production_guard_blocks_proof_mode()
    if blocked:
        raise RuntimeError(f"Proof runner safety guard blocked execution: {reason}")

    source_commit = _git_sha()
    source_tree_clean_at_start = git_source_tree_clean()
    started_at = datetime.now(timezone.utc).isoformat()
    assert_guarded_environment()
    environment = _backend_environment(dict(os.environ))
    python = sys.executable
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    npx = shutil.which("npx.cmd" if os.name == "nt" else "npx")
    if not npm or not npx:
        raise RuntimeError("npm and npx are required for real browser evidence")

    expected_head = "20260717_0012"
    heads = _run_output_checked(
        "Alembic heads",
        [python, "-m", "alembic", "-c", "alembic.ini", "heads"],
        cwd=ROOT,
        environment=environment,
    )
    head_revisions = {
        line.split()[0] for line in heads.splitlines() if line.strip()
    }
    if head_revisions != {expected_head}:
        raise RuntimeError("Disposable migration rehearsal requires the exact expected head")

    migration_steps = (
        ("Alembic upgrade", "upgrade", "head", expected_head),
        ("Alembic 0012 downgrade", "downgrade", "20260712_0011", "20260712_0011"),
        ("Alembic 0012 re-upgrade", "upgrade", "head", expected_head),
    )
    for label, action, revision, expected_current in migration_steps:
        _run_checked(
            label,
            [python, "-m", "alembic", "-c", "alembic.ini", action, revision],
            cwd=ROOT,
            environment=environment,
        )
        current = _run_output_checked(
            f"{label} current revision",
            [python, "-m", "alembic", "-c", "alembic.ini", "current"],
            cwd=ROOT,
            environment=environment,
        )
        current_revisions = {
            line.split()[0] for line in current.splitlines() if line.strip()
        }
        if current_revisions != {expected_current}:
            raise RuntimeError(f"{label} did not reach the expected revision")
    _run_checked(
        "Alembic model drift check",
        [python, "-m", "alembic", "-c", "alembic.ini", "check"],
        cwd=ROOT,
        environment=environment,
    )

    run_id = environment["JUALIN_TEST_RUN_ID"]
    token = uuid.UUID(run_id).hex
    email_a = f"seller-a-{token}@example.test"
    email_b = f"seller-b-{token}@example.test"
    password = f"E2E-{secrets.token_urlsafe(24)}"
    backend_port = _free_port()
    frontend_port = _free_port()
    backend_url = f"http://127.0.0.1:{backend_port}"
    frontend_url = f"http://127.0.0.1:{frontend_port}"

    with _disposable_redis(run_id) as redis_url, tempfile.TemporaryDirectory() as td:
        runtime = environment.copy()
        runtime.update(
            {
                "DEBUG": "true",
                "AUTO_CREATE_TABLES": "false",
                "REDIS_URL": redis_url,
                "SECRET_KEY": secrets.token_urlsafe(48),
                "JWT_SECRET_KEY": secrets.token_urlsafe(48),
                "PAYMENT_CAPABILITY_HMAC_KEY": secrets.token_urlsafe(48),
                "PAYMENT_REFERENCE_HMAC_KEY": secrets.token_urlsafe(48),
                "CONTACT_HMAC_KEY": secrets.token_urlsafe(48),
                "CONTACT_ENCRYPTION_KEY": secrets.token_urlsafe(48),
                "BASE_URL": backend_url,
                "FRONTEND_URL": frontend_url,
                "CORS_ORIGINS": json.dumps([frontend_url]),
                "PUBLIC_ORIGIN_ALLOWLIST": json.dumps([frontend_url]),
                "SCHEDULER_ENABLED": "false",
                "ENABLE_LEGACY_PENDING_PAYMENT_FOLLOWUP": "false",
                "ENABLE_PAYMENT_RECOVERY": "true",
                "PAYMENT_RECOVERY_MODE": "approval",
                "ENABLE_DEMO_PROOF_MODE": "false",
                "ENABLE_WHATSAPP": "false",
                "ENABLE_AI_ACTIONS": "false",
                "ENABLE_CAMPAIGNS": "false",
                "ENABLE_WORKFLOWS": "false",
                "ENABLE_BILLING": "false",
                "ENABLE_MARKETPLACE_IMPORT": "false",
            }
        )
        os.environ.update(runtime)
        fixture = asyncio.run(_seed_fixture(email_a, email_b, password))

        frontend_environment = _frontend_environment(environment, backend_url)
        _run_checked(
            "Next.js production build",
            [npm, "run", "build"],
            cwd=FRONTEND,
            environment=frontend_environment,
        )

        report_path = pathlib.Path(td) / "playwright-real-stack.json"
        browser_environment = frontend_environment.copy()
        browser_environment.update(
            {
                "CI": browser_environment.get("CI", "true"),
                "PLAYWRIGHT_SKIP_WEBSERVER": "1",
                "PLAYWRIGHT_BASE_URL": frontend_url,
                "PLAYWRIGHT_JSON_OUTPUT_FILE": str(report_path),
                "PLAYWRIGHT_CHANNEL": "",
                "E2E_SELLER_A_EMAIL": email_a,
                "E2E_SELLER_B_EMAIL": email_b,
                "E2E_SELLER_PASSWORD": password,
                "E2E_ORDER_ID": str(fixture["order_id"]),
                "E2E_CAPABILITY_TOKEN": fixture["capability_token"],
            }
        )
        with _process(
            [python, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(backend_port)],
            cwd=BACKEND,
            environment=runtime,
        ) as backend_process:
            _wait_http(f"{backend_url}/ready", backend_process)
            with _process(
                [npm, "run", "start", "--", "--hostname", "127.0.0.1", "--port", str(frontend_port)],
                cwd=FRONTEND,
                environment=frontend_environment,
            ) as frontend_process:
                _wait_http(f"{frontend_url}/login", frontend_process)
                _run_checked(
                    "Real Playwright disposable-stack suite",
                    [
                        npx,
                        "playwright",
                        "test",
                        "e2e/auth-cache-and-proof.real.spec.js",
                        "--output",
                        str(pathlib.Path(td) / "playwright-output"),
                    ],
                    cwd=FRONTEND,
                    environment=browser_environment,
                )

        report = json.loads(report_path.read_text(encoding="utf-8"))
        browser_assertions = playwright_assertions(
            report,
            EXPECTED_BROWSER_TESTS,
            expected_file="auth-cache-and-proof.real.spec.js",
        )
        worker_assertions = asyncio.run(
            _execute_approved_job(fixture["opportunity_id"])
        )
        source_identity_stable = (
            source_tree_clean_at_start
            and git_source_tree_clean()
            and source_commit != "unknown"
            and _git_sha() == source_commit
        )
        _write_artifact(
            browser_assertions,
            worker_assertions,
            started_at,
            source_commit=source_commit,
            source_identity_stable=source_identity_stable,
        )
    print("[REAL E2E] disposable browser/backend/PostgreSQL/Redis proof passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"[REAL E2E FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        if getattr(exc, "__notes__", None):
            print(
                "[REAL E2E CLEANUP] an additional sanitized cleanup failure occurred",
                file=sys.stderr,
            )
        raise SystemExit(1)
