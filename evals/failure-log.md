# Failure log (what broke, how it was measured, what changed)

## 2026-11-21 | architect on dbt-labs/jaffle_shop_duckdb, run 1
- Observed: scorer returned ETLT (ELT 4 / ETL 3) for a repo that is plainly ELT. The architect
  agent noticed, disagreed in the ADR and gave the reason, without silently overriding.
- Root cause: profile schema had no value for an embedded database, so `onprem_db` +
  `elastic_compute: false` was a forced fit that added ETL +3.
- Fix: added `embedded_warehouse` target type and a scorer rule; regression test
  `test_embedded_warehouse_is_not_forced_into_etl`. Re-score: ELT 7 / ETL 0.
- Also found by the architect (verified by hand): schema.yml documents `total_order_amount`
  but the model outputs `customer_lifetime_value`; 38 of 100 customers have NULL aggregates.
- Instruction gaps reported: PII field cannot express "present but fictional"; pattern-etl replay
  step assumes a real source system; a double-build idempotency check mutates the database.
- Evidence kept in `evals/architect-runs/jaffle_shop_duckdb/run1/`.

## 2026-11-21 | conformance checker vs architect's pack (cross-validation)
- Observed: `src/conformance.py`, written from the rules, failed R4, R6, R8, R9, R10, R13, R14, R17,
  R18 on the real repo. The architect's independent pack listed the same violations (plus R15 and
  R16, which need human judgement and are SKIP in the checker). Two separate methods agreed.
- Design change forced by the checker: R8 needs machine-readable foreign keys, so the architect now
  declares them in `architecture/foreign-keys.yaml`; R17 was generalised from jaffle-specific names
  to "a singular test compares sum() across two or more models".
- Test-design finding: a mutation can legitimately trip a second rule (R3->R6, R7->R10, R11->R7).
  Tests now declare expected collateral explicitly instead of assuming one rule per fault.
- Adoption method: ratchet baseline (`evals/conformance/baseline.json`), 9 accepted known
  violations with reasons; the gate fails only on NEW violations.
