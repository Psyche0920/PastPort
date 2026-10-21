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

The extracted database uses five relational tables (`var/bursa_evidence.db` and test database `var/test_evidence.db`).

| Table Name | Primary Key | Description |
|---|---|---|
| `projects` | `project_id` | Project-level scope identifier (for example `bursa` or `test-cluster`). |
| `sources` | `source_id` | Registered source files with origin, filename, and SHA-256 digest. |
| `sites` | `site_id` | Heritage monuments with district, category, and bilingual names/descriptions. |
| `assets` | `asset_id` | Image and panorama assets with safe relative paths, media types, and SHA-256 digests. |
| `claims` | `claim_id` | Historical facts, architectural styles, and artifact records linked to sites. |

## 360 Panorama Processing and Hotspot Authoring (Branch A)

This branch focuses on zero-AI, deterministic manual hotspot authoring connecting 360-degree equirectangular panoramas to SQLite heritage claims.

### 1. Panorama Asset Extraction
Panoramas exported from `PastPort-VR-Studio` (`pastport-tour.zip`) embed the equirectangular JPEG as a base64 Data URI inside `index.html`.
Extract the high-resolution 4096x2048 JPEG to `var/sources/panoramas/` using:

```bash
python tools/extract_panorama.py
```

### 2. Mock Test IDML and Database Setup
To test pipeline adaptability on arbitrary locations without touching official Bursa data, generate and ingest a mock computing heritage site ("Turing Retro-Computing Lab"):

```bash
python tools/create_mock_idml.py
python tools/ingest_test_cluster.py
```

This creates `var/sources/turing_lab.idml` and populates `var/test_evidence.db` with registered sites, claims, and the panorama asset.

### 3. Coordinate Conversion
PastPort represents interactive scene spots as integer coordinates normalized to `[0, 10000]` on equirectangular panoramas:
- $x = \text{round}\left(\frac{\text{yaw} + 180}{360} \times 10000\right)$
- $y = \text{round}\left(\frac{\text{pitch} + 90}{180} \times 10000\right)$

`tools/spot_converter.py` provides bidirectional conversion between viewer `(yaw, pitch)` and PastPort `Spot(x, y)`, as well as spherical great-circle angular distance calculation.

### 4. Manual Hotspot Authoring Tool
Run `tools/branch_a_handclick.py` to create a validated PastPort `Spot` contract linked to a target claim in SQLite:

```bash
python tools/branch_a_handclick.py --yaw 12.0 --pitch -8.0 --claim claim-turing-artifact-deepblue
```

Example verified output:
```json
{
  "spot_id": "spot-manual-claim-turing-artifact-deepblue",
  "site_id": "test-cluster-turing-retro-computing-lab",
  "x": 5333,
  "y": 4556,
  "spherical": {
    "yaw": 12.0,
    "pitch": -8.0
  },
  "text_key": "spot-manual-claim-turing-artifact-deepblue_desc",
  "claim_ids": [
    "claim-turing-artifact-deepblue"
  ],
  "authoring_method": "manual_handclick"
}
```

## Next Steps and Adapter Interface

The extracted database serves as the backing store for the `EvidencePort` interface in `src/pastport/ports/modules.py`:
- `inventory`: Scans and reports registered sources from `sources`.
- `index`: Exposes sites, candidate claims, and candidate assets from `sites` and `assets`.
- `research`: Answers narrative research queries and supplies route candidates.

