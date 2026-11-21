---
name: pattern-etl
description: Conventions for ETL pipelines - transform, cleanse or mask before loading. Use when project-profile paradigm is ETL, or for the pre-landing half of ETLT.
---

# ETL pattern

1. **Transform before load.** A transformation stage sits between extract and load; it runs
   outside the target (job server, container, orchestration worker).
2. **Masking and cleansing first.** Anything classified PII that must not land unmasked is
   masked, tokenised or dropped in this stage. Record the rule per column in the data
   architecture and test that no unmasked value reaches the target.
3. **Keep the stage deterministic and testable.** Pure functions over batches; unit tests with
   fixture files; the same input always produces the same output.
4. **Reject, do not repair silently.** Invalid records go to a quarantine location with a reason;
   rates above the agreed threshold stop the run and escalate (see guardrails in CLAUDE.md).
5. **Load idempotently.** Reruns upsert or replace by key; no duplicate loads on retry.
6. **Since raw is not kept,** document how to replay from the source system, and keep the
   extract files for the agreed retention period if policy allows.
7. **Observe the stage.** Row counts in, out and rejected per run; alert on shifts.

For ETLT, do only the cleansing, masking and light conformance here, then hand off to the
`pattern-elt` flow inside the warehouse.
