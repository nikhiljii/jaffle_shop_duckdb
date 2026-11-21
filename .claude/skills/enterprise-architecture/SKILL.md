---
name: enterprise-architecture
description: Guidelines for the system-level architecture of a data project - goals, constraints, integrations, security, non-functional requirements, cost. Use before any data architecture work.
---

# Enterprise / system architecture

Depth rule: for a data-engineering project, stay to about two pages. The goal is to fix the
boundaries and constraints the data architecture must respect, not to design the company.

## Steps

1. **Business goal and users.** One paragraph: what decision or product this data feeds, who
   consumes it, what happens if it is wrong or late.
2. **Constraints.** Regulation (GDPR, sector rules), data residency, budget ceiling, team skills,
   existing platforms that must be reused, deadlines.
3. **Integration landscape.** Every source and consumer with: owner, interface (file, API, DB,
   stream), volume, change frequency, who to call when it breaks. Unknown = write UNKNOWN.
4. **Security.** Classification of data handled, identity and access model, secrets handling,
   encryption in transit and at rest, audit needs.
5. **Non-functional requirements, with numbers.** Freshness, latency, availability, recovery
   time and point, volume growth, concurrency. "Fast" and "reliable" are not requirements.
6. **Build vs buy and technology choices.** For each major component, the options considered,
   the choice and the reason. Prefer the team's existing skills over fashionable tools.
7. **Deployment topology.** Environments (dev, staging, prod), promotion path, who approves.
8. **Cost.** Rough run cost and the biggest cost driver; what the ceiling is.
9. **Risks and open questions.** Ranked. Anything UNKNOWN that could change the design.

## Output: `architecture/system-architecture.md`

Headings: Goal, Constraints, Context diagram (text), Integrations table, Security, NFRs table,
Technology decisions (each linked to an ADR), Environments, Cost, Risks, Open questions.

## Checks before you stop

- Every NFR has a number and a way to measure it.
- Every source has an owner or is marked UNKNOWN.
- Every technology choice names the alternative that was rejected.
- Nothing here contradicts `project-profile.yaml`; if it must, update the profile via ADR.

## Anti-patterns

Designing for scale nobody asked for; picking tools before stating constraints; copying a
reference architecture without checking it fits the profile; hiding unknowns.
