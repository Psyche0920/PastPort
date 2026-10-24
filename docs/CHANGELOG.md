# Changelog

## 0.1.0 — standalone implementation

Status: implemented on the standalone development branch; not merged into main or deployed.

- Added one-command PDF/tour build using a fixed LangGraph workflow, bounded Codex SDK semantic execution, persistent identities, source-linked mapping/copy and local snapshots.
- Added numbered VR with transparent markers, click-to-read current copy, deep links to an editable review workbench, and per-view drag-release autosave. Human versions survive proposal regeneration; changed media/assignments do not inherit unrelated overrides.
- Retained explicit offline replay for the existing 37-object, 66-anchor demo. Original source files, old demo database and original service are not rewritten.
- Added native PDF extraction/Poppler rendering, data-only schema 3/4 tour import, panorama projections, whole-corpus retrieval, source crops/full-page references, claim scope checks, explicit gaps and durable run/execution journals.
- Added pinned optional Codex SDK and a reproducible uv dependency lock. Operator authentication stays local; no credential or private media is committed.

Evidence: 25 behavioral tests, strict typing, Ruff lint/format, JavaScript syntax checks and whitespace checks. Additional local native generated-PDF/Poppler-to-review verification used explicit semantic counterparts. SDK image capability and a small real-panorama sample were verified live. The small real sample exposed a possible cross-view column identity error; it remains unapplied and is recorded in the active plan. No complete real PDF/tour model run, second-site accuracy, main SDK/repository-checker success or cloud release is claimed.
