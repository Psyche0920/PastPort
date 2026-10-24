# PastPort PDF-to-VR Automation

Standalone implementation on `codex/pdf-to-vr-standalone`. The branch has independent history; it does not copy main's application. Main compatibility is a target contract, not a completed integration.

## Browser workflow: upload, generate, review

Start the local workbench after installation (`uv sync --locked --extra dev --extra codex`):

```sh
uv run pastport-pdf-vr studio --workspace .runtime/studio --port 8794
```

Open **http://127.0.0.1:8794/**. This server can start with no existing project. In the Chinese interface:

1. Choose or drop one **PDF**. Enable the large-PDF option for files above 64 MiB (maximum 512 MiB).
2. Choose/drop a supported **360 Studio HTML**, a complete tour folder, or one **ZIP**. Preserve relative image paths. The supported data-only export is schema 3/4, as used by the existing demo; arbitrary vendor HTML, raw panoramas without navigation, and uploaded scripts are not executed or silently converted.
3. Enter a project title and choose real-site matching or explicitly declared demonstration substitution. Expand generation settings to change the finite call/token thresholds.
4. Authorize this run to use the machine operator's Codex login, then click **生成 VR 与审核工作台**. No handwritten grant/request JSON or build command is needed. Poppler and the optional Codex SDK must already be installed; operator login must be available.
5. Read actual pipeline-stage progress in **生成记录**. Completed jobs provide **打开 VR 展示** and **打开审核工作台**. The existing popup editor and drag-release position autosave remain linked to the same project database.
6. To rebuild, select the existing project under **保存到** and upload its inputs again. The project URL remains stable; applicable human text and positions remain authoritative. Model calls may occur again under the explicitly authorized new run's limits. Changed historical assignments/media can invalidate applicability, retaining previous edits without blindly applying them.

Uploads and jobs stay under the selected ignored local workspace; source files, SQLite databases and credentials are not Git deliverables. Only one upload/build is admitted at a time. ZIP is limited to 150 MiB compressed / 200 MiB expanded; folder/HTML uploads total 200 MiB. Browser selection permits up to 100 tour files; ZIP inspection permits up to 1,000 entries. Traversal, duplicate paths, links, encrypted archives, oversized bodies and cross-origin edits are rejected. On interruption/failure, jobs stop for reconciliation rather than automatically retrying uncertain model dispatches or resetting usage. Keep the local server running during a build; closing it interrupts the owned process group.

The portal is localhost-only, not a hosted multiuser service. Project review and VR routes share `/projects/<project-id>/`; root `/` is the generation portal. The older `serve` command still serves an existing workspace directly. Stop another server before reusing its port. Existing demo workspaces are not automatically moved, reset, or adopted by this new portal.

### Input format capabilities and extensions

`GET /api/capabilities` is the single capability inventory shown by the UI. The submission contract declares `document_format` and `scene_format`; unsupported reserved formats fail **before model dispatch**.

| Input | Current behavior |
|---|---|
| PDF | Implemented, including exact evidence and page images |
| 360 Studio schema 3/4 HTML, folder, ZIP | Implemented safe packaging around the existing panorama importer |
| IDML + Links images | Reserved document format; parser is not yet implemented |
| INDD | Convert to IDML or PDF; native binary import is not implemented |
| 3D model / scene | Reserved `model_3d` format and capability; no model processing/viewer claimed |

The official source-directory workbook's Google Drive reference was inspected read-only: the II. Murat folder contains PDF, IDML, INDD and a Links folder with JPG/JPEG media. [Source folder](https://drive.google.com/drive/folders/18rlNGjpMhGuazgqqOUkJRDNbPEBIcTbh). This inspection verifies file organization, not semantic parsing or image/text associations. Future IDML input must retain XML member/Story/text ranges and original Links identities instead of manufacturing PDF pages. Future 3D support needs reference-view-to-surface transforms, geometry versioning, XYZ/surface anchors and its own viewer; panorama yaw/pitch must not be reused as XYZ. The `PanoramaSourceReader` port isolates the existing reader, while the typed submission's explicit format distinguishes future adapter selection.

Browser verification used a separate, explicitly labeled **offline fixture runner**, not live model inference. It exercised file selection, submission, completion, numbered VR popup and navigation to the corresponding evidence/editor. This does not establish full real-material recognition accuracy.

## Primary workflow: input PDF + VR, get linked VR and review

The `build` command runs a fixed LangGraph workflow: ingest → recognize → map PDF → extract grounded copy → publish review → export snapshot. Human review is optional after generation; it does not block output. Missing/unmatched items and exhausted budgets are listed as gaps rather than filled with invented information.

### One-time setup

Requires Python 3.12, a local Codex login/CLI, [uv](https://docs.astral.sh/uv/) and Poppler (`pdftoppm`). Install Poppler using your OS package manager (on macOS, `brew install poppler`). Then:

```sh
uv sync --locked --extra dev --extra codex
codex login
uv run --locked --extra codex pastport-pdf-vr codex-status --model gpt-6.1-sol
cp codex-grant.example.json my-grant.json
```

`codex login` is unnecessary if this machine is already signed in. The SDK uses the running operator's login, not a credential committed by the project. Edit `my-grant.json`: set a unique `project_id`, an explicit `grant_ref`, the model and finite call/token thresholds. No account tokens belong in this file. Keep the same grant identity on resume; changing its contents under the same ID is rejected. `my-grant.json` is ignored by Git.

### Build and open the result

Run from this branch's directory. The command below consumes subscription allowance:

```sh
uv run --locked --extra codex pastport-pdf-vr build \
  --pdf '/absolute/path/to/input.pdf' \
  --tour '/absolute/path/to/vr-directory' \
  --grant my-grant.json \
  --workspace .runtime/my-site \
  --run-id first-build \
  --mapping-mode same_site \
  --serve
```

The tour can be the supported export's `index.html` file or its directory. This version supports schema 3/4 data-only exports from the existing demo; it does not accept arbitrary vendor tours or ZIP archives. Default PDF limit is 64 MiB; add **`--large-pdf`** explicitly to opt into the bounded 512 MiB profile. Native-text-empty pages are recorded as OCR-needed; OCR is not yet implemented.

Use `same_site` when the PDF and VR depict the same physical heritage objects. Use **`--mapping-mode demo_substitution`** for the campus-to-Muradiye demonstration, where intentionally assigned substitutes are allowed. That mode still rejects small-object/whole-room scale mismatches. Source excerpts, whole-page references and selected image crops remain separate from generated copy.

When `build` finishes, `--serve` starts both fixed entries:

- Review workbench: <http://127.0.0.1:8794/>
- Numbered VR: <http://127.0.0.1:8794/vr/>

The pages consume the same database. Click a number for copy; open its workbench link to edit; use **调整编号位置** and release the dragged marker to autosave. The workbench also shows source crop, full source page, exact quotes/claims and build gaps. Human text and positions win over subsequent proposals. New panorama versions and changed historical assignments do not silently inherit unrelated edits. No manual JSON request or fixture database is needed for `build`.

Keep the terminal process running. Ctrl+C stops preview without removing data. To reopen the same result without model calls:

```sh
uv run --locked --extra codex pastport-pdf-vr serve --workspace .runtime/my-site --port 8794
```

Stop the previous preview before serving a different workspace on the same port. Before rebuilding, stop the preview so the next launch reads the new tour and build summary. Reuse the same run ID only for identical input/configuration. For a deliberately changed input, use a new run ID and keep the same workspace/project to retain valid human overrides. The workflow and execution ledgers retain completed work and uncertain usage across restarts. A recovery-required error stops automatic resubmission: inspect its ledger before granting further execution. Do not delete the database to make an error disappear.

### What has actually been checked

The full graph has passed a synthetic end-to-end test with explicit semantic counterparts, including editable review output, rerun deduplication and preservation of human edits. An additional local verification used a real generated PDF, native text extraction and Poppler rendering through the complete graph with semantic counterparts. The official SDK has passed a live image call, and two real campus panoramas were separately inspected for three known objects. These checks are **not** a complete live PDF + tour build or cross-site accuracy evaluation. No further live calls were made after the user requested stopping the sample. Your first whole-material build is the next live acceptance run.

## Available now: offline replay

Import an explicitly supplied prior tour/matching report and optional legacy evidence database, then open numbered VR and the linked review workbench. This performs **no new visual inference**. It does not prove automatic PDF-to-VR recognition or cross-site accuracy.

The current local replay contains 37 objects and 66 anchors across two viewpoints. An object visible in both viewpoints keeps its number and has a separate position per viewpoint. Unlocated objects are not invented. Existing historical associations and evidence are imported as unreviewed legacy data; the unbound chair remains unbound.

### Install and run

Requires Python 3.12. Install the package in a virtual environment:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

Run from this repository. Substitute your own local paths; inputs are never bundled in Git:

```sh
.venv/bin/python -m pastport_pdf_vr replay \
  --config config.example.toml \
  --tour '/path/to/exported-tour/index.html' \
  --report '/path/to/trial_report.json' \
  --legacy-db '/path/to/pastport_matching.sqlite3' \
  --workspace .runtime/demo \
  --run-id replay-1

.venv/bin/python -m pastport_pdf_vr serve --workspace .runtime/demo --port 8794
```

`--legacy-db` is optional: without it the report supplies positions/identities but historical copy is not imported. This option reads a specific legacy demo schema in a read-only transaction; it is not a generic database migration.

Fixed standalone entries while the process runs:

- Review: <http://127.0.0.1:8794/>
- VR: <http://127.0.0.1:8794/vr/>

The previous demo on port 8793 is separate and unchanged. The server binds localhost only; it is not a shared/cloud deployment. Stop with Ctrl+C and restart using the same workspace to retain saved edits.

### Review and positioning

1. Click a VR number for the latest effective introduction and expandable background.
2. Follow its workbench link, edit **VR 中显示的内容** or **相关背景**, and save. Reopen the VR popup to read the new human version.
3. Enable **调整编号位置**, drag a number and release. A successful save displays **人工位置已保存**. Failed/conflicting requests are explicitly unsaved; reload and drag again. An open popup is not live-pushed.
4. Human copy has precedence over newer AI drafts. Human positions are keyed by project, object, viewpoint, exact panorama and revision. A new panorama does not silently inherit old coordinates. Changing a historical assignment retains the old human history but does not apply it to the new subject.
5. Concurrent stale edits receive HTTP 409; retries with the same operation ID are idempotent. There is no silent last-writer overwrite across stale browser tabs.

### Repeat runs and evidence

Reuse the run ID with unchanged inputs to reuse completed stage receipts. Use a new run ID for deliberately changed inputs. Neither path overwrites human values. Interrupted stages with uncertain effects stop in `recovery_required`; no automatic redispatch is attempted. Use one project per workspace. Back up the entire workspace while the server is stopped, including SQLite files, tour metadata, content-addressed assets and stage journal.

The fixed LangGraph replay stages are `import_tour → import_replay → export_snapshot`. Stage receipts are durable; graph state stores references rather than large images. Snapshots are immutable, content-hashed **local preview records**, not validated main SDK `MuseumPackage` exports. Editing live review data does not rewrite an earlier snapshot. A new run exports current effective values.

The importer accepts the existing schema 3/4 HTML export with an `application/json` `tour-data` block, embedded images or contained relative image paths. It does not execute imported HTML/scripts or support arbitrary vendor tours/ZIP extraction. Navigation links and original panorama bytes are preserved.

Legacy evidence includes source crop where available, PDF page, printed page, quotation, translation, scope, limitations and building background. Legacy quotation selectors are checked against the legacy **normalized page text**, not claimed as raw PDF character offsets. Image/paragraph semantic correctness has not been re-evaluated by a real model. Missing crop or local description stays missing.

## Recognition and evidence services

Separately implemented typed services support overview/detail projection, cross-view identities, bounded missed-target recheck, whole-corpus evidence retrieval, exact quotations, scope validation and popup drafting through injected semantic ports. Their isolated tests use explicit offline counterparts. An optional Codex SDK adapter now implements these ports for local subscription execution. This is separate from the main shared gateway and does not complete the full automatic PDF/tour workflow.

The source PDF in the current material is about 319.1 MiB, beyond the 64 MiB PDF input profile. The default profile rejects it; the new build command allows explicit opt-in to a 512 MiB profile with `--large-pdf`. Offline replay reads existing extracted evidence instead. Native-text-empty pages are marked `ocr_needed`; OCR is not implemented. Real PDF rendering requires Poppler `pdftoppm`.


## Codex SDK semantic execution

Install the optional official SDK adapter:

```sh
.venv/bin/python -m pip install -e '.[dev,codex]'
.venv/bin/python -m pastport_pdf_vr codex-status --model gpt-6.1-sol
```

This reuses the current operator's existing local Codex ChatGPT login. It does not store credentials in the project, sign in automatically on another person's machine, share an account, silently use an API key or change global Codex settings. If no eligible login/model exists, it fails explicitly. The CLI status check performs no inference.

For a typed request prepared by the pipeline, use:

```sh
.venv/bin/python -m pastport_pdf_vr codex-run \
  --kind inspect \
  --request /path/to/scene-inspection-request.json \
  --grant codex-grant.example.json \
  --assets /path/to/registered-assets \
  --workspace .runtime/codex-execution \
  --output .runtime/codex-execution/result.json
```

Kinds `inspect`, `associate` and `draft` consume the existing `SceneInspectionRequest`, `EvidenceSelection` and `DraftRequest` contracts respectively. For association with a PDF image, `--image-bindings` must supply an array of `EvidenceImageBinding` records linking each selected image ID to its registered **crop**, not the complete PDF. An absent crop fails rather than pretending the model saw it. Higher-level recognition/evidence services remain responsible for identity, missing-target handling, exact quotations and claim scope; these adapters do not bypass them.

`CodexSemanticGateway` implements both semantic ports. It receives one `SubscriptionExecutor` and asset store by injection. The SDK transport uses explicit model/effort, ephemeral read-only threads, process-local tool restrictions, bounded image files, a deadline, and provider-compatible strict output schemas. It checks model availability and image support before inference; timeout/interruption requests cancellation and leaves uncertain usage blocked. Synchronous semantic ports must be run outside the event loop when integrated into an asynchronous server.

The grant binds project/model/effort/call cap/deadline and a recorded-token threshold. Completed executions persist SDK thread/turn identifiers, token usage and executor-issued receipt IDs. Exact requests reuse receipts; an uncertain prior dispatch blocks further work under that grant, and restarting cannot reset the cap. A changed grant requires a new explicit identifier. The token threshold is checked before the **next** call and can be exceeded by a single call; it is not a hard provider output-token cap. Subscription allowance percentages and dollar charges are not exposed by this receipt and are **not invented** from token counts. This does not claim main's dollar-budget/usage-grant integration.

A live synthetic image capability check passed with Sol 6.1 using ChatGPT login. The initial strict-schema rejection remains recorded as recovery-required rather than erased or counted as zero usage. Subsequent verification used a separate bounded grant. This proves transport/structured output, not museum recognition accuracy. The existing review workspace is not changed by `codex-run`; candidate results are written to the specified output for validation/composition.

## Source map

| Source | Purpose |
|---|---|
| `domain/` | Immutable identities, PDF, geometry, recognition, evidence, tour and editorial contracts |
| `ports/` | Asset/PDF/semantic/identity contracts independent of provider SDKs |
| `api/studio.py`, `application/studio.py`, `domain/studio.py`, `web/studio.*` | Local upload portal, bounded job lifecycle, format capabilities and project-scoped review routing |
| `ports/scene.py` | Panorama reader boundary; 3D geometry remains a separate future adapter |
| `application/configuration.py`, `inputs.py`, `pdf_ingestion.py` | Bounded configuration, preflight and registered native PDF ingestion |
| `application/projection.py`, `adapters/projection.py` | Coordinate inversion, seam handling and perspective pixel rendering |
| `application/recognition.py`, `adapters/identity.py` | Stable numbering, all-view dispositions, bounded recheck and response receipts |
| `application/evidence.py`, `prompts/` | Cross-page retrieval, exact selectors, scope separation and default-copy policy |
| `adapters/tour.py`, `assets.py`, `pdf.py` | Data-only tour import, verified content-addressed files and PDF extraction/rendering |
| `adapters/legacy_replay.py`, `application/replay.py` | Explicit prior-result/evidence import without inference |
| `adapters/editorial.py` | Transactional proposals, versioned human overrides and append-only edit events |
| `workflow/graph.py`, `application/bootstrap.py`, `automatic_build.py`, `domain/build.py` | Fixed replay/automatic graphs, project lock, bound receipts, grounded mapping/copy, recovery stop and snapshots |
| `adapters/codex_sdk.py`, `codex_semantics.py`, `execution.py`, `structured_output.py`, `application/codex_execution.py` | Optional official SDK, strict structured output, persistent subscription grants and semantic-port composition |
| `api/server.py`, `web/`, `cli.py` | Local API, linked Chinese workbench/VR and command entrypoints |
| `tests/` | Isolated geometry/identity/evidence checks and synthetic API/replay integration |

Pannellum 2.5.6 is vendored from the official npm package via jsDelivr (`pannellum@2.5.6/build/pannellum.js` and `.css`). Its MIT license is retained in `web/vendor/COPYING`. No third-party CDN is needed at runtime.

## Checks and next integration

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/mypy --strict src tests
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
git diff --check
```

See [ACTIVE_PLAN.md](docs/ACTIVE_PLAN.md) for verified evidence, pending model/second-site work and owners. [The PRD](docs/PRD_PDF_TO_VR_AUTOMATION.md) defines the wider target. Main's `tools/check_repository.py` and SDK checker are absent from this standalone branch and have not passed here. Integrate selected files on a fresh main-based branch after freezing the main counterpart; do not merge unrelated histories wholesale.
