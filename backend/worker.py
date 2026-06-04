"""
ARQ worker entrypoint for background jobs.

Run with:
    arq worker.WorkerSettings
"""
from datetime import datetime, timezone
from urllib.parse import urlparse
from sqlalchemy import select

from config import get_settings
from models.database import async_session
from models.scale_core import BackgroundJob
from core.logging_config import setup_logging, get_logger

settings = get_settings()
setup_logging(log_level="DEBUG" if settings.DEBUG else "INFO", log_to_file=False)
logger = get_logger(__name__)


async def process_recorded_job(ctx, job_id: int):
    async with async_session() as db:
        result = await db.execute(select(BackgroundJob).where(BackgroundJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            return {"success": False, "error": "job not found"}
        if job.status in ("done", "running"):
            return {"success": True, "status": job.status}

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        job.attempts += 1
        await db.commit()

        try:
            # V1 worker records lifecycle only. Actual side effects are added per feature.
            job.status = "done"
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("Background job processed", extra={"job_id": job.id, "job_type": job.job_type})
            return {"success": True, "job_id": job.id}
        except Exception as e:
            job.status = "failed" if job.attempts >= job.max_attempts else "queued"
            job.error_message = str(e)
            await db.commit()
            raise


class WorkerSettings:
    functions = [process_recorded_job]
    _redis_url = urlparse(settings.REDIS_URL)
    redis_settings = {
        "host": _redis_url.hostname or "localhost",
        "port": _redis_url.port or 6379,
        "database": int((_redis_url.path or "/0").lstrip("/") or "0"),
        "password": _redis_url.password,
    }
