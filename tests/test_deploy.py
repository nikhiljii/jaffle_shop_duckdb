import json

import pytest

from src.agent import ApprovalRequired
from src.deploy import SmokeFailed, promote, rollback, stage, _read_pointer
from src.faults import make_source
from src.pipeline import Config


def _src(tmp_path, scenario="clean", seed=1):
    p = tmp_path / "orders.csv"
    make_source(p, scenario, seed)
    return p


def test_stage_does_not_touch_current(tmp_path):
    root = tmp_path / "rel"
    r = stage(_src(tmp_path), root, Config())
    assert (root / r / "manifest.json").exists()
    assert _read_pointer(root)["current"] is None


def test_stage_refuses_broken_data(tmp_path):
    with pytest.raises(SmokeFailed):
        stage(_src(tmp_path, "duplicates_10pct"), tmp_path / "rel", Config())


def test_promote_needs_approver_and_a_staged_release(tmp_path):
    root = tmp_path / "rel"
    r = stage(_src(tmp_path), root, Config())
    with pytest.raises(ApprovalRequired):
        promote(root, r, None)
    with pytest.raises(SmokeFailed):
        promote(root, "never-staged", "gyan")
    assert promote(root, r, "gyan")["current"] == r


def test_rollback_restores_previous_release(tmp_path):
    root = tmp_path / "rel"
    r1 = stage(_src(tmp_path, seed=1), root, Config())
    promote(root, r1, "gyan")
    r2 = stage(_src(tmp_path, seed=2), root, Config())
    promote(root, r2, "gyan")
    assert _read_pointer(root)["current"] == r2
    assert rollback(root, "gyan")["current"] == r1
    assert (root / r2 / "db.duckdb").exists()  # bad release kept for forensics
    with pytest.raises(ApprovalRequired):
        rollback(root, None)


def test_fix_proposed_by_incident_agent_deploys_cleanly(tmp_path):
    from src.agent import investigate
    from src.diagnoser import RuleDiagnoser
    src = _src(tmp_path, "compound_rename_dup")
    inc = investigate(src, tmp_path / "w", RuleDiagnoser())
    assert inc.status == "PROPOSED"
    root = tmp_path / "rel"
    r = stage(src, root, inc.config)
    assert json.loads((root / r / "manifest.json").read_text())["config"]["dedupe"] is True
