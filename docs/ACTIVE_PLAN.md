# PastPort Active Plan

Plan owner: Wehan/Weijia. Current baseline: 2026-10-17. Read the current task plus relevant [PRD](README.md) sections/module README; [D-001](DECISION_LOG.md#d-001--four-document-collaboration-and-evidence-based-completion) defines the agreed collaboration structure. Full rules live in [PRD §15](README.md#15-coding-agent-and-documentation-rules), deliveries in [Change Log](CHANGELOG.md).

## Current goal and limits

Enable Weng and Mert to validate their replaceable modules against a fixed reference counterpart, then validate both together on the shared workflow/player. Framework/reference checks establish infrastructure behavior; they do not certify formal module delivery, professional evidence/rights, paid providers or human gameplay quality. External owners' progress is unconfirmed; verification tasks below do not claim their implementations are missing or complete. Dates and owner availability need confirmation; no deadline is inferred.

DOC-01 changed collaboration instructions and their offline gate. The current user task additionally authorizes committing and pushing this validated framework baseline to the shared repository; it does not authorize paid calls, production publication/deployment, merging other work or edits to official data. Shared wire 0.1.0 and gameplay profile t1a-single-task remain current (§1).

## Current tasks

| Task | Owner / acceptance owner | Dependencies | Deliverable | Acceptance | Status |
|---|---|---|---|---|---|
| DOC-01 Shared collaboration rules | Wehan / Weijia | Agreed D-001; current codebase guide | Four authorities, shared Agent/Copilot routes, module delivery links and documentation gate | Structure/links, handoff tests, Ruff/strict typing for changed tooling; final diff | accepted (local documentation gate) |
| BASE-01 Validate the complete shared framework baseline | Wehan / local engineering gates | Current code, locked dependencies, shared contracts and DOC-01 | Complete source/docs/CI baseline ready for team handoff; current verification | Full pytest, static/type/schema/JS checks, four-combination reference acceptance and synthetic real-browser workflow | accepted (local baseline gate) |
| EVD-01 Verify formal evidence module | Weng / Weng + Wehan for integration | Trusted evidence factory/version and resource mapping; fixed reference narrative | Versioned evidence adapter and reproducible check result; known limits | Single evidence check plus selected-evidence/reference-narrative matrix using current §5 contracts | todo; external delivery status unconfirmed |
| NAR-01 Verify formal narrative module | Mert / Mert + Wehan for integration | Trusted narrative factory/version; fixed reference evidence | Versioned narrative adapter and reproducible check result; known limits | Single narrative check plus reference-evidence/selected-narrative matrix using current §5 contracts | todo; external delivery status unconfirmed |
| INT-01 Verify joint workflow/player | Wehan / Weng + Mert for respective boundaries | EVD-01, NAR-01; agreed contract/implementation revisions | Both selected factories run together, matching resources, private preview/save results and failure details | Existing four-combination runner passes for the exact declared revisions; public publication remains unavailable | todo |
| PLAY-01 Validate one real playable slice | Mert / Mert; Weng approves evidence/rights | Compatible adapters/content inputs; traceable real material and permission for the test scope | A source-dependent inference, character choice and later visible consequence; human observations and prioritized fixes | Agree protocol/sample/threshold first; observe goal clarity, evidence use, consequences and blockers; record results separately from software checks | todo; protocol and input readiness unconfirmed |

## Continuation and blockers

- DOC-01: local structure/links and handoff checks passed; 4 documentation-gate tests, Ruff lint/format and strict mypy for the 2 changed Python files passed. Delivery evidence is in [10.17-wehan-team-workflow](CHANGELOG.md#1017-wehan-team-workflow). This records local engineering verification, not a human content approval or remote CI run.
- BASE-01: 422 Python tests passed; strict mypy passed on 109 files, 39 schemas/fixtures matched, player contracts and 18 JS modules/rendering checks passed, and Ruff/Prettier formatting passed. Reference module smoke/four-combination acceptance passed. The real-browser workflow passed using installed local Chromium via an explicit executable override; the default expected browser binary was absent. Fixed the browser test to wait for both the stage and its stable status before a version-bound preview. Git sharing and remote CI remain separately observable through the pushed revision/Actions; local checks do not establish formal-module or human acceptance.
- EVD-01 / NAR-01: obtain factory entry, exact implementation revision, dependencies/resources, command/results and cancellation/cleanup limits from the module owner. Keep the other reference fixed; do not assume another owner's progress.
- INT-01: run when both declared implementations are available; failed/skipped/not_run gates remain visible and return to the responsible owner. Commands and factory differences are in [PRD §5](README.md#5-independent-modules-and-composition).
- PLAY-01: confirm protocol/participants and material readiness; no human experience acceptance is currently claimed. Findings become small tasks here; any important scope change also updates the PRD/Decision Log.

Task fields: `owner | dependencies | deliverable | acceptance | status`. Use todo → in_progress → accepted; add awaiting_integration/verifying only when useful. On blocked/needs_changes, keep cause and next action. For incomplete sessions add affected paths and verification performed to this section. Do not copy transcripts, full test logs, completed-task history or the full PRD into the plan.
