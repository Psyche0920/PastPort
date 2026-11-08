# PastPort Matched Environment SDK

The isolated source-first trial reuses this SDK for localization and 3D attachment; that does not integrate text-first selection into Organizer. Attachment remains pending alignment and manual acceptance. New environment runs pin the v2 packaged localization and review skill snapshot into model requests and input bindings. Existing runs retain their original policy and receipts.

The native `idmlscene3d` entry requires only IDML, SPZ and PLY; Links is optional, and no field-photo upload is required. The pipeline derives observations from the hash-bound scene and records their provenance, then reuses native IDML matching, independent audit, localization and attachment. Missing linked graphics remain explicit gaps and are excluded from image evidence; source text and exact citations remain usable. The existing photo-based `idml3d` entry stays separate. Environment preparation stops at `environment_ready`, before Story.


## Current integration contract

| Item | Current behavior |
|---|---|
| Inputs | Matched source materials, tour/3D resources, existing review and navigation state. |
| Outputs | Shared museum content, object occurrences, 3D bindings/calibration, spatial/navigation records and preview. |
| Workflow | Import → match/read shared content → bind scenes → analyze space → navigate/export. |
| Technology | Python 3.12, typed APIs, browser viewer and bounded Node spatial processing. |

Unified architecture and exact current verification scope: [Technical PRD](../../docs/TECHNICAL_PRD.md#sdk-modules). Main reuses the registered upstream outputs and saved Story in its current replay entry; this is not a new recognition/rendering/model run.

Independent distribution: `pastport-matched-environment==0.1.0`; import namespace: `pastport_matched_environment`.
Source revision and notices: [UPSTREAM](UPSTREAM.md), [license](LICENSE).

Inputs: a matched PDF and a new VR tour for environment generation; Outputs: a source-bound museum/review candidate with stable identity and explicit
acceptance limits. Shared review and 3D remain in Matched Environment; appearance execution is
owned by the separate `pastport-stylization` distribution, which depends on Matched Environment.
Matched Environment does not depend on Stylization.
No Story Demo, UI-trial game, live database or private scene is bundled.

## Install independently

```sh
uv pip install './packages/matched-environment-sdk[codex]'
pastport-matched-environment --help
```

From inside this package directory, use `uv pip install '.[codex]'` instead.
Python 3.12 and Poppler are external requirements; Stylization documents its own
ffmpeg requirement.
Install/import/help must not start generation. Each real run requires its finite
existing grant, source identity, isolated workspace and retained usage receipts.

## Public boundaries

`pastport_matched_environment.sdk` exports `EnvironmentBuildWorkflow`, `BuildSummary`,
`SubscriptionGrant`, `SemanticTransport`, `Style3DVariant` and `current_style`. Constructors retain
injected transports; the SDK facade adds no direct model/provider bypass.

- Environment: `EnvironmentBuildWorkflow(pdftoppm, transport).run(pdf, tour, grant,
  workspace, run_id, ...) -> BuildSummary`.
- Review/preview: `StudioApplication(workspace)` exposes its existing local app.
  It owns child preview lifecycles. Main Organizer embeds the trusted packaged review UI
  behind its authenticated source-scoped routes; uploads do not supply executable review HTML.
  Direct standalone staff endpoints retain their separate local deployment boundary.

Source-only review links are not portable authority credentials. Export through the
owning reviewed-snapshot interface; do not rebuild an existing DB from sample data.
A styled candidate is not geometric reconstruction or human-accepted visual quality.

## Source responsibilities

| Source | Purpose |
|---|---|
| `src/pastport_matched_environment/sdk.py` | Stable typed public re-exports |
| `src/pastport_matched_environment/cli.py` | Existing environment and 3D commands |
| `src/pastport_matched_environment/application/` | Environment generation, shared review, 3D import and appearance-manifest verification |
| `src/pastport_matched_environment/domain/`, `ports/` | Immutable records and injected capabilities |
| `src/pastport_matched_environment/adapters/` | Bounded I/O/model execution, projection and source readers |
| `src/pastport_matched_environment/api/`, `web/` | Local staff/review/preview application |
| `src/pastport_matched_environment/reference_environment/` | Data-free renderer/persistence templates required by assembly; not a playable Demo |
| `src/pastport_matched_environment/scene3d_assets/` | Viewer dependencies and retained third-party notices |
| `src/pastport_matched_environment/prompts/` | Environment generation policy |
| `src/pastport_matched_environment/workflow/` | Bounded LangGraph production steps |
| `tests/` | Imported upstream deterministic regressions, no live models |

Run tests from this package root with `python -m unittest discover -s tests -t . -v` so the package's `tests` module resolves ahead of unrelated repository tests.
These tests do not establish human visual acceptance or end-to-end game delivery.

## Separate ownership and compatibility

The split preserves upstream provenance but moves style execution and its CLI
entry points into `pastport_stylization`. Matched Environment owns data-only appearance schemas
and hash/scene-binding verification, plus the shared metered image wire contract.
Its local staff app no longer implicitly mounts the separate style portal.
The Matched Environment page no longer links to an unmounted style portal; launch the
independent Stylization command explicitly. Main runtime adapters/authenticated API mounting are not supplied by
installing either package.

## Independent multi-view 3D tour

Navigation, arrow dragging/persistence, arrival headings and preview process cleanup
are owned by this SDK. Main supplies the source environment and registered result
folders; it does not implement jumps, duplicate the viewer or require Studio job records.
The existing Studio and this entry point share `Scene3DTourNavigator` and the same
viewer, arrow store and transition boundaries. Evidence and Stylization are unchanged.

```sh
pastport-matched-environment tour-preview \
  --environment /absolute/path/to/source-vr-environment \
  --view /absolute/path/to/point-1-result \
  --view /absolute/path/to/point-2-result \
  --port 8797
```

Open `http://127.0.0.1:8797/`. Keep the terminal running; Ctrl+C closes owned previews.
Each view must already share the source content authority and contain its matching
`scene3d/attachment.json`. Source scene IDs are read from those attachments, not
entered manually. Existing 3D arrow coordinates remain local to each result. New
results seed arrows from the source VR; later VR edits do not overwrite dragged
3D positions. The selected port must be free. This local portal is not a public
server or an automatic generation command.

Python callers can use `TourPreviewApplication(source, views, base_url).app` and
`TourPreviewView.from_result(path)` from `pastport_matched_environment.sdk`.
The host must bind the configured loopback origin and own the application's lifespan.

| Source | Responsibility |
|---|---|
| `application/tour_navigation.py` | Resolve saved source navigation into registered viewer targets; shared with Studio |
| `api/tour_preview.py` | Compose local scene previews, seed navigation and own their lifecycle without Studio records |


### Offline spatial input analysis

`application.spatial_analysis.OfflineSpatialAnalyzer.analyze` accepts a typed
`domain.spatial_analysis.SpatialProbeRequest`, verified collider bytes and an execution
cancellation/deadline callback. Node.js uses the bundled Three.js dependencies offline in
a bounded subprocess; no model, network, asset generation or review mutation is involved.

Every supplied object/arrow receives a spawn-to-target direct-route check and an anchor
sight ray. All ordered routes between successfully reached approach positions and spawn
are tested for continuous ground, step height and collision. This is a direct-path graph,
not an exhaustive navigation mesh: a blocked direct path does not prove no detour exists.
A clear anchor ray does not establish object identity, transparency or inscription detail.
Legibility and touch remain unknown without task-specific evidence. Candidate locations
and unconfirmed calibration stay unconfirmed even when geometry can be evaluated.

| File | Responsibility |
|---|---|
| `domain/spatial_analysis.py` | Bounded request/result schema for geometry evidence |
| `application/spatial_analysis.py` | Killable offline Node transport, identity checks and input-bound geometry cache |
| `scene3d_assets/spatial_analysis.mjs` | World-space triangle index, direct routes and sight rays |

Main injects its registered spatial reader once; each environment read automatically runs
this pass for all supplied occurrences, with a separate hash covering coordinates,
calibration, arrows, collider and algorithm. Process failures remain explicit unknowns.

<!-- BEGIN FILE INVENTORY -->
## 文件结构与用途

每个文件的用途直接写在同一行。以下覆盖本范围内的 **115 个维护文件**；依赖环境、缓存、私有产物和历史备份不属于源码清单。

```text
matched-environment-sdk/
├── src/
│   └── pastport_matched_environment/
│       ├── adapters/
│       │   ├── __init__.py  # I/O adapters for registered assets and source formats.
│       │   ├── assets.py  # Content-addressed local asset storage with atomic, size-bounded registration.
│       │   ├── codex_sdk.py  # Official Codex SDK transport using the operator's existing ChatGPT login.
│       │   ├── execution.py  # Durable grant reservations: uncertain dispatch consumes its slot until reconciled.
│       │   ├── matched_pdf.py  # Read optional internal evidence links from a supplied matched PDF, never scripts.
│       │   ├── pdf.py  # Native PDF text, positioned line and embedded image extraction plus Poppler rendering.
│       │   ├── projection.py  # Render matching images using the same camera convention as coordinate inversion.
│       │   ├── structured_output.py  # Translate Pydantic schemas to the provider's strict structured-output subset.
│       │   └── tour.py  # Parse data-only tour exports; imported HTML is never served or executed.
│       ├── api/
│       │   ├── __init__.py  # Local review and VR transport.
│       │   ├── scene3d.py  # Additive local 3D routes using the reference review database and version checks.
│       │   ├── scene3d_studio.py  # Optional Marble attachment UI alongside the unchanged panorama generation flow.
│       │   ├── shared_content.py  # Same-origin shared revision polling, independent of preview ports and broadcasts.
│       │   ├── studio.py  # Browser generation portal sharing the existing per-project review application.
│       │   ├── tour_preview.py  # Compose existing 3D viewers without requiring Studio job records.
│       │   └── vr_navigation.py  # Local-only navigation editing routes layered over the trusted review handler.
│       ├── application/
│       │   ├── __init__.py  # Application-level input and configuration services.
│       │   ├── appearance.py  # Read and verify a source-bound appearance manifest without executing stylization.
│       │   ├── environment_agent.py  # Prepare registered visual inputs for the repository's environment-generation skill.
│       │   ├── environment_build.py  # Metered matched-PDF inspection, fresh localization and reference-format delivery.
│       │   ├── inputs.py  # Bounded source PDF validation before asset registration.
│       │   ├── marble.py  # Admit existing Marble exports without generation, credentials or uploaded code.
│       │   ├── marble_generation.py  # One explicitly authorized panorama generation; resume only polls its saved operation.
│       │   ├── navigation.py  # Source-bound, versioned panorama navigation corrections.
│       │   ├── pdf_ingestion.py  # Register a source PDF and persist page text and rendered-page references.
│       │   ├── projection.py  # Invert stored image transforms before interpreting model pixels as VR angles.
│       │   ├── reference_environment.py  # Assemble a new, isolated review candidate from a hash-bound visual handoff.
│       │   ├── review_repository.py  # 原编号后台与Organizer共用的版本审核、历史持久化实现。
│       │   ├── vr_positions.py  # 原全景编号位置的版本化保存，与3D锚点保持独立。
│       │   ├── vr_content.py  # 原编号后台与Organizer共用的介绍版本、人工作文和审计记录。
│       │   ├── reference_preview.py  # Own isolated local reference servers, loading only packaged runtime code.
│       │   ├── scene3d.py  # Attach an existing Marble world to a labelled environment without rematching.
│       │   ├── scene3d_arrows.py  # Seed 3D navigation once from VR; all later spatial edits stay local to this result.
│       │   ├── scene3d_projection.py  # Offline candidate and arrow initialization; preserves saved edits and checks calibration versions.
│       │   ├── scene3d_export.py  # Portable scene assets and source-bound game data from one consistent review snapshot.
│       │   ├── scene3d_review.py  # Adapt only a 3D result's review links; keep shared content and source evidence.
│       │   ├── scene3d_tour.py  # Export separate source-ordered worlds and their saved navigation as one package.
│       │   ├── shared_content.py  # One content authority per source environment; spatial state remains per result.
│       │   ├── vr_export.py  # Portable matched-VR snapshot including consistent shared review data.
│       │   ├── spatial_analysis.py  # Bounded offline geometry subprocess using the SDK's bundled Three.js loader.
│       │   ├── storage.py  # Durable atomic metadata writes shared by generation and job storage.
│       │   ├── studio.py  # Local generation jobs; subprocess ownership is separate from editorial state.
│       │   └── tour_navigation.py  # Reuse source navigation across registered independent 3D deliveries.
│       ├── domain/
│       │   ├── __init__.py  # Framework-independent domain records.
│       │   ├── animation.py  # Typed image-generation boundary; image edits do not change museum identities.
│       │   ├── appearance.py  # Source-bound 3D appearance baking; geometry and matching stay independent.
│       │   ├── build.py  # Persisted matched-environment generation summary.
│       │   ├── environment.py  # Validated semantic proposals for matched-PDF environment generation.
│       │   ├── execution.py  # Bounded standalone subscription execution; no fabricated dollar accounting.
│       │   ├── geometry.py  # Coordinate contracts: image edges, top-left pixels, yaw-zero forward and pitch-up.
│       │   ├── models.py  # Immutable domain records shared by input, workflow and export boundaries.
│       │   ├── pdf.py  # Typed records produced while reading and rendering a registered PDF.
│       │   ├── scene3d.py  # Versioned Marble input and metric-space manual anchor contracts.
│       │   ├── spatial_analysis.py  # Source-bound advisory geometry evidence, independent of narrative permissions.
│       │   ├── studio.py  # Typed browser submissions and explicit input-adapter capabilities.
│       │   └── tour.py  # Imported tours preserve navigation and decoded panorama identity.
│       ├── ports/
│       │   ├── __init__.py  # Replaceable storage and document-processing boundaries.
│       │   ├── assets.py  # Asset storage contract used by application services.
│       │   ├── execution.py  # Transport boundary keeps the SDK outside domain/application services.
│       │   └── pdf.py  # PDF processing contract independent of the chosen extraction/render libraries.
│       ├── prompts/
│       │   ├── environment_policy_v1.txt  # 环境生成/准备阶段的模型策略与输出约束。
│       │   └── environment_skill_v1.txt  # 新任务使用的环境定位与审核 skill 版本快照。
│       ├── reference_environment/
│       │   ├── PROVENANCE.md  # 参考资源的来源与归属记录。
│       │   ├── landing.html  # 参考环境的导览入口页。
│       │   ├── review.html  # 共享物件内容与匹配结果的审核页面。
│       │   ├── review_server.py.template  # 生成环境审核 HTTP 服务的 Python 模板。
│       │   ├── schema.sql  # 共享内容审核 SQLite 数据表定义。
│       │   ├── start_demo.py.template  # 生成本地参考环境启动脚本的模板。
│       │   ├── viewer.html  # 全景参考环境查看与热点交互页面。
│       │   ├── vr_content.py.template  # 生成共享物件内容读取及审核持久化模块的模板。
│       │   ├── vr_position_editor.js  # Scene-specific drag review. A released marker is persisted automatically.
│       │   └── vr_positions.py.template  # 生成各视点热点与导航位置保存模块的模板。
│       ├── scene3d_assets/
│       │   ├── BufferGeometryUtils.js  # Three.js 几何体处理工具，供三维资源加载与处理使用。
│       │   ├── GLTFLoader.js  # Three.js glTF 模型加载器，用于读取三维场景资源。
│       │   ├── Pass.js  # Three.js 后处理渲染通道基础设施。
│       │   ├── SPARK-LICENSE.txt  # Spark 渲染库许可证。
│       │   ├── THREE-LICENSE.txt  # Three.js 库许可证。
│       │   ├── index.html  # 独立 3D 场景查看器 HTML 入口。
│       │   ├── navigation_boundary.js  # A one-way, unbounded vertical plane through an arrow; no altitude/radius test.
│       │   ├── shared_content.js  # 在 3D 场景中读取共享物件内容，让多视点复用同一物件档案。
│       │   ├── spark.module.js  # Spark Gaussian Splat 渲染库，显示点云式三维场景。
│       │   ├── project_candidates.mjs  # Headless source-ray projection with bundled Three.js and no external geometry resources.
│       │   ├── spatial_analysis.mjs  # Offline advisory geometry analysis; never changes player state or collision rules.
│       │   ├── three.core.js  # @license Copyright 2010-2025 Three.js Authors SPDX-License-Identifier: MIT
│       │   ├── three.module.js  # @license Copyright 2010-2025 Three.js Authors SPDX-License-Identifier: MIT
│       │   ├── transitions.js  # 三维点位转场与进入朝向管理。
│       │   └── viewer.js  # 三维查看器：加载场景、显示物件和处理空间交互。
│       ├── web/
│       │   ├── scene3d.html  # 工作台三维场景页面结构。
│       │   ├── scene3d.js  # 工作台三维场景控制与环境接口调用。
│       │   ├── scene3d_records.js  # 三维场景记录与视点相关数据的浏览器处理。
│       │   ├── studio.css  # 环境搭建工作台样式。
│       │   ├── studio.html  # 环境搭建工作台页面结构。
│       │   └── studio.js  # 环境搭建工作台操作控制与后端交互。
│       ├── workflow/
│       │   ├── __init__.py  # Fixed and resumable execution graph.
│       │   └── graph.py  # Fixed LangGraph stages backed by authoritative transactional stage receipts.
│       ├── __init__.py  # Standalone PDF-to-VR workflow implementation.
│       ├── __main__.py  # Run the standalone CLI using python -m pastport_matched_environment.
│       ├── cli.py  # Matched PDF and fresh panorama generation entrypoints.
│       ├── py.typed  # PEP 561 类型标记，让安装方的类型检查器识别本包类型。
│       └── sdk.py  # Public Matched Environment SDK surface; appearance execution belongs to pastport_stylization.
├── tests/
│   ├── __init__.py  # Behavioral checks for standalone contracts and bounded services.
│   ├── test_appearance.py  # 回归测试：Museum verifies appearance identity and bytes without a stylization dependency.
│   ├── test_assets.py  # 回归测试，覆盖 AssetRegistrationTests。
│   ├── test_codex_execution.py  # 回归测试：SDK port checks use an explicit transport double, not live subscription calls.
│   ├── test_environment_agent.py  # 回归测试：Portable skill assembly checks use labeled inputs, not claims of new visual inference.
│   ├── test_environment_build.py  # 回归测试：Behavioral SDK-pipeline and browser checks use explicit semantic counterparts.
│   ├── test_projection.py  # 回归测试：Geometry checks use known rays and actual synthetic pixels, not model answers.
│   ├── test_scene3d_candidates.py  # 回归测试：Automatic proposals must remain separate from authoritative human anchors.
│   ├── test_scene3d_submission.py  # 回归测试：Financial regression checks: submission replay and source backup, without providers.
│   ├── test_shared_content.py  # 回归测试：Shared identities/content must not collapse viewpoint state or divergent edits.
│   ├── test_scene3d_projection.py  # Real geometry projection, saved-coordinate preservation and stale-calibration rejection.
│   ├── test_spatial_analysis.py  # 回归测试：Execute the packaged geometry analyzer against a deterministic floor and wall.
│   ├── test_studio.py  # 回归测试：Upload boundaries and interruption handling, without model execution.
│   ├── test_tour_preview.py  # 回归测试：Independent tours retain saved navigation and reject unregistered destinations.
│   └── test_workflow.py  # 回归测试，覆盖 CounterStage, WorkflowTests, EvidenceFailure, RecoverableEvidenceStage, RecoveryTests。
├── LICENSE  # 本模块的许可证；分发源码或安装包时保留。
├── README.md  # 本模块的使用入口、输入输出及完整文件用途说明。
├── UPSTREAM.md  # 上游来源、提取范围及归属说明；不是运行入口。
└── pyproject.toml  # 本项目的包名、依赖、命令入口与构建配置。
```
<!-- END FILE INVENTORY -->

### Portable native inputs for Organizer

`pastport-matched-environment environment-export --environment /registered/result --output /new/matched-vr.zip` exports the current native VR data, consistent local spatial database and shared review content. It copies no credentials and grants no historical approval. Mounted 3D uses the existing `export_tour` ZIP with two native views, not a bare GLB/SPZ or a generated game directory.

Organizer preserves imported anchors and manually dragged arrows. Missing automatic candidates can be initialized headlessly with `OfflineCandidateProjector`; the result retains calibration state and never becomes human-approved identity merely because geometry was computed.

Organizer keeps the existing numbered-object review layout and controls. Its same-origin
routes delegate saves to `ReviewRepository` and `VRContentService`, including optimistic
versions and audit history; the server supplies the logged-in actor identity. Legacy preview
templates import these same implementations. Upstream outputs enter the current VR/3D shared review UI automatically, without a second
project selection or transfer confirmation. Saved changes automatically export a new local
environment input, without rerunning models/Marble or overwriting an old game package.

`export_scene(..., include_assets=False)` 供本机审核输入更新使用：保留当前元数据、原导览和审核快照，不在中间ZIP中重复装入场景二进制；默认仍导出完整可搬运场景。

### Existing SPZ / PLY import

`raw-scene-import --spz SCENE.spz --mesh SCENE.ply --workspace OUTPUT` imports an existing scene locally; it never calls Marble. PLY must be a binary little-endian triangle mesh. Local Chrome, Node.js and hardware WebGL render six derived observations, await actual scene rendering, and record camera matrices and input hashes. A blank direction is preserved unchanged in the panorama when other directions contain texture; it is never filled with neighbouring content. An entirely uniform/blank capture still fails before matching. `scene/capture-quality.json` records each face hash, contrast and informative/blank status, bound to the capture manifest. Saved six-face captures can resume locally without rerendering or new model calls. The output contains `scene/scene.json`, `raw-scene.json`, `capture.json` and `tour.html`; `scene3d-attach --local-scene` attaches a matched single-scene environment. Derived observations are not original photographs, and automatic positions/scale remain unapproved until reviewed. Organizer owns Evidence/matching authorization and downstream handoff.


Organizer uses one PDF + SPZ + PLY route for every PDF: verified scene renders → shared Evidence recognition, PDF source association and quotation checks → verified structured handoff → environment-handoff → scene3d-attach. The human-layout mapping PDF is not reread by a model. The source-text snapshot is bound to the unchanged original PDF hash and all page/line records; import uses that canonical extraction, including OCR pages, without PDF text/render subprocesses. Review images for text evidence are labelled text-preview cards, not original page renders or historical object photos. There is no catalog-layout classifier, special numbered-entry parser or fixed photo crop. The `catalog3d` entry ID and old saved quote-order marker remain compatibility data only. Derived views retain SPZ/PLY/capture provenance and are never labeled original field photographs. Environment-only requests stop before Story and assembly. Source PDF ingestion extracts every page as text; only scans/garbled pages use temporary rendering and local Tesseract OCR. Normal pages are not rendered; quotations retain original source/page/line selectors. Scene capture and the generated mapping-document transport remain separate environment artifacts. Missing OCR/language data, low-confidence recovery, corrupt input and unsupported evidence remain explicit diagnostics; a unified route is not a guarantee of a match.

Local capture chooses a horizontal triangle near the lower floor of the registered collision mesh, nearest the area-weighted floor centre, and places the camera at the existing provisional eye-height assumption. It falls back to the provider origin when no floor is available. The actual camera translation is recorded from all six matrices and checked for consistency; it is never hard-coded to a global height. This remains candidate calibration, not measured or human-approved placement. Existing capture receipts are retained; a changed camera requires a fresh generation run and does not reset prior usage.
New implementation files: [raw_scene.py](src/pastport_matched_environment/application/raw_scene.py) (bounded geometry import and injected capture lifecycle), [raw_scene_render.mjs](src/pastport_matched_environment/scene3d_assets/raw_scene_render.mjs) (owned local capture process), [raw_scene_capture.html](src/pastport_matched_environment/scene3d_assets/raw_scene_capture.html) (awaited GPU rendering), [test_raw_scene.py](tests/test_raw_scene.py) (offline format/capture/source-change boundaries).

Admin writes an explicit workspace token-policy marker to disable cumulative recorded-token stops. Remaining token allowance is then None; actual execution usage remains persisted, and call limits/timeouts/recovery checks remain active. Standalone workspaces without the marker retain their grant threshold.

Offline geometry supports at most 600,000 triangles with a bounded 1,536 MiB Node heap, a 100 MiB collider/input profile, unchanged output limits and timeout. The triangle bound is checked before allocating triangle records. This supports the supplied 583,649-triangle phone-capture mesh without removing collision geometry or treating unknown geometry as allowed.

Raw phone-capture scenes use one overview plus six detail views: four horizontal headings and upward/downward views at ±80 degrees. This keeps the eight-image request bound including the reference sheet, and preserves the existing two-call localization/audit pair. Ordinary VR retains its horizontal profile. The raw view profile has a separate run identity, so prior localization results are not silently reinterpreted. `localization-report.json` records per-object/view dispositions and located/unlocated numbers. Admin handoff messages report counts and missing numbers; an environment handoff is not a claim that every object is mounted or historically approved. A changed camera profile requires fresh localization authorization; local rendering itself issues zero model or Marble calls.

Native IDML handoffs can enter through `python -m pastport_matched_environment.idml_cli --handoff native-handoff --tour raw-scene/tour.html --workspace environment --run-id run --grant environment-grant.json`. This reuses localization, independent point checks, structural review, source-bound review storage and existing local 3D attachment. Source units retain IDML member/paragraph selectors; their internal integer keys are not PDF page numbers. PDF import remains separate. The offline IDML-to-review fixture rejects any `pdftotext`/`pdftoppm` execution and verifies completed stages are reused. The real IDML run handed off 48 matches, localized 34 candidates and projected 30 3D positions. The Organizer history preview exposes these positions for surface review. The 15 confirmed and reopened anchors milestone remains open.

审核页生成模板为物件名称、识别特征和判断说明保留 `data-review-display` 标记，状态标记独立于原始编号与枚举值。Organizer 通过同一语言模块和原文哈希缓存显示英文／土耳其语；不会覆盖权威数据库、原文引文或编辑框。新任务的静态界面直接复用该规则，新产生的自由文本需生成对应译文后显示，不能借用旧物件译文或宣称未翻译内容已经完成本地化。

Organizer 的新上传任务在环境准备完成前自动通过审核端口生成英／土译文，沿用原文哈希缓存；静态 SDK 离线导出本身不会偷偷调用模型。仅界面切换不调用模型。
