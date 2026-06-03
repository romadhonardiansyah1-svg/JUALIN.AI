"""
JUALIN.AI — Orders API Routes
List, detail, update status for seller's orders
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import csv
import io

from models.database import get_db
from models.user import User
from models.order import Order, OrderStatus
from api.routes_auth import get_current_user

router = APIRouter()


class OrderUpdateRequest(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


@router.get("/")
async def list_orders(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all orders for the current seller, optionally filtered by status."""
    query = select(Order).where(Order.seller_id == current_user.id)
    
    if status:
        query = query.where(Order.status == status)
    
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
            "followup_count": o.followup_count,
            "created_at": o.created_at.isoformat() if o.created_at else "",
        }
        for o in orders
    ]


@router.get("/{order_id}")
async def get_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get order detail."""
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .where(Order.seller_id == current_user.id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")
    
    return {
        "id": order.id,
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,
        "customer_address": order.customer_address,
        "items": order.items,
        "total": order.total,
        "status": order.status.value,
        "notes": order.notes,
        "followup_count": order.followup_count,
        "last_followup_at": order.last_followup_at.isoformat() if order.last_followup_at else None,
        "created_at": order.created_at.isoformat() if order.created_at else "",
        "updated_at": order.updated_at.isoformat() if order.updated_at else "",
    }


@router.patch("/{order_id}/status")
async def update_order_status(
    order_id: int,
    req: OrderUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update order status (pending → paid → shipped → done)."""
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .where(Order.seller_id == current_user.id)
    )
    order = result.scalar_one_or_none()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order tidak ditemukan")
    
    if req.status:
        try:
            order.status = OrderStatus(req.status)
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail=f"Status tidak valid. Pilih: {', '.join(s.value for s in OrderStatus)}"
            )
    
    if req.notes is not None:
        order.notes = req.notes
    
    await db.commit()
    await db.refresh(order)
    
    return {"message": "Order diupdate", "status": order.status.value}


@router.get("/export/csv")
async def export_orders_csv(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export all orders as CSV file for download."""
    query = select(Order).where(Order.seller_id == current_user.id)

    if status:
        query = query.where(Order.status == status)

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
        "Total Order", "Status", "Follow-up", "Catatan",
    ])

    # Data rows — satu baris per item produk
    for order in orders:
        items = order.items if isinstance(order.items, list) else []
        if not items:
            # Order tanpa item detail
            writer.writerow([
                f"#{order.id}",
                order.created_at.strftime("%Y-%m-%d %H:%M") if order.created_at else "",
                order.customer_name or "",
                order.customer_phone or "",
                order.customer_address or "",
                "-", "-", "-", "-",
                f"Rp {order.total:,.0f}" if order.total else "Rp 0",
                order.status.value if hasattr(order.status, 'value') else str(order.status),
                order.followup_count or 0,
                order.notes or "",
            ])
        else:
            for i, item in enumerate(items):
                qty = item.get("qty", 1)
                harga = item.get("harga", 0)
                writer.writerow([
                    f"#{order.id}" if i == 0 else "",  # Order ID hanya di baris pertama
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
                    order.followup_count if i == 0 else "",
                    order.notes if i == 0 else "",
                ])

    # Return as downloadable CSV
    output.seek(0)
    filename = f"jualin_orders_{current_user.slug}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
