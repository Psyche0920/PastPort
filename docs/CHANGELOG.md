# Photo Document Tool — Changelog

## 2026-10-24 — Document generation implementation

Implemented the fixed photo inventory, historical PDF matching, exact/scope-aware evidence and
paired PDF/IDML export on this branch. Prior delivery commit: `cb67cfc` (nested module layout).
Offline acceptance used two synthetic photo views, real PDF extraction and Poppler rendering;
one identity, five PDF pages and six resolving IDML image links were produced. Repeated runs
added no fixture dispatch. Strict mypy and Ruff passed. No live inference was made in that delivery.
Native Adobe InDesign and a full fresh real-material run remain pending.

## 2026-10-24 — Independent root layout

Moved the document tool to the repository root. Removed inherited main framework, game/VR code,
main schemas, references, unrelated tests/CI and framework-only documents. Replaced the main-only
repository checker with standalone source/document checks; strict mypy and Ruff remain required.
Root locked installation and command help passed, as did strict typing over 42 Python files,
Ruff and the standalone checker. Runtime records and operator files were preserved and ignored.
No live model call, main modification or new native-IDML acceptance is claimed.
