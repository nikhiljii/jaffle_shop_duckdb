"""Release tooling used by the deployment agent: stage -> smoke -> promote -> rollback.

A release is a directory holding a built database plus a manifest. `current` is a
pointer file naming the live release; promote and rollback only move that pointer,
so switching is atomic and the previous release always stays intact for rollback.
Promotion requires a named approver, same rule as the incident agent.

CLI:
    python -m src.deploy stage    --source orders.csv --root releases [--config cfg.json]
    python -m src.deploy promote  --root releases --release R --approver NAME
    python -m src.deploy rollback --root releases --approver NAME
    python -m src.deploy status   --root releases
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import duckdb

from .agent import ApprovalRequired
from .pipeline import Config, run_pipeline


class SmokeFailed(Exception):
    pass


def _pointer(root: Path) -> Path:
    return root / "current.json"


def _read_pointer(root: Path) -> dict:
    p = _pointer(root)
    return json.loads(p.read_text()) if p.exists() else {"current": None, "history": []}


def _write_pointer(root: Path, state: dict) -> None:
    tmp = root / "current.json.tmp"
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, _pointer(root))  # atomic on POSIX


def stage(source: Path, root: Path, cfg: Config) -> str:
    """Build a release in isolation and smoke-test it. Never touches `current`."""
    root = Path(root)
    release = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
    rdir = root / release
    rdir.mkdir(parents=True)
    res = run_pipeline(source, rdir / "db.duckdb", cfg)
    if res.failed:
        raise SmokeFailed(f"contracts failed in staging: {[(e.flow, e.check) for e in res.failures()]}")
    con = duckdb.connect(str(rdir / "db.duckdb"), read_only=True)
    try:
        mart_rows = con.execute("select count(*) from mart_daily_revenue").fetchone()[0]
    finally:
        con.close()
    if mart_rows == 0:
        raise SmokeFailed("mart_daily_revenue is empty")
    (rdir / "manifest.json").write_text(json.dumps(
        {"release": release, "config": cfg.to_dict(), "stats": res.stats, "mart_rows": mart_rows}, indent=2))
    return release


def promote(root: Path, release: str, approver: str | None) -> dict:
    root = Path(root)
    if not approver:
        raise ApprovalRequired("promotion needs a named human approver")
    if not (root / release / "manifest.json").exists():
        raise SmokeFailed(f"release {release} was never staged and smoke-tested")
    state = _read_pointer(root)
    if state["current"]:
        state["history"].append(state["current"])
    state["current"] = release
    state["approved_by"] = approver
    _write_pointer(root, state)
    return state


def rollback(root: Path, approver: str | None) -> dict:
    root = Path(root)
    if not approver:
        raise ApprovalRequired("rollback needs a named human approver")
    state = _read_pointer(root)
    if not state["history"]:
        raise SmokeFailed("no previous release to roll back to")
    state["current"] = state["history"].pop()
    state["approved_by"] = approver
    _write_pointer(root, state)
    return state


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["stage", "promote", "rollback", "status"])
    p.add_argument("--root", default="releases")
    p.add_argument("--source")
    p.add_argument("--config")
    p.add_argument("--release")
    p.add_argument("--approver")
    a = p.parse_args()
    root = Path(a.root)
    root.mkdir(parents=True, exist_ok=True)
    try:
        if a.cmd == "stage":
            cfg = Config(**json.loads(Path(a.config).read_text())) if a.config else Config()
            print(json.dumps({"staged": stage(Path(a.source), root, cfg)}))
        elif a.cmd == "promote":
            print(json.dumps(promote(root, a.release, a.approver)))
        elif a.cmd == "rollback":
            print(json.dumps(rollback(root, a.approver)))
        else:
            print(json.dumps(_read_pointer(root)))
    except (SmokeFailed, ApprovalRequired) as e:
        print(json.dumps({"error": type(e).__name__, "detail": str(e)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
