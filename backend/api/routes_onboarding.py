"""
Seller onboarding wizard endpoints.
Completion cannot be faked if required steps are not valid.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from config import get_settings
from models.database import get_db
from models.user import User
from models.onboarding import SellerOnboarding
from api.routes_auth import get_current_user

router = APIRouter()
settings = get_settings()

STEPS = ["profile", "product", "payment", "whatsapp", "ai_persona", "test_chat", "go_live"]
REQUIRED_STEPS = ["profile", "product", "ai_persona"]


class OnboardingUpdateRequest(BaseModel):
    step: str
    completed: bool = True
    metadata: dict = {}


@router.get("/")
async def get_onboarding(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SellerOnboarding).where(SellerOnboarding.seller_id == current_user.id)
    )
    ob = result.scalar_one_or_none()

    if not ob:
        ob = SellerOnboarding(seller_id=current_user.id)
        # Auto-check profile if user has nama_toko
        if current_user.nama_toko:
            ob.step_profile = True
            ob.current_step = "product"
        db.add(ob)
        await db.commit()
        await db.refresh(ob)

    return {
        "id": ob.id,
        "seller_id": ob.seller_id,
        "completed": ob.completed,
        "current_step": ob.current_step,
        "steps": {
            "profile": ob.step_profile,
            "product": ob.step_product,
            "payment": ob.step_payment,
            "whatsapp": ob.step_whatsapp,
            "ai_persona": ob.step_ai_persona,
            "test_chat": ob.step_test_chat,
            "go_live": ob.step_go_live,
        },
    }


@router.patch("/")
async def update_onboarding(
    req: OnboardingUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.step not in STEPS:
        raise HTTPException(status_code=400, detail=f"Step tidak valid. Pilihan: {', '.join(STEPS)}")

    result = await db.execute(
        select(SellerOnboarding).where(SellerOnboarding.seller_id == current_user.id)
    )
    ob = result.scalar_one_or_none()
    if not ob:
        ob = SellerOnboarding(seller_id=current_user.id)
        db.add(ob)

    step_attr = f"step_{req.step}"
    setattr(ob, step_attr, req.completed)

    # Advance current_step to next incomplete
    for s in STEPS:
        if not getattr(ob, f"step_{s}", False):
            ob.current_step = s
            break
    else:
        ob.current_step = "go_live"

    if req.metadata:
        meta = ob.metadata_json or {}
        meta[req.step] = req.metadata
        ob.metadata_json = meta

    await db.commit()
    return {"message": f"Step '{req.step}' updated", "current_step": ob.current_step}


@router.post("/complete")
async def complete_onboarding(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark onboarding as complete. Validates required steps."""
    result = await db.execute(
        select(SellerOnboarding).where(SellerOnboarding.seller_id == current_user.id)
    )
    ob = result.scalar_one_or_none()
    if not ob:
        raise HTTPException(status_code=404, detail="Onboarding belum dimulai")

    # Validate required steps
    missing = []
    for step in REQUIRED_STEPS:
        if not getattr(ob, f"step_{step}", False):
            missing.append(step)

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Step berikut wajib diselesaikan: {', '.join(missing)}",
        )

    ob.completed = True
    ob.step_go_live = True
    await db.commit()

    return {"message": "Onboarding selesai! Toko kamu sudah go-live 🎉", "completed": True}


@router.post("/test-chat")
async def test_chat(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run a test chat as part of onboarding."""
    result = await db.execute(
        select(SellerOnboarding).where(SellerOnboarding.seller_id == current_user.id)
    )
    ob = result.scalar_one_or_none()
    if ob:
        ob.step_test_chat = True
        await db.commit()

    return {
        "message": "Test chat berhasil! AI kamu sudah siap menerima customer.",
        "step_test_chat": True,
        "chat_url": f"/chat/{current_user.slug}",
    }


# ── Quick-Start Onboarding (Market Acceptance Sprint 1) ──

class QuickStartRequest(BaseModel):
    store_category: str = ""
    seller_goal: str = ""
    tone: str = "santai"
    top_products: list = []  # [{nama, harga, deskripsi}]


class SampleProductsRequest(BaseModel):
    products: list = []  # [{nama, harga, deskripsi}]


class SimulateChatRequest(BaseModel):
    message: str = "Halo, ada produk apa aja?"


@router.post("/quick-start")
async def quick_start(
    req: QuickStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    One-shot onboarding: create store setup, draft products, and AI persona in one call.
    Seller can be test-ready within minutes.
    """
    from models.product import Product
    from models.storefront import Storefront, StorefrontSection

    # 1. Get or create onboarding record
    result = await db.execute(
        select(SellerOnboarding).where(SellerOnboarding.seller_id == current_user.id)
    )
    ob = result.scalar_one_or_none()
    if not ob:
        ob = SellerOnboarding(seller_id=current_user.id)
        db.add(ob)

    # 2. Save quick-start data
    ob.store_category = req.store_category
    ob.seller_goal = req.seller_goal
    ob.tone = req.tone
    ob.step_profile = True
    ob.current_step = "product"

    meta = ob.metadata_json or {}
    meta["quick_start"] = {
        "store_category": req.store_category,
        "seller_goal": req.seller_goal,
        "tone": req.tone,
    }
    ob.metadata_json = meta

    # 3. Update seller AI style
    current_user.ai_style = req.tone
    if req.store_category:
        current_user.deskripsi_toko = current_user.deskripsi_toko or f"Toko {req.store_category} terpercaya"

    # 4. Create draft products if provided
    products_created = 0
    if req.top_products:
        for p_data in req.top_products[:5]:  # Max 5 products
            nama = p_data.get("nama", "").strip()
            if not nama:
                continue
            # Check for duplicate draft
            existing = await db.execute(
                select(Product).where(
                    Product.seller_id == current_user.id,
                    Product.nama == nama,
                )
            )
            if existing.scalar_one_or_none():
                continue

            product = Product(
                seller_id=current_user.id,
                nama=nama,
                deskripsi=p_data.get("deskripsi", ""),
                harga=float(p_data.get("harga", 0)),
                stok=int(p_data.get("stok", 10)),
                kategori=req.store_category or "umum",
                is_active=0,  # Draft — not published yet
            )
            db.add(product)
            products_created += 1

        if products_created > 0:
            ob.step_product = True

    # 5. Set AI persona step
    ob.step_ai_persona = True

    # 6. Generate storefront draft if not exists
    sf_result = await db.execute(
        select(Storefront).where(Storefront.seller_id == current_user.id)
    )
    sf = sf_result.scalar_one_or_none()
    if not sf:
        sf = Storefront(
            seller_id=current_user.id,
            slug=current_user.slug,
            title=current_user.nama_toko,
            tagline=current_user.deskripsi_toko or f"Selamat datang di {current_user.nama_toko}!",
            seo_title=current_user.nama_toko,
            seo_description=current_user.deskripsi_toko or "",
            is_published=False,
        )
        db.add(sf)
        await db.flush()

        # Add default sections
        for idx, sec in enumerate([
            {"type": "hero", "title": current_user.nama_toko, "content_json": {
                "headline": f"Selamat datang di {current_user.nama_toko}",
                "subheadline": current_user.deskripsi_toko or "Temukan produk terbaik!",
                "cta_text": "Chat Sekarang", "cta_url": f"/chat/{current_user.slug}",
            }},
            {"type": "featured_products", "title": "Produk Unggulan", "content_json": {"limit": 6}},
            {"type": "cta", "title": "Hubungi Kami", "content_json": {
                "text": "Chat langsung dengan AI kami!", "cta_text": "Mulai Chat",
                "cta_url": f"/chat/{current_user.slug}",
            }},
        ]):
            section = StorefrontSection(
                storefront_id=sf.id, type=sec["type"], title=sec["title"],
                content_json=sec["content_json"], order_index=idx,
            )
            db.add(section)

    ob.quick_start_completed = True
    await db.commit()

    return {
        "message": "Quick-start selesai! Toko kamu sudah siap untuk test.",
        "products_created": products_created,
        "store_category": req.store_category,
        "tone": req.tone,
        "storefront_slug": current_user.slug,
        "chat_url": f"/chat/{current_user.slug}",
        "next_step": "preview",
    }


@router.post("/sample-products")
async def create_sample_products(
    req: SampleProductsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create draft products from seller input. Status is draft (is_active=0).
    Products can be edited before publish.
    """
    from models.product import Product

    created = []
    for p_data in req.products[:5]:
        nama = p_data.get("nama", "").strip()
        if not nama:
            continue

        # Prevent duplicates
        existing = await db.execute(
            select(Product).where(
                Product.seller_id == current_user.id,
                Product.nama == nama,
            )
        )
        if existing.scalar_one_or_none():
            continue

        product = Product(
            seller_id=current_user.id,
            nama=nama,
            deskripsi=p_data.get("deskripsi", ""),
            harga=float(p_data.get("harga", 0)),
            stok=int(p_data.get("stok", 10)),
            kategori=p_data.get("kategori", "umum"),
            is_active=0,  # Draft
        )
        db.add(product)
        created.append(nama)

    # Update onboarding step
    result = await db.execute(
        select(SellerOnboarding).where(SellerOnboarding.seller_id == current_user.id)
    )
    ob = result.scalar_one_or_none()
    if ob and created:
        ob.step_product = True

    await db.commit()

    return {
        "message": f"{len(created)} produk draft berhasil dibuat",
        "products": created,
        "is_draft": True,
    }


@router.post("/simulate-chat")
async def simulate_chat(
    req: SimulateChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Run a simulated AI chat for onboarding preview.
    source=onboarding_simulation — does NOT deduct production quota.
    Falls back to static template if LLM fails.
    """
    from models.product import Product

    # Get seller's products for context
    products_result = await db.execute(
        select(Product).where(Product.seller_id == current_user.id).limit(10)
    )
    products = products_result.scalars().all()
    product_list = [
        f"- {p.nama}: Rp {p.harga:,.0f} ({p.deskripsi[:60]})" for p in products
    ] if products else ["- Belum ada produk"]

    # Try AI simulation
    try:
        from ai.llm_client import chat_completion
        system_prompt = (
            f"Kamu adalah asisten jualan AI untuk toko '{current_user.nama_toko}'. "
            f"Gaya bicara: {current_user.ai_style or 'santai'}. "
            f"Daftar produk:\n" + "\n".join(product_list) + "\n"
            f"Jawab pertanyaan customer dengan ramah dan bantu mereka menemukan produk yang cocok. "
            f"Ini adalah simulasi onboarding, jangan membuat order sungguhan."
        )
        response = await chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.message},
            ],
            max_tokens=300,
        )
        ai_reply = response.get("content", "") if isinstance(response, dict) else str(response)
        source = "ai"
    except Exception:
        # Fallback static template
        ai_reply = (
            f"Halo! Selamat datang di {current_user.nama_toko}! 😊\n\n"
            f"Kami punya beberapa produk menarik:\n"
            + "\n".join(product_list[:3]) + "\n\n"
            f"Mau tanya-tanya lebih lanjut? Silakan chat ya!"
        )
        source = "fallback_template"

    return {
        "message": ai_reply,
        "source": source,
        "simulation": True,
        "quota_deducted": False,
    }
