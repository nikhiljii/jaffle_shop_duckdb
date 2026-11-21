from pathlib import Path

import pytest

from src.profile import ProfileError, load_profile

P = Path(__file__).resolve().parent.parent / "profiles"


def test_all_presets_load():
    for f in P.glob("*.yaml"):
        assert load_profile(f)["project"]


def test_active_profile_loads():
    assert load_profile(P.parent / "project-profile.yaml")["target"]["type"] == "embedded_warehouse"


@pytest.mark.parametrize("field,value", [("processing", "weekly"), ("paradigm", "ELTT")])
def test_bad_enum_rejected(tmp_path, field, value):
    text = (P / "elt-cloud-warehouse.yaml").read_text()
    import re
    text = re.sub(rf"^{field}: \S+", f"{field}: {value}", text, flags=re.M)
    f = tmp_path / "p.yaml"
    f.write_text(text)
    with pytest.raises(ProfileError):
        load_profile(f)
