---
name: evidence-review
description: Extract, audit, and spatially map heritage records, claims, and 360/2D visual assets into SQLite databases and PastPort Spot contracts.
metadata:
  version: "1.0.0"
  owner: Weng
---

# Heritage Evidence Review & Spatial Mapping Skill

Module Owner: **Weng** (`T2` / `EVD-01`).
This skill guides the preparation, ingestion, auditing, and spatial mapping of heritage sources into validated PastPort Spot contracts.

## 1. Engineering & Code Guidelines

All code written or modified for this skill must adhere to the project standards in [.agents/agents/agent.md](../../.agents/agents/agent.md) and the bilingual PRD:
- **Architecture & PRD Specification**: Follow [PastPort PRD EN](../../docs/PastPort_PRD_EN.md#s2-6) (§2.6: reading, matching, projection and limits) and [IMPLEMENTATION_GUIDE.md](../../docs/IMPLEMENTATION_GUIDE.md#6-workflow-reviews-edits-and-bounded-routing).
- **OOP & SOLID**: Write strictly typed, object-oriented Python adhering to SOLID principles.
- **Simplicity First**: Avoid overcomplication, unnecessary abstractions, or dead code.
- **Calibration Reference**: For ambiguous images, conflicting claims, or spatial boundaries, consult [review examples](references/review-examples.md).
- **Security**: Never read, log, or commit `.env` files or API secrets.

## 2. Tools & Operational Commands

All tools live in `tools/` and run from the repository root:

| Tool | Command | Description |
|---|---|---|
| **Archive Ingestor** | `python tools/extract_bursa_sources.py` | Parses IDML stories/spreads from `var/sources/archive.zip` into `sites`, `claims`, and `assets` in SQLite. Automatically extracts media to disk. |
| **Pano Extractor** | `python tools/extract_panorama.py` | Extracts 4096x2048 equirectangular 360 JPEG from VR Studio tour zip to `var/sources/panoramas/`. |
| **Vision Pipeline** | `python tools/vision_hotspot_pipeline.py` | Multimodal AI detector locating claims on 360/2D images and saving spots directly to SQLite. |
| **Studio Viewer** | `python tools/hotspot_studio.py --db <db_path>` | Interactive local web server (`http://localhost:8088`) with dual 2D photo and 360 sphere inspection. |

### Vision Pipeline CLI Syntax
```bash
# Process a single monument
python tools/vision_hotspot_pipeline.py --db var/bursa_evidence.db --site bursa-ye-i-l-green-mosque

# Process all 31 monuments in batch
python tools/vision_hotspot_pipeline.py --db var/bursa_evidence.db --all

# Export Spot contracts to JSON
python tools/vision_hotspot_pipeline.py --db var/test_evidence.db --export var/spots.json
```
Backends supported via `--mode`: `auto` (default), `gemini`, `openai`, `mock`.

## 3. Database Schema

The evidence module produces a normalized SQLite database (`var/bursa_evidence.db` or `var/test_evidence.db`):

- **`projects`**: Scope identifier (`bursa`, `test-cluster`).
- **`sources`**: Registered source files with SHA-256 digests and origin.
- **`sites`**: Heritage monuments with bilingual names and district/category.
- **`assets`**: Image/panorama assets with relative paths and SHA-256 digests.
- **`claims`**: Segmented facts classified as `architectural_feature`, `historical_date`, or `historical_fact`.
- **`scene_hotspots`**: Clickable spot contracts linking `(spot_id, site_id, asset_id, claim_id, x, y, yaw, pitch, label, authoring_method)`.

## 4. Reference Datasets

- **Official Heritage Dataset**:
  - Archive: `var/sources/archive.zip` (Vakıf Eserleri Envanteri catalog).
  - Database: `var/bursa_evidence.db` (31 monuments, 105 photos, 306 claims).
  - Photographic Media: `var/sources/media/bursa/` (extracted from `Links/`).
- **Demo / Synthetic Reference Cluster**:
  - Mock IDML: `var/sources/turing_lab.idml` (generated via `tools/create_mock_idml.py`).
  - 360 Panorama: `var/sources/panoramas/turing_lab_room.jpg`.
  - Database: `var/test_evidence.db` (ingested via `tools/ingest_test_cluster.py`).

## 5. Execution Workflow

When fulfilling evidence review tasks, follow this order:
1. **Ingest Sources**: Run `extract_bursa_sources.py` to ensure `sites` and `claims` are populated in SQLite and images are extracted to disk.
2. **Resolve Visual Assets**: Ensure 360 panoramas or 2D photos are in `var/sources/media/bursa/` or `var/sources/panoramas/`.
3. **Execute Vision Pipeline**: Run `vision_hotspot_pipeline.py` to detect coordinates and populate `scene_hotspots`.
4. **Verify Visually**: Launch `hotspot_studio.py` to verify pin positions and claim associations in 2D or 360 mode.
5. **Quality Gates**: Run `python tools/check_repository.py` and `python tools/check_handoff.py` before completing work.
