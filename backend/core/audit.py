"""
Audit log helper for sensitive platform actions.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from models.scale_core import AuditLog


async def record_audit(
    db: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: str | int = "",
    seller_id: int | None = None,
    actor_user_id: int | None = None,
    actor_type: str = "system",
    before: dict | None = None,
    after: dict | None = None,
    metadata: dict | None = None,
    request_id: str = "",
) -> AuditLog:
    log = AuditLog(
        seller_id=seller_id,
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id or ""),
        before=before or {},
        after=after or {},
        metadata_json=metadata or {},
        request_id=request_id,
    )
    db.add(log)
    return log
