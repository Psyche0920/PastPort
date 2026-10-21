# PastPort Change Log

Owner: Wehan/Weijia. Major verified deliveries from the current baseline only; earlier history is not reconstructed. Naming/update rules live in [PRD §15](README.md#15-coding-agent-and-documentation-rules). Current work is in [Active Plan](ACTIVE_PLAN.md), rationale in [Decision Log](DECISION_LOG.md).

Use a full-date heading and `MM.DD-owner-function` entry. Record delivery, scope/status, verification/evidence and remaining limits. Link to a PR/revision/report when available; never invent a link or claim a local check proves remote CI, professional approval or player acceptance. Keep all entries here, without per-change files.

## 2026-10-21

### 10.21-weng-branch-a-handclick-pipeline

- Delivery: Branch A 360 panorama extraction tool `tools/extract_panorama.py`, mock IDML generator `tools/create_mock_idml.py`, test database ingest tool `tools/ingest_test_cluster.py`, spherical coordinate converter `tools/spot_converter.py`, and manual hotspot authoring tool `tools/branch_a_handclick.py`. Documented in `skills/evidence-review/README.md`.
- Scope/status: Implemented end-to-end Branch A pipeline for interactive 360 panorama hotspot placement without AI dependencies. Extracted 4096x2048 equirectangular panorama from VR Studio tour export to `var/sources/panoramas/turing_lab_room.jpg`. Generated and ingested mock Turing Retro-Computing Lab into isolated `var/test_evidence.db` with registered site, asset, and 4 claims. Built bidirectional `(yaw, pitch) <-> (x, y)` converter and produced verified PastPort `Spot` contract mapped to target artifact claims.
- Verification: `tools/extract_panorama.py`, `tools/create_mock_idml.py`, `tools/ingest_test_cluster.py`, `tools/spot_converter.py`, and `tools/branch_a_handclick.py` executed cleanly; `tools/check_repository.py` and `tools/check_handoff.py` passed offline repository gates on `branch-a-handclick`.
- Limits: Manual hand-click authoring and local test database verification only. Production Bursa site panorama capture, formal `EvidencePort` adapter integration (`EVD-01`), and multi-scene narrative gameplay testing remain in progress.

## 2026-10-20

### 10.20-weng-evidence-extraction

- Delivery: Initial data extraction tool `tools/extract_bursa_sources.py`, SQLite heritage database schema, and evidence module documentation in `skills/evidence-review/README.md`.
- Scope/status: Ingested official Bursa heritage sources from `var/sources/archive.zip` without committing multi-gigabyte raw binaries. Extracted 31 heritage sites with bilingual descriptions across İznik, Orhangazi, and Yıldırım; registered 105 image assets with SHA-256 digests; created `var/bursa_evidence.db`.
- Verification: `tools/extract_bursa_sources.py` executed cleanly; `tools/check_repository.py` and `tools/check_handoff.py` passed offline repository gates.
- Limits: Preprocessing and local database ingestion only. Formal `EvidencePort` adapter implementation (`EVD-01`) and integration with the narrative reference matrix remain in progress.

## 2026-10-17

### 10.17-wehan-team-workflow

- Delivery: [DOC-01](ACTIVE_PLAN.md#current-tasks); implemented the four-document collaboration structure approved in [D-001](DECISION_LOG.md#d-001--four-document-collaboration-and-evidence-based-completion). Preserved the current codebase guide as PRD/architecture authority; added the current plan and decision/delivery records, without reconstructing earlier history.
- Scope/status: documentation and offline documentation gate, locally verified. Shared AGENTS/Copilot and module links route to the same rules: small tasks, fixed-reference module handoffs, explicit evidence, scoped context and player feedback. The existing CI quality job already runs this gate; its workflow configuration did not need changes.
- Verification: tools/check_repository.py and tools/check_handoff.py passed; tests/test_handoff_docs.py passed all 4 tests; Ruff lint/format and strict mypy passed for tools/check_handoff.py and tests/test_handoff_docs.py. Checks cover required authorities, shared Agent routes, module inventories and duplicate-document rejection.
- Limits: local documentation/tooling acceptance only. No runtime behavior, formal module delivery, professional content approval, paid-provider billing, human play quality, remote CI or production acceptance is inferred. Formal module/real-material verification remains in the current plan.


### 10.17-wehan-workflow-baseline

- Delivery: [BASE-01](ACTIVE_PLAN.md#current-tasks), the complete locally verified framework baseline for team handoff: typed module interfaces, replaceable evidence/narrative ports, shared metered execution, durable workflow/reviews/budgets/recovery, assembly/private release, shared JS player/saves, authenticated workbench and offline acceptance/CI tooling.
- Scope/status: implemented and integrated locally against synthetic reference modules. This is the first shared-baseline record, not a reconstruction of earlier stage history. Product publication remains disabled; Git delivery does not certify formal Weng/Mert modules or production readiness.
- Verification: all 422 Python tests passed; Ruff lint/format, strict mypy on 109 files, 39 contract schemas/fixtures, generated player contracts, JS syntax/rendering checks for 18 modules, Prettier and documentation gates passed. The current offline reference kit passed both module smokes and all four real workflow combinations. The synthetic real-browser scenario passed using installed local Chromium via an explicit override; matching default Playwright browser installation is left to the locked CI setup.
- Browser gate correction: wait for both the expected stage and its stable review/published status; the prior test could click before the worker committed the review state and trigger STATE_STALE. Version guards and all business assertions are retained.
- Limits: real-material history/rights, formal module outputs, paid providers/billing, human player understanding, remote CI and production require their own evidence. Git commit/ref identifies the shared source revision; temporary local reports/screenshots are not committed.
