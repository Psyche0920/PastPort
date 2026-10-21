# PastPort Decision Log

Owner: wehan. Initial baseline: 2026-10-21. Requirements live in [PRD](PastPort_PRD_EN.md); current work is in [Active Plan](ACTIVE_PLAN.md). This file records significant accepted choices and reasons, without reproducing discussion history or defining another interface.

## D-001 — One bilingual specification

Accepted, 2026-10-21. Product, technical and topic sections share one PRD in Chinese and English. Both editions use identical section/interface/acceptance IDs. Chinese meaning governs translation discrepancies. The implementation guide documents current executable behavior; plan, decisions and changelog stay short and link to the PRD. This reduces duplicate rules and team reading cost.

## D-002 — Shared host and reusable gameplay plugins

Accepted, 2026-10-21. main owns common lifecycle, resources, authoritative saves, validated outcomes and story effects. Plugins own local mechanics/state/rendering under API 1.0.0. In-scope new games add plugins/configuration; new public capabilities require an explicit versioned host change. Existing wire 0.1.0 behavior and saves remain compatible. See [PRD 2.4](PastPort_PRD_EN.md#s2-4) and [3.3](PastPort_PRD_EN.md#s3-3).

## D-003 — Automatic preparation and complete game delivery

Accepted, 2026-10-21. wcheung reuses IDML/Links, matches panorama objects and attaches traceable text. maslan generates then filters tasks against that same museum, prepares exact plugins/resources and invokes shared deterministic assembly for a complete game bundle. Reuse compatible plugins first; automatic development/repair is bounded and may fail explicitly. Rights, budgets and publication authority remain enforced. See [PRD 1.5–1.6](PastPort_PRD_EN.md#s1-5) and [part 3](PastPort_PRD_EN.md#part-topic).

For future significant changes record date, accepted/proposed status, owner, decision, rationale, affected version/sections and replacement relationship. A log entry does not grant approval, paid execution or deployment rights.
