"""
P1.5 residual — real PostgreSQL concurrency/constraint tests.

Requires disposable DATABASE_URL from scripts.run_with_disposable_database
(ENVIRONMENT=test, jualin_test_* database name). Skips on ambient/prod DSNs.
"""
from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _disposable_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL") or ""
    env = (os.environ.get("ENVIRONMENT") or "").lower()
    if env != "test":
        raise unittest.SkipTest("ENVIRONMENT must be test for PG concurrency suite")
    if "jualin_test_" not in url:
        raise unittest.SkipTest("DATABASE_URL is not a disposable jualin_test_* DSN")
    if any(x in url.lower() for x in ("prod", "production", "jualin_ai")):
        # jualin_ai is default app name — disposable uses jualin_test_
        if "jualin_test_" not in url:
            raise unittest.SkipTest("Refusing non-disposable database URL")
    return url


class PostgresConcurrencyIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.url = _disposable_url()
        self.engine = create_async_engine(self.url, pool_size=10, max_overflow=5)
        self.Session = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_concurrent_enqueue_same_key_inserts_one_row(self):
        from core.idempotency import enqueue_job_record

        key = f"conc-enqueue-{uuid.uuid4()}"
        payload = {"thread_id": 1}

        async def one():
            async with self.Session() as db:
                job, is_new = await enqueue_job_record(
                    db,
                    job_type="inbox_ai_reply",
                    payload=payload,
                    seller_id=None,
                    idempotency_key=key,
                )
                await db.commit()
                return job.id, is_new

        results = await asyncio.gather(one(), one(), one())
        ids = {r[0] for r in results}
        new_flags = [r[1] for r in results]
        self.assertEqual(len(ids), 1, "exactly one background_jobs row")
        self.assertEqual(sum(1 for n in new_flags if n), 1, "exactly one is_new winner")

        async with self.Session() as db:
            count = (
                await db.execute(
                    text("SELECT count(*) FROM background_jobs WHERE idempotency_key=:k"),
                    {"k": key},
                )
            ).scalar()
        self.assertEqual(int(count), 1)

    async def test_concurrent_claim_only_one_worker_wins(self):
        from core.idempotency import enqueue_job_record
        from worker import atomic_claim_job

        key = f"conc-claim-{uuid.uuid4()}"
        async with self.Session() as db:
            job, is_new = await enqueue_job_record(
                db,
                job_type="inbox_ai_reply",
                payload={"thread_id": 99},
                seller_id=None,
                idempotency_key=key,
            )
            await db.commit()
            self.assertTrue(is_new)
            job_id = job.id

        async def claim(worker: str):
            async with self.Session() as db:
                claimed, token = await atomic_claim_job(db, worker, "inbox_ai_reply", 1)
                await db.commit()
                return (
                    claimed.id if claimed else None,
                    str(token) if token else None,
                )

        a, b = await asyncio.gather(claim("worker-a"), claim("worker-b"))
        winners = [x for x in (a, b) if x[0] is not None]
        self.assertEqual(len(winners), 1, "exactly one claim succeeds")
        self.assertEqual(winners[0][0], job_id)

        async with self.Session() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT status, claim_token IS NOT NULL AS has_token FROM background_jobs WHERE id=:id"
                    ),
                    {"id": job_id},
                )
            ).one()
        self.assertEqual(row[0], "running")
        self.assertTrue(row[1])

    async def test_stale_claim_token_cannot_finalize(self):
        from core.idempotency import enqueue_job_record
        from worker import atomic_claim_job

        key = f"stale-finalize-{uuid.uuid4()}"
        async with self.Session() as db:
            job, _ = await enqueue_job_record(
                db,
                job_type="inbox_ai_reply",
                payload={"thread_id": 7},
                seller_id=None,
                idempotency_key=key,
            )
            await db.commit()

        async with self.Session() as db:
            claimed, token = await atomic_claim_job(db, "worker-1", "inbox_ai_reply", 1)
            await db.commit()
            self.assertIsNotNone(claimed)
            self.assertIsNotNone(token)

        stale = uuid.uuid4()
        async with self.Session() as db:
            result = await db.execute(
                text(
                    """
                    UPDATE background_jobs
                    SET status='done', finished_at=now()
                    WHERE id=:id AND claim_token=:token
                    RETURNING id
                    """
                ),
                {"id": claimed.id, "token": stale},
            )
            await db.commit()
            self.assertIsNone(result.fetchone(), "stale token must not finalize")

        async with self.Session() as db:
            status = (
                await db.execute(
                    text("SELECT status FROM background_jobs WHERE id=:id"),
                    {"id": claimed.id},
                )
            ).scalar()
        self.assertEqual(status, "running")

    async def test_webhook_concurrent_dedupe(self):
        from core.idempotency import get_or_create_webhook_event_composite

        ext = f"evt-{uuid.uuid4()}"
        account = "acct-test"

        async def one():
            async with self.Session() as db:
                event, is_new = await get_or_create_webhook_event_composite(
                    db,
                    provider="whatsapp_cloud",
                    provider_account_id=account,
                    external_event_id=ext,
                    event_type="delivery_delivered",
                    payload={"status": "delivered", "message_id": "wamid.x"},
                )
                await db.commit()
                return event.id, is_new

        results = await asyncio.gather(one(), one(), one())
        ids = {r[0] for r in results}
        self.assertEqual(len(ids), 1)
        self.assertEqual(sum(1 for _, n in results if n), 1)

    async def test_composite_unique_webhook_key_rejects_duplicate(self):
        from core.idempotency import get_or_create_webhook_event_composite

        ext = f"evt-dup-{uuid.uuid4()}"
        async with self.Session() as db:
            e1, n1 = await get_or_create_webhook_event_composite(
                db,
                provider="whatsapp_cloud",
                provider_account_id="acct-a",
                external_event_id=ext,
                event_type="delivery_read",
                payload={"status": "read"},
            )
            await db.commit()
            e2, n2 = await get_or_create_webhook_event_composite(
                db,
                provider="whatsapp_cloud",
                provider_account_id="acct-a",
                external_event_id=ext,
                event_type="delivery_read",
                payload={"status": "read"},
            )
            await db.commit()
        self.assertTrue(n1)
        self.assertFalse(n2)
        self.assertEqual(e1.id, e2.id)


if __name__ == "__main__":
    unittest.main()
