"""Toy three-flow ETL (ingest -> transform -> publish) on DuckDB with data contracts.

Every flow emits Events. A failed contract check is an Event with ok=False and a
detail dict that carries the evidence a diagnoser needs. The pipeline is
configured only through `Config`, so every remediation is a reviewable config
change, never an edit to code or to production data.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field, asdict
from pathlib import Path

import duckdb

EXPECTED_COLS = ["order_id", "customer_id", "amount", "currency", "order_ts", "status"]
MIN_ROWS = 100            # baseline volume is ~200 rows/day
MAX_NULL_RATE = 0.02      # contract: at most 2% empty amounts


@dataclass
class Config:
    column_map: dict = field(default_factory=dict)  # source column -> expected column
    dedupe: bool = False
    quarantine_null_amount: bool = False
    decimal_comma: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Event:
    flow: str
    check: str
    ok: bool
    detail: dict = field(default_factory=dict)


@dataclass
class RunResult:
    events: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return any(not e.ok for e in self.events)

    def failures(self) -> list:
        return [e for e in self.events if not e.ok]


def run_pipeline(source: Path, db_path: Path, cfg: Config) -> RunResult:
    res = RunResult()
    source = Path(source)

    # ---------------- flow 1: ingest ----------------
    if not source.exists():
        res.events.append(Event("ingest", "file_exists", False, {"path": str(source)}))
        return res
    res.events.append(Event("ingest", "file_exists", True))

    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            "create or replace table raw_orders as "
            "select * from read_csv(?, header=true, all_varchar=true)",
            [str(source)],
        )
        cols = [r[0] for r in con.execute("describe raw_orders").fetchall()]
        for src, dst in cfg.column_map.items():
            if src in cols and dst not in cols:
                con.execute(f'alter table raw_orders rename column "{src}" to "{dst}"')
        cols = [r[0] for r in con.execute("describe raw_orders").fetchall()]
        missing = [c for c in EXPECTED_COLS if c not in cols]
        extra = [c for c in cols if c not in EXPECTED_COLS]
        if missing:
            res.events.append(Event("ingest", "schema", False, {"missing": missing, "extra": extra}))
            return res
        res.events.append(Event("ingest", "schema", True))

        n_raw = con.execute("select count(*) from raw_orders").fetchone()[0]
        res.stats["rows_raw"] = n_raw
        if n_raw < MIN_ROWS:
            res.events.append(Event("ingest", "volume", False, {"rows": n_raw, "min_rows": MIN_ROWS}))
            return res
        res.events.append(Event("ingest", "volume", True, {"rows": n_raw}))

        # ---------------- flow 2: transform ----------------
        amt = "nullif(trim(amount), '')"
        amt_num = f"replace({amt}, ',', '.')" if cfg.decimal_comma else amt
        unparseable = con.execute(
            f"select count(*) from raw_orders where {amt} is not null "
            f"and try_cast({amt_num} as double) is null"
        ).fetchone()[0]
        sample_bad = [
            r[0]
            for r in con.execute(
                f"select amount from raw_orders where {amt} is not null "
                f"and try_cast({amt_num} as double) is null limit 3"
            ).fetchall()
        ]
        ok = unparseable == 0
        res.events.append(Event("transform", "amount_parse", ok,
                                {} if ok else {"unparseable": unparseable, "sample": sample_bad}))

        con.execute(
            f"""create or replace table stg_all as
                select order_id, customer_id,
                       try_cast({amt_num} as double) as amount,
                       ({amt} is null) as amount_empty,
                       currency, order_ts, status,
                       row_number() over (partition by order_id) as rn
                from raw_orders"""
        )
        where = []
        if cfg.dedupe:
            where.append("rn = 1")
        if cfg.quarantine_null_amount:
            where.append("not amount_empty")
        clause = (" where " + " and ".join(where)) if where else ""
        con.execute(
            "create or replace table stg_orders as "
            "select order_id, customer_id, amount, amount_empty, currency, order_ts, status "
            f"from stg_all{clause}"
        )
        n_stg = con.execute("select count(*) from stg_orders").fetchone()[0]
        res.stats["rows_stg"] = n_stg
        res.stats["rows_dropped"] = n_raw - n_stg

        null_rate = con.execute(
            "select coalesce(avg(case when amount_empty then 1.0 else 0.0 end), 0) from stg_orders"
        ).fetchone()[0]
        ok = null_rate <= MAX_NULL_RATE
        res.events.append(Event("transform", "amount_nulls", ok,
                                {} if ok else {"null_rate": round(null_rate, 4)}))

        dups = con.execute(
            "select count(*) - count(distinct order_id) from stg_orders"
        ).fetchone()[0]
        ok = dups == 0
        res.events.append(Event("transform", "order_id_unique", ok,
                                {} if ok else {"duplicates": dups, "dup_rate": round(dups / max(n_stg, 1), 4)}))

        if res.failed:
            return res

        # ---------------- flow 3: publish ----------------
        con.execute(
            """create or replace table mart_daily_revenue as
               select cast(try_cast(order_ts as timestamp) as date) as day, currency,
                      count(*) as orders, sum(amount) as revenue
               from stg_orders group by 1, 2"""
        )
        mart_total = con.execute("select coalesce(sum(revenue),0) from mart_daily_revenue").fetchone()[0]
        stg_total = con.execute("select coalesce(sum(amount),0) from stg_orders").fetchone()[0]
        ok = abs(mart_total - stg_total) < 1e-6
        res.events.append(Event("publish", "reconciliation", ok,
                                {} if ok else {"mart": mart_total, "stg": stg_total}))
    finally:
        con.close()
    return res


def read_context(source: Path, n: int = 20) -> dict:
    """Evidence about the source file that a diagnoser may inspect (read-only)."""
    source = Path(source)
    if not source.exists():
        return {"exists": False, "header": [], "sample": []}
    with source.open(newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        sample = [row for _, row in zip(range(n), reader)]
    return {"exists": True, "header": header, "sample": sample}
