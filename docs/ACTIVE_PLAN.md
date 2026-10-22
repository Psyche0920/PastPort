# PastPort Active Plan

Owner: wehan. Baseline: 2026-10-21. Specification: [PRD CN](PastPort_PRD_CN.md) / [PRD EN](PastPort_PRD_EN.md). Read [ownership and dependencies](PastPort_PRD_EN.md#s2-9), the assigned row and affected module code. This plan records work, not authorization or completion inferred from a document.

## Goal and current boundary

Deliver the single-player cartoon-style 360° museum and complete game-making workflow. Existing main is wire 0.1.0 with native inspect/caseboard tasks. The target contracts and synthetic reference kit are available for parallel development; the generic plugin host and real-material integration remain implementation work. External owners' implementation progress is unconfirmed. No paid calls, production publication, commits, pushes or deployments are authorized by this plan.

## Current tasks

| Task | Owner | Dependencies | Deliverable | Acceptance | Status |
|---|---|---|---|---|---|
| DOC-BASE Initial bilingual specification | wehan | Reviewed integrated requirements | CN/EN PRD, navigation, current plan and reference attachments | Section/interface parity, links, cleanup and unchanged production code | accepted (documentation checks; legacy gates tracked separately) |
| T0 Shared typed contracts | wehan | Fixed SDK/API reference | Strict models/Protocols, generated schemas and loaders | PRD C01; reject invalid/unknown data, preserve wire 0.1.0 | todo |
| T1 Connected VR tour | wehan | Actual phone/tour sample | Existing-format connected ZIP and original panoramas | Identity, return links and real capture/navigation evidence | todo; single panorama user-confirmed |
| T2 Source and museum pipeline | wcheung | Fixed contracts; T0 for integration; image gateway | IDML/Links reader, projection/matching/style transfer and museum output | C02–C05; real samples and explicit missing/ambiguous results | in_progress |
| T3 Story and museum filtering | maslan | Fixed corpus/museum; real T2 output for integration | NarrativeDraft, FilterReport, PresentationPackage | C06; retained tasks executable with actual museum | todo; external delivery unconfirmed |
| T4 Plugin and panorama host | wehan | T0 | Registry/isolation, lifecycle/actions/saves/results, panorama navigation | C08–C11/C15; real host plus old-package regression | todo |
| T5 Plugins and game maker | maslan | Fixed API; T4 for integration | Existing-task adapter, distinct interaction, bounded plugin builder and complete game output | C07/C08/C11; default 3×3 non-rotating drag puzzle on actual host | todo |
| T6 Complete automated assembly | wehan with wcheung/maslan | T2–T5 and real materials | Version-bound assembly, validation and recovery | C09/C12/C14; approval, budget, isolation and real playable slice | todo |
| T7 Second project reuse | all three | T6 accepted | Another project using the same SDK/host | C13; no site-specific engine branches | todo |
| ENG-DOC Documentation gate alignment | wehan | New documentation structure | Update legacy documentation gates and affected tests/CI discovery | Permit canonical bilingual PRD/reference material and explicit HTML anchors, reject obsolete duplicates; retain inventory/link checks | todo; code outside current documentation scope |

## Parallel work and handoff

wcheung and maslan can use fixed examples immediately while wehan implements T0. Test substitutes are not production adapters. Work in separate branches/worktrees, not three Agents writing one checkout. Shared types/schema/host files belong to wehan; business adapters and plugins have the ownership in PRD 2.9.

Handoff records exact revision, contract/API versions, entry point, input hashes, relevant commands/results and remaining limits. Use todo → in_progress → awaiting_integration/verifying → accepted; blocked work retains cause and next action. Real-material, provider, browser, mobile and human-play results remain separate.

## Open engineering issue

`tools/check_handoff.py` currently rejects every extra file under docs/ and assumes the former four-document layout. `tools/check_repository.py` also recognizes heading-derived anchors only, so it falsely rejects valid explicit HTML anchor IDs used for bilingual section parity. Both limitations must be updated under ENG-DOC before the existing documentation gates can pass for this structure. Production/tooling code is intentionally outside the current documentation task. Do not suppress the gate or claim a passing CI result.
