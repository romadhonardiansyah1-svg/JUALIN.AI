"""
Workflow automation runner.

Matches active automation rules to entities and creates idempotent runs.
"""
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from core.logging_config import get_logger
from core.idempotency import enqueue_job_record
from models.workflow import AutomationRule, AutomationRun, AutomationRunStep
from models.order import Order, OrderStatus
from models.product import Product
from models.crm import Customer

settings = get_settings()
logger = get_logger(__name__)


def _period_key(template_key: str, entity_id: int) -> str:
    """Generate deterministic period key to prevent duplicate runs."""
    now = datetime.now(timezone.utc)
    if template_key == "pending_payment_2h":
        return now.strftime("%Y-%m-%dT%H")  # hourly bucket
    elif template_key in ("low_stock_alert", "repeat_buyer_bundle"):
        return now.strftime("%Y-%m-%d")  # daily bucket
    elif template_key == "paid_processing_message":
        return str(entity_id)  # once per entity
    return now.strftime("%Y-%m-%dT%H")


async def tick_workflows(db: AsyncSession):
    """
    Main workflow tick: iterate active rules, match entities, create runs.
    Called by the worker cron every 5 minutes.
    """
    result = await db.execute(
        select(AutomationRule)
        .where(AutomationRule.status == "active")
    )
    rules = result.scalars().all()

    for rule in rules:
        try:
            await _process_rule(db, rule)
        except Exception as e:
            logger.error(f"Workflow rule {rule.id} error: {e}", exc_info=True)

    await db.commit()


async def _process_rule(db: AsyncSession, rule: AutomationRule):
    """Find matching entities for a rule and create runs."""
    if rule.template_key == "pending_payment_2h":
        await _match_pending_payment(db, rule)
    elif rule.template_key == "low_stock_alert":
        await _match_low_stock(db, rule)
    elif rule.template_key == "repeat_buyer_bundle":
        await _match_repeat_buyer(db, rule)
    elif rule.template_key == "paid_processing_message":
        await _match_paid_processing(db, rule)


async def _match_pending_payment(db: AsyncSession, rule: AutomationRule):
    """Orders pending for more than 2 hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    result = await db.execute(
        select(Order)
        .where(Order.seller_id == rule.seller_id)
        .where(Order.status == OrderStatus.PENDING)
        .where(Order.created_at < cutoff)
        .limit(50)
    )
    for order in result.scalars().all():
        key = f"workflow:{rule.id}:order:{order.id}:{_period_key(rule.template_key, order.id)}"
        await _create_run_if_new(db, rule, key, "order", order.id, {"order_id": order.id})


async def _match_low_stock(db: AsyncSession, rule: AutomationRule):
    """Products with stock below 3."""
    result = await db.execute(
        select(Product)
        .where(Product.seller_id == rule.seller_id)
        .where(Product.is_active == 1)
        .where(Product.stok < 3)
        .where(Product.stok > 0)
        .limit(50)
    )
    for product in result.scalars().all():
        key = f"workflow:{rule.id}:product:{product.id}:{_period_key(rule.template_key, product.id)}"
        await _create_run_if_new(db, rule, key, "product", product.id, {"product_id": product.id, "stok": product.stok})


async def _match_repeat_buyer(db: AsyncSession, rule: AutomationRule):
    """Customers with 2+ orders."""
    result = await db.execute(
        select(Customer)
        .where(Customer.seller_id == rule.seller_id)
        .where(Customer.total_orders >= 2)
        .limit(50)
    )
    for customer in result.scalars().all():
        key = f"workflow:{rule.id}:customer:{customer.id}:{_period_key(rule.template_key, customer.id)}"
        await _create_run_if_new(db, rule, key, "customer", customer.id, {"customer_id": customer.id})


async def _match_paid_processing(db: AsyncSession, rule: AutomationRule):
    """Orders with status = paid (recently)."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    result = await db.execute(
        select(Order)
        .where(Order.seller_id == rule.seller_id)
        .where(Order.status == OrderStatus.PAID)
        .where(Order.updated_at > cutoff)
        .limit(50)
    )
    for order in result.scalars().all():
        key = f"workflow:{rule.id}:order:{order.id}:{_period_key(rule.template_key, order.id)}"
        await _create_run_if_new(db, rule, key, "order", order.id, {"order_id": order.id})


async def _create_run_if_new(
    db: AsyncSession,
    rule: AutomationRule,
    idempotency_key: str,
    entity_type: str,
    entity_id: int,
    context: dict,
):
    """Create an automation run if one doesn't already exist for this key."""
    existing = await db.execute(
        select(AutomationRun).where(AutomationRun.idempotency_key == idempotency_key)
    )
    if existing.scalar_one_or_none():
        return

    run = AutomationRun(
        seller_id=rule.seller_id,
        rule_id=rule.id,
        idempotency_key=idempotency_key,
        status="queued",
        context_json={
            "entity_type": entity_type,
            "entity_id": entity_id,
            "template_key": rule.template_key,
            **context,
        },
    )
    db.add(run)
    await db.flush()

    # Enqueue as background job
    await enqueue_job_record(
        db,
        job_type="workflow_run",
        seller_id=rule.seller_id,
        payload={"run_id": run.id},
        idempotency_key=f"workflow_run:{run.id}",
    )


async def execute_workflow_run(db: AsyncSession, run_id: int) -> dict:
    """Execute a workflow run (called by worker handler)."""
    result = await db.execute(select(AutomationRun).where(AutomationRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        return {"success": False, "error": "run not found"}

    if run.status == "done":
        return {"success": True, "skipped": True}

    run.status = "running"
    await db.flush()

    ctx = run.context_json or {}
    template_key = ctx.get("template_key", "")

    try:
        step_result = await _execute_step(db, run, template_key, ctx)

        step = AutomationRunStep(
            run_id=run.id,
            step_type=template_key,
            status="ok" if step_result.get("success") else "error",
            input_json=ctx,
            output_json=step_result,
            error_message=step_result.get("error", ""),
        )
        db.add(step)

        run.status = "done" if step_result.get("success") else "failed"
        run.error_message = step_result.get("error", "")
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()

        return step_result

    except Exception as e:
        run.status = "failed"
        run.error_message = str(e)
        run.finished_at = datetime.now(timezone.utc)

        step = AutomationRunStep(
            run_id=run.id,
            step_type=template_key,
            status="error",
            input_json=ctx,
            error_message=str(e),
        )
        db.add(step)
        await db.commit()
        return {"success": False, "error": str(e)}


async def _execute_step(db: AsyncSession, run: AutomationRun, template_key: str, ctx: dict) -> dict:
    """Execute a single workflow step based on template_key."""

    if template_key == "pending_payment_2h":
        order_id = ctx.get("order_id")
        if not order_id:
            return {"success": False, "error": "missing order_id"}
        order_result = await db.execute(select(Order).where(Order.id == order_id))
        order = order_result.scalar_one_or_none()
        if not order or order.status != OrderStatus.PENDING:
            return {"success": True, "skipped": True, "reason": "order not pending"}
        logger.info(f"Workflow: payment follow-up for order #{order_id}", extra={"seller_id": run.seller_id})
        return {"success": True, "action": "payment_followup", "order_id": order_id}

    elif template_key == "low_stock_alert":
        product_id = ctx.get("product_id")
        logger.info(f"Workflow: low stock alert for product #{product_id}", extra={"seller_id": run.seller_id})
        return {"success": True, "action": "low_stock_notified", "product_id": product_id}

    elif template_key == "repeat_buyer_bundle":
        customer_id = ctx.get("customer_id")
        logger.info(f"Workflow: repeat buyer bundle for customer #{customer_id}", extra={"seller_id": run.seller_id})
        return {"success": True, "action": "bundle_suggested", "customer_id": customer_id}

    elif template_key == "paid_processing_message":
        order_id = ctx.get("order_id")
        logger.info(f"Workflow: paid processing message for order #{order_id}", extra={"seller_id": run.seller_id})
        return {"success": True, "action": "paid_message_sent", "order_id": order_id}

    return {"success": False, "error": f"unknown template: {template_key}"}


async def dry_run_workflow(db: AsyncSession, rule: AutomationRule) -> list[dict]:
    """
    Simulate a workflow rule — match entities but don't create runs or execute.
    Returns list of matched entities.
    """
    matched = []

    if rule.template_key == "pending_payment_2h":
        params = rule.action_json.get("params", {}) if rule.action_json else {}
        delay_hours = params.get("delay_hours", 2)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=delay_hours)
        result = await db.execute(
            select(Order)
            .where(Order.seller_id == rule.seller_id, Order.status == OrderStatus.PENDING, Order.created_at < cutoff)
            .limit(50)
        )
        for order in result.scalars().all():
            matched.append({"entity_type": "order", "entity_id": order.id, "detail": f"Order #{order.id} pending since {order.created_at}"})

    elif rule.template_key == "low_stock_alert":
        params = rule.action_json.get("params", {}) if rule.action_json else {}
        threshold = params.get("stock_threshold", 3)
        result = await db.execute(
            select(Product)
            .where(Product.seller_id == rule.seller_id, Product.is_active == 1, Product.stok < threshold, Product.stok > 0)
            .limit(50)
        )
        for product in result.scalars().all():
            matched.append({"entity_type": "product", "entity_id": product.id, "detail": f"{product.nama} (stok: {product.stok})"})

    elif rule.template_key == "repeat_buyer_bundle":
        result = await db.execute(
            select(Customer)
            .where(Customer.seller_id == rule.seller_id, Customer.total_orders >= 2)
            .limit(50)
        )
        for customer in result.scalars().all():
            matched.append({"entity_type": "customer", "entity_id": customer.id, "detail": f"{customer.name} ({customer.total_orders} orders)"})

    elif rule.template_key == "paid_processing_message":
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        result = await db.execute(
            select(Order)
            .where(Order.seller_id == rule.seller_id, Order.status == OrderStatus.PAID, Order.updated_at > cutoff)
            .limit(50)
        )
        for order in result.scalars().all():
            matched.append({"entity_type": "order", "entity_id": order.id, "detail": f"Order #{order.id} paid"})

    return matched
