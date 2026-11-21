---
name: data-contracts
description: How to write data contract checks for a pipeline flow so failures are diagnosable. Use when adding or changing any check in src/pipeline.py.
---

# Data contracts

A contract check is a named, testable assertion about the data at a flow boundary.

- One check = one `Event(flow, check, ok, detail)`. Name checks by what they assert
  (`order_id_unique`), not by implementation.
- On failure, `detail` carries the evidence a diagnoser needs: counts, rates, a few sample
  values. Never a stack trace and never the whole table.
- Distinguish signals that look alike. Empty values and unparseable values are different
  checks, because they have different causes and different safe fixes.
- Run all checks within a flow and report every failure, so compound faults are visible.
  Stop only at a flow boundary: do not start `transform` if `ingest` failed.
- Every new check ships with a seeded fault in `src/faults.py` that trips it, plus a test.
- Thresholds are constants at the top of `src/pipeline.py`, never inline numbers.
