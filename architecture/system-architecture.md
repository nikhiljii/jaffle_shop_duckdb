# System architecture: jaffle_shop_duckdb

Status: PROPOSED, needs human approval. Facts come from the repo at commit 20cc904 (branch `duckdb`).

## Goal
A self-contained dbt + DuckDB demo/tutorial project (README: a "fictional app" with fake raw
data; seeds are used instead of sources "to make it self-contained"). It produces two
analytic tables, `customers` and `orders`. Consumers are learners and CI; no business decision
depends on it, so wrong or late data has no operational cost. Real business owner: UNKNOWN
(see OQ4). Whether this repo is to stay a demo or become a real pipeline is OQ5 and drives
everything below.

## Constraints
- Runs locally or in a devcontainer (Python 3.13, uv); no cloud account needed.
- dbt-core >=1.11 <2.0 (`require-dbt-version`); lockfile pins dbt-core 1.12.5, dbt-duckdb 1.11.0, duckdb 1.5.5; the last build used 1.12.7.
- Regulation / residency: none stated. Data is fictional. Budget: none stated, run cost ~0.
- DuckDB file allows one writer; README documents the lock error when a second process opens it.

## Context diagram (text)
```
seeds/*.csv --dbt seed--> main.raw_* --stg_* (views)--> main.customers, main.orders (tables)
                                  all inside jaffle_shop.duckdb (git-ignored)
Operator / CI: `dbt build` ; `dbt docs generate` ; ad hoc DuckDB CLI/Python reads
```

## Integrations
| Name | Direction | Interface | Volume | Change freq | Owner | Contact |
|---|---|---|---|---|---|---|
| raw_customers | in | CSV seed | 100 rows | static | UNKNOWN | UNKNOWN |
| raw_orders | in | CSV seed | 99 rows, 2018-01-01..2018-04-09 | static | UNKNOWN | UNKNOWN |
| raw_payments | in | CSV seed | 113 rows | static | UNKNOWN | UNKNOWN |
| customers, orders | out | DuckDB tables (CLI/Python/UI) | 100 / 99 rows | on build | UNKNOWN (CODEOWNERS: @dbt-labs/dx for the repo) | UNKNOWN |
| dbt docs site | out | `dbt docs generate` | n/a | on build | as above | UNKNOWN |

## Security
- Classification: no formal scheme. `models/schema.yml` labels `customers.first_name` and `last_name` as PII in descriptions only; values are fictional.
- Access: file-system permissions on `jaffle_shop.duckdb`; no roles. Secrets: none in repo (`profiles.yml` has only a file path). Encryption: none at rest or in transit (local file).
- Audit: git history only. Needs beyond that: UNKNOWN (OQ3).

## NFRs
| NFR | Value | How measured |
|---|---|---|
| Freshness | NONE DEFINED (profile uses 24 h as placeholder) | no monitor exists; OQ1 |
| Build time | not recorded; expected seconds at this volume | `dbt build` timing in target/run_results.json |
| Data quality | 20 tests, all passing at last build | `dbt build` exit code; 28 checks = 8 nodes + 20 tests |
| Availability / RTO / RPO | NONE DEFINED | OQ1; rebuild from seeds is the only recovery |
| Volume growth | none (static seeds) | n/a |
| Concurrency | 1 writer (DuckDB file lock); dbt threads: 24 | README lock note |

## Technology decisions
| Component | Choice | Rejected / alternative | Reason | ADR |
|---|---|---|---|---|
| Data movement | ELT recommended (scorer says ETLT) | ETL/ETLT | see ADR | ADR-001 |
| Transform | dbt Core, SQL + Jinja | Python models | existing repo | n/a (existing) |
| Engine | DuckDB via dbt-duckdb | cloud warehouse | self-contained demo. Alternatives were not documented in the repo | n/a (existing) |
| Packaging | uv + pyproject + lockfile, devcontainer | pip only | existing; requirements.txt generated for pip users | n/a (existing) |

## Environments
One target, `dev` (profiles.yml). No staging or prod, no promotion path. CI (`.github/workflows/validate_on_platforms.yml`) runs on push/PR to branch `duckdb` across macOS, Linux, Windows (PowerShell, cmd): `uv sync; dbt debug; dbt build; dbt docs generate;` then a sample query. No lint step (sqlfluff is configured, dialect duckdb, but not invoked in CI). No deploy, no schedule.

## Cost
Effectively zero (local file, free CI). Largest driver: CI minutes across 5 OS jobs.

## Risks (ranked)
1. Intent unknown: demo vs real pipeline (OQ5); the design standard to apply depends on it.
2. Doc/model drift already exists (customers: documented `total_order_amount`, actual `customer_lifetime_value`).
3. No source freshness/volume checks: acceptable for static seeds, wrong for any real source.
4. Currency/unit ambiguity: docs say AUD, a staging comment says "dollars".
5. Single writer and no backup; rebuild-from-seeds mitigates.

## Open questions
See the consolidated OQ list in `data-architecture.md`.
