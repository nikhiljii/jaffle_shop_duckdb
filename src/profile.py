"""Load and validate project-profile.yaml, the contract every agent reads."""
from __future__ import annotations

from pathlib import Path

import yaml

ALLOWED = {
    "paradigm": {"auto", "ELT", "ETL", "ETLT"},
    "processing": {"batch", "micro-batch", "streaming"},
    "target.type": {"cloud_warehouse", "lakehouse", "embedded_warehouse", "onprem_db", "file_store"},
    "transforms.style": {"sql", "code", "mixed"},
    "team.sql_strength": {"high", "medium", "low"},
    "requirements.schema_change_frequency": {"high", "low"},
}
REQUIRED = ["project", "paradigm", "processing", "target", "sources", "sensitivity",
            "transforms", "team", "requirements", "slas"]


class ProfileError(ValueError):
    pass


def _get(d: dict, dotted: str):
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def load_profile(path: str | Path) -> dict:
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict):
        raise ProfileError("profile must be a YAML mapping")
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise ProfileError(f"missing fields: {missing}")
    for dotted, allowed in ALLOWED.items():
        val = _get(data, dotted)
        if val not in allowed:
            raise ProfileError(f"{dotted}={val!r} not in {sorted(allowed)}")
    for dotted in ("target.elastic_compute", "sensitivity.pii", "sensitivity.mask_before_landing",
                   "requirements.keep_raw", "requirements.storage_constrained"):
        if not isinstance(_get(data, dotted), bool):
            raise ProfileError(f"{dotted} must be true or false")
    if data["sensitivity"]["mask_before_landing"] and not data["sensitivity"]["pii"]:
        raise ProfileError("mask_before_landing requires pii: true")
    return data
