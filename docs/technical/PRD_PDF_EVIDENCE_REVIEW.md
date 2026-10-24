# PDF Evidence Preparation and Review Workbench — Technical PRD

Owner: wehan. Date: 2026-10-24. Status: implementation specification derived from a local editorial experiment; software acceptance pending. Target repository: PastPort. Scope: phase A, photo/PDF preparation and review. This document does not implement phase B, VR recognition and hotspot attachment.

## 1. Decision and delivery boundary

Build a repeatable workflow whose **inputs are scene photographs and a heritage source PDF**, whose **operator interface is an evidence/mapping review workbench**, and whose **exported products are a new comparison PDF and a versioned structured dataset**. The new PDF uses the scene photographs as targets and attaches supported historical descriptions, source images or clearly labelled documentary evidence.

The workbench is a tool for generating, inspecting and correcting the products; it is not a second content artifact or a separate service with duplicate permissions. Reuse PastPort's existing project, resources, execution controls, review authority and UI shell.

Phase A has a dedicated development branch based on main. A later phase B may use another branch and the same backend/domain identities. Branches organize development; durable functional separation is by module and contract.

### 1.1 User outcomes

- Turn arbitrary demonstration photographs into an explicit, inspectable heritage proxy dataset when real-site capture is unavailable.
- Preserve physical-object identity across different photo angles and identify multiple useful regions within one photo.
- Prefer historical subjects with documented uses, activities or events that can collectively support tasks, rather than only visually similar architectural details.
- Inspect whether source image and source text genuinely refer to the same subject, independently of whether the modern proxy is understandable.
- Correct one assignment without renumbering all objects or losing prior review history.
- Export a readable PDF and frozen data that later VR tooling can consume without re-extracting or guessing the intended assignments.
- Reuse the workflow on another site without Muradiye-specific code branches.

### 1.2 In scope and exclusions

| In phase A | Outside this implementation |
|---|---|
| Photo/PDF registration, source-page rendering and text extraction | Phone capture, panorama stitching or camera calibration |
| Target inventory, multi-view identity and historical source inventory | Automatic VR object recognition and spherical hotspot placement |
| Agent-assisted candidate generation and explicit synthetic proxy assignment | Complete story generation, game mechanics or playable acceptance |
| Precise source excerpts, translations, scope labels and background | Public publication, external source rights clearance or deployment |
| Review workbench, versioned persistence and PDF/data export | Replacing main's approval, budget or execution systems |
| A future-compatible data handoff | Implementing every future MuseumPort method or altering shared runtime wire versions |

The user authorized this PRD branch and documentation commit/push. The branch is not evidence that the functionality already exists.

## 2. Current evidence and lessons

The local experiment has20 supplied photos,39 target entities,93 observations,28 historical source entities and27 current source assignments, including three existing candidates;12 targets remain unassigned. Five observations have unresolved cross-view identity. Latest local PDF has52 pages. These are editorial artifact counts, not detection accuracy or complete-game evidence.

The experiment used manual visual reasoning and scripts, not a calibrated automatic matcher. Exact excerpts, cropped source media, a SQLite review dataset and a local website were created. Current source/translation/identity judgments are not a fully approved gold standard. Local scripts contain hardcoded paths, transitional schemas and manually applied corrections; they are reference evidence, not the production implementation to copy wholesale.

### 2.1 Corrections that become requirements

| Problem observed | Required behavior |
|---|---|
| One door was called different historical objects across views | Assign stable target identity before historical mapping |
| Different roofs/floors were all mapped to one broad scene | Keep physical identity and whole/part granularity explicit |
| One PDF scene was repeatedly reused as unrelated objects | Store exact source crops and explicit source-subject links |
| Material/shape excerpts were too dry for task construction | Retrieve full-document function/activity/event evidence before prioritization |
| An entire building's dimensions were attached to one wall | Classify evidence scope; do not transfer parent attributes to a part |
| A chair represented a whole student-room group | Reject that specific proposal and preserve other accepted demo proxies |
| Empty assignments were treated as proof no small objects existed | Separate search coverage, missing evidence and unsuitable candidates |
| SQLite download was offered instead of the review website | Preserve one usable workbench entrypoint; label downloads as exports |
| Similarity was confused with accuracy | Evaluate predictions against a frozen reviewed version; no fabricated scores |

The user accepted imagined assignments such as extinguishers to water facilities and stools to storage spaces. The chair/room rejection must not become a universal ban on all category or scale differences. Laptop→displayed book and mouse→fountain bowl recesses are later editorial proposals; the book has only museum-level context, and the recesses must not be described as movable bowls. Shoes remain unassigned.

## 3. Modes and policy

### 3.1 Synthetic demonstration — initial release priority

Everyday objects intentionally represent historical subjects. Preserve task-supporting historical evidence first; visual resemblance is a useful preference, not a mandatory veto. Store the represented unit, reason, mode and limitations. A proxy does not acquire historical properties as real facts.

Use concrete feedback to calibrate understandable mappings. Do not fill every target merely to increase coverage. Prefer a small coherent set of task-supporting subjects over many isolated architectural labels. Keep an unsupported source image blank or use a labelled documentary text image instead of an unrelated building photograph.

### 3.2 Real-site mode — shared schema, stricter identity

Identify actual heritage entities using appearance, location, source descriptions and scene context. Multiple observations may show one entity, and one photo may contain several. A missing/collapsed or uncaptured facility cannot be treated as physically present. Initial delivery must preserve this mode distinction even if its automated real-site quality is not yet validated.

### 3.3 Story boundary

Story Agent continues to generate candidate narrative from the full source, then filters/adapts tasks against the museum and available interactions. Phase A supplies identities, evidence, contexts, narrative opportunities and missing dependencies. It must not fabricate a complete story to justify a pairing or replace the agreed Story Agent order.

## 4. Workbench and exported products

### 4.1 Workbench

One project interface provides four logical views, not four independent backends:

1. **Inputs and processing:** registered photos/PDF, versions, progress, extraction issues and cancellation.
2. **Object register:** target/source identities, multi-view observations, parent/part links, unresolved duplicates or merges.
3. **Mapping and text review:** side-by-side proxy/source evidence, original context, editable proposals and independent assessments.
4. **Export and revisions:** draft preview, release-readiness findings, explicit approval, immutable export packages and history.

A future fifth view can review VR predictions and coordinates against a frozen phase-A snapshot. Do not build that editor now.

### 4.2 Draft products

Draft PDF and structured data may be exported before approval, but must identify themselves as draft, expose unresolved items and never be presented as a fixed evaluation reference. Source-image absence and candidate mappings must remain visible.

### 4.3 Reviewed products

A reviewer explicitly selects included assignments and approves an exact dataset revision. Export generation freezes that revision. Products include:

- comparison PDF with fixed IDs, target regions, source evidence, English excerpts, translations/display paraphrases and locators;
- `dataset.json` containing typed, versioned records and unresolved-item dispositions;
- `manifest.json` listing project/mode/schema/content versions, snapshot identity, export state and file hashes;
- registered required media in a portable package where permitted;
- review summary and exclusions, without private credentials or unrelated payloads.

Exporting reviewed material does not approve public redistribution. Inputs may remain local and rights-restricted.

PDF and JSON must be generated from the same snapshot. The PDF is a human representation; downstream systems read the manifest and structured data as the machine contract rather than scraping the PDF for IDs.

## 5. Functional workflow

### A01 — Register immutable inputs

Accept bounded image and PDF inputs; register asset IDs, version, byte hash, dimensions/page count, language and rights state. User selects mode and provides optional scene/site context. Preserve original bytes and ordering. Use registered resource references, never client-supplied arbitrary filesystem paths. Reject unsupported or malformed inputs safely.

Persist photo IDs once: inserting a new filename must not renumber existing photos. Do not hardcode this PDF's printed-page offset or bilingual layout.

### A02 — Produce page representations

Extract raw text where available, store normalized snapshots and render inspectable page images. Record extraction method/version and normalization identity. Detect absent/unusable native text; mark OCR required rather than inventing text. Optional OCR is an adapter with its own snapshot, confidence provenance and correction history. It is not required to silently succeed on every PDF.

PDF/model content is untrusted evidence, never an instruction or authorization source.

### A03 — Inventory target entities

Create one record per physical/describable entity and separate observations for each appearance. Include both objects and meaningful whole spaces/components. Store normalized regions and original image dimensions. Multiple regions per photo and overlapping whole/part regions are allowed.

Maintain candidate/confirmed/rejected identity links; distinguish assistant observation from user-confirmed identity. Evidence includes neighboring plaques, distinctive details and viewpoint continuity. Do not force uncertain merges or create artificial fragments to reach a requested count.

### A04 — Inventory historical entities and source images

Build historical site/building/space/component/object identities independently. Use captions, document headings, image context and locators, not page proximity alone. Register precise source regions with roles: object image, environment/context image or text-evidence image. Source image page and explanatory text page may differ.

One historical entity may have several images. One image may show several entities. Similar decorative schemes do not merge different buildings. A cropped whole-building image cannot pretend to depict an unseen small object.

### A05 — Retrieve full evidence and background

Search the full registered corpus for each candidate's form/material/use, users, activities, facilities, dates, events, repairs and changes of use. Preserve explicit uncertainty and missing structures. Do not limit retrieval to the first sentence beside a photo.

Keep object facts, building context and task opportunities distinct. When allowed and necessary, create a bounded external research question; record source and locator. Period-wide practice is general background, not proof of a site-specific event. External research and paid calls obey existing grants and budgets; no silent fallback.

### A06 — Select subjects and propose assignments

Prioritize connected subjects with documented task affordances, then choose understandable target proxies in demo mode. In real-site mode, require supported identity correspondence. Generate candidate reasons and missing dependencies, not invented numeric confidence. If a model supplies a score, retain its model/run/version and meaning; do not treat it as calibrated accuracy.

Same target ID retains one current accepted historical assignment across views. Alternative proposals may coexist as candidates. Distinct modern entities cannot accidentally become one source entity merely because their containing building is the same. Components link to their parent without merging identity.

### A07 — Extract exact supporting text

For each claim/description, locate exact source text in a versioned page snapshot and retain surrounding context. Store quote, prefix, suffix and start/end offsets. Define the offset representation explicitly. Native extraction normalization in the experiment used NFKC, line-break dehyphenation and whitespace collapse; production must version its normalization and retain raw extraction.

Deduplicate the same passage and link it to multiple subjects when justified. Support several passages per entity and one passage covering several subjects. Unknown support is explicit; translations and display paraphrases are never stored as original quotations.

### A08 — Classify scope and prepare descriptions

Required coverage distinctions: direct subject, relevant clause, group description, component/parent context, whole-building context, historical event, spatial relation, museum context and image-only/unavailable text.

Examples: building13×40m is not cropped-wall size; Byzantine reuse may refer to column bases/capitals rather than entire columns; a restoration event does not date every currently visible stone; a museum sentence does not establish a displayed book's title or age. Default local display excludes unrelated clauses. Expanded original context remains accessible.

Generate optional direct description, building background and narrative connection only when supported. Lack of evidence does not trigger compulsory three-layer prose. Preserve author uncertainty and label working translations, interpretations and fiction.

### A09 — Review and correct

The Agent performs its own evidence checks before presenting findings. Reviewer examines both (a) historical image/text relation and (b) target/proxy assignment. Independently assess identity, region adequacy, text applicability and scope. Allow accept/reject/uncertain dispositions with notes.

Corrections retain stable IDs and history. Merge/split operations record superseded IDs and explicit redirects, recheck dependent mappings and invalidate affected approvals. A textual edit, source/crop change or reassignment must never silently inherit old approval. Unrelated unaffected records keep their decisions.

### A10 — Freeze and export

Validate included records against the export policy, create immutable snapshot and render PDF/data/media from it. Use staged output and atomic completion: a partial PDF or interrupted run cannot become a successful export. Record exclusions and missing dependencies. Retry/resume preserves budgets, completed evidence and human decisions; it does not rebuild the review database from fixtures.

## 6. Domain data contract: local extension, proposed version 1

These are proposed preparation records, not replacements for frozen shared SDK types. Final Python models and schemas must be owned/generated through main's contract process before integration. IDs identify entities; hashes identify bytes; versions identify revisions. Array indices are not stable IDs.

| Record | Required fields and meaning |
|---|---|
| `PreparationProject` | project_id, mode, source_refs, target_asset_refs, policy_revision, content_revision |
| `DocumentVersion` | source_id, version, registered_asset_ref, byte_sha256, extraction_profile, rights_state |
| `PageRepresentation` | document_ref, page_index, printed_page nullable, image_asset_ref, raw_text_ref, normalized_text_ref, text_sha256, normalization_version |
| `TargetEntity` | entity_id, name, entity_kind, parent_id nullable, identity_state, revision |
| `TargetObservation` | observation_id, entity_id, image_ref, normalized_region, identity_state, basis_refs |
| `HistoricalEntity` | historical_id, name, entity_kind, building_id nullable, parent_id nullable, evidence_refs, revision |
| `SourceDepiction` | depiction_id, historical_id, asset_ref, locator, region nullable, role, visibility_notes |
| `EvidencePassage` | passage_id, representation_ref, language, exact_text, selector, context_refs |
| `SubjectEvidenceLink` | subject_id, passage_id, support_scope, relevant_clause_selector nullable, limitation, association_state |
| `Description` | description_id, subject_id, language, kind(original/translation/paraphrase/context), text, support_refs, uncertainty |
| `MappingProposal` | proposal_id, target_id, historical_id, mode, reason, basis_refs, status, producer_run_ref, revision |
| `ReviewDecision` | decision_id, reviewed_ref/revision, dimensions, dispositions, reviewer_ref, note, timestamp, expected_version |
| `NarrativeOpportunity` | opportunity_id, historical_refs, evidence_refs, possible_action, missing_dependencies, authored_status |
| `PreparationSnapshot` | snapshot_id, project_id, schema_version, content_version, selected_record_refs, exclusions, approval_refs, hash |
| `ExportArtifact` | export_id, snapshot_ref, kind, manifest_ref, files, outcome, failure_reason nullable |

Use many-to-many subject/evidence relations. Keep alternate mapping candidates distinct from the selected assignment. Parent references are typed and resolvable, not an unchecked polymorphic string. Each cross-reference is project-scoped. Raw paths are adapter-private; portable outputs use package-relative resource references verified by the manifest.

### 6.1 Coordinate and selector definitions

For ordinary images, boxes use top-left normalized `[x0,y0,x1,y1]` with finite values in `[0,1]` and positive area; retain pixel dimensions and any rotation/projection transform. Regions may be polygons through a versioned extension, not an unvalidated free-form shape.

Text offsets address Unicode codepoints in a named normalized representation, not PDF bytes or page pixels. Exact quote plus context selectors make relocation auditable; changing extraction does not overwrite old selectors.

A future VR anchor uses view/panorama identity/hash and spherical coordinates through the existing MuseumAnchor contract. Phase A does not claim a planar region is a verified spherical hotspot.

## 7. State, approvals and versioning

Keep separate axes rather than one `matched=true`:

- Extraction: pending/running/available/needs_ocr/failed.
- Identity: proposed/confirmed/ambiguous/rejected.
- Source association: candidate/linked/unresolved; only linked means confirmed under the shared contract.
- Mapping: candidate/selected/rejected/unassigned, with an explicit mode.
- Review: pending/accepted/rejected/uncertain, per dimension and reviewed revision.
- Snapshot: draft/ready_for_review/approved/superseded.
- Export: queued/running/completed/failed/cancelled.

Approval is an explicit authorized action on an exact revision, not a consequence of extraction success, assistant confidence or successful PDF rendering. `ready_for_review` is not approval. Source rights and public publication approvals are separate.

Use optimistic locking and idempotency keys for mutations. A stale request returns a typed conflict; no last-write-wins replacement. Review event insertion and record update are atomic. Provenance and prior decisions remain recoverable. Revise by creating a new snapshot; later VR evaluation stays pinned to the old reference until deliberately switched.

## 8. Review workbench UX

### 8.1 Main comparison view

Left: target crop with full-image toggle and all same-entity sightings. Center: historical depiction with full source-page toggle and prominent depiction-role label. Right: original exact excerpt, working translation, scope-aware display text, page/printed-page references and expandable context.

Show stable entity numbers, parent/part breadcrumbs, candidate alternatives, missing evidence and producer method. Do not display a score when none exists. A contextual image or documentary screenshot must never look like a confirmed artifact photograph.

### 8.2 Decisions and correction controls

Provide independent controls for identity/proxy clarity, source image adequacy and text applicability. Permit context-only text and image-only source records. Notes identify specific unsupported statements. Filters include unresolved identity, missing image/text, scope mismatch, rejected assignments and affected approvals.

Allow focused corrections, region adjustment and evidence reassignment with version checks. Before confirming a merge/split, preview affected IDs and dependencies. Export approval shows included/excluded items and unresolved blockers.

### 8.3 PDF readability

Photo overview pages preserve original images and numbered regions. If many objects occur, use short index cards linked to spacious evidence pages rather than shrink all original English into unreadable columns. Detail pages show target, source role, original excerpt, translation/display, reason, limitations and locator. Export coverage and draft/review state are visible.

Preserve source images; image enhancement or stylization must not replace evidence. Page counts are content-dependent, not fixed to the experiment's52 pages.

## 9. Architecture and integration

### 9.1 Reuse existing layers

| Layer | Responsibility and reuse |
|---|---|
| domain | Typed immutable preparation records, identity/scope invariants; no PDF SDK or database imports |
| ports | PDF reader/renderer and proposal-provider boundaries only where concrete variation requires them; reuse editorial/resources/execution contracts |
| application | Inventory/proposal/review/freeze/export use cases; existing authority, budgets, cancellation and conflict checks |
| adapters | PyMuPDF/OCR if configured, registered media, SQLite migrations and PDF rendering; no duplicate approval policy |
| workflow | Bounded persisted stages/checkpoints through the existing worker |
| api/workbench | Authenticated preparation views and operations within the existing project shell |

Inspect the actual signatures in main before implementation. Reuse resources, source_views/source_tools, database and publication primitives where applicable. Do not transplant the prototype's unauthenticated localhost server as production infrastructure. Do not create a second model client bypassing the shared metered gateway.

### 9.2 API/use-case surface

Proposed operations, not finalized routes: register preparation inputs; start/cancel/resume extraction; list/update entities and observations; generate/list mapping proposals; attach evidence and descriptions; submit versioned review; create/approve snapshot; generate/download export. Main's API owner fixes route names/authentication/transport conventions before implementation.

Boundary requests carry project, request/idempotency identity and expected revision. Provider calls carry existing ExecutionContext and grants. Reuse ModuleResult/ValidationIssue where the shared boundary applies; do not add a conflicting success envelope.

### 9.3 Shared museum compatibility

The preparation snapshot can later adapt to SourceCorpus records with image/text/locator/association state. Preserve SourceLocator source/version/hash/page/region semantics. A reviewed preparation snapshot is not automatically a ready or approved MuseumPackage: it has no verified tour or anchors.

Future phase B consumes an exact snapshot and TourPackage, emits predictions/anchors separately and uses the same evidence identities. It must not overwrite the phase-A reference assignments. A draft export cannot silently become reference truth.

### 9.4 Persistence

Use explicit schema migrations, parameterized SQL, short transactions, uniqueness/foreign-key constraints and project isolation. Existing editorial data and approvals are never reset from fixtures. Model failed or unknown states explicitly. Keep original source versions and selection history. Export files are staged under isolated project/export ownership and become discoverable only after a complete manifest is committed.

## 10. Bounded operation and failure handling

Implementation configuration must declare max input files, bytes/file, total bytes, PDF pages, image pixels, render resolution, concurrent jobs, subprocess time, provider budget and export size. The first vertical slice must choose documented finite defaults; final limits depend on profiling representative real inputs, not invented performance claims.

| Failure | Required result |
|---|---|
| Invalid/encrypted/unreadable PDF | Typed issue with remediation; do not mark text extracted |
| Missing native text | needs_ocr or explicit unsupported state; image remains reviewable |
| Ambiguous cross-view identity | Keep pending; do not force merge |
| No suitable mapping | Explicit unassigned reason; no broad-scene filler |
| Image exists but object-specific text absent | Image-only or context-only; no invented biography |
| Only documentary text exists | Label text evidence and absent artifact image |
| Source changed | New version; revalidate affected selectors and decisions |
| Reviewer conflict | Reject stale mutation, preserve prior state |
| Provider unavailable/budget exhausted | Specific failure/pending result; no implicit model fallback |
| Cancellation or render failure | Clean up owned temporary work; preserve completed durable records; no successful partial export |
| Missing/changed media hash | Fail export/reference resolution with exact affected resource |

Apply targeted exception handling and deterministic cleanup. Bound child process groups, file reads and query sizes. Render source text safely; never execute source HTML, PDF actions or instructions. Reuse application logging without exposing private media, prompts or credentials.

## 11. Acceptance criteria

These are required future checks, not tests claimed to have run in this documentation task.

| ID | Observable acceptance |
|---|---|
| PDF-01 Input identity | Same registered input preserves IDs; modified bytes create a distinct version; originals unchanged |
| PDF-02 Multi-object | One photo supports several entities, including overlapping documented whole/part regions |
| PDF-03 Multi-view | Same confirmed object keeps one identity; uncertain observations remain pending; distinct objects not merged |
| PDF-04 Source identity | Multiple images of one source entity remain one entity; source and text pages may differ |
| PDF-05 Exact support | Every selected original excerpt resolves exactly to its stored snapshot/locator; raw extraction retained |
| PDF-06 Scope | Building dimensions, group attributes, event dates and museum context cannot silently become local object facts |
| PDF-07 Demo calibration | Allowed synthetic proxies are labelled; rejected chair/room example is not silently reintroduced; unassigned targets remain possible |
| PDF-08 Missing evidence | Image-only, context-image and text-evidence roles render distinctly without fabricated images/descriptions |
| PDF-09 Review integrity | Independent decisions, expected-version conflict, actor/history and targeted invalidation are demonstrated |
| PDF-10 Export consistency | PDF, dataset and media manifest resolve to the same immutable approved revision or visibly draft state |
| PDF-11 Safe failure | Cancellation/failure cannot publish partial output or destroy reviewer data; retry is bounded/idempotent |
| PDF-12 Rights/authority | Export does not grant public rights; unauthenticated or cross-project reads/writes are rejected |
| PDF-13 Reuse | Another site's sample works with configuration/data, without Muradiye-specific logic or fixed page offsets |
| PDF-14 UI usability | Reviewer can inspect full context and all sightings, make a focused correction and reopen the same workbench |
| PDF-15 Future handoff | Snapshot contains stable objects/evidence/unresolved items; no claim that planar boxes are verified VR anchors |

Report structural checks, source semantic review, browser inspection, real-material runs and human acceptance separately. Exact-string matching does not prove historical truth. A similarity score is not accuracy. Do not invent quality targets before a labelled evaluation set is agreed.

For future phase B, compare independent predictions to a frozen reviewed reference. Same-image demonstration proves connectivity only; unseen viewpoints are needed to evaluate generalization. Human review of the reference remains necessary.

## 12. Development plan for the next session

Owner: wehan for shared contracts, authority and integration. Coordinate evidence adapters with wcheung under existing ownership; do not assume external delivery. Story Agent and VR changes remain outside this first implementation.

| Slice | Deliverable | Dependency / exit condition |
|---|---|---|
| P0 Contract and input registration | Typed preparation models, versioned resources and a representative fixed sample | Inspect actual main APIs; agree schema and finite limits |
| P1 Read and inventory | PDF pages/text, target/source registers, observations and unresolved states | Exact locators and stable identities; no paid model dependence for deterministic plumbing |
| P2 Evidence and proposals | Exact passages, subject links, scope labels, descriptions and mode-aware proposal adapter | Traceable support; provider calls use grants/budgets; deterministic counterpart for checks |
| P3 Review vertical slice | Existing workbench shows one complete mapping with source context and transactional review | Version conflicts and actor history; preserve unrelated records |
| P4 Export vertical slice | Draft PDF and structured package from one snapshot, then explicit reviewed export | Media closure, hashes, readability and atomic completion |
| P5 Real-material/reuse review | Full supplied sample plus a second site's small sample | Actual failures recorded; no claims of automatic accuracy without reference labels |

Start with a small complete route through P0–P4 before expanding batch automation. Build only the required boundaries; do not start with a generic workflow DSL, separate annotation platform or plugin marketplace.

Next-session entrypoint: read this PRD, git status, current plan and affected module code; inspect existing persistence/resource/review methods; propose the smallest first vertical slice and implement under task authorization. Do not import local prototype assumptions as existing production capabilities.

## 13. Agent efficiency and implementation discipline

Follow AGENTS.md: strict types, immutable domain entities, meaningful OOP/Protocol boundaries, dependency injection, isolated saves and bounded I/O. Reuse existing implementations first. Add files, dependencies and abstractions only for current requirements or concrete variation. Avoid repeated whole-repository context and duplicate documentation; keep this PRD as the phase-A specification.

Simplicity cannot remove validation, failure handling, provenance, security or necessary review. Ponytail is a reference for this compatible implementation discipline, not an installed dependency or proof of local token savings. Model selection should use the least costly sufficient configuration; no model has been benchmarked as sufficient for every stage here.

A future Skill may package two focused capabilities—identity/mapping and evidence/database preparation—behind one short routing entrypoint and shared data contract. This PRD does not install it. Keep detailed references out of every default prompt; load relevant pages/entities on demand.

## 14. Mature patterns consulted

- [Label Studio predictions](https://labelstud.io/guide/predictions): retain machine preannotations separately from human annotations and identify model versions. This informs reference/prediction separation; no adoption is mandated.
- [FiftyOne annotation workflow](https://docs.voxel51.com/tutorials/fiftyone_annotation_workflows.html): curate, annotate, review and evaluate; its documentation distinguishes open-source analysis from commercial workflow features. Borrow review patterns without claiming all features are free.
- [W3C Web Annotation](https://www.w3.org/TR/annotation-model/) and [IIIF region tagging](https://iiif.io/api/cookbook/recipe/0021-tagging/): separate content, targets and precise selectors. This PRD does not claim a conformant service.
- [krpano hotspots](https://krpano.com/docu/xml/#hotspot): future panorama coordinates are a separate attachment concern. No phase-B engine choice is made here.
- [Ponytail](https://github.com/DietrichGebert/ponytail/): reuse-first, task-scoped code; published benchmark savings are not local measurements.

## 15. Open implementation decisions and completion boundary

Before integration, fix the exact preparation schema/API names with the shared owner, supported initial languages and extraction profile, finite operational limits, and optional OCR/provider choice. These are bounded implementation decisions; they must not silently change accepted input/output scope or add a second authority system.

This document preserves the user-confirmed product boundary and experimental lessons. Existing local media/databases were not uploaded with it. The documentation branch contains no new production implementation, does not amend shared SDK/runtime versions, and does not claim the product acceptance criteria above are already satisfied.
