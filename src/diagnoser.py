"""Diagnosers turn failed contract checks plus read-only evidence into one Diagnosis.

A diagnoser can only *propose* an action from the closed ACTIONS set. It never
touches data. Anything outside the set, or any guardrail breach, is rejected by
the agent. New diagnosers (for example an LLM-backed one) implement `diagnose`
and are scored by the same eval harness.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Protocol

from .pipeline import EXPECTED_COLS, Event

ACTIONS = {"RENAME_COLUMN", "DEDUPE", "QUARANTINE_NULLS", "PARSE_DECIMAL_COMMA", "ESCALATE"}
QUARANTINE_MAX_RATE = 0.05   # never silently drop more than 5% of rows as "nulls"

EXPECTED_TYPES = {
    "order_id": "id", "customer_id": "id", "amount": "number",
    "currency": "currency", "order_ts": "timestamp", "status": "text",
}


@dataclass
class Diagnosis:
    fault_type: str
    action: str
    params: dict = field(default_factory=dict)
    confidence: float = 0.0
    evidence: str = ""


class Diagnoser(Protocol):
    name: str

    def diagnose(self, failures: list[Event], context: dict) -> Diagnosis: ...


def _infer_type(values: list[str]) -> str:
    vals = [v for v in values if v not in ("", None)]
    if not vals:
        return "text"

    def share(rx):
        return sum(bool(re.match(rx, v)) for v in vals) / len(vals)

    for t, rx in (("timestamp", r"^\d{4}-\d{2}-\d{2}"), ("number", r"^-?\d+([.,]\d+)?$"),
                  ("currency", r"^[A-Z]{3}$"), ("id", r"^[A-Z]+-\d+$")):
        if share(rx) >= 0.9:
            return t
    return "text"


class RuleDiagnoser:
    """Deterministic baseline. Any LLM diagnoser has to beat this on the eval scorecard."""
    name = "rules"

    def diagnose(self, failures: list[Event], context: dict) -> Diagnosis:
        by = {(e.flow, e.check): e for e in failures}

        if ("ingest", "file_exists") in by:
            return Diagnosis("missing_file", "ESCALATE", confidence=0.95,
                             evidence="source file absent; upstream delivery problem, not fixable here")

        if ("ingest", "schema") in by:
            d = by[("ingest", "schema")].detail
            missing, extra = d["missing"], d["extra"]
            if len(missing) == 1 and len(extra) == 1:
                miss, ext = missing[0], extra[0]
                col_vals = [row.get(ext, "") for row in context.get("sample", [])]
                got = _infer_type(col_vals)
                sim = SequenceMatcher(None, miss, ext).ratio()
                if got == EXPECTED_TYPES[miss]:
                    return Diagnosis("schema_drift_rename", "RENAME_COLUMN",
                                     {"src": ext, "dst": miss}, 0.9 if sim > 0.5 else 0.75,
                                     f"'{ext}' looks like {got}, matching expected '{miss}' (name sim {sim:.2f})")
            return Diagnosis("schema_drift_unknown", "ESCALATE", confidence=0.8,
                             evidence=f"missing {missing}, extra {extra}; no safe mapping")

        if ("ingest", "volume") in by:
            d = by[("ingest", "volume")].detail
            return Diagnosis("volume_drop", "ESCALATE", confidence=0.9,
                             evidence=f"{d['rows']} rows vs minimum {d['min_rows']}; likely partial upstream load")

        if ("transform", "amount_parse") in by:
            d = by[("transform", "amount_parse")].detail
            if d.get("sample") and all(re.match(r"^-?\d+,\d+$", s) for s in d["sample"]):
                return Diagnosis("decimal_format", "PARSE_DECIMAL_COMMA", confidence=0.9,
                                 evidence=f"unparseable amounts look like decimal commas: {d['sample']}")
            return Diagnosis("unknown", "ESCALATE", confidence=0.5, evidence=f"unparseable amounts {d}")

        if ("transform", "order_id_unique") in by:
            d = by[("transform", "order_id_unique")].detail
            return Diagnosis("duplicates", "DEDUPE", {"key": "order_id"}, 0.85,
                             evidence=f"{d['duplicates']} duplicate order_id rows")

        if ("transform", "amount_nulls") in by:
            rate = by[("transform", "amount_nulls")].detail["null_rate"]
            if rate <= QUARANTINE_MAX_RATE:
                return Diagnosis("null_spike_small", "QUARANTINE_NULLS", {"rate": rate}, 0.8,
                                 evidence=f"{rate:.1%} empty amounts, within quarantine tolerance")
            return Diagnosis("null_spike_large", "ESCALATE", {"rate": rate}, 0.85,
                             evidence=f"{rate:.1%} empty amounts; dropping them would hide an upstream defect")

        return Diagnosis("unknown", "ESCALATE", confidence=0.3, evidence="no rule matched")


class NaiveDiagnoser:
    """Deliberately careless comparison point: always tries to patch, ignores type evidence."""
    name = "naive"

    def diagnose(self, failures: list[Event], context: dict) -> Diagnosis:
        by = {(e.flow, e.check): e for e in failures}
        if ("ingest", "schema") in by:
            d = by[("ingest", "schema")].detail
            if d["missing"] and d["extra"]:
                return Diagnosis("schema_drift_rename", "RENAME_COLUMN",
                                 {"src": d["extra"][0], "dst": d["missing"][0]}, 0.5, "first extra -> first missing")
        if ("transform", "order_id_unique") in by:
            return Diagnosis("duplicates", "DEDUPE", {"key": "order_id"}, 0.5, "dedupe")
        if ("transform", "amount_nulls") in by:
            return Diagnosis("null_spike_small", "QUARANTINE_NULLS", {}, 0.5, "drop empties")
        if ("transform", "amount_parse") in by:
            return Diagnosis("decimal_format", "PARSE_DECIMAL_COMMA", {}, 0.5, "assume comma")
        return Diagnosis("unknown", "ESCALATE", confidence=0.1, evidence="nothing to patch")


DIAGNOSERS = {"rules": RuleDiagnoser, "naive": NaiveDiagnoser}
