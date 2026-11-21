---
name: data-architecture
description: Guidelines for the data architecture of a pipeline project - layers, modeling, keys, history, partitioning, lineage, contracts, PII, orchestration. The primary design skill for data engineering projects.
---

# Data architecture

This is the main design document for a data-engineering project. Every agent conforms to it.

## Decisions to make, in order

1. **Paradigm** (ELT, ETL, ETLT): from `src.paradigm` and ADR-001. Confirm or challenge it.
2. **Layers.** Default: `raw` (landed as-is, all text, never edited) -> `staging` (typed, renamed,
   deduplicated, one model per source table) -> `marts` (business-facing, modeled). Under ETL or
   ETLT, state exactly what is cleansed or masked *before* landing and where that code runs.
3. **Modeling approach**, with the reason: dimensional (Kimball) for BI reporting and stable
   questions; Data Vault for many sources and heavy audit/history needs; wide flat tables only
   for narrow, single-purpose consumers.
4. **Entities and grain.** For each mart table: business meaning, grain ("one row per order"),
   primary key, foreign keys, owner.
5. **History.** Which attributes need slowly changing handling (SCD type 1 or 2), and which are
   overwritten. Say how deletes and late-arriving data are handled.
6. **Keys and identity.** Natural vs surrogate keys, how cross-source identity is resolved.
7. **Physical design.** Partitioning, clustering, incremental vs full refresh per model, and the
   reason (volume, freshness SLA, cost).
8. **Orchestration pattern.** Dependencies, schedule, retries, backfill procedure, idempotency.
9. **Data quality contracts per layer.** Raw: row count, schema, freshness. Staging: types,
   not-null, unique keys. Marts: reconciliation, accepted values, relationships.
10. **Governance.** Classify every column (public, internal, confidential, PII). State masking,
    retention, access by role, and lineage tooling.
11. **Observability.** Freshness and volume monitors per source; who is alerted; the runbook.
12. **Cost and performance.** Expected volumes, biggest cost driver, one tuning lever per layer.

## Output: `architecture/data-architecture.md`

Headings: Paradigm (link ADR-001), Layers, Model (entity table with grain and keys), History,
Physical design, Orchestration, Quality contracts, Governance and PII, Observability, Cost,
Conformance rules, Open questions.

## Conformance rules (the evaluator checks these; write them as numbered, testable rules)

Examples of the form to use:
- R1: raw tables hold source values unmodified; no business logic in raw.
- R2: under ETL or ETLT, no unmasked PII column exists in the landing zone.
- R3: every mart table has a unique/primary key test and a not-null test on that key.
- R4: every source has a freshness or volume check.
- R5: every model is idempotent; re-running yields the same result.
- R6: every column carries a classification; PII columns have a masking rule.
Add project-specific rules; each must be checkable by a command or a query.

Declare every foreign key in `architecture/foreign-keys.yaml` (model, column, to, field) so rule R8 can be checked by a command.

## Checks before you stop

- Each mart table states its grain and key.
- Every rule is testable; vague rules ("data should be clean") are rewritten or removed.
- Open questions are listed, not guessed.
