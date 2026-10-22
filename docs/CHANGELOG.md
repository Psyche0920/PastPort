# PastPort Change Log

Owner: wehan. Start at the 2026-10-21 initial documentation baseline; earlier drafting and discussion history is not retained here. Requirements: [PRD](PastPort_PRD_EN.md). Current implementation work: [Active Plan](ACTIVE_PLAN.md).

## 2026-10-22

### 10.22-weng-evidence-pipeline-refinement

- Delivery: Unified Vision Hotspot Pipeline (`tools/vision_hotspot_pipeline.py`), physical museum object extractor (`tools/extract_bursa_sources.py`), interactive 2D/360 Verification Studio with object and dossier separation (`tools/hotspot_studio.py`), SDK v1 MuseumPackage exporter (`tools/export_museum_package.py`), rewritten operational skill (`skills/evidence-review/SKILL.md`), and comprehensive multi-location/multi-image workflow documentation in `skills/evidence-review/README.md`.
- Scope/status: Consolidated the heritage evidence spatial mapping pipeline. Transitioned from unstructured sentence pinning to distinct physical architectural objects (`museum_objects` schema: Mihrab, Minbar, Dome, Portal, Revetment, Calligraphic Plaque, Courtyard, Tomb, Minaret, Arches, Windows), separating abstract historical claims into a reference dossier. Added per-asset pin filtering in Hotspot Studio so images only display pins belonging to their view. Exported validated SDK v1 `MuseumPackage` (`var/museum.json`: 31 views, 60 connections, 120 museum objects, 120 museum entries, 285 anchors) for downstream narrative and game assembly handoff.
- Verification: Batch pipeline ran across all 31 sites in `var/bursa_evidence.db`, generating 120 objects and 285 scene spots; Hotspot Studio verified with clean object cards and per-asset pins; `tools/export_museum_package.py` verified and strictly validated against SDK schema rules; repository checks run and reported per AGENTS.md limits.
- Limits: Local extraction, multimodal detection, studio verification, and offline SDK package export only. Live external model calls require environment keys (`GEMINI_API_KEY` / `OPENAI_API_KEY`). Downstream integration with narrative filtering (`T3`) and game bundle assembly (`T6`) remains pending external team work.

## 2026-10-21 — Initial bilingual PRD

- Deliverables: PastPort_PRD_CN and PastPort_PRD_EN, matching product/technical/topic sections, shared reference attachments, short navigation, active tasks and accepted design rationale.
- Scope: documentation and unchanged supporting contract examples. Production source, generated production contracts, workflow configuration and existing user changes are preserved.
- Verification: CN/EN contain the same 94 section IDs and all shared literal identifiers; independent document/link and source-preservation checks completed. Existing documentation gates need ENG-DOC for file layout and explicit anchors; this delivery does not claim passing CI or new runtime capabilities.
- Limits: generic host, new wire integration, real IDML/model results, browser/mobile and human-play acceptance remain in the plan. No paid call, commit/push or deployment is part of this delivery.

Record future meaningful verified deliveries here with exact scope, revision/report when available, actual checks and limits. Do not copy transcripts, old test counts or per-change archives into the team reading path.
