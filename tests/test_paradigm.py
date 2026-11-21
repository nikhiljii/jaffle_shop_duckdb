from pathlib import Path

import pytest

from src.paradigm import render_adr, score
from src.profile import ProfileError, load_profile

P = Path(__file__).resolve().parent.parent / "profiles"


def test_presets_give_expected_paradigm():
    assert score(load_profile(P / "elt-cloud-warehouse.yaml")).paradigm == "ELT"
    assert score(load_profile(P / "etl-sensitive-data.yaml")).paradigm == "ETL"
    assert score(load_profile(P / "etlt-hybrid.yaml")).paradigm == "ETLT"


def test_pii_masking_forces_hybrid_even_on_cloud_warehouse():
    p = load_profile(P / "elt-cloud-warehouse.yaml")
    p["sensitivity"] = {"pii": True, "mask_before_landing": True}
    assert score(p).paradigm == "ETLT"


def test_explicit_override_is_honoured_and_flagged():
    p = load_profile(P / "elt-cloud-warehouse.yaml")
    p["paradigm"] = "ETL"
    rec = score(p)
    assert rec.paradigm == "ETL" and rec.override
    assert "override" in render_adr(p, rec)


def test_adr_lists_reasons_and_needs_approval():
    p = load_profile(P / "elt-cloud-warehouse.yaml")
    adr = render_adr(p, score(p))
    assert "PROPOSED" in adr and "[ELT +3]" in adr


def test_invalid_profiles_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("project: x\n")
    with pytest.raises(ProfileError):
        load_profile(bad)
    p = (P / "elt-cloud-warehouse.yaml").read_text().replace("pii: false", "pii: false").replace(
        "mask_before_landing: false", "mask_before_landing: true")
    bad.write_text(p)
    with pytest.raises(ProfileError):
        load_profile(bad)  # masking without pii


def test_embedded_warehouse_is_not_forced_into_etl():
    # Found by running the architect on jaffle_shop_duckdb: DuckDB had no honest target type,
    # so elastic_compute=false + onprem_db produced a misleading ETLT. Regression test.
    p = load_profile(P / "elt-cloud-warehouse.yaml")
    p["target"] = {"type": "embedded_warehouse", "engine": "duckdb", "elastic_compute": False}
    p["requirements"]["schema_change_frequency"] = "low"
    rec = score(p)
    assert rec.paradigm == "ELT" and rec.etl_score == 0
