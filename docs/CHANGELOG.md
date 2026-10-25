# Changelog

## Single-workflow cleanup — 2026-10-25

- Removed photo-to-PDF, raw-history matching and replay UI/CLI entries, exclusive
  services, old review frontend, prompts, fonts and their exclusive tests/resources.
- Kept matched PDF + fresh VR generation, its reference backend/viewer, bounded SDK
  execution, source provenance, uploads, persistence, process cleanup and recovery.
- Extracted shared atomic storage from removed replay composition. Legacy job files
  remain on disk and are hidden from this single-workflow portal. Existing inputs,
  databases, human edits and the saved user stash are untouched.
- Updated current documentation and dependency packaging to this scope.

No tests, model calls or service launches were performed for this cleanup, as
explicitly requested by the user. Manual runtime/output acceptance is pending with
the user. Earlier entries below describe historical versions, including removed
features; their check results are not verification of the cleaned revision.

## 0.1.0 — standalone implementation

Status: implemented on the standalone development branch; not merged into main or deployed.

- Added one-command PDF/tour build using a fixed LangGraph workflow, bounded Codex SDK semantic execution, persistent identities, source-linked mapping/copy and local snapshots.
- Added numbered VR with transparent markers, click-to-read current copy, deep links to an editable review workbench, and per-view drag-release autosave. Human versions survive proposal regeneration; changed media/assignments do not inherit unrelated overrides.
- Retained explicit offline replay for the existing 37-object, 66-anchor demo. Original source files, old demo database and original service are not rewritten.
- Added native PDF extraction/Poppler rendering, data-only schema 3/4 tour import, panorama projections, whole-corpus retrieval, source crops/full-page references, claim scope checks, explicit gaps and durable run/execution journals.
- Added pinned optional Codex SDK and a reproducible uv dependency lock. Operator authentication stays local; no credential or private media is committed.

Evidence: 25 behavioral tests, strict typing, Ruff lint/format, JavaScript syntax checks and whitespace checks. Additional local native generated-PDF/Poppler-to-review verification used explicit semantic counterparts. SDK image capability and a small real-panorama sample were verified live. The small real sample exposed a possible cross-view column identity error; it remains unapplied and is recorded in the active plan. No complete real PDF/tour model run, second-site accuracy, main SDK/repository-checker success or cloud release is claimed.

## Browser generation workbench

Status: implemented on the standalone branch; localhost-only, not main-integrated or cloud-deployed.

- Set new browser-run defaults to 20 calls / 250,000 recorded tokens after user approval; existing grants remain unchanged. Large inputs may stop with explicit budget gaps.
- Added a Chinese upload/generate portal with PDF and 360 HTML/folder/ZIP selection or drag/drop, finite model authorization/settings, persisted job/stage progress and project-scoped result links.
- Reused the existing fixed build, VR popups, drag-save and evidence editor; existing-project rebuilds preserve applicable human overrides. Interrupted jobs stop for reconciliation, with no automatic uncertain redispatch.
- Added bounded streamed uploads, safe archive extraction, single-job admission and local origin/host boundaries. Uploaded tour scripts and arbitrary host paths are not exposed.
- Published explicit format capabilities: PDF and current 360 exports work; IDML/Links and 3D remain reserved adapters, and INDD requires conversion. Read-only official Drive inspection confirmed those document/media formats.

Evidence: 31 behavioral tests pass; strict mypy across 63 source/test files, Ruff lint/format, JavaScript syntax and whitespace checks pass. Six new tests cover linked upload/build/rebuild with preserved human text, rejected formats/origins, archive safety, request byte limits, interruption and missing renderer. Browser verification on a separate offline fixture server exercised file choosers, submission/progress/completion, numbered popup and the linked source/editor. No real model calls were made for this UI delivery; no full live-material or second-site accuracy is claimed. Main's repository checker is absent from this independent branch, so its gates remain unverified.

## Evidence rejection and recovery — 2026-10-24

Implemented locally; not yet committed or pushed. Partial evidence assessment excludes invalid
claims/associations with explicit diagnostics, while keeping source validation strict and raw
model receipts immutable. Added explicit, input-bound evidence recovery with an append-only
reconciliation audit; unknown dispatches and changed grants remain blocked.

The authorized actual Ulucamii recovery completed with gaps: 14 objects, 21 anchors, three
historical assignments, and three rejected minbar-balustrade background claims. All 23 previous
execution receipts were reused unchanged; no additional model usage occurred. Local project
VR/review and result APIs respond successfully. Validation: 33 tests, strict typing across 63
source/test files, Ruff and whitespace checks. Main's repository checker is absent; no full
semantic accuracy, second-site validation or release is claimed.


## Reference environment Agent Skill — 2026-10-25

Added a repository-local Skill and two deterministic preparation/assembly commands. The
active Codex Agent inspects each new PDF/tour, records identity, evidence, structural relations
and fresh locations, then produces the demonstrated linked review/VR format. No old database,
private input, matching answer or hotspot dataset is packaged. Existing upload, SDK budget,
photo-mapping and recovery functionality remains available as a separate workflow.

Verification: 41 offline tests, strict typing across 71 files, Ruff, Skill validation and
whitespace checks pass. New tests vary PDF, object numbering, viewpoint counts and relative
image packaging; they reject stale measurements, fabricated source quotes, invalid structure
and unsafe HTML in evidence descriptions. A known corrected real-material handoff reproduces
14 candidates/25 anchors. This verifies assembly and format, not equal fresh visual judgment
on an unseen project. Static schema 4 panoramas are supported; 360 video and hardware-specific
acceptance remain unimplemented or unverified. The main repository checker is absent.


## Browser matched-PDF environment automation — 2026-10-25

Integrated the default matched-PDF/new-VR upload stage with metered Codex SDK
execution and the demonstrated reference renderer. No interactive Codex session or
user-authored handoff JSON is needed. The optional repository Skill and SDK use a
shared business policy. Existing raw-PDF matching and photo-to-PDF remain selectable.

The input PDF's internal links can index complete numbered evidence entries and
photographic selections, with full-scan fallback for other layouts. Printed source
IDs and exact native quotations are preserved; a misnumbered quotation is only
reanchored when its exact text has a unique registered page, with an audit record.
A historical part may have an unrepresented parent without inventing a catalog ID.
Every new VR uses fresh measurements; 4K panoramas retain original geometry while
model previews obey their own size bounds. Overlay audits and whole/part review
exclude unconfirmed positions and structural parts. CSV snapshots reflect exclusion
states. Budget checks now reserve the observed cost of a proposal/audit pair where
available, avoiding a clearly unaffordable unreviewed next proposal.

Each run retains its own DB and result URL; identical inputs/model/policy in the
same project reuse the existing DB and human edits without further inference.
Owned local reference servers load only packaged code, survive ordinary data
reloads without regeneration, and close with Studio. Jobs expose actual counts,
gaps and failure stage. Explicit validation recovery retains settled receipts and
usage; uncertain dispatches are not retried. Original local PDF-evidence edits
remain in their earlier named Git stash.

Evidence: 53 offline behavioral tests; strict mypy across 76 source/test files;
Ruff lint/format, JavaScript syntax and whitespace checks. Browser navigation
opened the real review database and two-view reference VR. The actual supplied
40-page PDF and two 4096×2048 panoramas completed with 15 evidence records and nine
audited hotspots, with explicit gaps. Nine settled SDK calls consumed 266,471
recorded tokens, including two diagnostic requests before validation fixes; the
threshold stops subsequent calls and is not a hard per-call token cap. The second
view's final proposals were not audited after the threshold, and the part proxy
remained excluded pending physical proof. The later pair-cost guard is covered by
a deterministic budget test; no additional live inference was used to rerun it.

The user will manually assess output quality and report targeted issues. This
release verifies the automatic chain, not equivalence of all semantic judgments,
new-site accuracy, main integration, 360-video support or cloud deployment. The
main repository checker is absent from this standalone branch.

## Optional Marble 3D stage

Added a separate 3D handoff after panorama matching: consistent source backup,
existing-export import, explicit one-generation API entry and saved-operation polling,
real SPZ/GLB loading and free movement, camera alignment, ray-derived candidates,
manual anchor confirmation and versioned saves. Existing panorama generation/viewing
remains available. Source matches and human edits are copied, not rematched or reset.

One unrelated real indoor-video export completed asset/database attachment with no
new inference or credits. It is not same-scene alignment or museum business acceptance.
New Python passes local strict typing; syntax/lint checks cover the changed code.
No paid generation, automated test suite or browser/device acceptance was run.

## Simplified 3D frontend and separate records

Each completed VR record now opens its own 3D generation page with the source bound
automatically. The main form shows project, session-only API key and a single explicit
generation action; existing Marble export import remains collapsed. Homepage VR and
3D records are separate. 3D records read persistent local status, expose output and
query-original-task actions, and never trigger provider work on refresh. Native output
links remain available via the API. Key values are not returned, logged or saved.

New API/domain types pass strict typing, lint and Python/JS syntax checks. The current
workbench was reloaded without active tasks and retains the imported 14-object result.
No real key, paid generation or automatic test suite was used for this UI delivery.

## Pre-payment safeguards and portable scene output

Fixed generation backup parent creation and made repeated frontend requests reuse
the source result's persistent generation job. Added a version-bound source-fidelity
policy and portable ZIP export containing SPZ, collision GLB, metric transforms,
stable object/evidence JSON, original media/PDFs and a consistent review snapshot.
Unconfirmed anchors stay withheld; full textured visual mesh is not claimed.

Ten isolated checks with network disabled and simulated provider responses passed,
plus a real local-asset ZIP export check. No real key, provider call or paid export
was used. Actual provider billing, generated fidelity and engine import remain unverified.

## Existing 3D viewer load repair

Added the missing Three.js 0.180.0 Pass module required by Spark, its import-map
entry and the local static allowlist. Updated only viewer resources in the existing
output. Browser inspection now shows the saved scene and camera movement. No model
regeneration, asset changes, review DB reset or additional generation cost occurred.
The user's original trial settled at 1,500 credits. Spatial calibration and semantic
acceptance remain pending.
