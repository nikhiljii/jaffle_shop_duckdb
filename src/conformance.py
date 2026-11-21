"""Machine-checkable architecture conformance for dbt projects.

Reads the rules the architect wrote (architecture/data-architecture.md, R1..Rn) and checks the
ones that can be verified from files, and optionally from the built DuckDB database. Rules that
need judgement or a CI run are reported as SKIP with the reason, never as PASS.

An existing repo rarely starts clean, so a baseline lists accepted known violations. The gate is
a ratchet: exit code 1 only if a rule fails that is NOT in the baseline.

    python -m src.conformance --project . [--db jaffle_shop.duckdb] \
        [--baseline evals/conformance/baseline.json] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path

import yaml

REF = re.compile(r"""ref\(\s*['"]([\w.]+)['"]\s*\)""")
SRC = re.compile(r"""source\(\s*['"]([\w.]+)['"]\s*,""")
VOLATILE = re.compile(r"\b(now\(\)|current_timestamp|getdate\(\)|random\(\)|uuid\(\))", re.I)
SECRET = re.compile(r"(password|secret|token)\s*[:=]\s*(?!\{\{)['\"]?[^\s'\"{]+", re.I)
CONFIG_MAT = re.compile(r"""config\([^)]*materialized\s*=\s*['"](\w+)['"]""", re.S)

IMPLEMENTED = ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11", "R12",
               "R13", "R14", "R17", "R18", "R19"]
NOT_CHECKED = {
    "R15": "semantic: docs vs code agreement on currency and unit needs a human or LLM reviewer",
    "R16": "semantic: intended NULL behaviour is a business decision",
}


@dataclass
class Result:
    rule: str
    status: str          # PASS | FAIL | SKIP
    title: str
    detail: str = ""


def _tests_of(col: dict) -> list:
    out = []
    for t in (col.get("tests") or []) + (col.get("data_tests") or []):
        out.append(t if isinstance(t, str) else next(iter(t)))
    return out


class Project:
    def __init__(self, root: Path):
        self.root = Path(root)
        mdir = self.root / "models"
        self.models: dict = {}
        for p in sorted(mdir.rglob("*.sql")):
            parts = p.relative_to(mdir).parts[:-1]
            layer = "staging" if "staging" in parts else ("intermediate" if "intermediate" in parts else "marts")
            sql = p.read_text()
            self.models[p.stem] = {
                "path": p, "layer": layer, "sql": sql,
                "refs": REF.findall(sql), "sources": SRC.findall(sql),
                "config_mat": (CONFIG_MAT.findall(sql) or [None])[0],
            }
        self.seeds = {p.stem for p in (self.root / "seeds").glob("*.csv")} if (self.root / "seeds").exists() else set()
        self.yml_models: dict = {}
        self.sources: list = []
        for y in list(mdir.rglob("*.yml")) + list(mdir.rglob("*.yaml")):
            doc = yaml.safe_load(y.read_text()) or {}
            for m in doc.get("models", []) or []:
                self.yml_models[m["name"]] = m
            self.sources += doc.get("sources", []) or []
        dp = self.root / "dbt_project.yml"
        self.dbt_project = yaml.safe_load(dp.read_text()) if dp.exists() else {}

    def raw_names(self) -> set:
        return set(self.seeds) | {t["name"] for s in self.sources for t in (s.get("tables") or [])}

    def materialization(self, name: str) -> str | None:
        m = self.models[name]
        if m["config_mat"]:
            return m["config_mat"]
        node = (self.dbt_project.get("models") or {}).get(self.dbt_project.get("name"), {}) or {}
        mat = node.get("+materialized")
        if m["layer"] == "staging":
            mat = (node.get("staging") or {}).get("+materialized", mat)
        return mat

    def layer(self, layer: str) -> list:
        return [n for n, m in self.models.items() if m["layer"] == layer]

    def cols(self, model: str) -> list:
        return (self.yml_models.get(model) or {}).get("columns", []) or []

    def has_key_tests(self, model: str) -> bool:
        return any({"unique", "not_null"} <= set(_tests_of(c)) for c in self.cols(model))


def _res(rule, title, bad: list, detail_ok=""):
    return Result(rule, "FAIL" if bad else "PASS", title, "; ".join(bad) if bad else detail_ok)


def check(root: Path, db: Path | None = None, paradigm: str | None = None) -> list[Result]:
    P = Project(root)
    raw = P.raw_names()
    out: list[Result] = []

    # R1 raw is only referenced from staging
    bad = [f"{n} references raw ({', '.join(sorted(set(m['refs']) & raw))})" for n, m in P.models.items()
           if m["layer"] != "staging" and (set(m["refs"]) & raw or m["sources"])]
    out.append(_res("R1", "only staging may reference raw tables", bad))

    # R2 PII in landing zone (ETL/ETLT only)
    if paradigm in ("ETL", "ETLT"):
        out.append(Result("R2", "SKIP", "no unmasked PII in landing zone", "applies under ETL/ETLT; needs a data scan"))
    else:
        out.append(Result("R2", "PASS", "no unmasked PII in landing zone", f"not applicable under {paradigm or 'ELT'}"))

    # R3 every mart has unique + not_null key
    out.append(_res("R3", "every mart has a unique and not_null key",
                    [f"{n} has no key tested unique+not_null" for n in P.layer("marts") if not P.has_key_tests(n)]))

    # R4 freshness or volume check per raw table
    tests_sql = " ".join(p.read_text() for p in (root / "tests").rglob("*.sql")) if (root / "tests").exists() else ""
    fresh = {t["name"] for s in P.sources for t in (s.get("tables") or []) if t.get("freshness") or s.get("freshness")}
    bad = [f"{r} has no freshness or volume check" for r in sorted(raw)
           if r not in fresh and not (r in tests_sql and "count(" in tests_sql.lower())]
    out.append(_res("R4", "every raw table has a freshness or volume check", bad))

    # R5 static idempotency
    bad = [f"{n}: {', '.join(sorted(set(x.lower() for x in VOLATILE.findall(m['sql']))))}" for n, m in P.models.items()
           if VOLATILE.search(m["sql"])] + [f"{n}: incremental" for n in P.models if P.materialization(n) == "incremental"]
    out.append(_res("R5", "models are idempotent (static: no volatile functions, no incremental)", bad))

    # R6 every mart column classified
    bad = []
    for n in P.layer("marts"):
        missing = [c["name"] for c in P.cols(n) if not ((c.get("meta") or {}).get("classification")
                                                        or ((c.get("config") or {}).get("meta") or {}).get("classification"))]
        if missing:
            bad.append(f"{n}: {len(missing)} column(s) without meta.classification")
    out.append(_res("R6", "every mart column carries meta.classification", bad))

    # R7 one staging model per raw table, each with a tested key
    stg = P.layer("staging")
    bad = [f"{r}: {sum(r in P.models[s]['refs'] for s in stg)} staging models (need exactly 1)" for r in sorted(raw)
           if sum(r in P.models[s]["refs"] for s in stg) != 1]
    bad += [f"{s} has no unique+not_null key" for s in stg if not P.has_key_tests(s)]
    out.append(_res("R7", "one staging model per raw table, each with a tested key", bad))

    # R8 declared foreign keys have relationships tests
    fk_file = root / "architecture" / "foreign-keys.yaml"
    if fk_file.exists():
        bad = []
        for fk in yaml.safe_load(fk_file.read_text()).get("foreign_keys", []):
            col = next((c for c in P.cols(fk["model"]) if c["name"] == fk["column"]), None)
            if not col or "relationships" not in _tests_of(col):
                bad.append(f"{fk['model']}.{fk['column']} -> {fk['to']} has no relationships test")
        out.append(_res("R8", "declared foreign keys have relationships tests", bad))
    else:
        out.append(Result("R8", "SKIP", "declared foreign keys have relationships tests",
                          "architecture/foreign-keys.yaml not found"))

    # R10 every model described
    out.append(_res("R10", "every model has a description",
                    [f"{n} has no description" for n in P.models if not (P.yml_models.get(n) or {}).get("description")]))

    # R11 dependency direction
    bad = []
    for n, m in P.models.items():
        if m["layer"] == "staging":
            bad += [f"{n} (staging) refs non-raw {r}" for r in m["refs"] if r not in raw]
        elif m["layer"] == "marts":
            bad += [f"{n} (mart) refs non-staging {r}" for r in m["refs"] if r in P.models and P.models[r]["layer"] != "staging"]
    out.append(_res("R11", "marts ref only staging; staging refs only raw", bad))

    # R12 materialization
    bad = [f"{n}: staging is {P.materialization(n)}, want view" for n in stg if P.materialization(n) != "view"]
    bad += [f"{n}: mart is {P.materialization(n)}, want table" for n in P.layer("marts") if P.materialization(n) != "table"]
    out.append(_res("R12", "staging = view, marts = table", bad))

    # R17 reconciliation test
    ok = bool(re.search(r"sum\(", tests_sql, re.I)) and len(set(REF.findall(tests_sql))) >= 2
    out.append(Result("R17", "PASS" if ok else "FAIL", "reconciliation singular test exists",
                      "" if ok else "no tests/*.sql compares sum() across two or more models"))

    # R18 CI builds and lints
    wf = " ".join(p.read_text() for p in (root / ".github" / "workflows").glob("*.y*ml")) if (root / ".github" / "workflows").exists() else ""
    bad = [x for x, w in (("dbt build", "dbt build"), ("sqlfluff lint", "sqlfluff")) if w not in wf]
    out.append(_res("R18", "CI runs dbt build and sqlfluff lint", [f"CI missing: {b}" for b in bad]))

    # R19 no secrets committed
    bad = []
    for p in [root / "profiles.yml", root / "dbt_project.yml"] + list((root / "models").rglob("*.yml")) + list((root / "models").rglob("*.sql")):
        if p.exists() and SECRET.search(p.read_text()):
            bad.append(f"possible secret in {p.relative_to(root)}")
    out.append(_res("R19", "no secrets in the repo", bad))

    # database-backed rules: R9, R13, R14
    db_rules = [("R9", "documented columns match actual columns"), ("R13", "layers live in separate schemas"),
                ("R14", "raw layer is all text and carries load metadata")]
    if db and Path(db).exists():
        import duckdb
        con = duckdb.connect(str(db), read_only=True)
        try:
            actual: dict = {}
            for t, c, ty in con.execute("select table_name, column_name, data_type from information_schema.columns "
                                        "where table_schema not in ('information_schema','pg_catalog')").fetchall():
                actual.setdefault(t, []).append((c, ty))
            bad = []
            for n in P.layer("marts"):
                if n in actual and P.cols(n):
                    doc, act = {c["name"] for c in P.cols(n)}, {c for c, _ in actual[n]}
                    if doc - act:
                        bad.append(f"{n}: documented but absent {sorted(doc - act)}")
                    if act - doc:
                        bad.append(f"{n}: present but undocumented {sorted(act - doc)}")
            out.append(_res("R9", db_rules[0][1], bad))
            schemas = {r[0] for r in con.execute("select distinct table_schema from information_schema.tables "
                                                 "where table_schema not in ('information_schema','pg_catalog')").fetchall()}
            out.append(Result("R13", "PASS" if len(schemas) >= 3 else "FAIL", db_rules[1][1],
                              "" if len(schemas) >= 3 else f"only schemas: {sorted(schemas)}; need raw, staging, marts"))
            bad = []
            for r in sorted(raw):
                cols = actual.get(r, [])
                nontext = [c for c, ty in cols if ty not in ("VARCHAR", "TEXT")]
                nometa = not any(c in ("loaded_at", "_loaded_at", "batch_id", "_batch_id") for c, _ in cols)
                if cols and (nontext or nometa):
                    bad.append(f"{r}: {len(nontext)} non-text column(s)" + ("; no load metadata" if nometa else ""))
            out.append(_res("R14", db_rules[2][1], bad))
        finally:
            con.close()
    else:
        out += [Result(r, "SKIP", t, "needs a built database (--db)") for r, t in db_rules]

    out += [Result(r, "SKIP", "not machine-checked", why) for r, why in NOT_CHECKED.items()]
    return sorted(out, key=lambda r: int(r.rule[1:]))


def gate(results: list[Result], accepted: dict) -> tuple[int, list[str]]:
    msgs, code = [], 0
    for r in results:
        if r.status == "FAIL" and r.rule not in accepted:
            code = 1
            msgs.append(f"NEW VIOLATION {r.rule}: {r.title} :: {r.detail}")
        if r.status == "PASS" and r.rule in accepted:
            msgs.append(f"baseline can be tightened: {r.rule} now passes")
    return code, msgs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".")
    ap.add_argument("--db")
    ap.add_argument("--baseline")
    ap.add_argument("--paradigm")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    results = check(Path(a.project), Path(a.db) if a.db else None, a.paradigm)
    accepted = json.loads(Path(a.baseline).read_text()).get("accepted_failures", {}) if a.baseline else {}
    code, msgs = gate(results, accepted)
    if a.json:
        print(json.dumps([asdict(r) for r in results], indent=2))
    else:
        for r in results:
            tag = r.status + (" (baseline)" if r.status == "FAIL" and r.rule in accepted else "")
            print(f"{r.rule:<4} {tag:<18} {r.title}" + (f"\n       {r.detail}" if r.detail and r.status != "PASS" else ""))
        counts = {s: sum(x.status == s for x in results) for s in ("PASS", "FAIL", "SKIP")}
        print(f"\n{counts}   gate: {'PASS' if code == 0 else 'FAIL'}")
        for m in msgs:
            print(" -", m)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
