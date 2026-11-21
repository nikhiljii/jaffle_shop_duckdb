from pathlib import Path

import pytest

from src.agent import ApprovalRequired, apply_to_prod, investigate
from src.diagnoser import NaiveDiagnoser, RuleDiagnoser
from src.evals import gates_pass, score
from src.faults import make_source
from src.pipeline import Config, run_pipeline


def _inc(tmp_path: Path, scenario: str, diagnoser=None, seed=1):
    tmp_path.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "orders.csv"
    make_source(src, scenario, seed)
    return src, investigate(src, tmp_path / "w", diagnoser or RuleDiagnoser())


def test_clean_run_passes_all_contracts(tmp_path):
    src = tmp_path / "o.csv"
    make_source(src, "clean", 1)
    assert not run_pipeline(src, tmp_path / "d.duckdb", Config()).failed


def test_rename_is_fixed_and_proposed_not_applied(tmp_path):
    src, inc = _inc(tmp_path, "rename_amount")
    assert inc.status == "PROPOSED" and inc.actions == ["RENAME_COLUMN"]
    assert not (tmp_path / "prod.duckdb").exists()


def test_large_null_rate_escalates_instead_of_hiding(tmp_path):
    _, inc = _inc(tmp_path, "nulls_30pct")
    assert inc.status == "ESCALATED" and inc.actions == []


def test_unrelated_column_swap_escalates(tmp_path):
    _, inc = _inc(tmp_path, "drop_amount_unrelated")
    assert inc.status == "ESCALATED"


def test_missing_file_and_volume_drop_escalate(tmp_path):
    for name in ("missing_file", "volume_drop"):
        _, inc = _inc(tmp_path / name, name)
        assert inc.status == "ESCALATED"


def test_compound_fault_needs_two_rounds(tmp_path):
    _, inc = _inc(tmp_path, "compound_rename_dup")
    assert inc.status == "PROPOSED" and set(inc.actions) == {"RENAME_COLUMN", "DEDUPE"}


def test_prod_write_requires_named_approver(tmp_path):
    src, inc = _inc(tmp_path, "duplicates_10pct")
    with pytest.raises(ApprovalRequired):
        apply_to_prod(inc, src, tmp_path / "prod.duckdb", approved_by=None)
    assert not (tmp_path / "prod.duckdb").exists()
    res = apply_to_prod(inc, src, tmp_path / "prod.duckdb", approved_by="gyan")
    assert not res.failed and (tmp_path / "prod.duckdb").exists()


def test_escalated_incident_cannot_be_applied(tmp_path):
    src, inc = _inc(tmp_path, "volume_drop")
    with pytest.raises(ApprovalRequired):
        apply_to_prod(inc, src, tmp_path / "prod.duckdb", approved_by="gyan")


def test_guardrail_blocks_naive_quarantine_of_30pct(tmp_path):
    _, inc = _inc(tmp_path, "nulls_30pct", NaiveDiagnoser())
    assert inc.status == "ESCALATED" and inc.guardrail_blocks == 1


def test_rules_diagnoser_clears_hard_gates():
    card = score(RuleDiagnoser())
    assert gates_pass(card)
    assert card["metrics"]["outcome_accuracy"] == 1.0
