"""
Marketplace/file import endpoints.
"""
import csv
import io
import math
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.database import get_db
from models.user import User
from models.product import Product
from models.product_import import ProductImportBatch
from api.routes_auth import get_current_user

router = APIRouter()
settings = get_settings()


class ImportRequest(BaseModel):
    preview_token: str = Field(min_length=1, max_length=100)
    mode: str = Field(default="skip_duplicates", pattern="^(skip_duplicates|update_duplicates)$")


def _validate_import_row(
    row: dict,
    *,
    row_number: int,
    seen_names: set[str],
    existing_names: set[str],
) -> tuple[dict | None, list[dict]]:
    """Parse one CSV row; invalid values are never replaced with zero."""
    errors: list[dict] = []
    nama = str(row.get("nama") or row.get("name") or row.get("produk") or "").strip()
    normalized_name = nama.lower()
    if not nama:
        errors.append({"row": row_number, "field": "nama", "message": "Nama produk wajib diisi"})
    elif normalized_name in seen_names:
        errors.append({"row": row_number, "field": "nama", "message": "Duplikat nama produk di file"})
    seen_names.add(normalized_name)

    raw_harga = str(row.get("harga") or row.get("price") or "").strip()
    try:
        harga = float(raw_harga)
        if not math.isfinite(harga) or harga < 0:
            raise ValueError
    except (TypeError, ValueError):
        harga = None
        errors.append({"row": row_number, "field": "harga", "message": "Harga harus angka non-negatif"})

    raw_stok = str(row.get("stok") or row.get("stock") or "").strip()
    try:
        stok_value = float(raw_stok)
        if not math.isfinite(stok_value) or stok_value < 0 or not stok_value.is_integer():
            raise ValueError
        stok = int(stok_value)
    except (TypeError, ValueError):
        stok = None
        errors.append({"row": row_number, "field": "stok", "message": "Stok harus bilangan bulat non-negatif"})

    if errors:
        return None, errors
    return {
        "row": row_number,
        "nama": nama,
        "deskripsi": row.get("deskripsi") or row.get("description") or "",
        "harga": harga,
        "stok": stok,
        "kategori": row.get("kategori") or row.get("category") or "umum",
        "existing": normalized_name in existing_names,
        "valid": True,
    }, []


@router.post("/products/preview")
async def preview_product_import(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not settings.ENABLE_MARKETPLACE_IMPORT:
        raise HTTPException(status_code=403, detail="Marketplace import belum diaktifkan")
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="V1 hanya mendukung CSV")
    contents = await file.read()
    if len(contents) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File maksimal 2MB")

    reader = csv.DictReader(io.StringIO(contents.decode("utf-8-sig", errors="replace")))
    existing_result = await db.execute(
        select(Product.nama)
        .where(Product.seller_id == current_user.id)
        .where(Product.is_active == 1)
    )
    existing_names = {str(name or "").strip().lower() for name in existing_result.scalars().all()}
    seen_names: set[str] = set()
    rows: list[dict] = []
    errors: list[dict] = []
    for row_number, raw_row in enumerate(reader, start=2):
        parsed, row_errors = _validate_import_row(
            raw_row,
            row_number=row_number,
            seen_names=seen_names,
            existing_names=existing_names,
        )
        errors.extend(row_errors)
        if parsed is not None:
            rows.append(parsed)
        if len(rows) + len({error["row"] for error in errors}) >= 200:
            break

    token = secrets.token_urlsafe(24)
    batch = ProductImportBatch(
        seller_id=current_user.id,
        preview_token=token,
        filename=file.filename,
        rows_json=rows,
        errors_json=errors,
        status="preview",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(batch)
    await db.commit()

    return {
        "rows": rows,
        "errors": errors,
        "valid": len(errors) == 0,
        "count": len(rows),
        "preview_token": token,
    }


@router.post("/products/import")
async def execute_product_import(
    req: ImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute a validated preview exactly once."""
    if not settings.ENABLE_MARKETPLACE_IMPORT:
        raise HTTPException(status_code=403, detail="Marketplace import belum diaktifkan")

    result = await db.execute(
        select(ProductImportBatch)
        .where(ProductImportBatch.preview_token == req.preview_token)
        .where(ProductImportBatch.seller_id == current_user.id)
        .with_for_update()
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Preview tidak ditemukan atau sudah kedaluwarsa")
    if batch.status == "imported":
        raise HTTPException(status_code=400, detail="Batch ini sudah diimport sebelumnya")
    if batch.expires_at and batch.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Preview sudah kedaluwarsa, upload ulang")

    rows = [row for row in (batch.rows_json or []) if row.get("valid") is True]
    if not rows:
        raise HTTPException(status_code=400, detail="Tidak ada baris valid untuk diimport")

    from core.quota import lock_product_quota
    await lock_product_quota(db, current_user.id)

    existing_result = await db.execute(
        select(Product)
        .where(Product.seller_id == current_user.id)
        .where(Product.is_active == 1)
    )
    active_products = existing_result.scalars().all()
    existing_map = {p.nama.strip().lower(): p for p in active_products}
    new_rows = [row for row in rows if row["nama"].strip().lower() not in existing_map]

    from core.quota import get_tier_limit
    product_limit = get_tier_limit(current_user, "products")
    active_count = len(active_products)
    if product_limit >= 0 and active_count + len(new_rows) > product_limit:
        raise HTTPException(
            status_code=403,
            detail=f"Melebihi batas produk ({active_count}/{product_limit}). Upgrade tier untuk menambah kapasitas.",
        )

    inserted = updated = skipped = 0
    for row_data in rows:
        nama = row_data["nama"].strip()
        existing = existing_map.get(nama.lower())
        if existing:
            if req.mode == "update_duplicates":
                existing.harga = row_data["harga"]
                existing.stok = row_data["stok"]
                existing.deskripsi = row_data.get("deskripsi") or existing.deskripsi
                existing.kategori = row_data.get("kategori") or existing.kategori
                updated += 1
            else:
                skipped += 1
            continue

        product = Product(
            seller_id=current_user.id,
            nama=nama,
            deskripsi=row_data.get("deskripsi", ""),
            harga=row_data["harga"],
            stok=row_data["stok"],
            kategori=row_data.get("kategori", "umum"),
        )
        db.add(product)
        existing_map[nama.lower()] = product
        inserted += 1

    batch.status = "imported"
    await db.commit()

    try:
        from cache import get_redis
        redis = await get_redis()
        if redis:
            keys = await redis.keys(f"products:{current_user.id}:*")
            if keys:
                await redis.delete(*keys)
    except Exception:
        pass

    return {
        "batch_id": batch.id,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": batch.errors_json or [],
        "total_processed": inserted + updated + skipped,
    }
