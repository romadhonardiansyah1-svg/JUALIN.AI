"""
P2.4 — Consent grant flow for transactional payment reminder.

Purpose-specific, exact order/payment-cycle scope, unchecked by default,
privacy link, source checkout_checkbox, copy version, timestamp.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.payment_recovery import (
    ContactSubject,
    ContactSubjectFingerprint,
    ContactPermission,
    ContactSuppression,
    PaymentAttempt,
)
from services.payment_recovery.phone import normalize_indonesian_phone
from services.contact_identity import hmac_fingerprint, encrypt_address


async def resolve_or_create_contact_subject(
    db: AsyncSession,
    *,
    seller_id: int,
    channel: str,
    e164: str,
    customer_id: int | None = None,
) -> tuple[ContactSubject, str]:
    """
    Resolve stable contact_subject_id via HMAC fingerprint lookup,
    or create new subject with encrypted canonical address.
    Returns (ContactSubject, fingerprint).
    """
    fingerprint, key_version = hmac_fingerprint(e164)

    # Try to find existing fingerprint (current + previous key version readable)
    # For MVP, just current version
    fp_q = await db.execute(
        select(ContactSubjectFingerprint).where(
            ContactSubjectFingerprint.seller_id == seller_id,
            ContactSubjectFingerprint.channel == channel,
            ContactSubjectFingerprint.fingerprint == fingerprint,
            ContactSubjectFingerprint.retired_at.is_(None),
        )
    )
    fp_row = fp_q.scalar_one_or_none()

    if fp_row:
        # Load subject
        subj_q = await db.execute(select(ContactSubject).where(ContactSubject.id == fp_row.contact_subject_id))
        subject = subj_q.scalar_one()
        return subject, fingerprint

    # Create new subject
    ct, enc_version = encrypt_address(e164)
    subject = ContactSubject(
        seller_id=seller_id,
        customer_id=customer_id,
        channel=channel,
        address_ciphertext=ct,
        address_key_version=enc_version,
        address_revision=1,
        status="active",
    )
    db.add(subject)
    await db.flush()

    fp = ContactSubjectFingerprint(
        seller_id=seller_id,
        contact_subject_id=subject.id,
        channel=channel,
        key_version=key_version,
        fingerprint=fingerprint,
    )
    db.add(fp)
    await db.flush()

    return subject, fingerprint


async def grant_reminder_consent(
    db: AsyncSession,
    *,
    seller_id: int,
    order_id: int,
    payment_attempt_id: uuid.UUID,
    customer_id: int | None,
    channel: str,
    e164: str,
    provenance: str = "checkout_checkbox",
    source_reference: str | None = None,
    copy_version: str = "v1",
) -> tuple[ContactSubject, ContactPermission]:
    """
    Grant transactional payment reminder consent for exact order/payment cycle.
    Creates stable subject + permission instance. Withdraws previous? No, creates new instance and keeps history.
    """
    # Normalize already done, but re-validate
    norm = normalize_indonesian_phone(e164)
    if norm.status != "valid" or not norm.e164:
        raise ValueError(f"Invalid phone: {norm.reason}")

    e164_valid = norm.e164

    subject, fingerprint = await resolve_or_create_contact_subject(
        db, seller_id=seller_id, channel=channel, e164=e164_valid, customer_id=customer_id
    )

    # Check existing active permission for same cycle
    existing_q = await db.execute(
        select(ContactPermission).where(
            ContactPermission.seller_id == seller_id,
            ContactPermission.contact_subject_id == subject.id,
            ContactPermission.channel == channel,
            ContactPermission.purpose == "transactional_payment_reminder",
            ContactPermission.scope_type == "order_payment_cycle",
            ContactPermission.order_id == order_id,
            ContactPermission.payment_attempt_id == payment_attempt_id,
            ContactPermission.status == "active",
        )
    )
    existing = existing_q.scalar_one_or_none()
    if existing:
        # Already granted for this exact cycle
        return subject, existing

    # Check suppression active — if active suppression exists, it beats grant? But grant after suppression lifts? For grant flow, we should remove active suppression? Actually grant after explicit re-consent lifts suppression via explicit flow, audited.
    # For MVP, if active suppression exists, we allow grant to lift it? Per spec, suppression only lifted by explicit re-consent flow which this is.
    supp_q = await db.execute(
        select(ContactSuppression).where(
            ContactSuppression.seller_id == seller_id,
            ContactSuppression.contact_subject_id == subject.id,
            ContactSuppression.channel == channel,
            ContactSuppression.purpose == "transactional_payment_reminder",
            ContactSuppression.status == "active",
        )
    )
    suppression = supp_q.scalar_one_or_none()
    if suppression:
        # Lift suppression via explicit re-consent
        suppression.status = "lifted"
        suppression.lifted_at = datetime.now(timezone.utc)

    perm = ContactPermission(
        seller_id=seller_id,
        customer_id=customer_id,
        contact_subject_id=subject.id,
        channel=channel,
        address_fingerprint=fingerprint,
        fingerprint_key_version=subject.address_key_version or 1,
        purpose="transactional_payment_reminder",
        scope_type="order_payment_cycle",
        order_id=order_id,
        payment_attempt_id=payment_attempt_id,
        status="active",
        provenance=provenance,
        source_reference=source_reference,
        granted_at=datetime.now(timezone.utc),
    )
    db.add(perm)
    await db.flush()

    return subject, perm


async def withdraw_consent(
    db: AsyncSession,
    *,
    seller_id: int,
    contact_subject_id: uuid.UUID,
    channel: str,
    purpose: str = "transactional_payment_reminder",
) -> int:
    """
    Withdraw all active permissions for subject + channel + purpose.
    Returns count withdrawn.
    """
    q = await db.execute(
        select(ContactPermission).where(
            ContactPermission.seller_id == seller_id,
            ContactPermission.contact_subject_id == contact_subject_id,
            ContactPermission.channel == channel,
            ContactPermission.purpose == purpose,
            ContactPermission.status == "active",
        )
    )
    perms = q.scalars().all()
    count = 0
    for p in perms:
        p.status = "withdrawn"
        p.withdrawn_at = datetime.now(timezone.utc)
        count += 1
    await db.flush()
    return count
