"""
ARQ worker entrypoint for background jobs.

Run with:
    arq worker.WorkerSettings
"""
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from sqlalchemy import select, and_
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

async def process_recorded_job(ctx, job_id: int):
    """Dispatch a recorded background job to the appropriate handler."""
    worker_id = f"worker:{__import__('os').getpid()}"
    async with async_session() as db:
        result = await db.execute(select(BackgroundJob).where(BackgroundJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            return {"success": False, "error": "job not found"}
        if job.status in ("done", "dead_letter", "skipped"):
            return {"success": True, "skipped": True}
        if job.status == "running":
            return {"success": True, "status": "already running"}

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.locked_at = datetime.now(timezone.utc)
        job.locked_by = worker_id
        job.attempts += 1
        await db.commit()

        try:
            from services.job_handlers import (
                handle_inbox_ai_reply,
                handle_pending_payment_followup,
                handle_campaign_send_message,
                handle_workflow_run,
            )

            handler_map = {
                "inbox_ai_reply": handle_inbox_ai_reply,
                "pending_payment_followup": handle_pending_payment_followup,
                "campaign_send_message": handle_campaign_send_message,
                "workflow_run": handle_workflow_run,
            }

            handler = handler_map.get(job.job_type)
            if handler:
                result = await handler(db, job)
            else:
                result = {"success": False, "error": f"unknown job_type: {job.job_type}"}

            if result.get("success"):
                job.status = "skipped" if result.get("skipped") else "done"
                job.error_message = ""
            else:
                is_permanent = result.get("permanent", False)
                if is_permanent:
                    job.status = "dead_letter"
                    job.retryable = False
                else:
                    job.status = "failed"
                job.error_message = result.get("error", "")
                job.last_error_code = result.get("error_code", "")

            job.finished_at = datetime.now(timezone.utc)
            job.locked_at = None
            job.locked_by = ""
            await db.commit()
            logger.info(
                "Background job processed",
                extra={"job_id": job.id, "job_type": job.job_type, "result": result.get("success")},
            )
            return result

        except Exception as exc:
            if job.attempts >= job.max_attempts:
                job.status = "dead_letter"
                job.retryable = False
            else:
                job.status = "failed" if getattr(job, 'retryable', True) else "dead_letter"
            job.error_message = str(exc)
            job.last_error_code = type(exc).__name__
            job.finished_at = datetime.now(timezone.utc)
            job.locked_at = None
            job.locked_by = ""
            await db.commit()
            logger.error(f"Job {job.id} failed: {exc}", exc_info=True)
            raise


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
# Worker Settings
# ══════════════════════════════════════════════════

_redis_url = urlparse(settings.REDIS_URL)


class WorkerSettings:
    functions = [process_recorded_job]
    cron_jobs = [
        # Follow-up every 15 minutes
        cron(cron_followup_scheduler, minute={0, 15, 30, 45}, unique=True),
        # Workflow tick every 5 minutes
        cron(cron_workflow_tick, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}, unique=True),
        # Heartbeat every minute
        cron(cron_heartbeat, minute=None, unique=True),
    ]
    max_jobs = settings.ARQ_MAX_JOBS
    redis_settings = RedisSettings(
        host=_redis_url.hostname or "localhost",
        port=_redis_url.port or 6379,
        database=int((_redis_url.path or "/0").lstrip("/") or "0"),
        password=_redis_url.password,
    )

