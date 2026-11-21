---
name: pipeline-conventions
description: Project conventions for flows, config-driven remediation and tests. Use before adding a flow or changing pipeline behaviour.
---

# Pipeline conventions

- Flows are ingest -> transform -> publish; each reads the previous flow's table.
- Behaviour changes through `Config` only. A remediation is a config diff that can be reviewed,
  stored in a release manifest and rolled back.
- Idempotent by construction: tables are `create or replace`; re-running the same input gives
  the same output.
- Raw layer stays all-varchar; typing happens in transform, so bad values are measured, not lost.
- Anything that drops rows records how many (`rows_dropped`) so guardrails can see it.
- Tests: `tests/` mirrors modules; run `python -m pytest -q` before reporting done.
- Do not add dependencies without saying why in the report.
