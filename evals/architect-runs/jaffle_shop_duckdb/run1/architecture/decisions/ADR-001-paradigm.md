# ADR-001: Data movement paradigm for jaffle_shop_duckdb

Status: PROPOSED (needs human approval before any build)

## Decision

**ETLT**

## Scores

ELT 4 vs ETL 3 (hybrid margin 3)

## Reasons

- [ETL +3] target has limited compute; transform before loading
- [ELT +2] raw data must be kept for reprocessing and audit
- [ELT +2] transformations are SQL and the team is SQL-strong

## Consequences

- Cleanse and mask before landing (`pattern-etl`), then transform in-warehouse (`pattern-elt`).
- Any change to this decision needs a new ADR that supersedes this one.

## Architect's note (added by the architect; the scorer output above is unmodified)

The scorer says ETLT (ELT 4 vs ETL 3, inside the hybrid margin of 3). **I disagree with
acting on that verdict; my recommendation is ELT.**

- The +3 for ETL comes from `target.elastic_compute: false`, a field I set by judgement.
  DuckDB here is an embedded, single-process, 1.6 MB database holding ~300 seed rows.
  There is no compute pressure that would justify transforming before load. If the field is
  set to `true` the scorer returns ELT 7 / ETL 0 -> ELT. The enum offers no value for
  "embedded local database", so the field is a forced fit, not evidence.
- ETLT's consequence is "cleanse and mask before landing". The repo has no pre-landing stage,
  no requirement to mask (the only PII is two fictional name columns, last name already an
  initial), and nothing to cleanse. Adding such a stage would be design for a need nobody stated.
- What the repo really does is ELT: `dbt seed` lands CSVs unmodified as `raw_*`, then SQL models
  in the database transform them (staging views, mart tables).

Proposed resolution for the human approver: approve **ELT** by explicit override
(`paradigm: ELT` in project-profile.yaml) in a superseding ADR-002, or confirm ETLT if a
masking requirement exists (open question OQ3). I have left `paradigm: auto` and not
overridden anything. The data architecture is written on the ELT basis and flags which rules
change if ETLT is chosen.
