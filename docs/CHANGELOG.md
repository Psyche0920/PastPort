# Changelog

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
