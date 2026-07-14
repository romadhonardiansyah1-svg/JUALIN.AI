"""
ARQ worker entrypoint for background jobs.

Run with:
    arq worker.WorkerSettings
"""
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from sqlalchemy import select, and_, or_
from arq.cron import cron
from arq.connections import RedisSettings

from config import get_settings
from models.database import async_session
from models.scale_core import BackgroundJob
from models.order import Order, OrderStatus
from models.system_heartbeat import SystemHeartbeat
from core.logging_config import setup_logging, get_logger
from core.idempotency import enqueue_job_record

settings = get_settings()
setup_logging(log_level="DEBUG" if settings.DEBUG else "INFO", log_to_file=False)
logger = get_logger(__name__)


# ══════════════════════════════════════════════════
# Main Dispatcher
# ══════════════════════════════════════════════════

import uuid as uuid_module
from sqlalchemy import text

async def atomic_claim_job(db, worker_id: str, job_type: str, contract_version: int):
    """
    P1.2 atomic claim with lease/fencing token.
    Returns claimed BackgroundJob or None.
    """
    claim_token = uuid_module.uuid4()
    # Use CTE with FOR UPDATE SKIP LOCKED
    claim_sql = text(
        """
        WITH candidate AS (
          SELECT id FROM background_jobs
          WHERE (
              (
                status = 'queued'
                AND execution_stage = 'pre_side_effect'
                AND attempts < max_attempts
              )
              OR (
                status = 'failed'
                AND retryable = true
                AND execution_stage = 'pre_side_effect'
                AND attempts < max_attempts
              )
            )
            AND job_type = :job_type
            AND handler_contract_version = :contract_version
            AND payload_digest IS NOT NULL
            AND (next_run_at IS NULL OR next_run_at <= now())
            AND (lease_expires_at IS NULL OR lease_expires_at < now())
          ORDER BY next_run_at NULLS FIRST, id
          FOR UPDATE SKIP LOCKED
          LIMIT 1
        )
        UPDATE background_jobs j
        SET status='running', claim_token=:claim_token,
            lease_expires_at=now() + interval '2 minutes',
            lock_version=lock_version + 1, locked_by=:worker_id, locked_at=now(),
            attempts=attempts + 1, started_at=now()
        FROM candidate
        WHERE j.id=candidate.id
        RETURNING j.id
        """
    )
    result = await db.execute(
        claim_sql,
        {"job_type": job_type, "contract_version": contract_version, "claim_token": claim_token, "worker_id": worker_id},
    )
    row = result.fetchone()
    if not row:
        return None, None
    job_id = row[0]
    # Fetch full job
    job_q = await db.execute(select(BackgroundJob).where(BackgroundJob.id == job_id))
    job = job_q.scalar_one()
    return job, claim_token


async def process_recorded_job(ctx, job_id: int):
    """Dispatch a recorded background job to the appropriate handler — P1.2 fenced."""
    worker_id = f"worker:{__import__('os').getpid()}"
    async with async_session() as db:
        # Try atomic claim by id + token check for direct dispatch path (legacy direct id)
        # If job_id provided, we attempt to claim it specifically with fencing
        claim_token = uuid_module.uuid4()
        # First, attempt to claim this specific job if it is still claimable
        # We use a conditional update that ensures only one worker wins
        claim_specific_sql = text(
            """
            UPDATE background_jobs
            SET status='running', claim_token=:claim_token,
                lease_expires_at=now() + interval '2 minutes',
                lock_version=lock_version + 1, locked_by=:worker_id, locked_at=now(),
                attempts=attempts + 1, started_at=now()
            WHERE id=:job_id
              AND status IN ('queued', 'failed')
              AND execution_stage = 'pre_side_effect'
              AND attempts < max_attempts
              AND payload_digest IS NOT NULL
              AND (lease_expires_at IS NULL OR lease_expires_at < now())
            RETURNING id
            """
        )
        result = await db.execute(
            claim_specific_sql,
            {"job_id": job_id, "claim_token": claim_token, "worker_id": worker_id},
        )
        claimed_row = result.fetchone()
        if not claimed_row:
            # Either not found, not claimable, or already claimed
            # Fetch current state to decide
            existing_q = await db.execute(select(BackgroundJob).where(BackgroundJob.id == job_id))
            job = existing_q.scalar_one_or_none()
            if not job:
                return {"success": False, "error": "job not found"}
            if job.status in ("done", "dead_letter", "skipped", "manual_required"):
                return {"success": True, "skipped": True}
            if job.status == "running":
                return {"success": True, "status": "already running"}
            # Could be queued but not matched due to digest/null etc — treat as not claimable
            return {"success": False, "error": "job not claimable", "status": job.status}

        await db.commit()
        # Re-fetch job after claim
        job_q = await db.execute(select(BackgroundJob).where(BackgroundJob.id == job_id))
        job = job_q.scalar_one()

        # Now job is claimed with claim_token, proceed to handler outside of long transaction?
        # We already committed claim, now run handler
        await db.commit()

        try:
            from services.job_handlers import (
                handle_inbox_ai_reply,
                handle_pending_payment_followup,
                handle_campaign_send_message,
                handle_workflow_run,
                handle_payment_recovery_dispatch,
                handle_payment_reconciliation,
            )

            handler_map = {
                "inbox_ai_reply": handle_inbox_ai_reply,
                "pending_payment_followup": handle_pending_payment_followup,
                "campaign_send_message": handle_campaign_send_message,
                "workflow_run": handle_workflow_run,
                "payment_recovery_dispatch": handle_payment_recovery_dispatch,
                "payment_reconciliation": handle_payment_reconciliation,
            }

            handler = handler_map.get(job.job_type)
            if handler:
                # P1.2: verify claim_token still valid before handler (stale check)
                fresh_q = await db.execute(select(BackgroundJob).where(BackgroundJob.id == job.id))
                fresh_job = fresh_q.scalar_one_or_none()
                if not fresh_job or fresh_job.claim_token != claim_token:
                    logger.warning(f"Stale worker cannot finalize job {job_id} — token mismatch")
                    await db.rollback()
                    return {"success": False, "error": "stale worker token mismatch"}

                result = await handler(db, job)
            else:
                result = {"success": False, "error": f"unknown job_type: {job.job_type}"}

            # Fenced finalize — only if claim_token still matches
            finalize_sql = text(
                """
                UPDATE background_jobs
                SET status=:status, error_message=:error_message, last_error_code=:last_error_code,
                    next_run_at=:next_run_at, finished_at=now(),
                    locked_at=NULL, locked_by='', execution_stage=:execution_stage
                WHERE id=:job_id AND claim_token=:claim_token
                RETURNING id
                """
            )

            if result.get("success"):
                new_status = "skipped" if result.get("skipped") else "done"
                new_stage = "completed"
                err_msg = ""
                err_code = ""
                next_run = None
            else:
                is_permanent = result.get("permanent", False)
                if is_permanent or job.attempts >= job.max_attempts:
                    new_status = "dead_letter"
                    new_stage = "completed" if is_permanent else "manual_required"
                    next_run = None
                else:
                    new_status = "failed"
                    new_stage = "pre_side_effect"
                    backoff_seconds = min(900, 60 * (2 ** max(0, job.attempts - 1)))
                    next_run = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
                err_msg = result.get("error", "")[:1000]
                err_code = result.get("error_code", "")[:50]

            # For failed jobs that are retryable explicit, keep retryable flag
            # For done/skipped/dead_letter, set appropriate retryable
            # We will update retryable separately via ORM for simplicity after fenced check
            fenced_result = await db.execute(
                finalize_sql,
                {
                    "status": new_status,
                    "error_message": err_msg,
                    "last_error_code": err_code,
                    "next_run_at": next_run,
                    "execution_stage": new_stage,
                    "job_id": job.id,
                    "claim_token": claim_token,
                },
            )
            fenced_row = fenced_result.fetchone()
            if not fenced_row:
                logger.warning(f"Stale worker finalize blocked for job {job_id} — token changed during execution")
                await db.rollback()
                return {"success": False, "error": "stale finalize blocked"}

            # Update retryable flag based on result if needed (separate update, still fenced via status already set)
            if new_status == "dead_letter":
                await db.execute(
                    text("UPDATE background_jobs SET retryable=false WHERE id=:job_id"),
                    {"job_id": job.id},
                )
            elif new_status == "failed":
                # Keep retryable as is if spec says retryable, else false
                from services.background_job_registry import ENABLED_JOB_HANDLERS

                spec = ENABLED_JOB_HANDLERS.get(job.job_type)
                should_retry = spec.retryable if spec else False
                if not should_retry:
                    await db.execute(
                        text("UPDATE background_jobs SET retryable=false WHERE id=:job_id"),
                        {"job_id": job.id},
                    )

            await db.commit()
            logger.info(
                "Background job processed",
                extra={"job_id": job.id, "job_type": job.job_type, "result": result.get("success")},
            )
            return result

        except Exception as exc:
            # Fenced failure path
            try:
                # Attempt to set failed only if token matches
                fail_sql = text(
                    """
                    UPDATE background_jobs
                    SET status=CASE WHEN attempts >= max_attempts THEN 'dead_letter' ELSE 'failed' END,
                        retryable=CASE WHEN attempts >= max_attempts THEN false ELSE retryable END,
                        error_message=:err, last_error_code=:code,
                        next_run_at=CASE WHEN attempts >= max_attempts THEN NULL ELSE now() + interval '60 seconds' END,
                        finished_at=now(), locked_at=NULL, locked_by='',
                        execution_stage='pre_side_effect'
                    WHERE id=:job_id AND claim_token=:claim_token
                    RETURNING id
                    """
                )
                await db.execute(
                    fail_sql,
                    {"job_id": job_id, "claim_token": claim_token, "err": str(exc)[:1000], "code": type(exc).__name__[:50]},
                )
                await db.commit()
            except Exception:
                await db.rollback()
            logger.error(f"Job {job_id} failed: {exc}", exc_info=True)
            raise


async def cron_process_queued_jobs(ctx):
    """
    Execute DB-recorded jobs that were created by API routes or cron matchers — P1.2 stage-aware.

    Claims one job per enabled (job_type, contract_version) pair fairly, using FOR UPDATE SKIP LOCKED.
    Generic lease reaper only requeues pre_side_effect, not side_effect_in_flight/unknown/manual.
    """
    from services.background_job_registry import all_enabled_pairs

    worker_id = f"worker:{__import__('os').getpid()}"
    # Try each enabled pair fairly, up to ARQ_MAX_JOBS claims per tick
    claimed_ids = []
    async with async_session() as db:
        for job_type, contract_version in all_enabled_pairs():
            if len(claimed_ids) >= max(1, settings.ARQ_MAX_JOBS):
                break
            job, token = await atomic_claim_job(db, worker_id, job_type, contract_version)
            if job:
                await db.commit()
                claimed_ids.append(job.id)
            else:
                await db.rollback()

    for job_id in claimed_ids:
        try:
            await process_recorded_job(ctx, job_id)
        except Exception as exc:
            logger.warning(f"Queued job poll failed for job {job_id}: {exc}")

    # Also run inventory sweep for disabled/unknown handlers -> quarantine
    try:
        async with async_session() as db:
            await quarantine_disabled_jobs(db)
            await db.commit()
    except Exception as e:
        logger.warning(f"Quarantine sweep failed: {e}")


async def quarantine_disabled_jobs(db):
    """
    P1.2 inventory sweeper: move rows with handler disabled/unknown,
    contract stale/null, or digest null to quarantine/manual_required.
    """
    from services.background_job_registry import ENABLED_JOB_HANDLERS

    # Build list of enabled job_types
    enabled_types = list(ENABLED_JOB_HANDLERS.keys())
    # Quarantine if job_type not in enabled, or contract version mismatch, or payload_digest null
    # For each enabled type, we need to check contract version matches
    # We'll use raw SQL for simplicity
    # First, quarantine unknown job_type
    if enabled_types:
        placeholders = ", ".join([f"'{t}'" for t in enabled_types])
        # Unknown type
        await db.execute(
            text(
                f"""
                UPDATE background_jobs
                SET status='manual_required', execution_stage='manual_required',
                    retryable=false, error_message='handler disabled or unknown',
                    last_error_code='handler_disabled'
                WHERE status IN ('queued', 'failed')
                  AND job_type NOT IN ({placeholders})
                  AND status != 'manual_required'
                """
            )
        )
        # Contract mismatch or null digest
        for jt, spec in ENABLED_JOB_HANDLERS.items():
            await db.execute(
                text(
                    """
                    UPDATE background_jobs
                    SET status='manual_required', execution_stage='manual_required',
                        retryable=false, error_message='contract stale or digest null',
                        last_error_code='contract_mismatch'
                    WHERE status IN ('queued', 'failed')
                      AND job_type = :job_type
                      AND (
                        handler_contract_version IS NULL
                        OR handler_contract_version != :contract_version
                        OR payload_digest IS NULL
                      )
                      AND status != 'manual_required'
                    """
                ),
                {"job_type": jt, "contract_version": spec.contract_version},
            )
    else:
        # No enabled handlers — quarantine all queued
        await db.execute(
            text(
                """
                UPDATE background_jobs
                SET status='manual_required', execution_stage='manual_required',
                    retryable=false
                WHERE status IN ('queued', 'failed')
                """
            )
        )


# ══════════════════════════════════════════════════
# Cron: Follow-up Scheduler
# ══════════════════════════════════════════════════

async def cron_followup_scheduler(ctx):
    """
    Periodic job: find pending orders that need follow-up and enqueue jobs.
    Replaces the old in-process asyncio loop from main.py.
    """
    from ai.followup import get_pending_followups, auto_cancel_expired

    async with async_session() as db:
        try:
            # 1. Enqueue follow-ups
            followups = await get_pending_followups(db)
            enqueued = 0
            for fu in followups:
                idem_key = f"pending_payment_followup:{fu['order_id']}:{fu['followup_number']}"
                _, is_new = await enqueue_job_record(
                    db,
                    job_type="pending_payment_followup",
                    seller_id=fu["seller_id"],
                    payload={"order_id": fu["order_id"], "followup_number": fu["followup_number"]},
                    idempotency_key=idem_key,
                )
                if is_new:
                    enqueued += 1

            # 2. Auto-cancel expired
            cancelled = await auto_cancel_expired(db)

            await db.commit()

            if enqueued > 0 or cancelled > 0:
                logger.info(
                    f"Follow-up cron: enqueued {enqueued} jobs, cancelled {cancelled} orders",
                )
        except Exception as e:
            logger.error(f"Follow-up cron error: {e}", exc_info=True)


# ══════════════════════════════════════════════════
# Cron: Workflow Tick
# ══════════════════════════════════════════════════

async def cron_workflow_tick(ctx):
    """Periodic job: run workflow automation matching."""
    if not settings.ENABLE_WORKFLOWS:
        return

    try:
        from services.workflow_runner import tick_workflows
        async with async_session() as db:
            await tick_workflows(db)
    except Exception as e:
        logger.error(f"Workflow tick error: {e}", exc_info=True)


# ══════════════════════════════════════════════════
# Cron: JUALIN OS Tick (proaktif multi-agen)
# ══════════════════════════════════════════════════

async def cron_agent_os_tick(ctx):
    """Jalankan siklus proaktif (inventory scan + growth) untuk semua seller."""
    if not settings.ENABLE_AGENT_OS:
        return
    try:
        from services.agent_os.cycles import run_all_seller_cycles
        async with async_session() as db:
            result = await run_all_seller_cycles(db)
            logger.info("Agent OS tick done", extra=result)
    except Exception as e:
        logger.error(f"Agent OS tick error: {e}", exc_info=True)


# ══════════════════════════════════════════════════
# Cron: Worker Heartbeat
# ══════════════════════════════════════════════════

async def cron_heartbeat(ctx):
    """Write heartbeat to system_heartbeats table every 60s."""
    async with async_session() as db:
        try:
            result = await db.execute(
                select(SystemHeartbeat).where(SystemHeartbeat.service == "worker")
            )
            hb = result.scalar_one_or_none()
            if not hb:
                hb = SystemHeartbeat(service="worker", status="alive")
                db.add(hb)
            hb.status = "alive"
            hb.last_seen_at = datetime.now(timezone.utc)
            hb.metadata_json = {
                "max_jobs": settings.ARQ_MAX_JOBS,
                "pid": __import__("os").getpid(),
            }
            await db.commit()
        except Exception as e:
            logger.error(f"Heartbeat error: {e}", exc_info=True)


# ══════════════════════════════════════════════════
# Cron: Recovery Detector (P2.6 observe-only)
# ══════════════════════════════════════════════════

async def cron_recovery_detector(ctx):
    """Periodic job: detect pending payment recovery opportunities in observe mode."""
    if not getattr(settings, "ENABLE_PAYMENT_RECOVERY", False):
        return
    # In Phase 2, only observe mode is allowed; approval mode not yet enabled
    mode = getattr(settings, "PAYMENT_RECOVERY_MODE", "observe")
    if mode not in ("observe",):
        # Until P4, approval mode is unavailable via detector — will be reported via capabilities
        return

    try:
        from services.payment_recovery.detector import detect_payment_recovery_opportunities
        async with async_session() as db:
            opps = await detect_payment_recovery_opportunities(db)
            if opps:
                logger.info(f"Recovery detector: found {len(opps)} opportunities", extra={"count": len(opps)})
    except Exception as e:
        logger.error(f"Recovery detector error: {e}", exc_info=True)


# ══════════════════════════════════════════════════
# Worker Settings
# ══════════════════════════════════════════════════

_redis_url = urlparse(settings.REDIS_URL)


def _build_cron_jobs():
    """Build cron list with legacy followup gated by flag (P0.1) + recovery detector (P2.6)."""
    jobs = [
        # Execute DB-recorded jobs every minute
        cron(cron_process_queued_jobs, minute=None, unique=True),
        # Workflow tick every 5 minutes
        cron(cron_workflow_tick, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}, unique=True),
        # Heartbeat every minute
        cron(cron_heartbeat, minute=None, unique=True),
        # JUALIN OS proaktif setiap 10 menit
        cron(cron_agent_os_tick, minute={0, 10, 20, 30, 40, 50}, unique=True),
        # Recovery detector every 5 minutes in observe mode (P2.6) — exactly one worker registry behind new flag
        cron(cron_recovery_detector, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}, unique=True),
    ]
    # Legacy followup only if explicitly enabled — disabled by default
    if getattr(settings, "ENABLE_LEGACY_PENDING_PAYMENT_FOLLOWUP", False):
        jobs.append(
            cron(cron_followup_scheduler, minute={0, 15, 30, 45}, unique=True)
        )
        logger.info("Worker: legacy followup cron enabled via ENABLE_LEGACY_PENDING_PAYMENT_FOLLOWUP=true")
    else:
        logger.info("Worker: legacy followup cron disabled — ENABLE_LEGACY_PENDING_PAYMENT_FOLLOWUP=false")

    # Recovery detector logging
    if getattr(settings, "ENABLE_PAYMENT_RECOVERY", False):
        logger.info(f"Worker: recovery detector enabled mode={getattr(settings, 'PAYMENT_RECOVERY_MODE', 'observe')}")
    else:
        logger.info("Worker: recovery detector disabled — ENABLE_PAYMENT_RECOVERY=false")

    return jobs


class WorkerSettings:
    functions = [process_recorded_job]
    cron_jobs = _build_cron_jobs()
    max_jobs = settings.ARQ_MAX_JOBS
    redis_settings = RedisSettings(
        host=_redis_url.hostname or "localhost",
        port=_redis_url.port or 6379,
        database=int((_redis_url.path or "/0").lstrip("/") or "0"),
        password=_redis_url.password,
    )
