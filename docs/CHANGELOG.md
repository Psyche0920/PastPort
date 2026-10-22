# PastPort Change Log

Owner: wehan. Start at the 2026-10-21 initial documentation baseline; earlier drafting and discussion history is not retained here. Requirements: [PRD](PastPort_PRD_EN.md). Current implementation work: [Active Plan](ACTIVE_PLAN.md).

## 2026-10-22

### 10.22-weng-evidence-pipeline-refinement

- Delivery: Unified Vision Hotspot Pipeline (`tools/vision_hotspot_pipeline.py`), interactive 2D/360 Verification Studio (`tools/hotspot_studio.py`), rewritten operational skill (`skills/evidence-review/SKILL.md`), and comprehensive multi-location/multi-image workflow documentation in `skills/evidence-review/README.md`.
- Scope/status: Consolidated the heritage evidence spatial mapping pipeline. Renamed vision tooling to descriptive pipeline, removed temporary cross-branch comparison scripts, added batch processing across all 31 official monuments in `var/bursa_evidence.db` (306 spots persisted to `scene_hotspots`), refined SKILL.md with explicit tool instructions and links to `.agents/agents/agent.md`, and documented multi-image routing workflows.
- Verification: Batch pipeline ran across all 31 sites in `var/bursa_evidence.db`, generating 306 spots; Hotspot Studio verified at `http://localhost:8088`; repository and handoff checks passed offline gates.
- Limits: Local extraction, multimodal detection, and studio verification only. Live external model calls require environment keys (`GEMINI_API_KEY` / `OPENAI_API_KEY`). Integration with narrative reference (`T3` / `T6`) remains pending.

## 2026-10-21 — Initial bilingual PRD

- Deliverables: PastPort_PRD_CN and PastPort_PRD_EN, matching product/technical/topic sections, shared reference attachments, short navigation, active tasks and accepted design rationale.
- Scope: documentation and unchanged supporting contract examples. Production source, generated production contracts, workflow configuration and existing user changes are preserved.
- Verification: CN/EN contain the same 94 section IDs and all shared literal identifiers; independent document/link and source-preservation checks completed. Existing documentation gates need ENG-DOC for file layout and explicit anchors; this delivery does not claim passing CI or new runtime capabilities.
- Limits: generic host, new wire integration, real IDML/model results, browser/mobile and human-play acceptance remain in the plan. No paid call, commit/push or deployment is part of this delivery.

Record future meaningful verified deliveries here with exact scope, revision/report when available, actual checks and limits. Do not copy transcripts, old test counts or per-change archives into the team reading path.
