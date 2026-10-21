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

## 360 Panorama Processing and Vision LLM Pipeline (Branch B)

Branch B automates the hotspot authoring workflow by pairing multimodal vision models directly with the SQLite heritage claims and stitched 360 equirectangular panoramas.

### 1. Panorama Asset Extraction
High-resolution 360 equirectangular images (4096x2048) exported from VR Studio (`PastPort-VR-Studio/output/pastport-tour.zip`) are extracted using:

```bash
python tools/extract_panorama.py
```

This writes game-ready panoramas directly into `var/sources/panoramas/turing_lab_room.jpg`.

### 2. Automated Vision Spot Detector
Multimodal vision models analyze the 360 panorama and locate target heritage objects described in claims:

```bash
python tools/branch_b_vision.py --db var/test_evidence.db
```

- **Inputs**: Equirectangular 360 panorama image + heritage claims from SQLite.
- **Model Prompting**: Model is instructed to predict normalized center coordinates `[x, y]` in `[0..10000]`, where `x` maps to yaw `[-180°..+180°]` and `y` maps to pitch `[-90°..+90°]`.
- **Supported Backends**:
  - `auto`: Automatically selects active API key or falls back to offline mock.
  - `gemini`: Google `gemini-1.5-flash` via standard HTTPS.
  - `openai`: OpenAI `gpt-4o-mini` via standard HTTPS.
  - `mock`: Deterministic offline mode for local testing and CI gates.
- **Output**: Automatically writes validated spot records directly into SQLite `scene_hotspots` with `authoring_method='vision_llm'`.

### 3. Visual Verification Viewer (Hotspot Studio)
To visually inspect and verify the spots detected by the Vision AI in a web browser:

```bash
python tools/hotspot_studio.py --db var/test_evidence.db
```

Open `http://localhost:8088`. Placed spots are loaded from `scene_hotspots`, rendered as interactive 360 pins, and marked with a `VISION AI` badge.

### 4. Cross-Branch Accuracy Benchmark
To verify Vision LLM spatial accuracy against human-authored ground truth:

```bash
python tools/compare_branches.py --db var/test_evidence.db
```

Computes great-circle angular distance on the 360 sphere. Pass threshold: angular error <= 15.0°.

## Next Steps and Adapter Interface

The extracted database serves as the backing store for the `EvidencePort` interface in `src/pastport/ports/modules.py`:
- `inventory`: Scans and reports registered sources from `sources`.
- `index`: Exposes sites, candidate claims, and candidate assets from `sites` and `assets`.
- `research`: Answers narrative research queries and supplies route candidates.
