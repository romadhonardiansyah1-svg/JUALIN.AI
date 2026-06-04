"""
JUALIN.AI — Orders API Routes
List, detail, status transitions with validation, history tracking, CSV export.

Features:
- Status transition validation (enforces VALID_TRANSITIONS)
- Automatic OrderStatusHistory logging
- Stock restoration on cancellation/refund
- CSV export for bookkeeping
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
import csv
import io

from models.database import get_db
from models.user import User
from models.order import Order, OrderStatus, is_valid_transition, get_allowed_transitions, VALID_TRANSITIONS
from models.order_status_history import OrderStatusHistory
from api.routes_auth import get_current_user
from core.logging_config import get_logger
from core.exceptions import NotFoundError, OrderTransitionError, ValidationError

router = APIRouter()
logger = get_logger(__name__)


# ── Pydantic Schemas ──

class OrderUpdateRequest(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


class OrderStatusHistoryResponse(BaseModel):
    id: int
    from_status: str
    to_status: str
    changed_by: str
    note: str
    created_at: str

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════
# Helper: Record Status Change
# ══════════════════════════════════════════════════

async def _record_status_change(
    order: Order,
    from_status: str,
    to_status: str,
    changed_by: str,
    note: str,
    db: AsyncSession,
):
    """
    Record a status change in the history table.
    Always called inside an existing transaction — does NOT commit.
    """
    history = OrderStatusHistory(
        order_id=order.id,
        from_status=from_status,
        to_status=to_status,
        changed_by=changed_by,
        note=note,
    )
    db.add(history)


async def _restore_order_stock(order: Order, db: AsyncSession):
    """Restore product stock when an order is cancelled or refunded."""
    from models.product import Product

    items = order.items if isinstance(order.items, list) else []
    for item in items:
        if "product_id" in item:
            result = await db.execute(
                select(Product).where(Product.id == item["product_id"])
            )
            product = result.scalar_one_or_none()
            if product:
                product.stok += item.get("qty", 1)
                logger.info(
                    f"Stock restored: {product.nama} +{item.get('qty', 1)}",
                    extra={"product_id": product.id, "order_id": order.id},
                )


# ══════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════

@router.get("/")
async def list_orders(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all orders for the current seller, optionally filtered by status."""
    query = select(Order).where(Order.seller_id == current_user.id)

    if status:
        try:
            status_enum = OrderStatus(status)
            query = query.where(Order.status == status_enum)
        except ValueError:
            raise ValidationError(
                message=f"Status tidak valid. Pilih: {', '.join(s.value for s in OrderStatus)}",
                fields={"status": status},
            )

    query = query.order_by(Order.created_at.desc()).limit(100)

    result = await db.execute(query)
    orders = result.scalars().all()

    return [
        {
            "id": o.id,
            "customer_name": o.customer_name,
            "customer_phone": o.customer_phone,
            "customer_address": o.customer_address,
            "items": o.items,
            "total": o.total,
            "status": o.status.value,
            "notes": o.notes,
            "payment_method": o.payment_method,
            "payment_provider": o.payment_provider,
            "payment_url": o.payment_url,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            "followup_count": o.followup_count,
            "allowed_transitions": get_allowed_transitions(o.status),
            "created_at": o.created_at.isoformat() if o.created_at else "",
        }
        for o in orders
    ]


@router.get("/stats")
async def get_order_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get order count per status for the current seller."""
    counts = {}
    for status in OrderStatus:
        result = await db.execute(
            select(func.count(Order.id))
            .where(Order.seller_id == current_user.id)
            .where(Order.status == status)
        )
        counts[status.value] = result.scalar() or 0

    return counts


# BUG 17 FIX: Export route MUST come before /{order_id} to avoid path conflict
@router.get("/export/csv")
async def export_orders_csv(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export all orders as CSV file for download."""
    query = select(Order).where(Order.seller_id == current_user.id)

    if status:
        try:
            status_enum = OrderStatus(status)
            query = query.where(Order.status == status_enum)
        except ValueError:
            raise ValidationError(
                message="Status tidak valid",
                fields={"status": status},
            )

    query = query.order_by(Order.created_at.desc())

    result = await db.execute(query)
    orders = result.scalars().all()

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow([
        "Order ID", "Tanggal", "Customer", "No HP", "Alamat",
        "Produk", "Qty", "Harga Satuan", "Total Item",
        "Total Order", "Status", "Pembayaran", "Follow-up", "Catatan",
    ])

    # Data rows — satu baris per item produk
    for order in orders:
        items = order.items if isinstance(order.items, list) else []
        payment_info = f"{order.payment_provider or '-'}/{order.payment_method or '-'}"

        if not items:
            writer.writerow([
                f"#{order.id}",
                order.created_at.strftime("%Y-%m-%d %H:%M") if order.created_at else "",
                order.customer_name or "",
                order.customer_phone or "",
                order.customer_address or "",
                "-", "-", "-", "-",
                f"Rp {order.total:,.0f}" if order.total else "Rp 0",
                order.status.value if hasattr(order.status, 'value') else str(order.status),
                payment_info,
                order.followup_count or 0,
                order.notes or "",
            ])
        else:
            for i, item in enumerate(items):
                qty = item.get("qty", 1)
                harga = item.get("harga", 0)
                writer.writerow([
                    f"#{order.id}" if i == 0 else "",
                    order.created_at.strftime("%Y-%m-%d %H:%M") if order.created_at and i == 0 else "",
                    order.customer_name if i == 0 else "",
                    order.customer_phone if i == 0 else "",
                    order.customer_address if i == 0 else "",
                    item.get("nama", ""),
                    qty,
                    f"Rp {harga:,.0f}",
                    f"Rp {harga * qty:,.0f}",
                    f"Rp {order.total:,.0f}" if i == 0 else "",
                    order.status.value if hasattr(order.status, 'value') and i == 0 else ("" if i > 0 else str(order.status)),
                    payment_info if i == 0 else "",
                    order.followup_count if i == 0 else "",
                    order.notes if i == 0 else "",
                ])

    output.seek(0)
    filename = f"jualin_orders_{current_user.slug}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{order_id}")
async def get_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get order detail with allowed transitions."""
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .where(Order.seller_id == current_user.id)
    )
    order = result.scalar_one_or_none()

    if not order:
        raise NotFoundError("Order", order_id)

    return {
        "id": order.id,
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "customer_address": order.customer_address,
        "items": order.items,
        "total": order.total,
        "status": order.status.value,
        "notes": order.notes,
        "payment_method": order.payment_method,
        "payment_provider": order.payment_provider,
        "payment_url": order.payment_url,
        "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        "followup_count": order.followup_count,
        "last_followup_at": order.last_followup_at.isoformat() if order.last_followup_at else None,
        "allowed_transitions": get_allowed_transitions(order.status),
        "created_at": order.created_at.isoformat() if order.created_at else "",
        "updated_at": order.updated_at.isoformat() if order.updated_at else "",
    }


@router.get("/{order_id}/history")
async def get_order_history(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get complete status change history for an order.
    Returns chronological list of all status transitions.
    """
    # Verify order belongs to user
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .where(Order.seller_id == current_user.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise NotFoundError("Order", order_id)

    # Get history
    result = await db.execute(
        select(OrderStatusHistory)
        .where(OrderStatusHistory.order_id == order_id)
        .order_by(OrderStatusHistory.created_at.asc())
    )
    history = result.scalars().all()

    return {
        "order_id": order_id,
        "current_status": order.status.value,
        "history": [
            {
                "id": h.id,
                "from_status": h.from_status,
                "to_status": h.to_status,
                "changed_by": h.changed_by,
                "note": h.note or "",
                "created_at": h.created_at.isoformat() if h.created_at else "",
            }
            for h in history
        ],
    }


@router.patch("/{order_id}/status")
async def update_order_status(
    order_id: int,
    req: OrderUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update order status with validation.
    - Enforces valid state transitions (e.g., can't go shipped → pending)
    - Records history entry for every change
    - Restores product stock on cancellation/refund
    """
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .where(Order.seller_id == current_user.id)
    )
    order = result.scalar_one_or_none()

    if not order:
        raise NotFoundError("Order", order_id)

    if req.status:
        # Validate the new status value
        try:
            new_status = OrderStatus(req.status)
        except ValueError:
            raise ValidationError(
                message=f"Status tidak valid. Pilih: {', '.join(s.value for s in OrderStatus)}",
                fields={"status": req.status},
            )

        # Validate the transition
        if not is_valid_transition(order.status, new_status):
            raise OrderTransitionError(
                from_status=order.status.value,
                to_status=new_status.value,
            )

        old_status = order.status

        # Handle special transitions
        if new_status in (OrderStatus.CANCELLED, OrderStatus.REFUNDED):
            if old_status not in (OrderStatus.CANCELLED, OrderStatus.REFUNDED):
                await _restore_order_stock(order, db)
                logger.info(
                    f"Order #{order_id} stock restored due to {new_status.value}",
                    extra={"order_id": order_id, "new_status": new_status.value},
                )

        # Apply the status change
        order.status = new_status

        # Record the change in history
        await _record_status_change(
            order=order,
            from_status=old_status.value,
            to_status=new_status.value,
            changed_by="seller",
            note=req.notes or "",
            db=db,
        )

        logger.info(
            f"Order #{order_id}: {old_status.value} → {new_status.value}",
            extra={
                "order_id": order_id,
                "from_status": old_status.value,
                "to_status": new_status.value,
                "seller_id": current_user.id,
            },
        )

    if req.notes is not None:
        order.notes = req.notes

    await db.commit()
    await db.refresh(order)

    return {
        "message": "Order diupdate",
        "order_id": order.id,
        "status": order.status.value,
        "allowed_transitions": get_allowed_transitions(order.status),
    }
