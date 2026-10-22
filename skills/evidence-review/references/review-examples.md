# Evidence Calibration and Review Examples

This reference provides calibration standards for both historical claim verification (text analysis) and visual spatial grounding (multimodal vision AI). Use these cases to evaluate agent and model performance against official Bursa heritage assets and reference clusters.

## 1. Three Statements That Must Not Collapse Into One

1. **Modern Observation**: A publication photograph shows an octagonal marble pool or pointed relieving arch. This is supported only by direct inspection of the image asset.
2. **Historical Period Claim**: The pool or arch existed and served a specific architectural or religious function in the 1430s. This is a separate time-scoped claim requiring documentary evidence.
3. **Creative Narrative / Game Fiction**: A fictional character or narrative prop was placed beside that pool. This belongs in game design, not archaeological fact.

The same visual asset can corroborate Statement 1 without corroborating 2 or 3. Valid reviews narrow findings rather than conflating modern visual presence with historical proof or game fiction.

## 2. Calibration Review Examples

| ID | Input Case & Target | Unacceptable Judgment / Mistake | Expected Calibration Action |
|---|---|---|---|
| **E01** | Photo of courtyard + claim of 15th-century madrasa space (`bursa-yildirim-irgandi-bridge`) | Treat a modern glass skylight or tourist barrier as a 1430s feature because the photo is from an official catalog | Separate present-day observation from period claim; identify original locator; do not assert historical date from modern photo alone. |
| **E02** | Fictional quest prop or NPC dialogue in story script | Cite an in-game delivery note or NPC confession as corroboration for a historical event | Classify as `original_fiction`; isolate game logic from historical graph; do not insert historical support edges. |
| **E03** | Image in archive `Links/` without explicit spread binding | Assign `mapping_state: verified` to a monument merely because both are located in Osmangazi | Maintain `mapping_state: provisional` until verified by IDML spread link or document index; require human or catalog proof. |
| **E04** | Two municipal websites quoting the same inventory paragraph | Score as two independent primary sources to inflate source confidence | Record a single origin lineage; seek genuinely independent primary records where disputed facts exist. |
| **E05** | Legacy claim with `publication_state: approved` | Accept legacy state without verifying cryptographic hash or author | Mark as legacy metadata; schedule pending re-review unless signed decision and source hash match. |
| **E06** | Neighboring monuments in catalog folder | Assume a walkable direct corridor or specific transit time between two sites | Require explicit survey or road evidence; folder proximity is not a physical connection. |
| **E07** | External research lead found only in web snippet | Cite an uninspected paywalled book as an inspected primary source | Register as an unretrieved lead; record failure; never fabricate citation text or page numbers. |
| **E08** | 2D perspective photo from `Links/` folder | Treat $(x, y)$ planar coordinates as equirectangular $(\text{yaw}, \text{pitch})$ spherical angles | Distinguish planar 2D images from 360 panoramas; store normalized $[0, 1]$ coordinates for 2D and compute spherical angles only for panoramas. |
| **E09** | Multimodal Vision AI detects modern lighting fixture | Label a modern spotlight or security camera as an Ottoman architectural feature | Reject modern electrical fixtures; bind hotspot strictly to historical masonry, tilework, calligraphy, or arches. |
| **E10** | Non-visual abstract claim (e.g. endowment charter date) | Hallucinate pin coordinates on arbitrary wall or decorative panel | Bind claim to an inscription plaque or general monument info panel; do not invent coordinate points for non-spatial facts. |
| **E11** | 360 Panorama seam boundary $(\text{yaw} \approx \pm 180^\circ)$ | Bounding box coordinates wrap around image edge, causing invalid geometry | Split or clamp bounding box at boundary seam; ensure center point lands correctly on the target feature. |
| **E12** | Extreme lighting or oblique camera perspective | Low-confidence vision detection accepted without review flag | Set `authoring_method: ai_vision_gemini` with confidence score; route low confidence $(< 0.70)$ to human review in Hotspot Studio. |

## 3. Visual Grounding Calibration: 2D Photos vs 360 Panoramas

- **2D Perspective Photos (`Links/` folder)**:
  - Coordinate system: Normalized $(x, y) \in [0.0, 1.0]$ relative to image dimensions.
  - Verification: Open image in standard viewer or Hotspot Studio 2D mode; pin must align with visual feature center.
- **360 Equirectangular Panoramas**:
  - Coordinate system: $\text{yaw} \in [-180.0^\circ, +180.0^\circ]$, $\text{pitch} \in [-90.0^\circ, +90.0^\circ]$.
  - Verification: Open in Hotspot Studio spherical viewer; verify hotspot orientation relative to camera center.

## 4. Weng's Calibration Task & Quality Gate

For each model run:
1. **Compare Model Output Against Expected Boundaries**: Verify entity, time period, retrievable source locator, and coordinate precision.
2. **Enforce Database Schema Integrity**: Verify that all generated spots populate `scene_hotspots` in SQLite (`var/bursa_evidence.db` or `var/test_evidence.db`) and match the `Spot` contract schema.
3. **Audit Critical Failures**: Unsupported claims, fabricated locators, and misaligned spatial pins block production release.
4. **Follow Engineering Guidelines**: Maintain strict compliance with [.agents/agents/agent.md](../../../.agents/agents/agent.md).

