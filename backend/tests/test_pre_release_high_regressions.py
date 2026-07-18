"""Regression coverage for confirmed Critical/High pre-release defects."""
import inspect
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response


class AuthorizationRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_template_cannot_be_duplicated_cross_tenant(self):
        from api.routes_templates import duplicate_template

        query_result = MagicMock()
        query_result.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.add = MagicMock()
        db.execute.return_value = query_result

        with self.assertRaises(HTTPException) as raised:
            await duplicate_template(7, current_user=SimpleNamespace(id=1), db=db)

        self.assertEqual(raised.exception.status_code, 404)
        statement = str(db.execute.await_args.args[0]).lower()
        self.assertIn("templates.is_public", statement)
        self.assertIn("templates.created_by", statement)
        db.commit.assert_not_awaited()

    async def test_private_template_cannot_be_installed_cross_tenant(self):
        from api.routes_templates import install_template

        query_result = MagicMock()
        query_result.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute.return_value = query_result
        with self.assertRaises(HTTPException) as raised:
            await install_template(8, current_user=SimpleNamespace(id=1), db=db)
        self.assertEqual(raised.exception.status_code, 404)
        statement = str(db.execute.await_args.args[0]).lower()
        self.assertIn("templates.is_public", statement)
        self.assertIn("templates.created_by", statement)

    def test_logout_has_no_access_token_dependency(self):
        from api.routes_auth import logout

        self.assertNotIn("current_user", inspect.signature(logout).parameters)

    async def test_logout_fails_closed_when_revocation_lookup_fails(self):
        from api.routes_auth import logout

        request = Request({
            "type": "http", "method": "POST", "path": "/api/auth/logout",
            "headers": [(b"cookie", b"jualin_refresh=refresh-token")],
            "client": ("127.0.0.1", 1234),
        })
        response = Response()
        db = AsyncMock()
        db.execute.side_effect = RuntimeError("database unavailable")

        with self.assertRaises(HTTPException) as raised:
            await logout(request=request, response=response, db=db)

        self.assertEqual(raised.exception.status_code, 503)
        db.rollback.assert_awaited_once()

    async def test_unsupported_inbox_provider_is_not_recorded_as_sent(self):
        from api.routes_inbox import ReplyRequest, reply_thread

        thread = SimpleNamespace(id=4, last_message_preview="", last_message_at=None, mode="ai")
        channel = SimpleNamespace(provider="email", config_encrypted="", external_id="x")
        contact = SimpleNamespace(phone="0812", external_id="contact")
        query_result = MagicMock()
        query_result.first.return_value = (thread, channel, contact)
        db = AsyncMock()
        db.add = MagicMock()
        db.execute.return_value = query_result

        with patch("api.routes_inbox.record_audit", new=AsyncMock()):
            with self.assertRaises(HTTPException) as raised:
                await reply_thread(
                    4, ReplyRequest(text="halo"),
                    current_user=SimpleNamespace(id=1), db=db,
                )

        self.assertEqual(raised.exception.status_code, 409)
        db.add.assert_not_called()
        db.commit.assert_not_awaited()

    def test_manual_reply_http_route_is_registered(self):
        from api.routes_inbox import router

        matching_routes = [
            route for route in router.routes
            if route.path == "/threads/{thread_id}/reply" and "POST" in route.methods
        ]

        self.assertEqual(len(matching_routes), 1)


class CapabilityRegressionTests(unittest.IsolatedAsyncioTestCase):
    def test_localhost_substring_does_not_bypass_origin_allowlist(self):
        from api.routes_public_payments import _verify_origin

        request = Request({
            "type": "http", "method": "POST", "path": "/",
            "headers": [(b"origin", b"https://localhost.evil.example")],
        })
        with self.assertRaises(HTTPException) as raised:
            _verify_origin(request)
        self.assertEqual(raised.exception.status_code, 403)

    async def test_bootstrap_capability_is_single_use(self):
        from services.payment_capability import hmac_token, verify_and_use_capability

        token = "a" * 32
        token_hmac, _ = hmac_token(token)
        cap = SimpleNamespace(
            token_hmac=token_hmac, audience="public_payment", purpose="payment_status",
            order_id=5, expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            revoked_at=None, used_at=None, is_legacy_query_token=False,
        )
        query_result = MagicMock()
        query_result.scalar_one_or_none.return_value = cap
        db = AsyncMock()
        db.execute.return_value = query_result

        first = await verify_and_use_capability(
            db, raw_token=token, expected_audience="public_payment",
            expected_order_id=5, purpose="payment_status",
        )
        second = await verify_and_use_capability(
            db, raw_token=token, expected_audience="public_payment",
            expected_order_id=5, purpose="payment_status",
        )

        self.assertIs(first, cap)
        self.assertIsNone(second)

    async def test_session_is_invalid_when_parent_capability_is_revoked(self):
        from services.payment_capability import hmac_token, verify_capability_session

        token = "s" * 32
        session_hmac, _ = hmac_token(token)
        session = SimpleNamespace(
            session_token_hmac=session_hmac, order_id=5, seller_id=1,
            payment_attempt_id="attempt", expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            revoked_at=None,
        )
        capability = SimpleNamespace(
            revoked_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            order_id=5, payment_attempt_id="attempt",
        )
        attempt = SimpleNamespace(order_id=5, seller_id=1, is_current=True)
        query_result = MagicMock()
        query_result.first.return_value = (session, capability, attempt)
        db = AsyncMock()
        db.execute.return_value = query_result

        verified = await verify_capability_session(
            db, raw_session_token=token, expected_order_id=5,
        )
        self.assertIsNone(verified)

    async def test_capability_session_cannot_create_payment_for_cancelled_order(self):
        from api.routes_public_payments import create_via_session
        from models.order import OrderStatus

        body = json.dumps({"method": "snap", "provider": "midtrans"}).encode()
        sent = False

        async def receive():
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request({
            "type": "http", "method": "POST", "path": "/",
            "headers": [
                (b"content-type", b"application/json"),
                (b"cookie", b"payment_capability_session=session-token"),
            ],
        }, receive)
        order = SimpleNamespace(id=5, status=OrderStatus.CANCELLED, payment_url=None, payment_provider=None)
        query_result = MagicMock()
        query_result.scalar_one_or_none.return_value = order
        db = AsyncMock()
        db.execute.return_value = query_result

        with (
            patch("api.routes_public_payments._rate_limit_public", new=AsyncMock()),
            patch("api.routes_public_payments.verify_capability_session", new=AsyncMock(return_value=SimpleNamespace(id=1))),
            patch("services.payments.factory.create_payment_for_order", new=AsyncMock()) as create,
        ):
            with self.assertRaises(HTTPException):
                await create_via_session(5, request, db)
        create.assert_not_awaited()


class DataIntegrityRegressionTests(unittest.IsolatedAsyncioTestCase):
    def test_draft_products_can_be_activated(self):
        from api.routes_products import ProductUpdate
        self.assertIn("is_active", ProductUpdate.model_fields)

    async def test_seller_product_list_includes_drafts(self):
        from api.routes_products import list_products

        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = []
        db = AsyncMock()
        db.execute.return_value = query_result
        with (
            patch("api.routes_products.cache_get", new=AsyncMock(return_value=None)),
            patch("api.routes_products.cache_set", new=AsyncMock()),
        ):
            await list_products(current_user=SimpleNamespace(id=8), db=db)
        statement = str(db.execute.await_args.args[0]).lower()
        where_clause = statement.split("where", 1)[1]
        self.assertNotIn("products.is_active", where_clause)

    def test_invalid_import_row_is_rejected_not_zero_filled(self):
        from api.routes_marketplace import _validate_import_row

        parsed, errors = _validate_import_row(
            {"nama": "Rusak", "harga": "not-a-number", "stok": "-2"},
            row_number=2, seen_names=set(), existing_names=set(),
        )
        self.assertIsNone(parsed)
        self.assertTrue(errors)

    async def test_import_batch_is_locked_before_one_shot_status_check(self):
        from api.routes_marketplace import ImportRequest, execute_product_import

        batch = SimpleNamespace(status="imported", expires_at=None)
        query_result = MagicMock()
        query_result.scalar_one_or_none.return_value = batch
        db = AsyncMock()
        db.execute.return_value = query_result
        with patch("api.routes_marketplace.settings.ENABLE_MARKETPLACE_IMPORT", True):
            with self.assertRaises(HTTPException):
                await execute_product_import(
                    ImportRequest(preview_token="token", mode="skip_duplicates"),
                    current_user=SimpleNamespace(id=1), db=db,
                )
        self.assertIn("FOR UPDATE", str(db.execute.await_args.args[0]).upper())

    def test_registration_accepts_referral_attribution(self):
        from api.routes_auth import RegisterRequest
        self.assertIn("referral_code", RegisterRequest.model_fields)

    async def test_product_quota_lock_serializes_on_seller_row(self):
        from core.quota import lock_product_quota

        db = AsyncMock()
        await lock_product_quota(db, seller_id=7)

        statement = str(db.execute.await_args.args[0]).upper()
        self.assertIn("USERS", statement)
        self.assertIn("FOR UPDATE", statement)

    async def test_activating_draft_at_tier_limit_is_rejected_under_row_lock(self):
        from api.routes_products import ProductUpdate, update_product

        product = SimpleNamespace(id=5, seller_id=1, is_active=0)
        product_result = MagicMock()
        product_result.scalar_one_or_none.return_value = product
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        db = AsyncMock()
        quota_lock_result = MagicMock()
        db.execute.side_effect = [quota_lock_result, product_result, count_result]
        current_user = SimpleNamespace(id=1, tier=SimpleNamespace(value="free"))

        with patch("api.routes_products.settings.PRODUCT_LIMIT_FREE", 1):
            with self.assertRaises(HTTPException) as raised:
                await update_product(
                    5, ProductUpdate(is_active=1), current_user=current_user, db=db,
                )

        self.assertEqual(raised.exception.status_code, 403)
        self.assertIn("USERS", str(db.execute.await_args_list[0].args[0]).upper())
        self.assertIn("FOR UPDATE", str(db.execute.await_args_list[0].args[0]).upper())
        self.assertIn("FOR UPDATE", str(db.execute.await_args_list[1].args[0]).upper())
        db.commit.assert_not_awaited()

    async def test_marketplace_quota_counts_duplicate_active_rows(self):
        from api.routes_marketplace import ImportRequest, execute_product_import

        batch = SimpleNamespace(
            id=9, status="preview", expires_at=None, errors_json=[],
            rows_json=[{
                "valid": True, "nama": "Produk Baru", "harga": 1000,
                "stok": 1, "deskripsi": "", "kategori": "umum",
            }],
        )
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        products_result = MagicMock()
        products_result.scalars.return_value.all.return_value = [
            SimpleNamespace(nama="Nama Sama"), SimpleNamespace(nama="Nama Sama"),
        ]
        db = AsyncMock()
        db.add = MagicMock()
        quota_lock_result = MagicMock()
        db.execute.side_effect = [batch_result, quota_lock_result, products_result]

        with (
            patch("api.routes_marketplace.settings.ENABLE_MARKETPLACE_IMPORT", True),
            patch("core.quota.get_tier_limit", return_value=2),
        ):
            with self.assertRaises(HTTPException) as raised:
                await execute_product_import(
                    ImportRequest(preview_token="token", mode="skip_duplicates"),
                    current_user=SimpleNamespace(id=1), db=db,
                )

        self.assertEqual(raised.exception.status_code, 403)
        db.commit.assert_not_awaited()

    async def test_registration_persists_referral_conversion_without_unusable_reward(self):
        import uuid
        from api import routes_auth
        from models.referral import ReferralEvent, ReferralReward

        none_result = MagicMock()
        none_result.scalar_one_or_none.return_value = None
        referral = SimpleNamespace(id=4, seller_id=9, total_conversions=0)
        referral_result = MagicMock()
        referral_result.scalar_one_or_none.return_value = referral
        db = AsyncMock()
        db.add = MagicMock()
        db.execute.side_effect = [none_result, referral_result, none_result]

        async def refresh_user(user):
            user.id = 77
        db.refresh.side_effect = refresh_user
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 1)})
        response = Response()
        user_response = routes_auth.UserResponse(
            id=77, email="new@example.com", nama_toko="Toko", slug="toko",
            tier="free", role="seller", ai_active=True, ai_style="santai", no_hp="",
        )
        with (
            patch("core.rate_limit.check_rate_limit", new=AsyncMock(return_value={"allowed": True})),
            patch.object(routes_auth, "hash_password", return_value="hash"),
            patch.object(routes_auth, "_record_auth_audit", new=AsyncMock()),
            patch.object(routes_auth, "create_session_family", new=AsyncMock(return_value=(SimpleNamespace(id=uuid.uuid4()), "refresh", "csrf"))),
            patch.object(routes_auth, "build_user_response", return_value=user_response),
        ):
            await routes_auth.register(
                routes_auth.RegisterRequest(
                    email="new@example.com", password="password-aman",
                    nama_toko="Toko", referral_code="ref-seller-1234",
                ),
                request, response, db,
            )

        added = [call.args[0] for call in db.add.call_args_list]
        self.assertTrue(any(isinstance(item, ReferralEvent) for item in added))
        self.assertFalse(any(isinstance(item, ReferralReward) for item in added))
        self.assertEqual(referral.total_conversions, 1)


    async def test_seller_status_change_locks_order_and_product_before_stock_restore(self):
        from api.routes_orders import OrderUpdateRequest, update_order_status
        from models.order import OrderStatus

        order = SimpleNamespace(
            id=12, seller_id=1, status=OrderStatus.PAID,
            items=[{"product_id": 3, "qty": 2}], notes=None,
        )
        product = SimpleNamespace(id=3, nama="Produk", stok=0)
        order_result = MagicMock()
        order_result.scalar_one_or_none.return_value = order
        history_result = MagicMock()
        history_result.scalar_one_or_none.return_value = None
        product_result = MagicMock()
        product_result.scalar_one_or_none.return_value = product
        db = AsyncMock()
        db.add = MagicMock()
        db.execute.side_effect = [order_result, history_result, product_result]

        await update_order_status(
            12, OrderUpdateRequest(status="refunded"),
            current_user=SimpleNamespace(id=1), db=db,
        )

        self.assertIn("FOR UPDATE", str(db.execute.await_args_list[0].args[0]).upper())
        self.assertIn("FOR UPDATE", str(db.execute.await_args_list[2].args[0]).upper())
        self.assertEqual(product.stok, 2)


class WorkflowRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_unimplemented_workflow_action_fails_closed(self):
        from services.workflow_runner import _execute_step

        result = await _execute_step(
            AsyncMock(), SimpleNamespace(seller_id=1),
            "low_stock_alert", {"product_id": 9},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result.get("error"), "workflow action not implemented")


class PaymentCreationRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_payment_creation_locks_and_reloads_order(self):
        from services.payments.factory import _lock_order_for_payment

        order = SimpleNamespace(id=3)
        query_result = MagicMock()
        query_result.scalar_one_or_none.return_value = order
        db = AsyncMock()
        db.execute.return_value = query_result

        locked = await _lock_order_for_payment(db, 3)

        self.assertIs(locked, order)
        self.assertIn("FOR UPDATE", str(db.execute.await_args.args[0]).upper())

    async def test_second_midtrans_payment_creation_reuses_invoice(self):
        from models.order import OrderStatus
        from services.payments.factory import create_payment_for_order

        order = SimpleNamespace(
            id=3, seller_id=1, status=OrderStatus.PENDING, total=100000,
            customer_name="Buyer", customer_phone="0812", items=[],
            payment_url=None, payment_provider=None, payment_method=None,
            payment_invoice_id=None, payment_qr_data=None, payment_va_number=None,
            payment_expires_at=None, payment_access_token_hmac=None,
        )
        locked_result = MagicMock()
        locked_result.scalar_one_or_none.return_value = order
        events = []
        db = AsyncMock()
        db.add = MagicMock()
        db.execute.return_value = locked_result

        async def commit():
            events.append("commit")

        db.commit.side_effect = commit
        gateway = SimpleNamespace(create_payment=AsyncMock(return_value=SimpleNamespace(
            success=True, method="snap", provider="midtrans", order_id="JUALIN-3",
            payment_url="https://app.sandbox.midtrans.com/pay", qr_data=None,
            token="snap-token", expires_at=None, amount=100000, error_message=None,
        )))
        attempt = SimpleNamespace(id="attempt-1")
        capability = SimpleNamespace(
            token_hmac="hmac", key_version=1, expires_at=datetime.now(timezone.utc),
        )

        async def create_capability(*_args):
            events.append("capability")
            return attempt, capability, "cap-token"

        with (
            patch("services.payments.factory.get_payment_gateway", return_value=gateway),
            patch(
                "services.payments.factory._get_or_create_payment_attempt_and_capability",
                new=AsyncMock(side_effect=create_capability),
            ),
        ):
            first = await create_payment_for_order(order, db=db)
            second = await create_payment_for_order(order, db=db)

        self.assertTrue(first["payment_created"])
        self.assertTrue(second["already_exists"])
        self.assertEqual(second["invoice_id"], "JUALIN-3")
        self.assertEqual(second["provider"], "midtrans")
        self.assertEqual(gateway.create_payment.await_count, 1)
        self.assertEqual(events, ["commit", "capability", "commit"])

    async def test_midtrans_retries_use_the_same_provider_invoice_id(self):
        from services.payments.midtrans_gateway import MidtransGateway

        gateway = object.__new__(MidtransGateway)
        gateway.snap_url = "https://snap.example"
        gateway._auth_header = "auth"
        response = MagicMock(status_code=201, text="ok")
        response.json.return_value = {
            "token": "snap-token", "redirect_url": "https://pay.example",
        }
        client = AsyncMock()
        client.post.return_value = response
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=None)

        with patch("services.payments.midtrans_gateway.httpx.AsyncClient", return_value=context):
            await gateway.create_payment(3, 100000, "Buyer", "", "0812", [])
            await gateway.create_payment(3, 100000, "Buyer", "", "0812", [])

        invoice_ids = [
            call.kwargs["json"]["transaction_details"]["order_id"]
            for call in client.post.await_args_list
        ]
        self.assertEqual(invoice_ids, ["JUALIN-3", "JUALIN-3"])

    def test_retired_provider_payload_hides_payment_instructions(self):
        from api.routes_public_payments import _payment_payload

        order = SimpleNamespace(
            id=3, status="pending", payment_provider="retired-provider", payment_method="qris",
            payment_invoice_id="LEGACY-3", payment_url="https://retired.invalid/pay",
            payment_qr_data="retired-qr", payment_va_number="retired-va",
            payment_expires_at=None, total=100000, paid_at=None,
        )

        payload = _payment_payload(order)

        self.assertFalse(payload["payment_created"])
        self.assertTrue(payload["migration_required"])
        self.assertIsNone(payload["payment_url"])
        self.assertIsNone(payload["qr_data"])
        self.assertIsNone(payload["va_number"])

    async def test_existing_invoice_without_capability_repairs_access_without_new_invoice(self):
        from models.order import OrderStatus
        from services.payments.base import PaymentStatus
        from services.payments.factory import create_payment_for_order

        order = SimpleNamespace(
            id=4, seller_id=1, status=OrderStatus.PENDING, total=100000,
            customer_name="Buyer", customer_phone="0812", items=[],
            payment_url="https://app.sandbox.midtrans.com/pay",
            payment_provider="midtrans", payment_method="snap",
            payment_invoice_id="JUALIN-4", payment_qr_data=None,
            payment_va_number=None, payment_expires_at=None,
            payment_access_token_hmac=None, payment_access_token_key_version=None,
            payment_access_token_expires_at=None,
        )
        locked_result = MagicMock()
        locked_result.scalar_one_or_none.return_value = order
        db = AsyncMock()
        db.add = MagicMock()
        db.execute.return_value = locked_result
        gateway = SimpleNamespace(
            create_payment=AsyncMock(),
            check_status=AsyncMock(return_value=SimpleNamespace(
                status=PaymentStatus.PENDING, amount=100000, verified=True,
            )),
        )
        attempt = SimpleNamespace(id="attempt-4")
        capability = SimpleNamespace(
            token_hmac="hmac", key_version=1, expires_at=datetime.now(timezone.utc),
        )

        with (
            patch("services.payments.factory.get_payment_gateway", return_value=gateway),
            patch(
                "services.payments.factory._get_or_create_payment_attempt_and_capability",
                new=AsyncMock(return_value=(attempt, capability, "repaired-token")),
            ),
        ):
            result = await create_payment_for_order(order, db=db)

        gateway.create_payment.assert_not_awaited()
        gateway.check_status.assert_awaited_once_with("JUALIN-4")
        self.assertEqual(result["capability_token"], "repaired-token")
        self.assertEqual(result["payment_attempt_id"], "attempt-4")
        self.assertEqual(order.payment_access_token_hmac, "hmac")
        db.commit.assert_awaited_once()

    async def test_existing_invoice_repair_rejects_underpayment(self):
        from core.exceptions import PaymentError
        from models.order import OrderStatus
        from services.payments.base import PaymentStatus
        from services.payments.factory import create_payment_for_order

        order = SimpleNamespace(
            id=5, seller_id=1, status=OrderStatus.PENDING, total=100000,
            customer_name="Buyer", customer_phone="0812", items=[],
            payment_url="https://app.sandbox.midtrans.com/pay",
            payment_provider="midtrans", payment_method="snap",
            payment_invoice_id="JUALIN-5", payment_qr_data=None,
            payment_va_number=None, payment_expires_at=None,
            payment_access_token_hmac=None,
        )
        locked_result = MagicMock()
        locked_result.scalar_one_or_none.return_value = order
        db = AsyncMock()
        db.execute.return_value = locked_result
        gateway = SimpleNamespace(check_status=AsyncMock(return_value=SimpleNamespace(
            status=PaymentStatus.PENDING, amount=50000, verified=True,
        )))

        with patch("services.payments.factory.get_payment_gateway", return_value=gateway):
            with self.assertRaises(PaymentError):
                await create_payment_for_order(order, db=db)

        db.commit.assert_not_awaited()


class MidtransOnlyMigrationRegressionTests(unittest.IsolatedAsyncioTestCase):
    def test_payment_requests_default_to_midtrans_snap(self):
        from api.routes_payments import CreatePaymentRequest, PublicCreatePaymentRequest

        seller_request = CreatePaymentRequest(order_id=1)
        public_request = PublicCreatePaymentRequest(order_id=1, token="public-token")

        self.assertEqual((seller_request.provider, seller_request.method), ("midtrans", "snap"))
        self.assertEqual((public_request.provider, public_request.method), ("midtrans", "snap"))

    def test_payment_requests_reject_retired_provider_and_non_snap_method(self):
        from pydantic import ValidationError as PydanticValidationError
        from api.routes_payments import CreatePaymentRequest

        with self.assertRaises(PydanticValidationError):
            CreatePaymentRequest(order_id=1, provider="retired-provider")
        with self.assertRaises(PydanticValidationError):
            CreatePaymentRequest(order_id=1, method="qris")

    def test_available_methods_expose_only_midtrans_snap(self):
        from api.routes_payments import _available_payment_methods

        with patch("api.routes_payments.settings.MIDTRANS_SERVER_KEY", "configured"):
            methods = _available_payment_methods()

        self.assertEqual(
            [(method["provider"], method["method"]) for method in methods],
            [("midtrans", "snap")],
        )

    def test_retired_provider_webhook_route_is_absent(self):
        from api.routes_webhooks import router

        routes = {(route.path, frozenset(route.methods or [])) for route in router.routes}
        self.assertNotIn(("/retired-provider", frozenset({"POST"})), routes)
        self.assertIn(("/midtrans", frozenset({"POST"})), routes)

    async def test_existing_retired_provider_invoice_is_blocked_without_network_call(self):
        from core.exceptions import PaymentError
        from models.order import OrderStatus
        from services.payments.factory import create_payment_for_order

        order = SimpleNamespace(
            id=44, seller_id=1, status=OrderStatus.PENDING, total=100000,
            customer_name="Buyer", customer_phone="0812", items=[],
            payment_url="https://retired.invalid/pay", payment_provider="retired-provider",
            payment_method="qris", payment_invoice_id="LEGACY-44",
            payment_qr_data=None, payment_va_number=None, payment_expires_at=None,
            payment_access_token_hmac="legacy-hmac",
        )
        locked_result = MagicMock()
        locked_result.scalar_one_or_none.return_value = order
        db = AsyncMock()
        db.execute.return_value = locked_result

        with patch("services.payments.factory.get_payment_gateway") as gateway_factory:
            with self.assertRaises(PaymentError) as raised:
                await create_payment_for_order(order, db=db)

        self.assertIn("tidak lagi didukung", str(raised.exception).lower())
        gateway_factory.assert_not_called()
        db.commit.assert_not_awaited()

    async def test_reconciliation_suppresses_retired_provider_without_network_call(self):
        from models.order import OrderStatus
        from services.job_handlers import handle_payment_reconciliation

        order = SimpleNamespace(
            id=45, seller_id=1, status=OrderStatus.PENDING,
            payment_provider="retired-provider", payment_invoice_id="LEGACY-45",
        )
        order_result = MagicMock()
        order_result.scalar_one_or_none.return_value = order
        db = AsyncMock()
        db.execute.return_value = order_result

        with patch("services.payments.factory.get_payment_gateway") as gateway_factory:
            result = await handle_payment_reconciliation(
                db, SimpleNamespace(payload={"order_id": 45}),
            )

        self.assertFalse(result["success"])
        self.assertTrue(result["permanent"])
        self.assertEqual(result["error_code"], "payment_provider_retired")
        gateway_factory.assert_not_called()
        db.commit.assert_not_awaited()

    async def test_capability_session_rejects_retired_provider_before_db_or_network(self):
        from api.routes_public_payments import create_via_session

        body = json.dumps({"method": "snap", "provider": "retired-provider"}).encode()
        sent = False

        async def receive():
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request({
            "type": "http", "method": "POST", "path": "/",
            "headers": [
                (b"content-type", b"application/json"),
                (b"cookie", b"payment_capability_session=session-token"),
            ],
        }, receive)
        db = AsyncMock()

        with (
            patch("api.routes_public_payments._rate_limit_public", new=AsyncMock()),
            patch(
                "api.routes_public_payments.verify_capability_session",
                new=AsyncMock(return_value=SimpleNamespace(id=1)),
            ),
            patch(
                "services.payments.factory.create_payment_for_order",
                new=AsyncMock(),
            ) as create_payment,
        ):
            with self.assertRaises(HTTPException) as raised:
                await create_via_session(45, request, db)

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(
            raised.exception.detail["error"], "payment_method_not_supported"
        )
        db.execute.assert_not_awaited()
        create_payment.assert_not_awaited()

    async def test_admin_provider_health_exposes_only_midtrans_payment(self):
        from api.routes_admin import get_provider_health

        query_result = MagicMock()
        query_result.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute.return_value = query_result

        with (
            patch("cache.get_redis", new=AsyncMock(return_value=None)),
            patch("api.routes_admin.settings.MIDTRANS_SERVER_KEY", "configured"),
        ):
            result = await get_provider_health(
                admin=SimpleNamespace(id=1),
                db=db,
            )

        self.assertEqual(result["payment"], {"midtrans": "configured"})


class AdditionalHardeningRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_reconciliation_rejects_paid_status_without_current_attempt(self):
        from models.order import OrderStatus
        from services.job_handlers import handle_payment_reconciliation
        from services.payments.base import PaymentStatus

        order = SimpleNamespace(
            id=3, seller_id=1, status=OrderStatus.PENDING,
            payment_provider="midtrans", payment_invoice_id="JUALIN-3",
            paid_at=None,
        )
        order_result = MagicMock()
        order_result.scalar_one_or_none.return_value = order
        no_attempt = MagicMock()
        no_attempt.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.add = MagicMock()
        db.execute.side_effect = [order_result, no_attempt]
        gateway = SimpleNamespace(check_status=AsyncMock(return_value=SimpleNamespace(
            status=PaymentStatus.PAID, amount=100000,
        )))

        with patch("services.payments.factory.get_payment_gateway", return_value=gateway):
            result = await handle_payment_reconciliation(
                db, SimpleNamespace(payload={"order_id": 3}),
            )

        self.assertFalse(result["success"])
        self.assertIn("payment attempt", result["error"])
        self.assertEqual(order.status, OrderStatus.PENDING)
        db.commit.assert_not_awaited()

    async def test_auto_cancel_locks_order_and_seller_scoped_product(self):
        from ai.followup import auto_cancel_expired
        from models.order import OrderStatus

        order = SimpleNamespace(
            id=8, seller_id=2, status=OrderStatus.PENDING, notes=None,
            items=[{"product_id": 4, "qty": 1}],
        )
        product = SimpleNamespace(stok=0)
        orders_result = MagicMock()
        orders_result.scalars.return_value.all.return_value = [order]
        product_result = MagicMock()
        product_result.scalar_one_or_none.return_value = product
        db = AsyncMock()
        db.execute.side_effect = [orders_result, product_result]

        count = await auto_cancel_expired(db)

        self.assertEqual(count, 1)
        order_sql = str(db.execute.await_args_list[0].args[0]).upper()
        product_sql = str(db.execute.await_args_list[1].args[0]).upper()
        self.assertIn("FOR UPDATE", order_sql)
        self.assertIn("FOR UPDATE", product_sql)
        self.assertIn("PRODUCTS.SELLER_ID", product_sql)

    def test_expired_referral_code_is_rejected_by_attribution_window(self):
        from api.routes_auth import _referral_is_expired

        referral = SimpleNamespace(
            created_at=datetime.now(timezone.utc) - timedelta(days=31),
            expiry_days=30,
        )

        self.assertTrue(_referral_is_expired(referral, datetime.now(timezone.utc)))

    async def test_reconciliation_applies_late_paid_stock_and_recovery_outcome(self):
        from decimal import Decimal
        from models.order import OrderStatus
        from services.job_handlers import handle_payment_reconciliation
        from services.payments.base import PaymentStatus

        order = SimpleNamespace(
            id=14, seller_id=2, status=OrderStatus.CANCELLED,
            payment_provider="midtrans", payment_invoice_id="JUALIN-14",
            paid_at=None, total=100000, notes="", items=[{"product_id": 5, "qty": 2}],
        )
        attempt = SimpleNamespace(
            id="attempt-14", seller_id=2, is_current=True,
            amount=Decimal("100000"),
        )
        product = SimpleNamespace(id=5, stok=2)
        order_result = MagicMock(); order_result.scalar_one_or_none.return_value = order
        attempt_result = MagicMock(); attempt_result.scalar_one_or_none.return_value = attempt
        locked_result = MagicMock(); locked_result.scalar_one_or_none.return_value = order
        product_result = MagicMock(); product_result.scalar_one_or_none.return_value = product
        db = AsyncMock(); db.add = MagicMock()
        db.execute.side_effect = [order_result, attempt_result, locked_result, product_result]
        gateway = SimpleNamespace(check_status=AsyncMock(return_value=SimpleNamespace(
            status=PaymentStatus.PAID, amount=100000, verified=True,
        )))
        outcome = AsyncMock(return_value={})

        with (
            patch("services.payments.factory.get_payment_gateway", return_value=gateway),
            patch("core.audit.record_audit", new=AsyncMock()),
            patch("services.payment_recovery.outcomes.on_verified_payment", new=outcome),
        ):
            result = await handle_payment_reconciliation(
                db, SimpleNamespace(payload={"order_id": 14}),
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["new_status"], "paid")
        self.assertEqual(product.stok, 0)
        outcome.assert_awaited_once()
        db.commit.assert_awaited_once()

    async def test_reconciliation_applies_refund_and_restores_stock(self):
        from decimal import Decimal
        from models.order import OrderStatus
        from services.job_handlers import handle_payment_reconciliation
        from services.payments.base import PaymentStatus

        order = SimpleNamespace(
            id=15, seller_id=2, status=OrderStatus.PAID,
            payment_provider="midtrans", payment_invoice_id="JUALIN-15",
            paid_at=datetime.now(timezone.utc), total=100000, notes="",
            items=[{"product_id": 5, "qty": 2}],
        )
        attempt = SimpleNamespace(
            id="attempt-15", seller_id=2, is_current=True,
            amount=Decimal("100000"),
        )
        product = SimpleNamespace(id=5, stok=0)
        order_result = MagicMock(); order_result.scalar_one_or_none.return_value = order
        attempt_result = MagicMock(); attempt_result.scalar_one_or_none.return_value = attempt
        locked_result = MagicMock(); locked_result.scalar_one_or_none.return_value = order
        history_result = MagicMock(); history_result.scalar_one_or_none.return_value = None
        product_result = MagicMock(); product_result.scalar_one_or_none.return_value = product
        db = AsyncMock(); db.add = MagicMock()
        db.execute.side_effect = [
            order_result, attempt_result, locked_result, history_result, product_result,
        ]
        gateway = SimpleNamespace(check_status=AsyncMock(return_value=SimpleNamespace(
            status=PaymentStatus.REFUNDED, amount=100000, verified=True,
        )))
        reversal = AsyncMock(return_value={})

        with (
            patch("services.payments.factory.get_payment_gateway", return_value=gateway),
            patch("core.audit.record_audit", new=AsyncMock()),
            patch("services.payment_recovery.outcomes.record_payment_reversal", new=reversal),
        ):
            result = await handle_payment_reconciliation(
                db, SimpleNamespace(payload={"order_id": 15}),
            )

        self.assertEqual(result["new_status"], "refunded")
        self.assertEqual(product.stok, 2)
        reversal.assert_awaited_once()


class ChatStreamPersistenceRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_done_is_not_emitted_when_assistant_persistence_fails(self):
        from api.routes_chat_stream import StreamChatRequest, stream_chat

        seller = SimpleNamespace(
            id=1, ai_active=True, nama_toko="Toko", no_hp="0812", ai_style="santai",
        )
        conversation = SimpleNamespace(
            id=7, customer_phone="", customer_name="Customer",
        )
        seller_result = MagicMock()
        seller_result.scalar_one_or_none.return_value = seller
        conversation_result = MagicMock()
        conversation_result.scalar_one_or_none.return_value = conversation
        history_result = MagicMock()
        history_result.scalars.return_value.all.return_value = []
        db = AsyncMock()
        db.add = MagicMock()
        db.execute.side_effect = [seller_result, conversation_result, history_result]
        db.commit.side_effect = [None, RuntimeError("database unavailable")]

        async def ai_chunks(**_kwargs):
            yield {"type": "token", "token": "Halo"}
            yield {
                "type": "done", "full_response": "Halo",
                "intent": "general", "stage": "greeting", "duration_ms": 5,
            }

        request = Request({
            "type": "http", "method": "POST", "path": "/api/chat/stream",
            "headers": [], "client": ("127.0.0.1", 1234),
        })
        with (
            patch("core.rate_limit.check_rate_limit", new=AsyncMock(return_value={"allowed": True})),
            patch("api.routes_chat_stream._check_quota_simple", new=AsyncMock(return_value=(False, 0, 50))),
            patch("api.routes_chat_stream.settings.ENABLE_AGENT_OS", False),
            patch("services.customer_memory.get_or_create_memory", new=AsyncMock(return_value=(SimpleNamespace(), False))),
            patch("services.customer_memory.format_memory_context", return_value=""),
            patch("ai.agent.get_ai_response_stream", ai_chunks),
            patch("api.routes_chat.maybe_create_order_from_ai_response", new=AsyncMock(return_value=("Halo", False))),
        ):
            response = await stream_chat(
                StreamChatRequest(message="Hai", seller_slug="toko"), request, db,
            )
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)

        transcript = "".join(chunks)
        self.assertNotIn('"type": "done"', transcript)
        self.assertIn('"type": "error"', transcript)
        db.rollback.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
