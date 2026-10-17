# PastPort Decision Log

Owner: Wehan/Weijia. Important decisions only; proposed decisions are not authority. The schema and replacement rule live in [PRD §15](README.md#15-coding-agent-and-documentation-rules). Current work is in [Active Plan](ACTIVE_PLAN.md); completed deliveries are in [Change Log](CHANGELOG.md). Start at the present baseline; do not reconstruct old decisions.

For each new decision: `ID | date | status | owner | decision | reason/tradeoffs | affected scope | supersedes`.

## D-001 — Four-document collaboration and evidence-based completion

- Date: 2026-10-17. Status: accepted. Decision owner: Weijia; explicitly approved in this task.
- Decision: use the existing PRD/current guide plus separate Active Plan, Decision Log and Change Log. Route agents through short shared instructions and load relevant fragments only. Tasks need owner/dependencies/deliverable/acceptance/status; cross-module tasks use contract/reference checks, and player acceptance requires human feedback.
- Reason/tradeoffs: one oversized file obscures current tasks and decision rationale; many stage/per-change documents add reading and drift. Four authorities keep these concerns discoverable while adding a small maintenance duty. Update only affected entries and link to evidence.
- Affected scope: [PRD §15](README.md#15-coding-agent-and-documentation-rules), [Agent rules](../AGENTS.md), [Copilot rules](../.github/copilot-instructions.md), root/module navigation and documentation CI gate. Runtime contracts, approval rights and paid execution are unchanged.
- Supersedes: the earlier repository convention forbidding current plan/decision/delivery records; no old decisions or changelogs are backfilled. If replaced, mark this entry superseded and link the new accepted record rather than rewriting its rationale.
