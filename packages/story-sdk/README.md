# PastPort Story SDK

## Current integration contract

| Item | Current behavior |
|---|---|
| Inputs | Original PDF/Evidence, reviewed object content, matched space/navigation, gameplay capabilities and brief. |
| Outputs | Readable script, NarrativeDraft, explicit task gameplay/spatial intents, author report and execution receipts. |
| Workflow | Lock four input constraints → generate or revalidate saved response → typed/source/rule checks. |
| Technology | Shared Python 3.12/FastAPI/LangGraph/SQLite runtime; metered Sol 6.1 Medium transport. |

Unified architecture and exact current verification scope: [Technical PRD](../../docs/TECHNICAL_PRD.md#sdk-modules). Main reuses the registered upstream outputs and saved Story in its current replay entry; this is not a new recognition/rendering/model run.

Create a short readable story plus a typed NarrativeDraft from registered PDF,
Evidence and matched 3D environment exports. Gameplay preparation, UI, game
packaging and publication are outside this SDK.

| Component | Ownership |
|---|---|
| `pastport-story` | Public Python interface and installed Story-only CLI. |
| `pastport==0.2.1rc4` | Shared existing graph, contracts, budget, receipts and adapters. One dependency, no second engine. |
| `pastport/bundled_skills` | Canonical Skills bundled automatically by the shared wheel build. |

Story orchestration is supplied by the matching shared runtime. Changes to that
implementation require a corresponding runtime version; SDK/API changes have
their own version. This release separates installation/API boundaries, without
copying the runtime or creating another repository.

Both distributions are local release candidates. Use the matching wheelhouse;
this does not imply either package has been published to an external registry.
Python 3.12 and a previously signed-in Codex CLI are required for real generation.
Sol 6.1 Medium uses account quota; SDK installation and offline validation do not.

## Install

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --find-links /absolute/path/wheels 'pastport-story==0.1.0rc4'
.venv/bin/pastport-story --help
```

The wheelhouse includes the matching shared runtime. Other pinned dependencies
must be available from your package index or wheel cache. Run outside the source
checkout; the installed CLI supplies bundled Skills automatically.

## CLI

```sh
pastport-story \
  --pdf /absolute/path/original.pdf \
  --source-document /absolute/path/source-document.json \
  --environment /absolute/path/story-environment-input-with-spatial.json \
  --media-directory /absolute/path/result/media \
  --output /absolute/path/new-story-run \
  --brief 'Create a short story whose decisions depend on the supplied heritage.'
```

One generation request is budgeted. Same-run retries never silently spend again.
Model waiting is bounded at four minutes. Original response, invocation identity,
actual usage or unresolved usage, local normalization and validation are retained.
A changed input/Skill/execution setting requires a new output directory.

## Python

```python
from pathlib import Path
from pastport_story import StoryClient, StoryRequest

async def generate_story():
    return await StoryClient().generate(StoryRequest(
        original_pdf=Path('/absolute/path/original.pdf'),
        source_document=Path('/absolute/path/source-document.json'),
        environment=Path('/absolute/path/environment.json'),
        media_directory=Path('/absolute/path/media'),
        output_directory=Path('/absolute/path/new-story-run'),
        brief='Create an evidence-grounded story and tasks.',
    ))
```

`StoryResult` provides paths to the short script, NarrativeDraft, validation,
input lock and budget. `StoryError` exposes core typed operational failures.
Human approval remains false. `revalidate_saved_response=True` disables model
transport and validates a saved response only; it cannot recover absent usage.
An explicitly injected Python provider runs under the core's test-only policy.

## Boundaries

Existing source/review/spatial identities and uncertainty are retained. The SDK
uses supplied environment results, without rematching or rebuilding the scene.
Passing schema/reference checks does not establish narrative quality, historical
approval, physical accessibility, gameplay readiness or successful game assembly.
Large private materials and Codex login credentials are not bundled.

| Source | Purpose |
|---|---|
| `client.py` | Typed request/result and shared-workflow composition. |
| `cli.py` | Existing Story CLI with installed resource defaults. |
| `__init__.py` | Stable public exports. |
| `__main__.py` | Module command entry point. |
| `py.typed` | Typed package marker. |

## Installation acceptance

Main runtime 0.2.1rc4, Story 0.1.0rc4 and Gameplay 0.1.0rc2 were installed with the three upstream SDKs outside the checkout. Saved real output was revalidated without changing the draft or making model calls; preparation, presentation, independent assembly and both ending branches passed. Source/fresh-generation evidence and installed replay evidence remain separate. Human content-quality acceptance is pending. See the Technical PRD for current counts and scope.

### Structured task location output

The current source implementation emits `NarrativeDraft.spatial_intents` with
`task_id`, `object_number`, `view_id`, `station_id` and `interaction`.
New Story automation validates exact task coverage and registered source-reading
stations/view connectivity. The environment owns coordinates and physics; Story
selects existing identities. Gameplay preparation consumes the selected station
and pins the full draft; presentation still owns ordered movement and UI binding.
Legacy drafts can be read but are not silently assigned an arbitrary view.
The current candidate includes these contracts, explicit gameplay intents and the shared capability catalog. Older archives remain unchanged.

### Current paired SDK acceptance

The current shared runtime includes the latest capability catalog, neutral explicit gameplay
intents, audited normalization and tuple-schema support. It is paired with
`pastport-gameplay==0.1.0rc2`. A local candidate distribution is not a public release.
Installed-package acceptance revalidates the saved real Sol response with provider
transport disabled, then prepares and presents all three tasks. The separate
assembler produces a game whose two branches and lifecycle checks pass. No new
model call is made for package verification; fresh generation was verified before
packaging. Human narrative/game-quality acceptance remains pending.

<!-- BEGIN FILE INVENTORY -->
## 文件结构与用途

每个文件的用途直接写在同一行。以下覆盖本范围内的 **8 个维护文件**；依赖环境、缓存、私有产物和历史备份不属于源码清单。

```text
story-sdk/
├── src/
│   └── pastport_story/
│       ├── __init__.py  # Public Story-only SDK; generation reuses the shared PastPort runtime.
│       ├── __main__.py  # Support python -m pastport_story.
│       ├── cli.py  # Standalone installed command reusing shared CLI and canonical Skills.
│       ├── client.py  # Typed Python interface over the existing metered Story authoring use case.
│       └── py.typed  # PEP 561 类型标记，让安装方的类型检查器识别本包类型。
├── LICENSE  # 本模块的许可证；分发源码或安装包时保留。
├── README.md  # 本模块的使用入口、输入输出及完整文件用途说明。
└── pyproject.toml  # 本项目的包名、依赖、命令入口与构建配置。
```
<!-- END FILE INVENTORY -->
