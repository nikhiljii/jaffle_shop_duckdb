import json
import shutil
from pathlib import Path

import duckdb
import pytest
import yaml

from src.conformance import check, gate

ROOT = Path(__file__).resolve().parent.parent


def build(tmp: Path, **over) -> Path:
    """A minimal dbt project that complies with every file-checkable rule."""
    (tmp / "models/staging").mkdir(parents=True)
    (tmp / "seeds").mkdir()
    (tmp / "tests").mkdir()
    (tmp / "architecture").mkdir()
    (tmp / ".github/workflows").mkdir(parents=True)
    (tmp / "dbt_project.yml").write_text(yaml.safe_dump({
        "name": "p", "models": {"p": {"+materialized": "table", "staging": {"+materialized": "view"}}}}))
    (tmp / "seeds/raw_a.csv").write_text("id,v\n1,2\n")
    (tmp / "models/staging/stg_a.sql").write_text("select id, v from {{ ref('raw_a') }}")
    (tmp / "models/mart.sql").write_text("select id, v from {{ ref('stg_a') }}")
    key = {"tests": ["unique", "not_null"]}
    (tmp / "models/staging/schema.yml").write_text(yaml.safe_dump({"models": [
        {"name": "stg_a", "description": "staging a", "columns": [{"name": "id", **key}]}]}))
    (tmp / "models/schema.yml").write_text(yaml.safe_dump({"models": [
        {"name": "mart", "description": "the mart", "columns": [
            {"name": "id", "meta": {"classification": "internal"}, **key},
            {"name": "v", "meta": {"classification": "internal"}}]}]}))
    (tmp / "architecture/foreign-keys.yaml").write_text("foreign_keys: []\n")
    (tmp / "tests/volume.sql").write_text("select 1 from {{ ref('raw_a') }} having count(*) < 1")
    (tmp / "tests/reconcile.sql").write_text(
        "select 1 from (select sum(v) a from {{ ref('mart') }}) m, (select sum(v) b from {{ ref('stg_a') }}) s where a <> b")
    (tmp / ".github/workflows/ci.yml").write_text("steps:\n  - run: dbt build\n  - run: sqlfluff lint models\n")
    (tmp / "profiles.yml").write_text("p:\n  target: dev\n  outputs:\n    dev: {type: duckdb, path: p.duckdb}\n")
    for rel, text in over.items():
        (tmp / rel.replace("__", "/")).write_text(text)
    return tmp


def status(results):
    return {r.rule: r.status for r in results}


def test_compliant_project_has_no_failures(tmp_path):
    s = status(check(build(tmp_path)))
    assert [r for r, v in s.items() if v == "FAIL"] == []
    assert s["R9"] == s["R13"] == s["R14"] == "SKIP"      # no database given
    assert s["R15"] == s["R16"] == "SKIP"                 # never claimed as checked


# Collateral: rules a mutation legitimately trips as a side effect (anything else is a bug).
ALSO = {"R3": {"R6"}, "R7": {"R10"}, "R11": {"R7"}}


@pytest.mark.parametrize("rule,files", [
    ("R1", {"models__mart.sql": "select * from {{ ref('raw_a') }}"}),
    ("R3", {"models__schema.yml": yaml.safe_dump({"models": [{"name": "mart", "description": "d", "columns": [{"name": "id"}]}]})}),
    ("R4", {"tests__volume.sql": "select 1"}),
    ("R5", {"models__mart.sql": "select now() as t, id from {{ ref('stg_a') }}"}),
    ("R6", {"models__schema.yml": yaml.safe_dump({"models": [{"name": "mart", "description": "d", "columns": [
        {"name": "id", "tests": ["unique", "not_null"]}]}]})}),
    ("R7", {"models__staging__stg_b.sql": "select id from {{ ref('raw_a') }}"}),
    ("R8", {"architecture__foreign-keys.yaml": "foreign_keys:\n  - {model: mart, column: id, to: stg_a, field: id}\n"}),
    ("R10", {"models__schema.yml": yaml.safe_dump({"models": [{"name": "mart", "columns": [
        {"name": "id", "meta": {"classification": "x"}, "tests": ["unique", "not_null"]}]}]})}),
    ("R11", {"models__staging__stg_a.sql": "select id from {{ ref('mart') }}"}),
    ("R12", {"models__mart.sql": "{{ config(materialized='view') }} select id from {{ ref('stg_a') }}"}),
    ("R17", {"tests__reconcile.sql": "select 1"}),
    ("R18", {".github__workflows__ci.yml": "steps:\n  - run: dbt build\n"}),
    ("R19", {"profiles.yml": "p:\n  outputs:\n    dev: {type: duckdb, password: hunter2}\n"}),
])
def test_each_rule_can_fail(tmp_path, rule, files):
    s = status(check(build(tmp_path, **files)))
    assert s[rule] == "FAIL", f"{rule} did not fail: {s}"
    others = {r for r, v in s.items() if v == "FAIL" and r != rule}
    assert others == ALSO.get(rule, set()), f"unexpected collateral failures: {others}"


def test_env_var_secret_reference_is_not_flagged(tmp_path):
    p = build(tmp_path, **{"profiles.yml": "p:\n  outputs:\n    dev: {password: \"{{ env_var('PW') }}\"}\n"})
    assert status(check(p))["R19"] == "PASS"


def test_database_rules_r9_r13_r14(tmp_path):
    p = build(tmp_path)
    db = tmp_path / "w.duckdb"
    con = duckdb.connect(str(db))
    con.execute("create table mart (id int, extra int)")           # 'v' documented but absent, 'extra' undocumented
    con.execute("create table raw_a (id int, v int)")              # typed, no metadata, same schema
    con.close()
    s = status(check(p, db))
    assert s["R9"] == s["R13"] == s["R14"] == "FAIL"
    con = duckdb.connect(str(db))
    con.execute("drop table mart")
    con.execute("create schema raw; create schema staging; create schema marts")
    con.execute("create table marts.mart (id int, v int)")
    con.execute("drop table raw_a")
    con.execute("create table raw.raw_a (id varchar, v varchar, loaded_at varchar)")
    con.execute("create table staging.stg_a (id int)")
    con.close()
    s = status(check(p, db))
    assert s["R9"] == s["R13"] == s["R14"] == "PASS", s


def test_gate_is_a_ratchet(tmp_path):
    res = check(build(tmp_path, **{"models__schema.yml": yaml.safe_dump({"models": [
        {"name": "mart", "columns": [{"name": "id", "meta": {"classification": "x"}, "tests": ["unique", "not_null"]}]}]})}))
    code, msgs = gate(res, {})
    assert code == 1 and "R10" in msgs[0]
    code, msgs = gate(res, {"R10": "accepted at adoption"})
    assert code == 0
    code, msgs = gate(check(build(tmp_path / "ok")), {"R10": "stale"})
    assert code == 0 and any("tightened" in m for m in msgs)


def test_real_repo_static_failures_are_all_in_baseline():
    if not (ROOT / "models/customers.sql").exists():
        pytest.skip("not the jaffle_shop checkout")
    accepted = json.loads((ROOT / "evals/conformance/baseline.json").read_text())["accepted_failures"]
    code, msgs = gate(check(ROOT, paradigm="ELT"), accepted)
    assert code == 0, msgs
