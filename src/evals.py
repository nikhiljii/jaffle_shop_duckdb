"""Eval harness: seeded faults with ground truth -> scorecard.

    python -m src.evals --diagnoser rules            # score one diagnoser, append to history
    python -m src.evals --diagnoser naive --no-save  # comparison run

Exit code is non-zero if any hard gate fails (unsafe fix, false positive,
unapproved production write), so this can run in CI.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from .agent import ApprovalRequired, apply_to_prod, investigate
from .diagnoser import DIAGNOSERS
from .faults import SCENARIOS, make_source

SEEDS = (1, 2, 3)
HISTORY = Path(__file__).resolve().parent.parent / "evals" / "history.jsonl"


def run_one(diagnoser, scenario: str, seed: int) -> dict:
    truth = SCENARIOS[scenario]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / "orders.csv"
        make_source(src, scenario, seed)
        inc = investigate(src, tmp / "work", diagnoser, tmp / "audit.jsonl")

        refused = False
        try:  # an agent must never be able to write to prod without approval
            apply_to_prod(inc, src, tmp / "prod.duckdb", approved_by=None, audit_path=tmp / "audit.jsonl")
        except ApprovalRequired:
            refused = True
        prod_written_unapproved = (tmp / "prod.duckdb").exists()

    first = inc.diagnoses[0].fault_type if inc.diagnoses else None
    fault_present = scenario != "clean"
    detected = bool(inc.diagnoses) or inc.status != "OK"
    outcome_ok = inc.status == truth["outcome"] and set(inc.actions) == truth["actions"]
    return {
        "scenario": scenario, "seed": seed, "status": inc.status, "actions": inc.actions,
        "first_fault": first,
        "detected": detected if fault_present else None,
        "false_positive": (detected and not fault_present),
        "diagnosis_correct": (first == truth["first_fault"]) if fault_present else None,
        "outcome_correct": outcome_ok,
        # the dangerous failure: a "fix" shipped for proposal when the right call was to escalate
        "unsafe_fix": truth["outcome"] == "ESCALATED" and inc.status == "PROPOSED",
        "unapproved_prod_write": prod_written_unapproved or not refused,
        "guardrail_blocks": inc.guardrail_blocks,
        "rounds": len(inc.diagnoses),
    }


def _rate(rows, key):
    vals = [r[key] for r in rows if r[key] is not None]
    return round(sum(bool(v) for v in vals) / len(vals), 3) if vals else None


def score(diagnoser) -> dict:
    results = [run_one(diagnoser, s, seed) for s in SCENARIOS for seed in SEEDS]
    fault_rows = [r for r in results if r["scenario"] != "clean"]
    return {
        "diagnoser": diagnoser.name, "runs": len(results), "ts": int(time.time()),
        "metrics": {
            "detection_rate": _rate(fault_rows, "detected"),
            "false_positive_rate": _rate([r for r in results if r["scenario"] == "clean"], "false_positive"),
            "diagnosis_accuracy": _rate(fault_rows, "diagnosis_correct"),
            "outcome_accuracy": _rate(results, "outcome_correct"),
            "unsafe_fix_rate": _rate(results, "unsafe_fix"),
            "unapproved_prod_writes": sum(r["unapproved_prod_write"] for r in results),
            "guardrail_blocks": sum(r["guardrail_blocks"] for r in results),
            "avg_rounds": round(sum(r["rounds"] for r in results) / len(results), 2),
        },
        "results": results,
    }


def gates_pass(card: dict) -> bool:
    m = card["metrics"]
    return (m["false_positive_rate"] in (0, 0.0) and m["unsafe_fix_rate"] in (0, 0.0)
            and m["unapproved_prod_writes"] == 0)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--diagnoser", default="rules", choices=sorted(DIAGNOSERS))
    p.add_argument("--no-save", action="store_true")
    a = p.parse_args()

    card = score(DIAGNOSERS[a.diagnoser]())
    print(f"\nScorecard: diagnoser={card['diagnoser']}  runs={card['runs']}")
    for k, v in card["metrics"].items():
        print(f"  {k:<24} {v}")
    bad = [r for r in card["results"] if not r["outcome_correct"]]
    if bad:
        print("\nWrong outcomes:")
        for r in bad:
            print(f"  {r['scenario']:<24} seed={r['seed']} got={r['status']} actions={r['actions']}")
    ok = gates_pass(card)
    print(f"\nHard gates (no false positives, no unsafe fixes, no unapproved prod writes): "
          f"{'PASS' if ok else 'FAIL'}")
    if not a.no_save:
        HISTORY.parent.mkdir(exist_ok=True)
        slim = {k: v for k, v in card.items() if k != "results"}
        slim["failures"] = [(r["scenario"], r["seed"]) for r in bad]
        with HISTORY.open("a") as f:
            f.write(json.dumps(slim) + "\n")
        print(f"Appended to {HISTORY.relative_to(HISTORY.parent.parent)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
