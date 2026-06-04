"""
Marketplace/file import endpoints.
"""
import csv
import io
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


@router.post("/products/preview")
async def preview_product_import(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not settings.ENABLE_MARKETPLACE_IMPORT:
        raise HTTPException(status_code=403, detail="Marketplace import belum diaktifkan")
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="V1 hanya mendukung CSV")
    contents = await file.read()
    if len(contents) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File maksimal 2MB")
    text = contents.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    errors = []
    seen_names = set()
    existing_result = await db.execute(
        select(Product.nama)
        .where(Product.seller_id == current_user.id)
        .where(Product.is_active == 1)
    )
    existing_names = {str(name or "").strip().lower() for name in existing_result.scalars().all()}
    for idx, row in enumerate(reader, start=2):
        nama = (row.get("nama") or row.get("name") or row.get("produk") or "").strip()
        harga = (row.get("harga") or row.get("price") or "0").strip()
        stok = (row.get("stok") or row.get("stock") or "0").strip()
        if not nama:
            errors.append({"row": idx, "field": "nama", "message": "Nama produk wajib diisi"})
        if nama.lower() in seen_names:
            errors.append({"row": idx, "field": "nama", "message": "Duplikat nama produk di file"})
        if nama.lower() in existing_names:
            errors.append({"row": idx, "field": "nama", "message": "Nama produk sudah ada di katalog"})
        seen_names.add(nama.lower())
        try:
            harga_num = float(harga)
        except ValueError:
            harga_num = 0
            errors.append({"row": idx, "field": "harga", "message": "Harga harus angka"})
        try:
            stok_num = int(float(stok))
        except ValueError:
            stok_num = 0
            errors.append({"row": idx, "field": "stok", "message": "Stok harus angka"})
        rows.append({
            "row": idx,
            "nama": nama,
            "deskripsi": row.get("deskripsi") or row.get("description") or "",
            "harga": harga_num,
            "stok": stok_num,
            "kategori": row.get("kategori") or row.get("category") or "umum",
        })
        if len(rows) >= 200:
            break

    # Store preview batch
    token = secrets.token_urlsafe(24)
    batch = ProductImportBatch(
        seller_id=current_user.id,
        preview_token=token,
        filename=file.filename or "",
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
    """Execute a previously previewed product import."""
    if not settings.ENABLE_MARKETPLACE_IMPORT:
        raise HTTPException(status_code=403, detail="Marketplace import belum diaktifkan")

    # Load batch
    result = await db.execute(
        select(ProductImportBatch)
        .where(ProductImportBatch.preview_token == req.preview_token)
        .where(ProductImportBatch.seller_id == current_user.id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Preview tidak ditemukan atau sudah kedaluwarsa")
    if batch.status == "imported":
        raise HTTPException(status_code=400, detail="Batch ini sudah diimport sebelumnya")
    if batch.expires_at and batch.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Preview sudah kedaluwarsa, upload ulang")
    if batch.errors_json and len(batch.errors_json) > 0 and req.mode == "skip_duplicates":
        pass  # Proceed, but only insert valid rows

    rows = batch.rows_json or []
    if not rows:
        raise HTTPException(status_code=400, detail="Tidak ada data untuk diimport")

    # Check product limit
    from core.quota import get_tier_limit
    product_limit = get_tier_limit(current_user, "products")
    active_count_result = await db.execute(
        select(Product.id)
        .where(Product.seller_id == current_user.id)
        .where(Product.is_active == 1)
    )
    active_count = len(active_count_result.scalars().all())
    if product_limit >= 0 and active_count + len(rows) > product_limit:
        raise HTTPException(
            status_code=403,
            detail=f"Melebihi batas produk ({active_count}/{product_limit}). Upgrade tier untuk menambah kapasitas."
        )

    # Get existing products for duplicate handling
    existing_result = await db.execute(
        select(Product)
        .where(Product.seller_id == current_user.id)
        .where(Product.is_active == 1)
    )
    existing_map = {p.nama.strip().lower(): p for p in existing_result.scalars().all()}

    inserted = 0
    updated = 0
    skipped = 0
    errors = []

    for row_data in rows:
        nama = row_data.get("nama", "").strip()
        if not nama:
            skipped += 1
            continue

        existing = existing_map.get(nama.lower())

        if existing:
            if req.mode == "update_duplicates":
                existing.harga = row_data.get("harga", existing.harga)
                existing.stok = row_data.get("stok", existing.stok)
                existing.deskripsi = row_data.get("deskripsi") or existing.deskripsi
                existing.kategori = row_data.get("kategori") or existing.kategori
                updated += 1
            else:
                skipped += 1
        else:
            product = Product(
                seller_id=current_user.id,
                nama=nama,
                deskripsi=row_data.get("deskripsi", ""),
                harga=row_data.get("harga", 0),
                stok=row_data.get("stok", 0),
                kategori=row_data.get("kategori", "umum"),
            )
            db.add(product)
            inserted += 1

    batch.status = "imported"
    await db.commit()

    # Invalidate product cache
    try:
        from cache import get_redis
        r = await get_redis()
        if r:
            keys = await r.keys(f"products:{current_user.id}:*")
            if keys:
                await r.delete(*keys)
    except Exception:
        pass

    return {
        "batch_id": batch.id,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "total_processed": inserted + updated + skipped,
    }
