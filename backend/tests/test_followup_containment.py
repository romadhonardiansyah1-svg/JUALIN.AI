"""P0.1 regression tests for legacy scheduler containment."""

import asyncio
import os
import sys
import types
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx


class ConfigAndWorkerContainmentTests(unittest.TestCase):
    def test_legacy_scheduler_flags_default_to_false(self):
        from config import Settings

        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)

        self.assertFalse(settings.SCHEDULER_ENABLED)
        self.assertFalse(settings.ENABLE_LEGACY_PENDING_PAYMENT_FOLLOWUP)

    def test_worker_settings_registry_excludes_only_legacy_followup(self):
        import worker

        cron_names = [
            job.coroutine.__name__
            for job in worker.WorkerSettings.cron_jobs
        ]
        self.assertEqual(
            cron_names,
            [
                "cron_process_queued_jobs",
                "cron_workflow_tick",
                "cron_heartbeat",
                "cron_agent_os_tick",
                "cron_recovery_detector",
            ],
        )
        self.assertNotIn("cron_followup_scheduler", cron_names)


class LifespanContainmentTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_lifespan_requires_both_legacy_flags_and_has_no_side_effects(self):
        import main
        from config import Settings

        one_sided_or_default_flags = (
            (False, False),
            (True, False),
            (False, True),
        )

        for scheduler_enabled, legacy_enabled in one_sided_or_default_flags:
            with self.subTest(
                scheduler_enabled=scheduler_enabled,
                legacy_enabled=legacy_enabled,
            ):
                with patch.dict(os.environ, {}, clear=True):
                    safe_settings = Settings(_env_file=None)
                safe_settings.SCHEDULER_ENABLED = scheduler_enabled
                safe_settings.ENABLE_LEGACY_PENDING_PAYMENT_FOLLOWUP = legacy_enabled

                init_db = AsyncMock(return_value=None)
                scheduler = AsyncMock(return_value=None)
                pending = AsyncMock(
                    return_value=[
                        {
                            "order_id": 1,
                            "seller_id": 1,
                            "customer_name": "not-logged",
                            "followup_number": 1,
                        }
                    ]
                )
                mark_sent = AsyncMock(return_value=None)
                auto_cancel = AsyncMock(return_value=0)
                close_client = AsyncMock(return_value=None)
                test_logger = MagicMock()

                with (
                    patch.object(main, "settings", safe_settings),
                    patch.object(main, "init_db", init_db),
                    patch.object(main, "followup_scheduler", scheduler),
                    patch.object(main, "setup_logging"),
                    patch.object(main, "logger", test_logger),
                    patch("ai.followup.get_pending_followups", pending),
                    patch("ai.followup.mark_followup_sent", mark_sent),
                    patch("ai.followup.auto_cancel_expired", auto_cancel),
                    patch("ai.llm_client.close_client", close_client),
                ):
                    async with main.lifespan(main.app):
                        init_db.assert_awaited_once_with()
                        scheduler.assert_not_called()

                scheduler.assert_not_called()
                pending.assert_not_awaited()
                mark_sent.assert_not_awaited()
                auto_cancel.assert_not_awaited()
                close_client.assert_awaited_once_with()
                self.assertTrue(
                    any(
                        "legacy scheduler disabled" in str(call.args[0]).lower()
                        for call in test_logger.info.call_args_list
                        if call.args
                    )
                )

    async def test_retained_legacy_scheduler_log_mode_never_marks_followup_sent(self):
        import main

        customer_name = "Sensitive Customer Marker"
        database_session = object()

        @asynccontextmanager
        async def fake_session():
            yield database_session

        pending = AsyncMock(
            return_value=[
                {
                    "order_id": 1,
                    "seller_id": 2,
                    "customer_name": customer_name,
                    "followup_number": 1,
                }
            ]
        )
        mark_sent = AsyncMock(return_value=None)
        auto_cancel = AsyncMock(return_value=0)
        test_logger = MagicMock()

        with (
            patch.object(main, "async_session", fake_session),
            patch.object(main, "logger", test_logger),
            patch.object(
                main.asyncio,
                "sleep",
                AsyncMock(side_effect=asyncio.CancelledError),
            ),
            patch("ai.followup.get_pending_followups", pending),
            patch("ai.followup.mark_followup_sent", mark_sent),
            patch("ai.followup.auto_cancel_expired", auto_cancel),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await main.followup_scheduler()

        mark_sent.assert_not_awaited()
        logged_messages = " ".join(
            str(call.args[0])
            for call in test_logger.info.call_args_list
            if call.args
        )
        self.assertNotIn(customer_name, logged_messages)


class _FakeCronJob:
    def __init__(self, coroutine):
        self.coroutine = coroutine


def cron_followup_scheduler():
    pass


def cron_recovery_detector():
    pass


def _module(name, **attributes):
    module = types.ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    return module


def _worker_module(*coroutines):
    worker_settings = type(
        "WorkerSettings",
        (),
        {"cron_jobs": [_FakeCronJob(coroutine) for coroutine in coroutines]},
    )
    return _module("worker", WorkerSettings=worker_settings)


class AdminSchedulerStatusTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _settings(**overrides):
        values = {
            "SCHEDULER_ENABLED": False,
            "ENABLE_LEGACY_PENDING_PAYMENT_FOLLOWUP": False,
            "ENABLE_PAYMENT_RECOVERY": False,
            "PAYMENT_RECOVERY_MODE": "observe",
            "APP_VERSION": "test",
            "LLM_MODEL": "test",
            "EMBEDDING_MODEL": "test",
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    async def _get_health(self, settings, worker_module):
        from api import routes_admin

        cache_module = _module("cache", get_redis=AsyncMock(return_value=None))
        db = SimpleNamespace(execute=AsyncMock(return_value=None))

        with (
            patch.object(routes_admin, "settings", settings),
            patch.dict(
                sys.modules,
                {"cache": cache_module, "worker": worker_module},
            ),
        ):
            return await routes_admin.get_system_health(admin=MagicMock(), db=db)

    @staticmethod
    async def _request_system(app):
        from core.rate_limit import RateLimitResult

        rate_limit_result = RateLimitResult(
            allowed=True,
            status="allowed",
            remaining=9,
            retry_after=0,
            limit=10,
        )
        with patch(
            "middleware.check_rate_limit_typed",
            AsyncMock(return_value=rate_limit_result),
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.get("/api/admin/system")

    async def test_registry_failure_is_unknown_not_false_negative(self):
        health = await self._get_health(self._settings(), None)

        self.assertEqual(health["schedulers"]["legacy_main"], "disabled")
        self.assertEqual(health["schedulers"]["legacy_worker_cron"], "unknown")
        self.assertEqual(health["schedulers"]["recovery"], "unknown")

    async def test_status_combines_configuration_with_actual_worker_registry(self):
        worker_module = _worker_module(cron_recovery_detector)

        health = await self._get_health(self._settings(), worker_module)

        self.assertEqual(health["followup_scheduler"], "disabled")
        self.assertEqual(health["schedulers"]["legacy_main"], "disabled")
        self.assertEqual(health["schedulers"]["legacy_worker_cron"], "not_registered")
        self.assertEqual(health["schedulers"]["recovery"], "registered_disabled")

    async def test_enabled_status_uses_arq_coroutine_registry_attribute(self):
        worker_module = _worker_module(
            cron_followup_scheduler,
            cron_recovery_detector,
        )
        settings = self._settings(
            SCHEDULER_ENABLED=True,
            ENABLE_LEGACY_PENDING_PAYMENT_FOLLOWUP=True,
            ENABLE_PAYMENT_RECOVERY=True,
        )

        health = await self._get_health(settings, worker_module)

        self.assertEqual(health["followup_scheduler"], "running")
        self.assertEqual(health["schedulers"]["legacy_main"], "enabled")
        self.assertEqual(
            health["schedulers"]["legacy_worker_cron"],
            "registered_enabled",
        )
        self.assertEqual(health["schedulers"]["recovery"], "registered_enabled")

    async def test_registered_legacy_cron_with_false_config_is_reported_unsafe(self):
        worker_module = _worker_module(cron_followup_scheduler)

        health = await self._get_health(self._settings(), worker_module)

        self.assertEqual(
            health["schedulers"]["legacy_worker_cron"],
            "registered_config_disabled_unsafe",
        )

    async def test_system_route_rejects_unauthenticated_request(self):
        import main

        response = await self._request_system(main.app)

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("schedulers", response.json())

    async def test_system_route_rejects_non_admin(self):
        import main
        from api import routes_admin
        from models.user import UserRole

        previous_overrides = dict(main.app.dependency_overrides)
        main.app.dependency_overrides[routes_admin.get_current_user] = lambda: SimpleNamespace(
            role=UserRole.SELLER
        )
        try:
            response = await self._request_system(main.app)
        finally:
            main.app.dependency_overrides.clear()
            main.app.dependency_overrides.update(previous_overrides)

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("schedulers", response.json())

    async def test_system_route_returns_scheduler_status_for_admin(self):
        import main
        from api import routes_admin
        from models.user import UserRole

        worker_module = _worker_module(cron_recovery_detector)
        cache_module = _module("cache", get_redis=AsyncMock(return_value=None))
        db = SimpleNamespace(execute=AsyncMock(return_value=None))

        previous_overrides = dict(main.app.dependency_overrides)
        main.app.dependency_overrides[routes_admin.get_current_user] = lambda: SimpleNamespace(
            role=UserRole.ADMIN
        )
        main.app.dependency_overrides[routes_admin.get_db] = lambda: db
        try:
            with (
                patch.object(routes_admin, "settings", self._settings()),
                patch.dict(
                    sys.modules,
                    {"cache": cache_module, "worker": worker_module},
                ),
            ):
                response = await self._request_system(main.app)
        finally:
            main.app.dependency_overrides.clear()
            main.app.dependency_overrides.update(previous_overrides)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["schedulers"],
            {
                "legacy_main": "disabled",
                "legacy_worker_cron": "not_registered",
                "recovery": "registered_disabled",
            },
        )


if __name__ == "__main__":
    unittest.main()
