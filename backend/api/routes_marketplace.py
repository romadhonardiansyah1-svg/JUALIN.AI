"""
Marketplace/file import endpoints.
"""
import csv
import io
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.database import get_db
from models.user import User
from models.product import Product
from api.routes_auth import get_current_user

router = APIRouter()
settings = get_settings()


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
    return {"rows": rows, "errors": errors, "valid": len(errors) == 0, "count": len(rows)}
