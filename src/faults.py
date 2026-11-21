"""Seeded source-data generator and fault injectors, with ground truth for evals.

The agent never sees SCENARIOS; only the eval harness does.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

HEADER = ["order_id", "customer_id", "amount", "currency", "order_ts", "status"]
BASE_ROWS = 200


def _clean_rows(seed: int, n: int = BASE_ROWS) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "order_id": f"ORD-{i:05d}",
            "customer_id": f"C-{rng.randint(1, 60):03d}",
            "amount": f"{rng.uniform(5, 500):.2f}",
            "currency": rng.choice(["EUR", "USD", "GBP"]),
            "order_ts": f"2026-11-{rng.randint(1, 20):02d} {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00",
            "status": rng.choice(["paid", "shipped", "refunded"]),
        })
    return rows


def _write(path: Path, rows: list[dict], header: list[str]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)


def _rename(rows, header, old, new):
    header = [new if h == old else h for h in header]
    rows = [{(new if k == old else k): v for k, v in r.items()} for r in rows]
    return rows, header


def make_source(path: Path, scenario: str, seed: int) -> None:
    """Write today's source file for a scenario (or nothing, for missing_file)."""
    rng = random.Random(seed * 7919)
    rows, header = _clean_rows(seed), list(HEADER)

    if scenario == "missing_file":
        return
    if scenario in ("rename_amount", "compound_rename_dup"):
        rows, header = _rename(rows, header, "amount", "total_amount")
    if scenario == "rename_ts":
        rows, header = _rename(rows, header, "order_ts", "created_at")
    if scenario == "drop_amount_unrelated":
        header = [h for h in header if h != "amount"] + ["notes"]
        rows = [{**{k: v for k, v in r.items() if k != "amount"}, "notes": rng.choice(["gift", "rush", "none"])}
                for r in rows]
    if scenario == "nulls_4pct":
        for r in rng.sample(rows, int(len(rows) * 0.04)):
            r["amount"] = ""
    if scenario == "nulls_30pct":
        for r in rng.sample(rows, int(len(rows) * 0.30)):
            r["amount"] = ""
    if scenario in ("duplicates_10pct", "compound_rename_dup"):
        rows = rows + [dict(r) for r in rng.sample(rows, int(len(rows) * 0.10))]
        rng.shuffle(rows)
    if scenario == "volume_drop":
        rows = rows[:20]
    if scenario == "decimal_comma":
        for r in rows:
            r["amount"] = r["amount"].replace(".", ",")
    _write(path, rows, header)


# scenario -> ground truth. first_fault is the fault type the first diagnosis should name.
# outcome: "OK" (nothing to do), "PROPOSED" (fix ready for approval) or "ESCALATED".
SCENARIOS = {
    "clean":                 {"first_fault": None,                 "outcome": "OK",        "actions": set()},
    "missing_file":          {"first_fault": "missing_file",       "outcome": "ESCALATED", "actions": set()},
    "rename_amount":         {"first_fault": "schema_drift_rename", "outcome": "PROPOSED", "actions": {"RENAME_COLUMN"}},
    "rename_ts":             {"first_fault": "schema_drift_rename", "outcome": "PROPOSED", "actions": {"RENAME_COLUMN"}},
    "drop_amount_unrelated": {"first_fault": "schema_drift_unknown", "outcome": "ESCALATED", "actions": set()},
    "nulls_4pct":            {"first_fault": "null_spike_small",   "outcome": "PROPOSED",  "actions": {"QUARANTINE_NULLS"}},
    "nulls_30pct":           {"first_fault": "null_spike_large",   "outcome": "ESCALATED", "actions": set()},
    "duplicates_10pct":      {"first_fault": "duplicates",         "outcome": "PROPOSED",  "actions": {"DEDUPE"}},
    "volume_drop":           {"first_fault": "volume_drop",        "outcome": "ESCALATED", "actions": set()},
    "decimal_comma":         {"first_fault": "decimal_format",     "outcome": "PROPOSED",  "actions": {"PARSE_DECIMAL_COMMA"}},
    "compound_rename_dup":   {"first_fault": "schema_drift_rename", "outcome": "PROPOSED", "actions": {"RENAME_COLUMN", "DEDUPE"}},
}
