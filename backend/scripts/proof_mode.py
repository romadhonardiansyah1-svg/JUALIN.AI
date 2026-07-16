"""
CLI: python -m scripts.proof_mode run --scenario <id> --seed 42
     python -m scripts.proof_mode run-all --suite backend --seed 42 --output ../artifacts/proof-backend.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="proof_mode")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run one scenario")
    run_p.add_argument("--scenario", required=True)
    run_p.add_argument("--seed", type=int, default=42)

    all_p = sub.add_parser("run-all", help="Run backend proof suite")
    all_p.add_argument("--suite", default="backend")
    all_p.add_argument("--seed", type=int, default=42)
    all_p.add_argument("--output", default="")

    args = parser.parse_args(argv)

    # Import after path is backend cwd
    from services.payment_recovery.proof import SCENARIOS, run_all, run_scenario

    if args.command == "run":
        result = run_scenario(args.scenario, seed=args.seed)
        print(json.dumps(result.__dict__, indent=2, default=str))
        return 0 if result.status == "passed" else 1

    if args.command == "run-all":
        payload = run_all(seed=args.seed, suite=args.suite)
        text = json.dumps(payload, indent=2, default=str)
        if args.output:
            out = Path(args.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            print(f"wrote {out} status={payload['status']} commit={payload['commit_sha']}")
        else:
            print(text)
        return 0 if payload["status"] == "passed" else 1

    print(f"known scenarios: {sorted(SCENARIOS.keys())}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
