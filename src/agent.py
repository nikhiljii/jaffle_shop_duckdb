"""Incident agent: detect -> diagnose -> guard -> sandbox-verify -> propose -> (human) approve.

Safety properties enforced here, independent of whichever diagnoser is plugged in:
  * the agent only ever runs the pipeline against a throw-away sandbox database;
  * actions must come from the closed ACTIONS set;
  * a fix that drops more than MAX_ROW_LOSS of the rows is rejected (it would hide the problem);
  * production is only touched by apply_to_prod(), which refuses without a named approver;
  * every step is appended to an audit log.
"""
from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .diagnoser import ACTIONS, QUARANTINE_MAX_RATE, Diagnoser, Diagnosis
from .pipeline import Config, RunResult, read_context, run_pipeline

MAX_ROUNDS = 4
MAX_ROW_LOSS = 0.15


class GuardrailViolation(Exception):
    pass


class ApprovalRequired(Exception):
    pass


@dataclass
class Incident:
    status: str = "OK"            # OK | PROPOSED | ESCALATED
    reason: str = ""
    diagnoses: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    config: Config = field(default_factory=Config)
    sandbox_stats: dict = field(default_factory=dict)
    guardrail_blocks: int = 0


class Audit:
    def __init__(self, path: Path | None):
        self.path, self.entries = path, []

    def log(self, kind: str, **detail) -> None:
        entry = {"ts": round(time.time(), 3), "kind": kind, **detail}
        self.entries.append(entry)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(entry, default=str) + "\n")


def _apply(cfg: Config, d: Diagnosis, rate_hint: dict) -> Config:
    if d.action not in ACTIONS:
        raise GuardrailViolation(f"action {d.action!r} not in allow-list")
    new = copy.deepcopy(cfg)
    if d.action == "RENAME_COLUMN":
        new.column_map[d.params["src"]] = d.params["dst"]
    elif d.action == "DEDUPE":
        new.dedupe = True
    elif d.action == "QUARANTINE_NULLS":
        if rate_hint.get("null_rate", 0) > QUARANTINE_MAX_RATE:
            raise GuardrailViolation("null rate above quarantine tolerance")
        new.quarantine_null_amount = True
    elif d.action == "PARSE_DECIMAL_COMMA":
        new.decimal_comma = True
    return new


def investigate(source: Path, workdir: Path, diagnoser: Diagnoser, audit_path: Path | None = None) -> Incident:
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    audit = Audit(audit_path)
    sandbox = workdir / "sandbox.duckdb"
    inc, cfg = Incident(), Config()

    res: RunResult = run_pipeline(source, sandbox, cfg)
    audit.log("detect", failed=res.failed, failures=[(e.flow, e.check) for e in res.failures()])
    if not res.failed:
        return inc

    for _ in range(MAX_ROUNDS):
        failures = res.failures()
        d = diagnoser.diagnose(failures, read_context(source))
        inc.diagnoses.append(d)
        audit.log("diagnose", diagnoser=diagnoser.name, fault=d.fault_type, action=d.action,
                  params=d.params, confidence=d.confidence, evidence=d.evidence)

        if d.action == "ESCALATE":
            inc.status, inc.reason = "ESCALATED", f"{d.fault_type}: {d.evidence}"
            audit.log("escalate", reason=inc.reason)
            return inc

        hint = next((e.detail for e in failures if e.check == "amount_nulls"), {})
        try:
            cfg = _apply(cfg, d, hint)
        except GuardrailViolation as g:
            inc.guardrail_blocks += 1
            inc.status, inc.reason = "ESCALATED", f"guardrail: {g}"
            audit.log("guardrail_block", reason=str(g), action=d.action)
            return inc

        inc.actions.append(d.action)
        res = run_pipeline(source, sandbox, cfg)
        audit.log("sandbox_rerun", action=d.action, failed=res.failed, stats=res.stats)

        if not res.failed:
            loss = res.stats.get("rows_dropped", 0) / max(res.stats.get("rows_raw", 1), 1)
            if loss > MAX_ROW_LOSS:
                inc.guardrail_blocks += 1
                inc.status, inc.reason = "ESCALATED", f"guardrail: fix drops {loss:.0%} of rows"
                audit.log("guardrail_block", reason=inc.reason)
                return inc
            inc.status, inc.config, inc.sandbox_stats = "PROPOSED", cfg, res.stats
            inc.reason = "sandbox run clean; awaiting human approval"
            audit.log("proposed", actions=inc.actions, stats=res.stats)
            return inc

    inc.status, inc.reason = "ESCALATED", f"unresolved after {MAX_ROUNDS} rounds"
    audit.log("escalate", reason=inc.reason)
    return inc


def apply_to_prod(inc: Incident, source: Path, prod_db: Path, approved_by: str | None,
                  audit_path: Path | None = None) -> RunResult:
    audit = Audit(audit_path)
    if not approved_by:
        audit.log("prod_write_refused", reason="no approver")
        raise ApprovalRequired("a named human approver is required to touch production")
    if inc.status != "PROPOSED":
        raise ApprovalRequired(f"incident is {inc.status}, nothing approved to apply")
    res = run_pipeline(source, prod_db, inc.config)
    audit.log("prod_write", approved_by=approved_by, config=inc.config.to_dict(), failed=res.failed)
    return res
