"""P0.2 regression tests for fail-closed legacy follow-up jobs."""

import unittest
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from services.messaging.base import SendMessageResult


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one.return_value = value
    result.scalar_one_or_none.return_value = value
    return result


class FollowupJobSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from models.order import OrderStatus
        from services import job_handlers

        legacy_flag = patch.object(
            job_handlers.settings,
            "ENABLE_LEGACY_PENDING_PAYMENT_FOLLOWUP",
            True,
        )
        whatsapp_flag = patch.object(
            job_handlers.settings,
            "ENABLE_WHATSAPP",
            True,
        )
        legacy_flag.start()
        whatsapp_flag.start()
        self.addCleanup(legacy_flag.stop)
        self.addCleanup(whatsapp_flag.stop)

        self.order = SimpleNamespace(
            id=1,
            seller_id=10,
            status=OrderStatus.PENDING,
            followup_count=0,
            customer_name="Sensitive Customer Marker",
            customer_phone="+6281234567890",
            items="Item A",
            total=100000,
        )
        self.channel = SimpleNamespace(
            seller_id=10,
            type="whatsapp",
            status="active",
            external_id="phone-id",
            config_encrypted="encrypted-config",
        )
        self.job = SimpleNamespace(id=77, payload={"order_id": 1}, seller_id=10)

    @staticmethod
    def _db(order, channel=...):
        db = AsyncMock()
        results = [_scalar_result(order)]
        if channel is not ...:
            results.append(_scalar_result(channel))
        db.execute.side_effect = results
        return db

    @staticmethod
    def _provider(*, result=None, side_effect=None):
        provider = MagicMock()
        provider.send_message = AsyncMock(return_value=result, side_effect=side_effect)
        return provider

    async def _configured_call(self, db, provider, mark=None):
        from services.job_handlers import handle_pending_payment_followup

        mark = mark or AsyncMock(return_value=True)
        with (
            patch(
                "services.job_handlers.decrypt_config",
                return_value={"access_token": "token", "phone_number_id": "phone-id"},
            ),
            patch(
                "services.job_handlers.WhatsAppCloudProvider",
                return_value=provider,
            ),
            patch("ai.followup.mark_followup_sent", new=mark),
        ):
            result = await handle_pending_payment_followup(db, self.job)
        return result, mark

    async def test_provider_rejection_is_terminal_and_never_marked(self):
        provider_error = "Sensitive provider rejection payload"
        provider = self._provider(
            result=SendMessageResult(
                success=False,
                error_message=provider_error,
                raw={"error": {"code": 131047}},
                outcome="rejected",
            )
        )
        db = self._db(self.order, self.channel)
        test_logger = MagicMock()

        with patch("services.job_handlers.logger", test_logger):
            result, mark = await self._configured_call(db, provider)

        self.assertEqual(
            result,
            {
                "success": False,
                "outcome": "rejected",
                "reason": "provider_rejected",
                "error": "provider rejected",
                "error_code": "provider_rejected",
                "permanent": True,
                "retryable": False,
            },
        )
        provider.send_message.assert_awaited_once()
        mark.assert_not_awaited()
        self.assertEqual(self.order.followup_count, 0)
        db.commit.assert_not_awaited()
        self.assertNotIn(provider_error, repr(test_logger.method_calls))
        self.assertNotIn(provider_error, repr(result))

    async def test_provider_timeout_is_unknown_and_never_blind_retried(self):
        sensitive_error = "timeout after writing +6281234567890"
        provider = self._provider(side_effect=TimeoutError(sensitive_error))
        db = self._db(self.order, self.channel)
        test_logger = MagicMock()

        with patch("services.job_handlers.logger", test_logger):
            result, mark = await self._configured_call(db, provider)

        self.assertEqual(
            result,
            {
                "success": False,
                "outcome": "provider_unknown",
                "reason": "provider_unknown",
                "error": "provider outcome unknown",
                "error_code": "provider_unknown",
                "permanent": True,
                "retryable": False,
            },
        )
        mark.assert_not_awaited()
        db.commit.assert_not_awaited()
        self.assertNotIn(sensitive_error, repr(test_logger.method_calls))
        self.assertNotIn(sensitive_error, repr(result))

    async def test_unproven_false_result_is_unknown_not_rejected_or_retryable(self):
        provider = self._provider(
            result=SendMessageResult(
                success=False,
                error_message="connection reset after possible write",
            )
        )
        db = self._db(self.order, self.channel)

        result, mark = await self._configured_call(db, provider)

        self.assertEqual(result["outcome"], "provider_unknown")
        self.assertEqual(result["error_code"], "provider_unknown")
        self.assertTrue(result["permanent"])
        self.assertFalse(result["retryable"])
        mark.assert_not_awaited()
        db.commit.assert_not_awaited()

    async def test_pre_send_configuration_failure_is_classified_and_sanitized(self):
        from services.job_handlers import handle_pending_payment_followup

        sensitive_error = "decrypt failed for secret-token-value"
        db = self._db(self.order, self.channel)
        provider_type = MagicMock()
        mark = AsyncMock(return_value=True)
        test_logger = MagicMock()

        with (
            patch(
                "services.job_handlers.decrypt_config",
                side_effect=ValueError(sensitive_error),
            ),
            patch("services.job_handlers.WhatsAppCloudProvider", provider_type),
            patch("services.job_handlers.logger", test_logger),
            patch("ai.followup.mark_followup_sent", new=mark),
        ):
            result = await handle_pending_payment_followup(db, self.job)

        self.assertEqual(
            result,
            {
                "success": False,
                "outcome": "not_sent",
                "reason": "provider_configuration_unavailable",
                "error": "provider configuration unavailable",
                "error_code": "provider_configuration_unavailable",
                "permanent": True,
                "retryable": False,
            },
        )
        provider_type.assert_not_called()
        mark.assert_not_awaited()
        db.commit.assert_not_awaited()
        self.assertNotIn(sensitive_error, repr(test_logger.method_calls))
        self.assertNotIn(sensitive_error, repr(result))

    async def test_success_without_provider_message_id_is_unknown(self):
        provider = self._provider(
            result=SendMessageResult(success=True, outcome="accepted")
        )
        db = self._db(self.order, self.channel)

        result, mark = await self._configured_call(db, provider)

        self.assertEqual(result["outcome"], "provider_unknown")
        self.assertFalse(result["success"])
        self.assertFalse(result["retryable"])
        mark.assert_not_awaited()
        db.commit.assert_not_awaited()

    async def test_truthy_non_boolean_success_is_not_accepted(self):
        provider = self._provider(
            result=SendMessageResult(
                success="false",
                outcome="accepted",
                provider_message_id="wamid.malformed",
            )
        )
        db = self._db(self.order, self.channel)

        result, mark = await self._configured_call(db, provider)

        self.assertEqual(result["outcome"], "provider_unknown")
        self.assertFalse(result["success"])
        self.assertFalse(result["retryable"])
        mark.assert_not_awaited()
        db.commit.assert_not_awaited()

    async def test_only_accepted_provider_evidence_marks_tenant_scoped_order(self):
        provider = self._provider(
            result=SendMessageResult(
                success=True,
                provider_message_id="wamid.accepted",
                raw={"messages": [{"id": "wamid.accepted"}]},
                outcome="accepted",
            )
        )
        db = self._db(self.order, self.channel)

        result, mark = await self._configured_call(db, provider)

        self.assertEqual(
            result,
            {
                "success": True,
                "outcome": "accepted",
                "order_id": 1,
                "sent_via": "whatsapp",
                "provider_message_id": "wamid.accepted",
            },
        )
        mark.assert_awaited_once_with(1, 10, db)
        channel_statement = db.execute.await_args_list[1].args[0]
        channel_sql = " ".join(
            str(channel_statement.compile(compile_kwargs={"literal_binds": True}))
            .lower()
            .split()
        )
        self.assertIn("channels.seller_id = 10", channel_sql)
        self.assertIn("channels.type = 'whatsapp'", channel_sql)
        self.assertIn("channels.provider = 'whatsapp_cloud'", channel_sql)
        self.assertIn("channels.status = 'active'", channel_sql)

    async def test_accepted_result_without_persisted_evidence_is_terminal(self):
        provider = self._provider(
            result=SendMessageResult(
                success=True,
                outcome="accepted",
                provider_message_id="wamid.accepted",
            )
        )
        db = self._db(self.order, self.channel)
        mark = AsyncMock(return_value=False)

        result, mark = await self._configured_call(db, provider, mark=mark)

        self.assertEqual(result["outcome"], "accepted")
        self.assertEqual(result["error_code"], "accepted_evidence_not_persisted")
        self.assertFalse(result["success"])
        self.assertTrue(result["permanent"])
        self.assertFalse(result["retryable"])
        mark.assert_awaited_once_with(1, 10, db)

    async def test_accepted_evidence_exception_is_sanitized_and_not_retryable(self):
        provider = self._provider(
            result=SendMessageResult(
                success=True,
                outcome="accepted",
                provider_message_id="wamid.accepted",
            )
        )
        db = self._db(self.order, self.channel)
        sensitive_error = "commit failed for +6281234567890"
        mark = AsyncMock(side_effect=RuntimeError(sensitive_error))
        test_logger = MagicMock()

        with patch("services.job_handlers.logger", test_logger):
            result, mark = await self._configured_call(db, provider, mark=mark)

        self.assertEqual(result["outcome"], "accepted")
        self.assertEqual(result["error_code"], "accepted_evidence_not_persisted")
        self.assertFalse(result["success"])
        self.assertTrue(result["permanent"])
        self.assertFalse(result["retryable"])
        db.rollback.assert_awaited_once_with()
        self.assertNotIn(sensitive_error, repr(test_logger.method_calls))
        self.assertNotIn(sensitive_error, repr(result))

    async def test_no_channel_is_explicit_not_sent_and_contains_no_pii_log(self):
        from services.job_handlers import handle_pending_payment_followup

        db = self._db(self.order, None)
        provider_type = MagicMock()
        mark = AsyncMock(return_value=True)
        test_logger = MagicMock()

        with (
            patch("services.job_handlers.WhatsAppCloudProvider", provider_type),
            patch("services.job_handlers.logger", test_logger),
            patch("ai.followup.mark_followup_sent", new=mark),
        ):
            result = await handle_pending_payment_followup(db, self.job)

        self.assertEqual(
            result,
            {
                "success": False,
                "outcome": "not_sent",
                "reason": "simulated_not_sent",
                "error": "channel unavailable",
                "error_code": "channel_unavailable",
                "permanent": True,
                "retryable": False,
            },
        )
        self.assertNotIn("sent_via", result)
        provider_type.assert_not_called()
        mark.assert_not_awaited()
        db.commit.assert_not_awaited()
        self.assertNotIn(self.order.customer_name, repr(test_logger.method_calls))
        self.assertNotIn(self.order.customer_phone, repr(test_logger.method_calls))

    async def test_channel_without_explicit_token_cannot_fall_back_to_global_credentials(self):
        from services.job_handlers import handle_pending_payment_followup

        db = self._db(self.order, self.channel)
        provider_type = MagicMock()
        mark = AsyncMock(return_value=True)

        with (
            patch("services.job_handlers.decrypt_config", return_value={}),
            patch("services.job_handlers.WhatsAppCloudProvider", provider_type),
            patch("ai.followup.mark_followup_sent", new=mark),
        ):
            result = await handle_pending_payment_followup(db, self.job)

        self.assertEqual(result["outcome"], "not_sent")
        self.assertEqual(result["reason"], "simulated_not_sent")
        self.assertEqual(result["error_code"], "channel_not_configured")
        self.assertFalse(result["retryable"])
        provider_type.assert_not_called()
        mark.assert_not_awaited()
        db.commit.assert_not_awaited()

    async def test_order_lookup_sql_contains_order_and_seller_predicates(self):
        from services.job_handlers import handle_pending_payment_followup

        job = SimpleNamespace(id=78, payload={"order_id": 1}, seller_id=999)
        db = AsyncMock()

        async def execute(statement):
            compiled = str(
                statement.compile(compile_kwargs={"literal_binds": True})
            ).lower()
            normalized = " ".join(compiled.split())
            self.assertIn("orders.id = 1", normalized)
            self.assertIn("orders.seller_id = 999", normalized)
            return _scalar_result(None)

        db.execute.side_effect = execute
        provider_type = MagicMock()
        mark = AsyncMock(return_value=True)

        with (
            patch("services.job_handlers.WhatsAppCloudProvider", provider_type),
            patch("ai.followup.mark_followup_sent", new=mark),
        ):
            result = await handle_pending_payment_followup(db, job)

        self.assertEqual(result["outcome"], "suppressed")
        self.assertEqual(result["reason"], "order_not_found_or_tenant_mismatch")
        self.assertTrue(result["permanent"])
        self.assertFalse(result["retryable"])
        provider_type.assert_not_called()
        mark.assert_not_awaited()
        db.commit.assert_not_awaited()

    async def test_defense_in_depth_rejects_foreign_order_returned_by_database(self):
        from services.job_handlers import handle_pending_payment_followup

        foreign_order = SimpleNamespace(**vars(self.order))
        foreign_order.seller_id = 11
        db = self._db(foreign_order)
        provider_type = MagicMock()
        mark = AsyncMock(return_value=True)

        with (
            patch("services.job_handlers.WhatsAppCloudProvider", provider_type),
            patch("ai.followup.mark_followup_sent", new=mark),
        ):
            result = await handle_pending_payment_followup(db, self.job)

        self.assertEqual(result["outcome"], "suppressed")
        self.assertEqual(result["reason"], "cross_tenant_reference")
        self.assertFalse(result["retryable"])
        provider_type.assert_not_called()
        mark.assert_not_awaited()
        db.commit.assert_not_awaited()

    async def test_missing_and_invalid_references_are_typed_terminal_results(self):
        from services.job_handlers import handle_pending_payment_followup

        invalid_order_ids = (..., None, 0, -1, "1", True)
        for order_id in invalid_order_ids:
            with self.subTest(order_id=order_id):
                payload = {} if order_id is ... else {"order_id": order_id}
                job = SimpleNamespace(id=79, payload=payload, seller_id=10)
                db = AsyncMock()

                result = await handle_pending_payment_followup(db, job)

                self.assertEqual(
                    result,
                    {
                        "success": False,
                        "outcome": "suppressed",
                        "reason": "invalid_order_reference",
                        "error": "invalid order reference",
                        "error_code": "invalid_order_reference",
                        "permanent": True,
                        "retryable": False,
                    },
                )
                db.execute.assert_not_awaited()
                db.commit.assert_not_awaited()

        for payload in (None, [], "order_id=1"):
            with self.subTest(payload=payload):
                job = SimpleNamespace(id=80, payload=payload, seller_id=10)
                db = AsyncMock()

                result = await handle_pending_payment_followup(db, job)

                self.assertEqual(result["error_code"], "invalid_order_reference")
                self.assertTrue(result["permanent"])
                self.assertFalse(result["retryable"])
                db.execute.assert_not_awaited()
                db.commit.assert_not_awaited()

    async def test_invalid_seller_reference_is_terminal_before_database(self):
        from services.job_handlers import handle_pending_payment_followup

        for seller_id in (None, 0, -1, "10", True):
            with self.subTest(seller_id=seller_id):
                job = SimpleNamespace(
                    id=81,
                    payload={"order_id": 1},
                    seller_id=seller_id,
                )
                db = AsyncMock()

                result = await handle_pending_payment_followup(db, job)

                self.assertEqual(
                    result,
                    {
                        "success": False,
                        "outcome": "suppressed",
                        "reason": "invalid_seller_reference",
                        "error": "invalid seller reference",
                        "error_code": "invalid_seller_reference",
                        "permanent": True,
                        "retryable": False,
                    },
                )
                db.execute.assert_not_awaited()
                db.commit.assert_not_awaited()

    async def test_missing_order_is_typed_terminal_and_masked(self):
        from services.job_handlers import handle_pending_payment_followup

        db = self._db(None)

        result = await handle_pending_payment_followup(db, self.job)

        self.assertEqual(
            result,
            {
                "success": False,
                "outcome": "suppressed",
                "reason": "order_not_found_or_tenant_mismatch",
                "error": "order not found",
                "error_code": "order_not_found",
                "permanent": True,
                "retryable": False,
            },
        )
        db.commit.assert_not_awaited()

    async def test_default_disabled_flags_block_stale_direct_job_before_database(self):
        from services import job_handlers

        disabled_combinations = ((False, False), (False, True), (True, False))
        for legacy_enabled, whatsapp_enabled in disabled_combinations:
            with self.subTest(
                legacy_enabled=legacy_enabled,
                whatsapp_enabled=whatsapp_enabled,
            ):
                db = AsyncMock()
                provider_type = MagicMock()
                mark = AsyncMock(return_value=True)
                with (
                    patch.object(
                        job_handlers.settings,
                        "ENABLE_LEGACY_PENDING_PAYMENT_FOLLOWUP",
                        legacy_enabled,
                    ),
                    patch.object(
                        job_handlers.settings,
                        "ENABLE_WHATSAPP",
                        whatsapp_enabled,
                    ),
                    patch(
                        "services.job_handlers.WhatsAppCloudProvider",
                        provider_type,
                    ),
                    patch("ai.followup.mark_followup_sent", new=mark),
                ):
                    result = await job_handlers.handle_pending_payment_followup(
                        db,
                        self.job,
                    )

                self.assertEqual(
                    result,
                    {
                        "success": False,
                        "outcome": "not_sent",
                        "reason": "legacy_followup_disabled",
                        "error": "legacy followup disabled",
                        "error_code": "legacy_followup_disabled",
                        "permanent": True,
                        "retryable": False,
                    },
                )
                db.execute.assert_not_awaited()
                db.commit.assert_not_awaited()
                provider_type.assert_not_called()
                mark.assert_not_awaited()


class FollowupAcceptedEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_mark_followup_sent_query_is_tenant_scoped(self):
        from ai.followup import mark_followup_sent

        order = SimpleNamespace(followup_count=0, last_followup_at=None)
        db = AsyncMock()
        db.execute.return_value = _scalar_result(order)

        marked = await mark_followup_sent(1, 10, db)

        statement = db.execute.await_args.args[0]
        normalized = " ".join(
            str(statement.compile(compile_kwargs={"literal_binds": True}))
            .lower()
            .split()
        )
        self.assertIn("orders.id = 1", normalized)
        self.assertIn("orders.seller_id = 10", normalized)
        self.assertTrue(marked)
        self.assertEqual(order.followup_count, 1)
        db.commit.assert_awaited_once_with()

    async def test_mark_followup_sent_does_not_mutate_when_tenant_match_is_absent(self):
        from ai.followup import mark_followup_sent

        db = AsyncMock()
        db.execute.return_value = _scalar_result(None)

        marked = await mark_followup_sent(1, 999, db)

        self.assertFalse(marked)
        db.commit.assert_not_awaited()


class FollowupWorkerFinalizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_nonaccepted_outcomes_are_dead_lettered_without_retry(self):
        import worker

        cases = (
            ("rejected", "provider_rejected", "provider rejected"),
            ("provider_unknown", "provider_unknown", "provider outcome unknown"),
            (
                "accepted",
                "accepted_evidence_not_persisted",
                "accepted evidence not persisted",
            ),
        )
        claim_token = "followup-claim-token"

        for outcome, error_code, error in cases:
            with self.subTest(outcome=outcome, error_code=error_code):
                handler_result = {
                    "success": False,
                    "outcome": outcome,
                    "reason": error_code,
                    "error": error,
                    "error_code": error_code,
                    "permanent": True,
                    "retryable": False,
                }
                job = SimpleNamespace(
                    id=77,
                    job_type="pending_payment_followup",
                    attempts=1,
                    max_attempts=3,
                    claim_token=claim_token,
                )
                db = AsyncMock()
                claim_result = MagicMock()
                claim_result.fetchone.return_value = (77,)
                job_result = MagicMock()
                job_result.scalar_one.return_value = job
                fresh_result = MagicMock()
                fresh_result.scalar_one_or_none.return_value = job
                finalize_result = MagicMock()
                finalize_result.fetchone.return_value = (77,)
                db.execute.side_effect = (
                    claim_result,
                    job_result,
                    fresh_result,
                    finalize_result,
                    MagicMock(),
                )
                handler = AsyncMock(return_value=handler_result)

                @asynccontextmanager
                async def fake_session():
                    yield db

                with (
                    patch.object(worker, "async_session", fake_session),
                    patch.object(worker.uuid_module, "uuid4", return_value=claim_token),
                    patch(
                        "services.job_handlers.handle_pending_payment_followup",
                        new=handler,
                    ),
                ):
                    result = await worker.process_recorded_job({}, 77)

                self.assertEqual(result, handler_result)
                handler.assert_awaited_once_with(db, job)
                finalize_calls = [
                    call
                    for call in db.execute.await_args_list
                    if "last_error_code=:last_error_code" in str(call.args[0])
                ]
                self.assertEqual(len(finalize_calls), 1)
                finalize_params = finalize_calls[0].args[1]
                self.assertEqual(finalize_params["status"], "dead_letter")
                self.assertNotEqual(finalize_params["status"], "done")
                self.assertEqual(finalize_params["execution_stage"], "completed")
                self.assertIsNone(finalize_params["next_run_at"])
                self.assertEqual(finalize_params["last_error_code"], error_code)
                self.assertEqual(finalize_params["error_message"], error)

                retry_updates = [
                    call
                    for call in db.execute.await_args_list
                    if "SET retryable=false" in str(call.args[0])
                ]
                self.assertEqual(len(retry_updates), 1)
                self.assertEqual(retry_updates[0].args[1], {"job_id": 77})


class PaymentRecoverySendOutcomeCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def _run_dispatch(self, send_result, *, commit_side_effect=None):
        from services.payment_recovery import dispatch as dispatch_module

        dispatch_id = uuid.uuid4()
        opportunity_id = uuid.uuid4()
        contact_subject_id = uuid.uuid4()
        claim_token = uuid.uuid4()
        dispatch = SimpleNamespace(
            id=dispatch_id,
            seller_id=10,
            opportunity_id=opportunity_id,
            contact_subject_id=contact_subject_id,
            channel_id=12,
            template_code="payment-reminder-v1",
            status="pending",
            attempt_count=0,
            last_error_code=None,
            provider_message_id=None,
            accepted_at=None,
        )
        opportunity = SimpleNamespace(
            status="dispatch_pending",
            state_version=4,
            terminal_reason_code=None,
        )
        window = SimpleNamespace(status="reserved", consumed_at=None)
        channel = SimpleNamespace(
            config_encrypted="encrypted-config",
            external_id="phone-id",
        )
        job = SimpleNamespace(
            id=91,
            seller_id=10,
            payload={"dispatch_id": str(dispatch_id)},
            claim_token=claim_token,
            status="running",
            retryable=True,
            execution_stage="pre_side_effect",
            side_effect_started_at=None,
            error_message="",
        )
        provider = MagicMock()
        provider.send_message = AsyncMock(return_value=send_result)
        db = MagicMock()
        db.execute = AsyncMock(
            side_effect=(
                _scalar_result(dispatch),
                _scalar_result(window),
                _scalar_result(channel),
                _scalar_result(None),
                _scalar_result(job),
                _scalar_result(opportunity),
            )
        )
        db.commit = AsyncMock(side_effect=commit_side_effect)
        db.rollback = AsyncMock()
        transaction = MagicMock()
        transaction.__aenter__ = AsyncMock(return_value=None)
        transaction.__aexit__ = AsyncMock(return_value=None)
        db.begin = MagicMock(return_value=transaction)
        test_logger = MagicMock()

        with (
            patch.object(
                dispatch_module,
                "revalidate_before_send",
                new=AsyncMock(return_value=(True, None)),
            ),
            patch(
                "services.messaging.whatsapp_cloud.WhatsAppCloudProvider",
                return_value=provider,
            ),
            patch(
                "core.secure_config.decrypt_config",
                return_value={
                    "access_token": "tenant-token",
                    "phone_number_id": "phone-id",
                },
            ),
            patch.object(dispatch_module, "logger", test_logger),
        ):
            result = await dispatch_module.handle_payment_recovery_dispatch(db, job)

        return SimpleNamespace(
            result=result,
            dispatch=dispatch,
            opportunity=opportunity,
            window=window,
            job=job,
            provider=provider,
            logger=test_logger,
        )

    async def test_pre_send_state_failure_is_sanitized_and_never_calls_provider(self):
        sensitive_error = "commit exposed tenant-secret-value"
        state = await self._run_dispatch(
            SendMessageResult(
                success=True,
                outcome="accepted",
                provider_message_id="must-not-send",
            ),
            commit_side_effect=RuntimeError(sensitive_error),
        )

        self.assertEqual(
            state.result,
            {
                "success": False,
                "outcome": "not_sent",
                "error": "failed to persist pre-send state",
                "error_code": "pre_send_state_not_persisted",
                "permanent": True,
                "retryable": False,
            },
        )
        state.provider.send_message.assert_not_awaited()
        self.assertNotIn(sensitive_error, repr(state.result))
        self.assertNotIn(sensitive_error, repr(state.logger.method_calls))

    async def test_returned_unknown_enters_reconciliation_without_retry(self):
        sensitive_error = "timeout after write to +6281234567890"
        state = await self._run_dispatch(
            SendMessageResult(
                success=False,
                outcome="unknown",
                error_message=sensitive_error,
            )
        )

        self.assertEqual(
            state.result,
            {
                "success": False,
                "outcome": "provider_unknown",
                "error": "provider outcome unknown",
                "error_code": "provider_unknown",
                "permanent": True,
                "retryable": False,
            },
        )
        self.assertEqual(state.dispatch.status, "provider_unknown")
        self.assertEqual(state.dispatch.last_error_code, "reconciliation_required")
        self.assertEqual(state.opportunity.status, "dispatch_pending")
        self.assertEqual(state.opportunity.state_version, 4)
        self.assertIsNone(state.opportunity.terminal_reason_code)
        self.assertEqual(state.window.status, "consumed")
        self.assertEqual(state.job.status, "dead_letter")
        self.assertEqual(state.job.execution_stage, "completed")
        self.assertFalse(state.job.retryable)
        self.assertNotIn(sensitive_error, repr(state.result))
        self.assertNotIn(sensitive_error, repr(vars(state.job)))
        self.assertNotIn(sensitive_error, repr(state.logger.method_calls))

    async def test_malformed_acceptance_without_message_id_is_unknown(self):
        state = await self._run_dispatch(
            SendMessageResult(success=True, outcome="accepted")
        )

        self.assertEqual(state.result["outcome"], "provider_unknown")
        self.assertEqual(state.dispatch.status, "provider_unknown")
        self.assertEqual(state.opportunity.status, "dispatch_pending")
        self.assertEqual(state.job.status, "dead_letter")

    async def test_explicit_rejection_is_terminal_and_sanitized(self):
        sensitive_error = "provider rejected +6281234567890"
        state = await self._run_dispatch(
            SendMessageResult(
                success=False,
                outcome="rejected",
                error_message=sensitive_error,
            )
        )

        self.assertEqual(state.result["outcome"], "rejected")
        self.assertEqual(state.result["error_code"], "provider_rejected")
        self.assertTrue(state.result["permanent"])
        self.assertFalse(state.result["retryable"])
        self.assertEqual(state.dispatch.status, "failed_terminal")
        self.assertEqual(state.dispatch.last_error_code, "provider_rejected")
        self.assertEqual(state.opportunity.status, "suppressed")
        self.assertEqual(
            state.opportunity.terminal_reason_code,
            "dispatch_provider_rejected",
        )
        self.assertEqual(state.job.status, "dead_letter")
        self.assertNotIn(sensitive_error, repr(state.result))
        self.assertNotIn(sensitive_error, repr(vars(state.job)))

    async def test_proven_acceptance_requires_stable_message_id(self):
        state = await self._run_dispatch(
            SendMessageResult(
                success=True,
                outcome="accepted",
                provider_message_id="wamid.accepted",
            )
        )

        self.assertEqual(
            state.result,
            {
                "success": True,
                "outcome": "accepted",
                "provider_message_id": "wamid.accepted",
            },
        )
        self.assertEqual(state.dispatch.status, "accepted")
        self.assertEqual(state.dispatch.provider_message_id, "wamid.accepted")
        self.assertEqual(state.opportunity.status, "dispatched")
        self.assertEqual(state.opportunity.state_version, 5)
        self.assertEqual(state.job.status, "done")


class WhatsAppProviderOutcomeTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _client(*, response=None, side_effect=None):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=response, side_effect=side_effect)
        return client

    async def test_http_failure_without_authoritative_rejection_is_unknown(self):
        import httpx

        from services.messaging.whatsapp_cloud import WhatsAppCloudProvider

        response = httpx.Response(400, json={"error": {"code": 131047}})
        client = self._client(response=response)
        provider = WhatsAppCloudProvider(
            access_token="token",
            phone_number_id="phone-id",
        )

        with patch(
            "services.messaging.whatsapp_cloud.httpx.AsyncClient",
            return_value=client,
        ):
            result = await provider.send_message("+6281234567890", "message")

        self.assertIs(result.success, False)
        self.assertEqual(result.outcome, "unknown")

    async def test_ambiguous_http_statuses_are_unknown(self):
        import httpx

        from services.messaging.whatsapp_cloud import WhatsAppCloudProvider

        for status_code in (408, 500, 503):
            with self.subTest(status_code=status_code):
                response = httpx.Response(status_code, json={"error": {}})
                client = self._client(response=response)
                provider = WhatsAppCloudProvider(
                    access_token="token",
                    phone_number_id="phone-id",
                )

                with patch(
                    "services.messaging.whatsapp_cloud.httpx.AsyncClient",
                    return_value=client,
                ):
                    result = await provider.send_message(
                        "+6281234567890",
                        "message",
                    )

                self.assertIs(result.success, False)
                self.assertEqual(result.outcome, "unknown")

    async def test_transport_timeout_has_explicit_unknown_outcome(self):
        from services.messaging.whatsapp_cloud import WhatsAppCloudProvider

        client = self._client(side_effect=TimeoutError("possible write"))
        provider = WhatsAppCloudProvider(
            access_token="token",
            phone_number_id="phone-id",
        )

        with patch(
            "services.messaging.whatsapp_cloud.httpx.AsyncClient",
            return_value=client,
        ):
            result = await provider.send_message("+6281234567890", "message")

        self.assertIs(result.success, False)
        self.assertEqual(result.outcome, "unknown")

    async def test_only_2xx_with_message_id_has_accepted_outcome(self):
        import httpx

        from services.messaging.whatsapp_cloud import WhatsAppCloudProvider

        response = httpx.Response(
            200,
            json={"messages": [{"id": "wamid.accepted"}]},
        )
        client = self._client(response=response)
        provider = WhatsAppCloudProvider(
            access_token="token",
            phone_number_id="phone-id",
        )

        with patch(
            "services.messaging.whatsapp_cloud.httpx.AsyncClient",
            return_value=client,
        ):
            result = await provider.send_message("+6281234567890", "message")

        self.assertIs(result.success, True)
        self.assertEqual(result.outcome, "accepted")
        self.assertEqual(result.provider_message_id, "wamid.accepted")

    async def test_2xx_without_message_id_is_unknown_not_success(self):
        import httpx

        from services.messaging.whatsapp_cloud import WhatsAppCloudProvider

        response = httpx.Response(200, json={"messages": []})
        client = self._client(response=response)
        provider = WhatsAppCloudProvider(
            access_token="token",
            phone_number_id="phone-id",
        )

        with patch(
            "services.messaging.whatsapp_cloud.httpx.AsyncClient",
            return_value=client,
        ):
            result = await provider.send_message("+6281234567890", "message")

        self.assertIs(result.success, False)
        self.assertEqual(result.outcome, "unknown")
        self.assertEqual(result.provider_message_id, "")


if __name__ == "__main__":
    unittest.main()
