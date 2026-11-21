"""CLI the incident subagent calls: investigate a source file, print the outcome as JSON.

    python -m src.incident_cli --source orders.csv [--workdir .incident]
Proposed config is written to <workdir>/proposed_config.json for the deployment agent.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent import investigate
from .diagnoser import DIAGNOSERS


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--workdir", default=".incident")
    p.add_argument("--diagnoser", default="rules", choices=sorted(DIAGNOSERS))
    a = p.parse_args()
    work = Path(a.workdir)
    inc = investigate(Path(a.source), work, DIAGNOSERS[a.diagnoser](), work / "audit.jsonl")
    if inc.status == "PROPOSED":
        (work / "proposed_config.json").write_text(json.dumps(inc.config.to_dict(), indent=2))
    print(json.dumps({
        "status": inc.status, "reason": inc.reason, "actions": inc.actions,
        "diagnoses": [{"fault": d.fault_type, "action": d.action, "evidence": d.evidence} for d in inc.diagnoses],
        "proposed_config": str(work / "proposed_config.json") if inc.status == "PROPOSED" else None,
    }, indent=2))
    return 0 if inc.status in ("OK", "PROPOSED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
