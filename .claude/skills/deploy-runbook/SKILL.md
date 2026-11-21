---
name: deploy-runbook
description: Steps and safety rules for staging, promoting and rolling back a pipeline release. Use for any deployment task.
---

# Deploy runbook

1. Stage: `python -m src.deploy stage --source FILE --root releases [--config CFG]`.
   It builds the release in isolation, runs every contract and checks the mart is non-empty.
2. If staging fails: stop. Report the failing checks. Do not alter the input to make it pass.
3. Present to the human: release id, config diff vs live, rows in/out, rows dropped.
4. Promote only with a named approver: `python -m src.deploy promote --root releases --release R --approver NAME`.
   Promotion only moves the `current` pointer; nothing is overwritten.
5. Verify: `python -m src.deploy status`; confirm live release and a rollback target exist.
6. Rollback (when a promoted release misbehaves): `python -m src.deploy rollback --root releases --approver NAME`.
   The bad release stays on disk for forensics. Record why in PLAN.md.

Never: promote an unstaged release, promote without an approver, delete a release directory,
or "fix" a failed smoke test by editing the data.
