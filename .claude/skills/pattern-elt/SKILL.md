---
name: pattern-elt
description: Conventions for ELT pipelines - land raw data first, transform inside the warehouse in SQL. Use when project-profile paradigm is ELT, or for the in-warehouse half of ETLT.
---

# ELT pattern

1. **Extract and load without transforming.** Land source data as-is into the raw layer; keep
   source column names and values; add load metadata (loaded_at, source file or batch id).
2. **Transform in the warehouse.** Staging models clean and type (one per source table); marts
   model the business. Prefer SQL; keep logic in version-controlled models, not in the loader.
3. **Reprocessable by design.** Raw is the source of truth; any downstream table can be rebuilt
   from it. Never edit raw in place.
4. **Tests live next to models.** Not-null, unique, accepted values and relationships on
   staging and marts; freshness on sources.
5. **Incremental where volume demands it,** with a documented full-refresh and backfill path.
6. **Cost awareness.** Prefer views for light staging, tables for expensive or frequently read
   marts; note the biggest cost driver in the data architecture.
7. **No PII surprises.** If the profile requires masking before landing, ELT applies only after
   the cleansing step (see `pattern-etl`).

Typical stack hints: dbt (models, tests, docs), a warehouse (Snowflake, BigQuery, Databricks,
DuckDB for local), an ingestion tool or scripts for the load step.
