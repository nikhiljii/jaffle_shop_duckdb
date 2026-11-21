# Data architecture: jaffle_shop_duckdb

Status: PROPOSED, needs human approval. Written on the ELT basis recommended in the ADR note;
rules that change under ETLT are marked. Observed facts come from the repo and from the built
`jaffle_shop.duckdb` (read-only).

## Paradigm
See `decisions/ADR-001-paradigm.md`. Scorer: ETLT (ELT 4 / ETL 3). Architect: ELT; disagreement
reasoned in the ADR. Actual behaviour of the repo is ELT (`dbt seed` lands, SQL transforms in DuckDB).

## Layers
| Layer | Where | What exists | Materialization |
|---|---|---|---|
| raw | schema `main`, tables `raw_customers`, `raw_orders`, `raw_payments` | loaded by `dbt seed` from `seeds/*.csv`; types inferred by dbt (INTEGER, DATE, VARCHAR), not all-text; no load metadata | table |
| staging | `models/staging/`, schema `main` | `stg_customers`, `stg_orders`, `stg_payments`: rename (`id`->`customer_id`/`order_id`/`payment_id`, `user_id`->`customer_id`) and `amount/100` | view |
| marts | `models/` root (no `marts/` folder), schema `main` | `customers`, `orders` | table |

All three layers share one schema (`main`). Staging models say "normally we would select from
the table here"; they read `ref('raw_*')` seeds rather than `source()`.

## Model
| Table | Meaning | Grain | PK | FKs | Owner |
|---|---|---|---|---|---|
| orders | order with payment totals per method | one row per order (99) | order_id | customer_id -> customers.customer_id | UNKNOWN |
| customers | customer with order facts and lifetime value | one row per customer (100) | customer_id | none | UNKNOWN |
| stg_customers / stg_orders / stg_payments | renamed copies of seeds | one row per source row (100/99/113) | customer_id / order_id / payment_id | stg_orders.customer_id -> stg_customers; stg_payments.order_id -> stg_orders (neither tested) | UNKNOWN |

Observed: 38 of 100 customers have no orders, so `number_of_orders`, `first_order`,
`most_recent_order` and `customer_lifetime_value` are NULL for them. This is not documented
or tested; whether NULL or 0 is intended is OQ7. Dates in data: 2018-01-01 to 2018-04-09.

Column drift: `models/schema.yml` documents `customers.total_order_amount`; the model outputs
`customer_lifetime_value` (undocumented). Documented column names `orders.amount` and the four
`*_amount` columns do exist.

## History
None. Everything is overwritten on rebuild (full refresh); no SCD, no snapshots, no incremental
models. Deletes and late-arriving data: not applicable to static seeds; any real source would
need a decision (OQ5).

## Physical design
No partitioning or clustering (not needed at ~300 rows). Per `dbt_project.yml`: default
`+materialized: table`, staging overridden to `view`. `threads: 24` in profiles.yml. Full
refresh each run is fine at this volume; revisit only if OQ5 says real data.

## Orchestration
Manual or CI only: `dbt build` (seed, run, test in DAG order). Dependency order is from `ref()`.
No schedule, retries or alerts. Backfill = rerun `dbt build` (seeds are static). Idempotent by
construction (full refresh, no `now()`/random in models; checked with grep).

## Quality contracts
Current: 20 tests, all passing. Raw: none. Staging: unique/not_null on each key; accepted_values
on `stg_orders.status` and `stg_payments.payment_method`. Marts: unique/not_null on keys;
`orders.customer_id` not_null + relationships; accepted_values on status; not_null on amount and
the four method amounts. Missing: raw row-count/schema/freshness; staging relationships;
reconciliation (e.g. sum(orders.amount) = sum(stg_payments.amount); customers lifetime value
consistent with orders).

## Governance and PII
| Column | Class (proposed; none exist in repo) | Rule |
|---|---|---|
| customers.first_name, last_name (and raw/stg copies) | PII (labelled in description only) | masking rule: none; values fictional, last name already an initial. Needed only if real data (OQ3) |
| all ids, dates, status, payment_method | internal | none |
| amounts (amount, *_amount, customer_lifetime_value) | internal | currency to be fixed (OQ8) |
Retention: none. Access by role: none (file permissions). Lineage: dbt docs graph (`dbt docs generate`), node colors in dbt_project.yml.

## Observability
None beyond dbt logs (`logs/dbt.log`) and `target/run_results.json`. No freshness/volume
monitors, no alert target, no runbook.

## Cost
Near zero. Biggest driver: CI across 5 OS jobs. Tuning lever per layer: not needed; if data grows,
raw -> external/parquet load, staging stays views, marts become incremental.

## Conformance rules
Status key: PASS = verified true now; VIOLATED = repo currently breaks it; NOT RUN = static check only.

| # | Rule | Check | Status |
|---|---|---|---|
| R1 | Raw tables hold source values unmodified; only `models/staging/*` may reference `raw_*`. | `grep -rn "ref('raw_" models \| grep -v models/staging` returns nothing | PASS |
| R2 | (ETL/ETLT only) No unmasked PII in the landing zone. | query `raw_customers` for names | N/A under ELT. If ETLT is approved: VIOLATED (`raw_customers` holds unmasked names) |
| R3 | Every mart has unique and not_null tests on its key. | manifest: tests on `customers.customer_id`, `orders.order_id` | PASS |
| R4 | Every source/raw table has a freshness or volume check. | `dbt source freshness` or a row-count test per raw table | VIOLATED (none exist; no `source()` used) |
| R5 | Every model is idempotent: no incremental, `now()`, `current_timestamp`, `random`. Two consecutive `dbt build` runs give identical row hashes. | grep (done, none found); double-build compare | PASS static; dynamic NOT RUN (would modify the db) |
| R6 | Every column in marts carries a classification (`meta.classification`); PII columns have a masking rule. | parse schema.yml for `meta.classification` on all mart columns | VIOLATED (only description text "PII") |
| R7 | Each staging model has unique and not_null on its key, one staging model per source table. | manifest | PASS |
| R8 | Every FK in the Model table has a `relationships` test. | manifest tests of type relationships | VIOLATED (only `orders.customer_id` is tested; `stg_orders.customer_id` and `stg_payments.order_id` are not) |
| R9 | Documented columns match actual columns for every mart. | compare schema.yml with `information_schema.columns` / `dbt docs` catalog | VIOLATED (`total_order_amount` documented, absent; `customer_lifetime_value` present, undocumented) |
| R10 | Every model has a description in YAML. | `dbt ls --resource-type model` vs descriptions in manifest | VIOLATED (the 3 staging models have none) |
| R11 | Dependency direction: marts reference only staging; staging reference only raw/sources. | grep `ref(` per folder | PASS |
| R12 | Materialization: staging = view, marts = table. | `dbt_project.yml` / manifest `config.materialized` | PASS |
| R13 | Layers live in separate schemas (raw, staging, marts). | `select distinct table_schema from information_schema.tables` has 3 | VIOLATED (all in `main`) |
| R14 | Raw layer is all text and carries load metadata (`loaded_at`, batch id). | `information_schema.columns` on `raw_*` | VIOLATED (INTEGER/DATE inferred; no metadata). Accepted deviation candidate for seeds (OQ5) |
| R15 | Monetary columns state currency and unit in YAML; docs and code agree. | read descriptions vs `stg_payments.sql` | VIOLATED (docs say AUD; code comment says dollars) |
| R16 | Mart aggregate columns define NULL behaviour for entities with no orders. | test or documented rule on `customers.number_of_orders`, `customer_lifetime_value` | VIOLATED (38 NULL rows, undocumented; intent unknown, OQ7) |
| R17 | Reconciliation: sum(orders.amount) = sum(stg_payments.amount); count(orders) = count(stg_orders). | singular test in `tests/` (`test-paths` points to a `tests` dir that does not exist) | VIOLATED (no such test) |
| R18 | CI runs `dbt build` on every PR and lints SQL (`sqlfluff lint`). | read workflow | build PASS; lint VIOLATED (sqlfluff configured, not run) |
| R19 | No secrets in repo; `profiles.yml` holds no credentials. | `grep -rniE "password\|secret\|token"` | PASS |

## Open questions
- OQ1: Freshness / availability / recovery targets, if any (none in repo; 24 h in the profile is a placeholder).
- OQ2: Will schemas ever drift? Profile says low only because the sources are static CSVs.
- OQ3: Is there any masking, retention or audit requirement? Decides ELT vs ETLT (R2).
- OQ4: Business owner, data owners and escalation contacts for each source and mart.
- OQ5: Is this to remain a demo (accept seeds-as-sources, R14 and R4 as deviations) or become a real pipeline with real sources?
- OQ6: Team size and SQL strength (profile value `high` is assumed).
- OQ7: Intended NULL vs 0 for customers with no orders.
- OQ8: Currency and unit of `amount` (AUD vs generic dollars; cents divided by 100).
- OQ9: Are the upstream CI branch `duckdb` and the `@dbt-labs/dx` CODEOWNERS relevant to a fork, or do they get replaced?
