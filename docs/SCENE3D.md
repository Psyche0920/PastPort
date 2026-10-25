# Matched environment → Marble 3D

Owner: wehan. Branch: `codex/pdf-to-3d-standalone`, based on
`codex/pdf-to-vr-standalone`. The animation branch is unchanged.

## Flow and user entry

Use the existing PDF + panorama matching first. The new optional stage freezes its
review database using SQLite backup, keeps the original panorama, identities,
numbering, quotations, introductions, human edits and backend links, and then uses
Marble for the scene asset. Matching is not repeated against a blurry generated 3D.

Start the same Studio command from the README. Each completed VR record has its own **生成 3D** action. It opens the 3D page
already bound to that result and its initial panorama; users do not select internal
IDs. Only project name, API Key and explicit generation are shown in the main form.
For multiple panoramas, select one deliberately; there is no implicit camera-pose
estimation or multi-world stitching.

Two modes are available:

- Import existing `world.json`: downloads full-resolution SPZ when available (500k only when absent)
  SPZ, collider GLB and panorama from the Marble CDN. No new generation or model usage.
  The CLI also accepts contained local asset references in a world export folder.
- Generate from the selected clean source panorama: requires local `WORLDLABS_API_KEY`,
  an explicit single-generation authorization and a credit budget. The key is inherited
  by the child process; it is never entered in the page or saved in the project.
  Set it locally before starting Studio. This delivery did not use a key or call the
  paid generation endpoint.

The original panorama viewer is preserved. The 3D result has its own snapshot database
and stable saved-result link; subsequent 3D review edits do not write back into the
upstream result. Both the 3D popup and its review page use this snapshot database.

## CLI

Import an existing result without model calls:

```sh
uv run --locked pastport-pdf-vr scene3d-attach \
  --environment /absolute/path/to/matched-environment \
  --world /absolute/path/to/world.json \
  --source-scene SOURCE_SCENE_ID \
  --workspace .runtime/scene3d-site
```

The source scene IDs are in the environment's `vr_trial/trial_report.json`; these
are the imported scene IDs, not the old input IDs. Studio offers them automatically.
The result includes `start_3d.py`; run it with this package installed to serve the
review page and `/scene3d/index.html` locally on port 8796. Ctrl+C stops the service.
Studio owns and closes the local preview/import processes that it starts.

When the operator is ready to spend credits, configure `WORLDLABS_API_KEY` locally and run:

```sh
uv run --locked pastport-pdf-vr scene3d-generate \
  --environment /absolute/path/to/matched-environment \
  --source-scene SOURCE_SCENE_ID --workspace .runtime/scene3d-generation \
  --model marble-1.1 --credit-budget 1500 --authorize-marble
```

The same command resumes the same job. A pending operation returns immediately;
resume polls its saved ID instead of submitting another generation. The browser
provides the same generation/resume controls. Unknown submissions stop rather than
retry. Do not create a different workspace to bypass a recovery-required job.

Supported models are standard Marble 1.1 and Draft, with documented existing-pano
estimates of 1500 and 150 credits respectively. This is a local admission budget and
one-submission limit, not a provider-enforced hard billing cap. Settled provider
costs are recorded separately; unknown usage is never reset. No automatic model
fallback, repeated generation, HQ export or auto-refill configuration is included.

The generator sends the clean panorama with `is_pano=true`, a fixed seed,
`disable_recaption=true` and preservation guidance. These constrain the request but
cannot guarantee that object appearance or geometry remains unchanged. Raw panorama
images are not object evidence for new historical claims. Source matching remains
bound to its original PDF and photographs.

## Alignment and hotspots

SPZ raw coordinates are scaled using the returned metric scale, ground offset and
Marble's documented OpenCV-to-Three.js X-axis half-turn. The collider is loaded in
the same asset group. Check its alignment to the splat visually; do not treat these
metadata or a ray hit as physical survey accuracy.

The original panorama camera pose inside a generated world is unknown. Initial camera
values are guesses. Align it against the preserved original panorama and record the
basis. The UI stores translation and yaw/pitch/roll, with a version check. Existing
confirmed anchors must be removed before changing this alignment.

After alignment, an original hotspot direction can intersect the collision surface
to propose an XYZ point in metric Three.js coordinates. A missed ray stays missing.
A hit does not prove object identity or correct depth. Manual surface picking can
correct the candidate. The user confirms that the original object still exists,
records an identity basis, and saves it before it becomes a visible 3D hotspot.
Whole/part membership needs a confirmed whole and an explicit physical relation
basis. Rejected historical bindings remain excluded. All new anchors start empty.

Anchor edits bind to the source snapshot/world version, use compare-and-swap versions
and idempotent operation IDs, and retain edit events. Changing input creates a separate
result. Original panorama angles are never labelled as verified three-dimensional
coordinates. Stale saves return conflicts instead of overwriting another edit.

## Execution evidence and limits

One real, already-generated Marble SPZ/GLB/panorama export was downloaded and attached
to an isolated copy of an existing matched environment. No new model calls or paid
Marble generation occurred. That export came from an unrelated indoor-video pilot;
it proves asset/data handoff only, not corresponding object identity, correct camera
alignment or museum acceptance. No candidates were confirmed as business hotspots.

Local strict typing and syntax/lint checks cover the new modules. No automated test
suite, fresh paid generation, browser/device acceptance or museum-quality acceptance
was run. The user will manually assess appearance, movement, identity, calibration and
saving after supplying the key for the final trial. Original inputs and databases
remain untouched. The main repository checker is absent on this standalone branch.

## Source map

| Source | Purpose |
|---|---|
| `application/marble.py` | Bounded local/CDN export registration without generation |
| `application/marble_generation.py` | Explicit one-shot generation, frozen source and saved-operation recovery |
| `application/scene3d.py` | Isolated environment backup and fixed three-stage attachment |
| `api/scene3d_studio.py` | Additive Studio selection/import/generation entry |
| `api/scene3d.py`, `domain/scene3d.py` | Versioned camera/anchor edits and source binding |
| `scene3d_assets/` | Pinned Spark 2.2.0, Three.js 0.180.0, notices and the 3D viewer |

API references: [generation patterns](https://docs.worldlabs.ai/api/world-generation-examples),
[scale and axes](https://docs.worldlabs.ai/api/rendering-spz),
[pricing](https://docs.worldlabs.ai/api/pricing),
[Spark loading](https://sparkjs.dev/docs/splat-mesh/).

## Separate generation records and key dialog

The homepage has two distinct sections: VR matching records, and 3D generation
records. Generation starts from the specific VR record, not a second global entry. 3D records
show the source title, import/generation mode, running/pending/stopped state, an
explicit query-original-task action when an operation exists, and a ready 3D
output link. Review and native-asset links remain available through the output/API
without cluttering the primary record card.
Read-only refresh never submits or polls a provider task. No fake result is created
when there is no 3D output. The generation page uses the same records component.

The 3D page accepts the key in a password field and stores it only for the session.
The primary flow requires no internal view IDs, model selector or export JSON. An
optional collapsed **导入已有 3D** form retains existing-export import without a
key or new generation. Both paths bind automatically to the selected VR result.
The API returns only configured state, never the key. Local edit protections apply
to setting and clearing. A key already passed to a running request is not revoked
by clearing the session field. No real-key call was performed for this UI change.

## Portable development package

The 3D output includes **下载开发文件包**, also available from a ready record. It
creates a ZIP from a consistent current SQLite snapshot. The package contains
`manifest.json`, `game-data.json`, original SPZ, glTF 2.0 collision GLB, the source
and matched PDFs, source media and an audit database. Object stable IDs, historical
bindings, exact evidence, current human introduction and confirmed metric anchors
remain separate from generated geometry. Withheld/unconfirmed anchors are null.

The manifest states units, handedness and asset-to-world transform. Unity and Blender
can consume the GLB, but the current GLB is collision-only; SPZ requires a compatible
splat renderer or conversion. This is not a claim that a complete textured modelling
asset is already present. No paid HQ mesh export is performed. Engine-specific import
adapters and visual-mesh authoring remain downstream work. The package is a private
local download, not an automatic public publication or main-framework acceptance.

The Marble request now prioritizes faithful translation-only reconstruction: retain
identity, appearance and layout; no repair/restyling or creative additions. Only tiny
unavoidable geometric adjustments for translation are allowed. Restoration belongs
to the later art stage. The exact prompt hash is bound to the generation job.

## Pre-payment preflight

A network-disabled isolated run with simulated provider responses checked ten
behaviors: one submission then polling, completed resume without a new call, actual
local asset attachment, empty unconfirmed anchors, alignment conflict, anchor
idempotency/conflict, reload persistence, unknown-dispatch blocking, pre-dispatch
budget rejection and repeated frontend POST reuse. The portable ZIP was also opened
and its assets, identities and withheld anchors checked. Two defects were fixed:
source backup parent creation and repeated requests creating separate paid jobs.

These checks used no real key and spent zero credits. They do not verify provider
availability, actual final billing, visual fidelity or Unity/Blender import behavior.
A source result now owns one generation job; changed parameters stop for review,
not a second hidden charge.

The paid boundary additionally has a source-panorama ownership ledger outside the
source result directory. Even a different job directory or older frontend cannot
submit the same panorama again; it must resume the owning job. Existing submitted
jobs are registered without changing their request or resetting their usage. Three
committed offline regression tests cover this guard, repeated frontend POST and
source-backup parent creation.

## Rendering quality

Full-resolution SPZ is now preferred over the 500k simplification. The existing
trial keeps its original 500k bytes and registers a hash-bound full-resolution
render variant from the same world; anchors and review data are not rewritten.
Native screen pixel ratio is used. For an unconfirmed untouched camera, the initial
position starts at the converted generated-asset origin, not an assumed 1.6 m height.
This is an initial viewing position, not verified source-camera alignment.

The actual request used the unchanged 4096×2048 JPEG from source viewpoint 1,
encoded as an image with `is_pano=true`; the saved byte hash matches. Only the
initial viewpoint of the two-view panorama tour was submitted. Full-resolution
rendering and its development-package asset were checked without regeneration.
This does not repair inaccurate generated geometry or prove parity with a different
Marble-platform run/input.
