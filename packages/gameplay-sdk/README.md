# Gameplay Preparation and Presentation SDK

## Current integration contract

| Item | Current behavior |
|---|---|
| Inputs | Checked locked Story, capability catalog, source/spatial snapshot and prepared museum. |
| Outputs | GameplayPlan, exact plugin parameters/lifecycle proof, canonical environment and presentation input. |
| Workflow | Compile declared intent → verify actual plugin/solution → bind object/station/view/UI; assembly stays separate. |
| Technology | Python typed facade, shared Node/JS host and deterministic local compilation; no model calls. |

Unified architecture and exact current verification scope: [Technical PRD](../../docs/TECHNICAL_PRD.md#sdk-modules). Main reuses the registered upstream outputs and saved Story in its current replay entry; this is not a new recognition/rendering/model run.

`pastport-gameplay==0.1.0rc2` uses `pastport==0.2.1rc4` as its single shared runtime.
It makes no model calls. Python 3.12 and Node.js are required.

| Stage | Input | Output |
|---|---|---|
| prepare | Validated locked Story directory | Typed gameplay plan, lifecycle receipts, canonical environment |
| present | Same Story, preparation, existing museum | Exact task/plugin/source/view/navigation/UI bindings (`story-input.json`) |
| Separate assembler | Prepared story input, museum resources | Playable game bundle |

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --find-links /absolute/path/wheels pastport-gameplay==0.1.0rc2 pastport-story==0.1.0rc4
.venv/bin/pastport-gameplay prepare --story-run /absolute/story --output /absolute/new-preparation
.venv/bin/pastport-gameplay present --story-run /absolute/story --preparation /absolute/new-preparation --museum /absolute/museum --output /absolute/new-presentation/story-input.json
```

Outputs must be new paths. Wrong hashes, catalog versions, source/space identities,
unsupported tasks and unsolvable puzzles fail explicitly. No implicit reading fallback.
Museum assets, private PDFs, saves and credentials are not included in distributions.
Shared host code, Skills and schemas live once in the shared runtime wheel, not in
both SDK wheels. The assembler is a separate shared-runtime tool; this SDK does not
publish, serve or package games. Current adapter supports the verified two-view
museum and reading/coverage plugins, not arbitrary games or arbitrary scene counts.

| Source | Purpose |
|---|---|
| client.py | Typed preparation/presentation API with bounded local subprocesses |
| cli.py / __main__.py | Installed command and module entry points |
| __init__.py / py.typed | Public typed exports |

## Implementation and runtime ownership

This SDK is the typed preparation/presentation entry, not the browser game engine.
Its Python implementation is shared in [gameplay_preparation.py](../../src/pastport/application/gameplay_preparation.py).
The verifier calls [gameplay/plugins](../../gameplay/plugins); presentation uses
[prepared-game.mjs](../../gameplay/prepared-game.mjs) and the shared
[contracts.mjs](../../gameplay/contracts.mjs). The player UI is in
[frontend/game](../../frontend/game); the independent assembler is in
[tools/game-package](../../tools/game-package).

The `pastport` core wheel carries the required production resources. Installed SDKs
use those bundled resources without requiring this checkout. The assembler includes
frontend code, the registered activity executor, configuration and copies generated
from the canonical [player engine](../../src/pastport/player) in the standalone game.
The Python SDK itself is not shipped to the player's browser. Current bundling
includes the whole registered executor, not a separate code slice per mechanic.

The source-layout migration passed installed-wheel replay with real saved Story,
plugin checks, browser source-failure retry, puzzle completion, viewpoint navigation
and ending reload. This reuses saved generation; it is not fresh model generation.
Local wheels and acceptance evidence are under `var/runtime-layout-20261101/` in the
repository; they are not public registry releases.

<!-- BEGIN FILE INVENTORY -->
## 文件结构与用途

每个文件的用途直接写在同一行。以下覆盖本范围内的 **8 个维护文件**；依赖环境、缓存、私有产物和历史备份不属于源码清单。

```text
gameplay-sdk/
├── src/
│   └── pastport_gameplay/
│       ├── __init__.py  # Gameplay preparation and presentation; shared engine is a pinned dependency.
│       ├── __main__.py  # Python 模块命令入口，将 python -m 调用转交本包 CLI。
│       ├── cli.py  # Local SDK commands; all generation calls remain in Story.
│       ├── client.py  # Installed local production stages over the single shared gameplay host.
│       └── py.typed  # PEP 561 类型标记，让安装方的类型检查器识别本包类型。
├── LICENSE  # 本模块的许可证；分发源码或安装包时保留。
├── README.md  # 本模块的使用入口、输入输出及完整文件用途说明。
└── pyproject.toml  # 本项目的包名、依赖、命令入口与构建配置。
```
<!-- END FILE INVENTORY -->

## Authored investigation blueprints

The shared JS player host can bind image spot-the-difference, drag timelines, image reconstruction and scene search using `prepareInvestigationBlueprint` from `tools/game-package/investigation-blueprint.mjs`. Supply a prepared runtime-package Story input, the exact museum snapshot, a filled blueprint and a local asset root; retain the returned compiled input and lifecycle/hash receipt for normal assembly. See the repository [Gameplay Preparation Skill](../../skills/gameplay-preparation/SKILL.md) for reusable patterns and a template.

This is an explicit authored preparation path. The typed Python preparation catalog still covers source reading and source-gated coverage; it does not automatically generate or accept these new intent kinds. Unsupported typed requests must remain capability gaps. Image comparison, collection and puzzle completion grant Story progress only through the shared host. Scene-source uncertainty and review authority are unchanged.

The start screen independently enables or disables Auto LOD. A device preference overrides package `startupPreparation` (`lod` or `none`). Off skips optimization but still waits for scene readiness, then presents a spoiler-free `briefing`, character introductions and gameplay. Cast and graphics controls do not depend on LOD. The display-only briefing contains a bilingual title, 1–10 heading/body sections and closing text. A collapsible SVG minimap uses same-origin collider bounds, registered object positions and camera direction, with pose updates at most five times per second. It provides orientation only, grants no observations, collects no clues and claims no metre calibration. It hides during dialogue and modal tasks.

Renderer adapters may implement `prepareWithoutLod()` for explicit original-detail activation, separately from `prepare()` optimization. The saved Spark viewer must disable its mesh and renderer LOD flags on this path; skipping the optimizer alone can leave its default LOD renderer blank. The shared player bridge adapts the bundled imported-SPZ Spark viewer using its loaded SplatMesh and SparkRenderer instances when no custom preparation hook is present. Both paths wait for initialization and renderer update; missing adapters and failed LOD generation remain failures. This adapter is renderer-specific and is not inferred for arbitrary providers.


Optional presentation-only `mapSymbols` provide a registered object number, table/chair/board/shelf/laptop/object symbol and bilingual label. The minimap draws a plain schematic, not measured room geometry. Persistent information controls use People, Story background and Case notebook.

Use optional `stationRecords` to explain why a real object matters to an authored task without changing its identity. Each entry has a registered number, localized title/body and optional assets/reference/<filename>.pdf. Keep historical reference claims separate from fictional character documents; station text grants no observations or approvals.

The automatic `present` path now projects compiler-marked `opening_context` into the same briefing, character and station cards used by authored games. It validates bilingual coverage and exact used-object coverage, never derives introductions from hidden character goals, and creates no raw-PDF links. Unmarked legacy drafts retain the previous presentation. This is deterministic saved-content integration; fresh model quality, full four-mechanic typed-intent coverage and renderer-specific LOD remain separate acceptance work.

### Deterministic investigation packaging

After `present` has written a pinned Story input, an approved filled blueprint can be
validated and packaged through the SDK, without a model call or manual output patching:

```sh
uv run --no-sync pastport-gameplay investigate \
  --input /path/to/story-input.json \
  --museum /path/to/prepared-museum \
  --blueprint /path/to/investigation-blueprint.json \
  --activity-assets /path/to/checked-image-root \
  --output /path/to/new-investigation-game
node /path/to/new-investigation-game/serve3d.mjs
```

`--input` accepts either the schema-validated NarrativeDraft bridge from `present` or
an existing RuntimePackage bridge. It preserves source identities and Story choices,
inserts the explicitly requested activities only on unambiguous edges, and packages
only manifest-checked local activity images. Search targets need an explicit common
prepared view. Images cannot overwrite museum assets; changed hashes and existing
output directories fail. The new game retains `data/investigation-receipt.json`,
including upstream/input, blueprint, runtime and asset identities, lifecycle checks
and zero model-call evidence. Existing games and their saves are not migrated.

This automates approved blueprint validation and assembly, not blueprint authoring,
image creation, fresh Story generation, human readability acceptance or Organizer
import. Older schemas/catalogs still report unsupported intents as gaps; the optional
compiled-plan design path below is separate from the base task-intent catalog.

Compiled Story plans can now include typed `activity_design`. The compiler chooses stable
interlude IDs and emits a bounded versioned blueprint; `investigate` reads it directly:
omit `--blueprint` and retain `--activity-assets` only when image files are requested.
Absent design metadata preserves legacy assembly. Malformed/different bilingual
metadata, invalid insertion edges, missing images and mismatched explicit overrides
fail. Preparation consumes the metadata once and retains the emitted blueprint beside
its receipt; rebuilding the prepared result does not insert the activities twice.
The original Story input and image files remain the reproducible upstream inputs.
This supports model-output structure and deterministic replay, not a claim that a
fresh model has produced a good game. The base `gameplay_intents` catalog is unchanged.
