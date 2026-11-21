# ADR-001: Data movement paradigm for jaffle_shop_duckdb

Status: PROPOSED (needs human approval before any build)

## Decision

**ELT**

## Scores

ELT 7 vs ETL 0 (hybrid margin 3)

## Reasons

- [ELT +3] embedded analytical engine runs SQL transforms in-process at no extra cost
- [ELT +2] raw data must be kept for reprocessing and audit
- [ELT +2] transformations are SQL and the team is SQL-strong

## Consequences

- Land raw data first, transform in the warehouse; use the `pattern-elt` skill.
- Any change to this decision needs a new ADR that supersedes this one.

## Revision note

First run scored ETLT only because the profile schema had no honest value for an embedded
database (see the architect's original note, kept in the pipeline-guardian repo under
`evals/architect-runs/jaffle_shop_duckdb/run1/`). The schema gained `embedded_warehouse`; the
scorer now returns ELT, which matches what the architect recommended and what the repo does.
Still PROPOSED until a human approves.
