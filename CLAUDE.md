# pipeline-guardian: end-to-end data engineering with a team of agents

Goal: take a data-pipeline request from idea to a safely deployed, monitored, self-checked
pipeline, with humans approving only what touches production.

## The team (see .claude/agents/)

| Agent | Owns | Never does |
|---|---|---|
| `architect` | System then data architecture, ADRs, conformance rules | Writes pipeline code or proceeds without approval |
| `orchestrator` | Turns a goal into a plan in PLAN.md, delegates, merges results, decides next step | Writes pipeline code, deploys, or scores its own team |
| `pipeline-builder` | Ingest + transform code in `src/pipeline.py`, data contracts, tests | Deploys, approves, edits evals |
| `deployment` | stage -> smoke -> promote -> rollback via `src/deploy.py` | Promotes without a named human approver |
| `incident` | Detect and diagnose broken runs via `src/incident_cli.py`, propose a fix | Touches production, applies fixes |
| `evaluator` | Independent scoring: tests, `src/evals.py`, scenarios; can veto a release | Edits pipeline code or the scenarios it scores against |

The evaluator is independent on purpose: no agent grades its own work.

## Skills (see .claude/skills/)

`data-contracts`, `pipeline-conventions`, `deploy-runbook`. Agents load a skill when the task matches it.

## Workflow for any request

0. Phase 0 gate: `architect` produces project-profile.yaml, ADR-001 (paradigm), system then data
   architecture. A human approves the pack before any builder runs. All agents conform to it.

1. Orchestrator reads this file and PLAN.md, writes/updates the plan (small, testable steps).
2. pipeline-builder implements; tests first; evaluator runs the suite and evals.
3. If evaluator passes, deployment stages and smoke-tests a release.
4. Orchestrator asks the human to approve promotion. Only then does `promote` run.
5. After release, incident agent handles failures; its proposals loop back through steps 2-4.
6. Orchestrator updates PLAN.md with state and open items. State lives in files, not in chat.

## Hard rules (every agent)

- Production changes need a named human approver. No exceptions, no "just this once".
- Never loosen a guardrail, gate, scenario or test to make something pass. Fix the cause.
- Actions stay a closed set (`src/diagnoser.py: ACTIONS`); a new action needs a guardrail test first.
- Escalate rather than hide: if a fix would drop more than 15% of rows, escalate.
- Report evidence (command output, scores), not impressions.

## Commands

```bash
python -m pytest -q                          # tests
python -m src.evals --diagnoser rules         # scorecard + hard gates (appends evals/history.jsonl)
python -m src.incident_cli --source FILE      # investigate a source file (toy pipeline)
dbt build --profiles-dir .                    # build the dbt project
python -m src.conformance --project . --db jaffle_shop.duckdb --baseline evals/conformance/baseline.json
python -m src.deploy stage --source FILE --root releases [--config cfg.json]
python -m src.deploy promote --root releases --release R --approver NAME
python -m src.deploy rollback --root releases --approver NAME
```
