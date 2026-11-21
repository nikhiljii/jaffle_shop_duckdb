"""Score a project profile and recommend ELT, ETL or ETLT, with the reasons written out.

Weights are standard industry heuristics, not laws: tune them on real projects.
The recommendation is rendered as an ADR (architecture decision record) so the choice
is reviewed and approved by a human before anything is built.

    python -m src.paradigm project-profile.yaml [--adr architecture/decisions/ADR-001-paradigm.md]
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

from .profile import load_profile

HYBRID_MARGIN = 3


@dataclass
class Recommendation:
    paradigm: str
    elt_score: int
    etl_score: int
    reasons: list = field(default_factory=list)   # (side, points, text)
    override: bool = False


def score(p: dict) -> Recommendation:
    elt = etl = 0
    reasons: list = []

    def add(side: str, pts: int, text: str):
        nonlocal elt, etl
        if side == "ELT":
            elt += pts
        else:
            etl += pts
        reasons.append((side, pts, text))

    t, s, r, tr, team = p["target"], p["sensitivity"], p["requirements"], p["transforms"], p["team"]
    if t["elastic_compute"]:
        add("ELT", 3, "target has elastic compute, so transforming inside it is cheap")
    elif t["type"] == "embedded_warehouse":
        add("ELT", 3, "embedded analytical engine runs SQL transforms in-process at no extra cost")
    else:
        add("ETL", 3, "target has limited compute; transform before loading")
    if r["keep_raw"]:
        add("ELT", 2, "raw data must be kept for reprocessing and audit")
    if tr["style"] == "sql" or team["sql_strength"] == "high":
        add("ELT", 2, "transformations are SQL and the team is SQL-strong")
    if tr["style"] == "code":
        add("ETL", 2, "transformations need non-SQL code")
    if r["schema_change_frequency"] == "high":
        add("ELT", 1, "schemas change often; raw landing absorbs drift")
    if r["storage_constrained"]:
        add("ETL", 2, "storage or bandwidth is constrained; do not land everything raw")
    if s["mask_before_landing"]:
        add("ETL", 5, "PII must be masked before it lands in the target")

    if p["paradigm"] != "auto":
        return Recommendation(p["paradigm"], elt, etl, reasons, override=True)
    if s["mask_before_landing"] and elt >= 3:
        verdict = "ETLT"   # mask/cleanse first (ETL), heavy transforms in the warehouse (ELT)
    elif elt - etl >= HYBRID_MARGIN:
        verdict = "ELT"
    elif etl - elt >= HYBRID_MARGIN:
        verdict = "ETL"
    else:
        verdict = "ETLT"
    return Recommendation(verdict, elt, etl, reasons)


def render_adr(p: dict, rec: Recommendation, number: int = 1) -> str:
    lines = [
        f"# ADR-{number:03d}: Data movement paradigm for {p['project']}", "",
        "Status: PROPOSED (needs human approval before any build)", "",
        f"## Decision\n\n**{rec.paradigm}**" + ("  (explicit human override of the scorer)" if rec.override else ""), "",
        f"## Scores\n\nELT {rec.elt_score} vs ETL {rec.etl_score} (hybrid margin {HYBRID_MARGIN})", "",
        "## Reasons", "",
    ]
    lines += [f"- [{side} +{pts}] {text}" for side, pts, text in rec.reasons]
    lines += ["", "## Consequences", ""]
    if rec.paradigm == "ELT":
        lines.append("- Land raw data first, transform in the warehouse; use the `pattern-elt` skill.")
    elif rec.paradigm == "ETL":
        lines.append("- Transform and mask before load; use the `pattern-etl` skill.")
    else:
        lines.append("- Cleanse and mask before landing (`pattern-etl`), then transform in-warehouse (`pattern-elt`).")
    lines.append("- Any change to this decision needs a new ADR that supersedes this one.")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--adr")
    a = ap.parse_args()
    p = load_profile(a.profile)
    rec = score(p)
    print(f"{p['project']}: {rec.paradigm}  (ELT {rec.elt_score} / ETL {rec.etl_score})")
    for side, pts, text in rec.reasons:
        print(f"  [{side} +{pts}] {text}")
    if a.adr:
        Path(a.adr).parent.mkdir(parents=True, exist_ok=True)
        Path(a.adr).write_text(render_adr(p, rec))
        print(f"wrote {a.adr}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
