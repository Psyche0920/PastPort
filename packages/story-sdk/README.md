# PastPort Story SDK

## Current integration contract

| Item | Current behavior |
|---|---|
| Inputs | Original PDF/Evidence, reviewed object content, matched space/navigation, gameplay capabilities and brief. |
| Outputs | Readable script, NarrativeDraft, explicit task gameplay/spatial intents, author report and execution receipts. |
| Workflow | Lock four input constraints → generate content plan → deterministic graph compilation → typed/source/rule checks; old saved runs retain their pinned contract. |
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

## Reuse after review or spatial edits

Organizer's shared runtime performs provider-free compatibility checks before
reusing an old story against a new environment version. It selects a successful
parent only from the same authorized source lineage, verifies story locks and
source identities, and checks task evidence, current spatial intents and gameplay
executability. Unused-object edits do not invalidate unrelated tasks. A changed
used introduction or source mapping is conservatively reported for that task;
compatibility is not inferred from a marker merely being visible. If only a used
introduction changed and executable checks pass, Organizer offers explicit
confirmation bound to that report, environment, parent story and exact changes.
The confirmed reuse records its actor/time and leaves the story unchanged.
Changed source mapping, missing objects or non-executable tasks remain blocked.

A successful check creates a separate reuse record with unchanged narrative
bytes, new environment/index locks and a hash-bound parent reference. Existing
model receipts and usage remain with their original run. Game preparation
validates this proof instead of re-running a model response under changed inputs.
No Story generation or paid repair is implicit in this path.

## Fixed structure for new Story runs

New automatic runs use `compiled_plan_v1`: the model returns a `StoryPlanResult`
with bilingual task content, registered source/object/view selections, supported
gameplay requirements and final choice consequences. The shared runtime's
[compiler](../../src/pastport/application/story_compiler.py) generates every internal
task/scene/rule ID, locale key, variable declaration, completion transition and
ending reference. Runtime/plugin contracts downstream remain `NarrativeDraft`.

This first profile supports 1–8 ordered one-task scenes and 2–4 final choices.
It does not represent arbitrary mid-story branching or model-authored state
machines. Unsupported structure must return an explicit infeasibility reason.
Source validity, spatial executability, capability limits and quantity consistency
remain separately checked. The raw metered response is retained; compilation does
not trigger a repair call or erase previous failed generations. Existing runs use
the structure profile pinned by their input lock; locks without that field mean
legacy `authored_graph`. An old failed graph is never silently converted.

The fixed path has passed deterministic-provider generation/resume and the real
JS runtime's task-to-ending execution. No fresh paid generation has been performed
for this change. Existing wheel archives predate this change and need rebuilding
before independent-install acceptance can be claimed.

## Implementation location

The public SDK remains in this package. Story generation and validation are implemented
in the shared runtime's [story_authoring.py](../../src/pastport/application/story_authoring.py),
with model and workflow wiring in [model_narrative.py](../../src/pastport/adapters/model_narrative.py)
and [story_workflow.py](../../src/pastport/adapters/story_workflow.py).
Installing this SDK installs the matching `pastport` runtime; it does not fetch source
files from a working checkout at execution time. Story outputs data for Gameplay;
it does not package the frontend or execute minigames in the player's browser.

The source-layout migration preserves these APIs. The paired installed SDKs passed
saved-response revalidation, local preparation/presentation, assembly and browser
acceptance without another model invocation. Current local candidate artifacts are
under `var/runtime-layout-20261101/`; prior wheel archives are not rewritten.

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

## Model reference binding

New Story generation selects registered claim IDs and asset IDs (for example,
`claim-object-86` and `object-86`). Native object UUIDs are omitted from the model's
object projection. The model gateway constrains `authoring_report.heritage_refs`
to the pinned Evidence package's keys **before** computing the schema identity and
reserving the model call, then validates the returned keys again after metering.
The existing environment/asset join supplies native identities for downstream use.
Known but unrelated object references still fail task-linked checks; they are not
silently replaced. Original provider responses and usage receipts remain intact.
Legacy saved drafts retain their original schema and inspection path.

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

### Byte-bound environment snapshots

Story preserves the exact registered environment JSON bytes because `input-lock.json` binds their file hash. It does not serialize the DTO again before handing it to Gameplay. Revalidation can reconcile a prior formatting-only snapshot only after checking semantic equality, preserving its previous bytes and a zero-call reconciliation receipt. Changed semantic content remains an error. Narrative Skill rules do not replace this file-integrity contract.
