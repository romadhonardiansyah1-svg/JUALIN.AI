"""
P1.2 — Stage-aware handler registry for durable jobs.

Each enabled job_type has an exact contract version.
Unknown handlers are quarantined as manual_required, not executable.
"""
from dataclasses import dataclass
from typing import Dict

@dataclass(frozen=True)
class JobHandlerSpec:
    job_type: str
    contract_version: int
    initial_stage: str = "pre_side_effect"
    max_attempts: int = 3
    retryable: bool = False  # P1.1 default false, explicit per spec
    description: str = ""


# Immutable enabled registry — single source of truth for worker and enqueue
ENABLED_JOB_HANDLERS: Dict[str, JobHandlerSpec] = {
    "inbox_ai_reply": JobHandlerSpec(
        job_type="inbox_ai_reply",
        contract_version=1,
        retryable=False,
        description="AI reply for inbox thread",
    ),
    "pending_payment_followup": JobHandlerSpec(
        job_type="pending_payment_followup",
        contract_version=1,
        retryable=False,  # legacy followup should not retry blindly
        description="Legacy pending payment followup (contained, should be disabled)",
    ),
    "campaign_send_message": JobHandlerSpec(
        job_type="campaign_send_message",
        contract_version=1,
        retryable=False,
        description="Single campaign message send",
    ),
    "workflow_run": JobHandlerSpec(
        job_type="workflow_run",
        contract_version=1,
        retryable=False,
        description="Workflow automation run",
    ),
    "payment_recovery_dispatch": JobHandlerSpec(
        job_type="payment_recovery_dispatch",
        contract_version=1,
        retryable=False,
        description="Payment recovery WA dispatch with revalidation",
    ),
    "payment_reconciliation": JobHandlerSpec(
        job_type="payment_reconciliation",
        contract_version=1,
        retryable=False,
        description="Payment status reconciliation from provider",
    ),
}

# For quick lookup by (job_type, contract_version)
def get_enabled_spec(job_type: str, contract_version: int | None) -> JobHandlerSpec | None:
    spec = ENABLED_JOB_HANDLERS.get(job_type)
    if not spec:
        return None
    if contract_version is None:
        return None
    if spec.contract_version != contract_version:
        return None
    return spec


def is_enabled_job_type(job_type: str) -> bool:
    return job_type in ENABLED_JOB_HANDLERS


def all_enabled_pairs():
    """Return list of (job_type, contract_version) tuples for query building."""
    return [(spec.job_type, spec.contract_version) for spec in ENABLED_JOB_HANDLERS.values()]
