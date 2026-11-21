# pipeline-guardian

An incident agent for data pipelines. It detects a broken run, diagnoses the cause from
evidence, proposes a fix from a closed set of actions, proves the fix in a sandbox, and
waits for a named human before touching production. Success is measured by an eval
harness with seeded faults and ground truth, not by opinion.

```
source file -> [ingest] -> [transform] -> [publish]      (DuckDB, data contracts per flow)
                   |            |             |
              failed contract checks  --->  Diagnoser (rules | naive | LLM later)
                                                |  proposes ONE action from a closed set
                                       guardrails + sandbox re-run
                                                |
                  OK | PROPOSED (needs approval) | ESCALATED (human decides)
```

## Run it

```bash
pip install duckdb pytest
python -m pytest -q                      # 10 tests
python -m src.evals --diagnoser rules     # scorecard, appended to evals/history.jsonl
python -m src.evals --diagnoser naive --no-save
```

## Safety design (enforced in `src/agent.py`, not in the diagnoser)

- Agent only runs against a throw-away sandbox DB.
- Actions come from a closed allow-list; anything else is rejected.
- A "fix" that drops more than 15% of rows, or quarantines more than 5% nulls, is blocked.
- Production is written only by `apply_to_prod()`, which refuses without a named approver.
- Every step is appended to an audit log.

## Scenarios (11 x 3 seeds)

clean, missing file, renamed column (two variants), unrelated column swap, 4% nulls,
30% nulls, 10% duplicates, volume drop, decimal comma, compound (rename + duplicates).
The judgment cases matter most: 30% nulls, volume drop and the unrelated column swap
must ESCALATE, because a "successful" patch there would hide an upstream defect.

## Honest limits

- The rules diagnoser scores 100% because the scenarios and rules were written together.
  Treat that as a regression baseline, not evidence of generalisation.
- The data is synthetic and small. Nothing here has met a real warehouse yet.
- No LLM diagnoser yet. It plugs into `DIAGNOSERS` and is scored by the same harness.

## Next

1. LLM diagnoser (Claude API, structured output validated against the action allow-list).
2. Held-out scenarios the rules have never seen, so the LLM and rules can be compared fairly.
3. Swap DuckDB for a real warehouse (Snowflake/BigQuery trial) and a real orchestrator
   (Airflow/Dagster) for one flow.
4. Orchestrator over the three flows; scheduled runs; case-study write-up.
