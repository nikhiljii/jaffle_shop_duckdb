# PLAN.md (orchestrator owns this file; update after every step)

## Current state
- Pipeline: ingest -> transform -> publish on DuckDB, with contracts. DONE, tested.
- Incident logic: rule diagnoser + naive comparison, closed actions, guardrails, sandbox verify. DONE.
- Deployment tooling: stage/smoke/promote/rollback with approver gate. DONE, tested.
- Eval harness: 11 scenarios x 3 seeds, hard gates. DONE (rules baseline 100%, which is NOT generalisation evidence).
- Agent + skill files written (this commit). NOT yet exercised by Claude Code end to end.

## Phase 0 architecture gate: BUILT and exercised on this repo
- Layout follows the agreed tree: .claude/ (agents + skills), architecture/, profiles/, src/, evals/, tests/.
- Agents so far: orchestrator, architect, pipeline-builder, quality-engineer, deployment, incident, evaluator.
- src/profile.py, src/paradigm.py (ELT/ETL/ETLT scorer + ADR), src/conformance.py (R1..R19 checker with ratchet baseline).
- Test 1 done: architect produced the pack; conformance checker independently reproduced its violations. See evals/failure-log.md.
- Status: architecture pack is PROPOSED, awaiting human approval. 43 tests pass; dbt build 28/28.

## Next steps (in order)
0. Human approves the architecture pack (ADR-001 ELT) and the baseline. Then:
   - test 2: fault injection in seeds (rename, duplicates, nulls); needs a dbt adapter for the incident agent.
   - test 3: feature request through the orchestrator, e.g. fix R9/R10 or add a refunds mart; builder + quality-engineer + evaluator + deployment.
1. Run the orchestrator in Claude Code on a real request: "add a daily returns feed" and record what it gets wrong.
2. Held-out scenarios no rule was written for; the evaluator owns them, builder never sees them.
3. LLM diagnoser behind the same `Diagnoser` interface; compare against rules on the scorecard.
4. Replace DuckDB with a real warehouse trial; put one flow under Airflow or Dagster.
5. Scheduled monitoring run that calls the incident agent and writes findings to PLAN.md.
6. Case study: problem, architecture, scorecard history, failures found, lessons.

## Open questions
- Which real dataset/domain will the flagship demo use for the case study?

## Decisions log
- Agents coordinate through files (PLAN.md, audit logs, releases/), not shared chat memory.
