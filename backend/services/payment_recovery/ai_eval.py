"""
P5.4 — Offline evaluation of bounded recovery template selection.

Runs a versioned fixture dataset against the deterministic parser/validator.
Does not enqueue orphan jobs and does not call live providers.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.payment_recovery.ai_copy import (
    parse_model_selection,
    render_variant,
    select_static,
)

EVAL_DATASET_VERSION = "recovery_variant_eval_v1"
DEFAULT_DATASET = (
    Path(__file__).resolve().parents[2] / "ai" / "evals" / "recovery_variant_cases.json"
)


def load_dataset(path: Path | None = None) -> list[dict[str, Any]]:
    dataset_path = path or DEFAULT_DATASET
    with dataset_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError("dataset must be a list")
    return data


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    raw = case.get("raw_model_output", "")
    variant = parse_model_selection(raw if isinstance(raw, str) else "")
    expect_accept = bool(case.get("expect_accept"))
    accepted = variant is not None
    rendered = None
    if accepted and variant:
        rendered = render_variant(
            variant,
            {"order_ref": "ORD-EVAL", "amount_display": "Rp1.000"},
        )
        if rendered is None:
            accepted = False
            variant = None

    passed = accepted == expect_accept
    if expect_accept and case.get("expect_variant"):
        passed = passed and variant == case.get("expect_variant")

    return {
        "id": case.get("id"),
        "passed": passed,
        "accepted": accepted,
        "variant_id": variant,
        "expect_accept": expect_accept,
        "rendered_ok": rendered is not None if accepted else None,
    }


def run_recovery_variant_eval(path: Path | None = None) -> dict[str, Any]:
    cases = load_dataset(path)
    results = [evaluate_case(c) for c in cases]
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    # Static baseline always available for demo of unsafe rejection → static path
    static = select_static({"order_ref": "ORD-EVAL", "amount_display": "Rp1.000"})
    return {
        "dataset_version": EVAL_DATASET_VERSION,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": (passed / total) if total else 0.0,
        "prohibited_output_blocked": sum(
            1
            for r, c in zip(results, cases)
            if not c.get("expect_accept") and r["passed"] and not r["accepted"]
        ),
        "static_baseline_ok": static.ok,
        "results": results,
        "disclaimer": (
            "Offline deterministic eval of parser/validator only. "
            "Does not claim model superiority without human labels."
        ),
    }
