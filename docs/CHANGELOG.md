# PastPort Change Log

Owner: wehan. Start at the 2026-10-21 initial documentation baseline; earlier drafting and discussion history is not retained here. Requirements: [PRD](PastPort_PRD_EN.md). Current implementation work: [Active Plan](ACTIVE_PLAN.md).

## 2026-10-21 — Initial bilingual PRD

- Deliverables: PastPort_PRD_CN and PastPort_PRD_EN, matching product/technical/topic sections, shared reference attachments, short navigation, active tasks and accepted design rationale.
- Scope: documentation and unchanged supporting contract examples. Production source, generated production contracts, workflow configuration and existing user changes are preserved.
- Verification: CN/EN contain the same 94 section IDs and all shared literal identifiers; independent document/link and source-preservation checks completed. Existing documentation gates need ENG-DOC for file layout and explicit anchors; this delivery does not claim passing CI or new runtime capabilities.
- Limits: generic host, new wire integration, real IDML/model results, browser/mobile and human-play acceptance remain in the plan. No paid call, commit/push or deployment is part of this delivery.

Record future meaningful verified deliveries here with exact scope, revision/report when available, actual checks and limits. Do not copy transcripts, old test counts or per-change archives into the team reading path.

## 2026-10-26 — Independent evidence, matched environment and stylization SDK packages

- Deliverables: `pastport-evidence`, `pastport-matched-environment` and `pastport-stylization` workspace distributions (the former Museum/PDF-to-VR package is named Matched Environment SDK; its included PDF-to-VR functionality is retained without a duplicate distribution), typed public import surfaces, source provenance, independent install/build instructions, and optional Main authoring dependencies. Matched Environment contains the 360° PDF-to-VR and 3D/shared-review capabilities. Stylization separately contains the appearance-processing workflows from `environment-stylization` and depends on Matched Environment's scene/review/execution contracts. No Story Demo, private tour, grant, or runtime data is included.
- Verification: Main's full suite passed 428 tests; SDK regressions passed Evidence 2/2, Matched Environment 46/46 and Stylization 3/3. Strict mypy passed Main/checkers/tests (112 files) and SDK sources/boundary tests (129 files). Final SDK wheels were independently installed without Main/Codex, with six CLI help commands and package resources checked. The locked default Main wheel installed/imported without SDK/provider packages; dependency checks passed. Browser acceptance passed with system Chrome on fresh synthetic data; offline module acceptance and the 84-case fault gate passed with unchanged source identity. Repository/handoff, lint/format, generated-contract, JS, lockfile and diff checks passed. CI now includes a required SDK test/build job.
- Review/fixes: one-way Matched Environment→shared-contract ownership and Stylization dependency; public transport helpers replace private cross-package access; base authoring/provider extras separated; standalone portal links/resources corrected; explicit-anchor/registered-reference gates aligned with negative tests. Core Main runtime code and wire 0.1.0 were unchanged.
- Limits: Main runtime budget/permission adapters, automatic Story generation and the generic game host remain implementation work. Real-material correctness/rights, live provider allowance/billing, human playtests, remote CI and production deployment were not certified. Private scenes, review databases, credentials and generated reports are excluded from the commit.
