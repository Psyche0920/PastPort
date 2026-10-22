# Heritage Evidence Review Module

Module owner: Weng.
This module prepares, extracts, and audits heritage source materials, site records, and image mappings for PastPort.

## Resource Locations and Paths

Raw archive files, media assets, and generated local databases are kept under `var/`, which is ignored by Git to prevent repository bloat.

| Resource Type | File Path | Description |
|---|---|---|
| Raw Archive | `var/sources/archive.zip` | Original organizer archive containing IDML files and linked image directories. |
| Extracted Sample | `var/sources/idml_sample_yesil/` | Pretty-printed XML inspection directory for InDesign stories and layouts. |
| SQLite Evidence DB | `var/bursa_evidence.db` | Normalized SQLite database containing extracted sites, sources, and assets. |
| Media Output | `media/bursa/` | Game-ready relative image paths referenced in the database and resource catalog. |

## Archive Extraction and Zip Handling

The runtime agent does not execute zip extraction commands inside the skill. In PastPort:
1. Ingestion is an offline preprocessing step performed before running the workflow.
2. The extraction tool reads `var/sources/archive.zip` directly in streaming memory using Python's standard `zipfile` library.
3. Manual unzipping of the 2 GB archive to disk is not required to build or update the database.
4. If manual XML inspection in an editor is needed, unpack single IDML files using:
   `python -c "import zipfile; zipfile.ZipFile('path/to/file.idml').extractall('var/sources/target_folder')"`

## Database Generation and Updates

The SQLite database is populated and updated using `tools/extract_bursa_sources.py`.

### Initial Generation
Run the extraction script from the repository root:

```bash
python tools/extract_bursa_sources.py
```

This creates `var/bursa_evidence.db` with foreign key enforcement and indexes.

### Updating When New Resources Are Added
The extraction script uses parameterized `INSERT OR REPLACE` operations keyed on unique SHA-256 digests and stable identifiers:
- When a new IDML or image is added to `var/sources/archive.zip` (or an updated zip replaces the old one), rerun the exact same command:
  `python tools/extract_bursa_sources.py`
- Existing identical records remain unchanged.
- Modified files are updated based on their new content hash.
- New sites, sources, and assets are inserted without duplicating existing records.

## Database Schema

The extracted database uses four relational tables.

| Table Name | Primary Key | Description |
|---|---|---|
| `projects` | `project_id` | Project-level scope identifier (for example `bursa` or `test-cluster`). |
| `sources` | `source_id` | Registered source files with origin, filename, and SHA-256 digest. |
| `sites` | `site_id` | Heritage monuments with district, category, and bilingual names/descriptions. |
| `assets` | `asset_id` | Image and panorama assets with safe relative paths, media types, and SHA-256 digests. |
| `claims` | `claim_id` | Historical facts, architectural styles, and artifact records linked to sites. |
| `scene_hotspots` | `spot_id` | Validated clickable spot contracts with normalized [0..10000] coordinates and spherical yaw/pitch. |

## Multi-Location & Multi-Image Pipeline Workflow

When scaling to real heritage archives (e.g., 31 monuments, 105 photographs, and 306 claims), the evidence pipeline operates in five automated stages:

```
┌────────────────────────────────────────────────────────┐
│  STAGE 1: Ingestion & Relational Linking               │
│  - 31 Sites extracted (Yeşil Mosque, Ayasofya, etc.)   │
│  - 105 Photos extracted from archive Links/            │
│  - 306 Claims extracted from InDesign monographs       │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│  STAGE 2: Location-to-Asset Mapping                    │
│  - InDesign IDML spreads link images and text frames.  │
│  - Photos on spread #9 automatically belong to site #9.│
│  - Stored in SQLite: assets.site_id = site.site_id     │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│  STAGE 3: Claim-to-Image Routing (Two-Phase Matching)  │
│  A site has multiple photos (facade, mihrab, dome).    │
│  For each claim (e.g., "The minaret is made of brick"):│
│                                                        │
│  Phase 3A: Candidate Relevance Filter                  │
│  - Keyword match (claim: "minaret" -> photo: "facade") │
│  - Or ask Vision LLM: "Which photo shows the minaret?" │
│                                                        │
│  Phase 3B: Spatial Localization                        │
│  - Selected Image + Claim -> Vision LLM                │
│  - Outputs normalized [x, y] in [0..10000]             │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│  STAGE 4: Database Persistence & Spot Contracts        │
│  - Writes to SQLite scene_hotspots table:              │
│    (spot_id, site_id, asset_id, claim_id, x, y, conf) │
│  - Every spot explicitly binds its asset_id & claim_id │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│  STAGE 5: Visual Verification Studio                   │
│  - Curators open the studio at http://localhost:8088   │
│  - Inspect pins rendered on 360 panorama or 2D image   │
│  - Spots marked with purple VISION AI badge            │
└────────────────────────────────────────────────────────┘
```

## Tools and CLI Usage

### 1. Ingestion Tool (`tools/extract_bursa_sources.py`)
Extracts monuments, image asset references, and segmented claims from the raw archive into SQLite:

```bash
python tools/extract_bursa_sources.py
```

### 2. Panorama Extractor (`tools/extract_panorama.py`)
Extracts stitched equirectangular 360 images from VR Studio tours:

```bash
python tools/extract_panorama.py
```

### 3. Vision Hotspot Pipeline (`tools/vision_hotspot_pipeline.py`)
Automated multimodal spatial detector that reads claims from SQLite, runs vision detection, and saves spots directly to `scene_hotspots`:

```bash
# Process a single monument
python tools/vision_hotspot_pipeline.py --db var/bursa_evidence.db --site bursa-ye-i-l-green-mosque

# Batch-process all 31 monuments in the database
python tools/vision_hotspot_pipeline.py --db var/bursa_evidence.db --all

# Export Spot contracts to JSON for the game engine
python tools/vision_hotspot_pipeline.py --db var/test_evidence.db --export var/test_spots.json
```

- **Supported Backends** (`--mode`):
  - `auto`: Automatically selects active API key or falls back to offline mock.
  - `gemini`: Google `gemini-1.5-flash` via standard HTTPS.
  - `openai`: OpenAI `gpt-4o-mini` via standard HTTPS.
  - `mock`: Deterministic offline spatial predictor for local testing and CI gates.

### 4. Verification Studio (`tools/hotspot_studio.py`)
Web viewer for visual review and curation of placed hotspots:

```bash
python tools/hotspot_studio.py --db var/bursa_evidence.db
```

Open `http://localhost:8088`. Select any monument from the top dropdown to see its claims and interactive 360 spots.

## Reference Sample (Demo Cluster)

For offline verification without the full 2 GB archive, a synthetic reference cluster is provided:
- Mock IDML package: `var/sources/turing_lab.idml` (created via `tools/create_mock_idml.py`).
- 360 Panorama: `var/sources/panoramas/turing_lab_room.jpg`.
- Test SQLite database: `var/test_evidence.db` (ingested via `tools/ingest_test_cluster.py`).

## Next Steps and Adapter Interface

The extracted database serves as the backing store for the `EvidencePort` interface in `src/pastport/ports/modules.py`:
- `inventory`: Scans and reports registered sources from `sources`.
- `index`: Exposes sites, candidate claims, and candidate assets from `sites` and `assets`.
- `research`: Answers narrative research queries and supplies route candidates.
