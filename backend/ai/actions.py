"""
Structured AI action contracts and safe executor.

This module is intentionally separate from the legacy text parser so the old
chat flow can remain as fallback while structured actions are rolled out.
"""
from typing import Any, Literal
import secrets

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.order import Order, OrderStatus
from models.product import Product
from models.crm import Customer, CustomerTag
from core.audit import record_audit

settings = get_settings()

SalesStage = Literal[
    "discovering",
    "recommending",
    "ready_to_order",
    "payment_pending",
    "paid",
    "post_sale",
    "handoff",
]

ActionType = Literal["create_order", "send_payment_link", "handoff", "tag_customer"]


class CreateOrderItem(BaseModel):
    product_id: int = Field(gt=0)
    qty: int = Field(gt=0, le=99)


class CreateOrderPayload(BaseModel):
    customer_name: str = Field(min_length=1, max_length=255)
    customer_phone: str = Field(default="", max_length=32)
    customer_address: str = Field(default="", max_length=2000)
    items: list[CreateOrderItem] = Field(min_length=1, max_length=50)
    conversation_id: int | None = Field(default=None, gt=0)


class SendPaymentLinkPayload(BaseModel):
    order_id: int = Field(gt=0)


class HandoffPayload(BaseModel):
    reason: str = Field(default="AI requested handoff", max_length=500)


class TagCustomerPayload(BaseModel):
    customer_id: int = Field(gt=0)
    tag: str = Field(min_length=1, max_length=100)

    @field_validator("tag")
    @classmethod
    def normalize_tag(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "-")


class AIAction(BaseModel):
    type: ActionType
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_payload(self):
        payload_model = {
            "create_order": CreateOrderPayload,
            "send_payment_link": SendPaymentLinkPayload,
            "handoff": HandoffPayload,
            "tag_customer": TagCustomerPayload,
        }[self.type]
        payload_model(**self.payload)
        return self

    def parsed_payload(self):
        payload_model = {
            "create_order": CreateOrderPayload,
            "send_payment_link": SendPaymentLinkPayload,
            "handoff": HandoffPayload,
            "tag_customer": TagCustomerPayload,
        }[self.type]
        return payload_model(**self.payload)


class AIStructuredResponse(BaseModel):
    reply: str = Field(min_length=1, max_length=4096)
    stage: SalesStage
    actions: list[AIAction] = Field(default_factory=list, max_length=5)
    confidence: float = Field(ge=0.0, le=1.0)


async def execute_ai_actions(
    *,
    seller_id: int,
    actions: list[AIAction],
    db: AsyncSession,
    actor: str = "ai",
) -> list[dict[str, Any]]:
    """Execute allowed v1 AI actions without committing the outer transaction."""
    if not settings.ENABLE_AI_ACTIONS:
        return [{"type": action.type, "success": False, "error": "AI actions disabled"} for action in actions]

    results: list[dict[str, Any]] = []
    for action in actions:
        try:
            async with db.begin_nested():
                if action.type == "create_order":
                    result = await _execute_create_order(seller_id=seller_id, payload=action.parsed_payload(), db=db, actor=actor)
                elif action.type == "send_payment_link":
                    result = await _execute_send_payment_link(seller_id=seller_id, payload=action.parsed_payload(), db=db)
                elif action.type == "handoff":
                    result = await _execute_handoff(seller_id=seller_id, payload=action.parsed_payload(), db=db, actor=actor)
                elif action.type == "tag_customer":
                    result = await _execute_tag_customer(seller_id=seller_id, payload=action.parsed_payload(), db=db, actor=actor)
                else:
                    result = {"type": action.type, "success": False, "error": "Unsupported action"}
                results.append(result)
        except Exception as exc:
            results.append({"type": action.type, "success": False, "error": str(exc)})
    return results


async def _execute_create_order(
    *,
    seller_id: int,
    payload: CreateOrderPayload,
    db: AsyncSession,
    actor: str,
) -> dict[str, Any]:
    product_ids = [item.product_id for item in payload.items]
    result = await db.execute(
        select(Product)
        .where(Product.seller_id == seller_id)
        .where(Product.id.in_(product_ids))
        .where(Product.is_active == 1)
        .with_for_update()
    )
    products = {product.id: product for product in result.scalars().all()}

    order_items = []
    total = 0.0
    for item in payload.items:
        product = products.get(item.product_id)
        if not product:
            raise ValueError(f"Produk #{item.product_id} tidak ditemukan")
        if product.stok < item.qty:
            raise ValueError(f"Stok {product.nama} tidak cukup")
        product.stok -= item.qty
        line_total = float(product.harga) * item.qty
        total += line_total
        order_items.append({
            "product_id": product.id,
            "nama": product.nama,
            "qty": item.qty,
            "harga": product.harga,
        })

    order = Order(
        seller_id=seller_id,
        conversation_id=payload.conversation_id,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        customer_address=payload.customer_address,
        items=order_items,
        total=total,
        status=OrderStatus.PENDING,
        payment_access_token=secrets.token_urlsafe(32),
    )
    db.add(order)
    await db.flush()
    payment_url = f"{settings.FRONTEND_URL.rstrip('/')}/pay/{order.id}?token={order.payment_access_token}"
    await record_audit(
        db,
        action="ai.create_order",
        entity_type="order",
        entity_id=order.id,
        seller_id=seller_id,
        actor_type=actor,
        after={"items": order_items, "total": total},
    )
    return {"type": "create_order", "success": True, "order_id": order.id, "total": total, "payment_url": payment_url}


async def _execute_send_payment_link(
    *,
    seller_id: int,
    payload: SendPaymentLinkPayload,
    db: AsyncSession,
) -> dict[str, Any]:
    result = await db.execute(select(Order).where(Order.id == payload.order_id).where(Order.seller_id == seller_id))
    order = result.scalar_one_or_none()
    if not order:
        raise ValueError("Order tidak ditemukan")
    if not order.payment_access_token:
        order.payment_access_token = secrets.token_urlsafe(32)
        await db.flush()
    return {
        "type": "send_payment_link",
        "success": True,
        "order_id": order.id,
        "payment_url": f"{settings.FRONTEND_URL.rstrip('/')}/pay/{order.id}?token={order.payment_access_token}",
    }


async def _execute_handoff(
    *,
    seller_id: int,
    payload: HandoffPayload,
    db: AsyncSession,
    actor: str,
) -> dict[str, Any]:
    await record_audit(
        db,
        action="ai.handoff",
        entity_type="inbox_thread",
        entity_id="",
        seller_id=seller_id,
        actor_type=actor,
        after={"reason": payload.reason},
    )
    return {"type": "handoff", "success": True, "reason": payload.reason}


async def _execute_tag_customer(
    *,
    seller_id: int,
    payload: TagCustomerPayload,
    db: AsyncSession,
    actor: str,
) -> dict[str, Any]:
    existing = await db.execute(
        select(CustomerTag)
        .where(CustomerTag.seller_id == seller_id)
        .where(CustomerTag.name == payload.tag)
    )
    if not existing.scalar_one_or_none():
        db.add(CustomerTag(seller_id=seller_id, name=payload.tag))

    customer_result = await db.execute(
        select(Customer)
        .where(Customer.seller_id == seller_id)
        .where(Customer.id == payload.customer_id)
        .with_for_update()
    )
    customer = customer_result.scalar_one_or_none()
    if not customer:
        raise ValueError("Customer tidak ditemukan")
    tags = list(customer.tags or [])
    already_exists = payload.tag in tags
    if not already_exists:
        tags.append(payload.tag)
        customer.tags = tags[:20]
    await db.flush()
    await record_audit(
        db,
        action="ai.tag_customer",
        entity_type="customer",
        entity_id=payload.customer_id,
        seller_id=seller_id,
        actor_type=actor,
        after={"tag": payload.tag},
    )
    return {"type": "tag_customer", "success": True, "customer_id": payload.customer_id, "tag": payload.tag, "already_exists": already_exists}
