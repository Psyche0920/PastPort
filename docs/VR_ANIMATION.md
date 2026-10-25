# Labelled museum → animated VR

This branch adds an executable animation workflow to the existing PastPort repository.
It leaves matched-PDF generation available as an upstream producer. The animation
node is callable from Python/LangGraph or the CLI. The `/stylization` staff page
now uses the independent reference-guided Agent for new jobs; legacy jobs keep their mode. No new repository, server deployment or provider is required.

## Input and output

`AnimationRun` takes an existing reference-environment directory, a fresh isolated
workspace, and either `existing_panoramas` or a finite subscription `grant`.
The directory contains `vr_trial/index.html` with one embedded schema-4 `tour-data`
block, `pastport_matching.sqlite3`, `vr_trial/trial_report.json`, and its evidence/media.
Embedded JPEG/PNG panoramas must be full 2:1 spheres. Arbitrary remote URLs, vendor
runtimes and bare screenshots need an adapter; uploaded code is never executed.

`AnimationDelivery` returns the isolated environment directory, ZIP path, manifest
path, viewpoint count and pending human-acceptance state. The output keeps the same
schema-4 tour identities, object labels, introductions, navigation, spatial metadata
and evidence database. Current human content and coordinates come from a SQLite
backup, not an unsafe copy of a live DB file. New textures receive new hashes and
panorama revisions; inherited angles remain proposals for manual review.

The ZIP includes the data, evidence, packaged review/VR runtime and
`STORY_AGENT_HANDOFF.md`. Use `animation-manifest.json` to distinguish original
sources, reused media, new generations and pending acceptance. Artistic invention
is never historical evidence. Input material is not overwritten or published.

## Two explicit execution modes

**Reuse existing images:** supply one immutable `ExistingPanorama` per scene with
its scene ID, source panorama SHA-256, existing image path/SHA-256 and provenance
reference. The workflow requires exact scene coverage and original sphere dimensions,
copies bytes unchanged, updates tour data and packages the result. No transport or
grant is needed; no SDK process, inference or new model usage occurs. This is the
selected mode for the current two-viewpoint flow run.

**Generate new images:** provide `SubscriptionGrant` and `CodexImageTransport`.
FFmpeg extracts six padded cube directions. Each source face and the pinned style
image are passed as actual SDK image inputs, not merely described by name. Subsequent
faces use the first front face for material consistency; later views use the first
view's corresponding face. One native image-generation event is expected per model
turn. Images must be square, consistent in native size, and sufficient for the
original panorama's angular detail. Output is reprojected at the source dimensions;
insufficient native detail is rejected rather than upscaled.

The demonstrated 4096×2048 method used 1280-square source faces, 1254-square generated
faces, FFmpeg cube order `rludfb`, 5% padding and JPEG quality 94. The generic source
face size is `ceil(panorama_width / 3.2)`; required generated size is
`ceil(panorama_width / (4 * 0.9))`. Independent painting can still produce seams;
these parameters are a reproducible method, not proof of seamlessness.

The current default style is the user-approved viewpoint-two sample in
`animation_assets/approved-style-v2.png`, bound by `approved-style-v2.json` and
`policy-v2.txt`. Both generation and the independent Agent reviewer receive the
actual image. `approved_animation_style()` validates the image/policy hashes.
The old reference/policy remain available for historical runs. Resume uses each
run's frozen reference/policy and its original grant; approval of v2 does not
silently change an older run or reset unknown usage. The selected sample is a
style standard, not evidence of complete panorama or 3D acceptance.

## Python and LangGraph

```python
from pathlib import Path
from pastport_pdf_vr.application.animation import AnimationRun, AnimationWorkflow
from pastport_pdf_vr.application.animation_style import approved_animation_style
from pastport_pdf_vr.domain.animation import ExistingPanorama
from pastport_pdf_vr.workflow.animation import AnimationNode

style = approved_animation_style()
workflow = AnimationWorkflow(
    ffmpeg=None,                         # not needed in reuse mode
    style=style.reference,
    prompt=style.policy,
    transport=None,                      # guarantees no SDK calls in reuse mode
)
request = AnimationRun(
    source_directory="/absolute/path/to/labelled-museum",
    workspace="/absolute/path/to/new-isolated-run",
    existing_panoramas=(
        ExistingPanorama(
            scene_id="INPUT_SCENE_ID",
            source_panorama_sha256="SOURCE_DECODED_IMAGE_SHA256",
            image_path="/absolute/path/to/existing-animation.jpg",
            image_sha256="EXISTING_IMAGE_SHA256",
            provenance_ref="original-generation-manifest.json",
        ),  # include one binding for every input scene
    ),
)
# Add this callable directly to a parent graph, then connect its delivery to Story Agent.
node = AnimationNode(workflow)
# parent.add_node("animate_museum", node)
# parent.add_edge("animate_museum", "story_agent")
# result = node({"animation_request": request, "animation_delivery": None})
```

The capitalized hash values in the example must be real 64-character hexadecimal
hashes; the typed models reject placeholders. `build_animation_graph(workflow)`
is also available as a standalone one-node graph. Domain objects, not unstructured
SDK responses, cross the graph boundary. Story Agent receives the delivery and reads
the retained DB/evidence; it must preserve identity and source provenance.

CLI, after `uv sync --locked --extra codex`:

```sh
uv run --locked python -m pastport_pdf_vr.application.animation_cli \
  --environment /path/to/labelled-museum --workspace /path/to/new-run \
  --reuse-images /path/to/bound-existing-images.json
```

The reuse file is a JSON array of the same `ExistingPanorama` records and can be
constructed by a calling node. Users do not need to author it when calling Python.
For explicitly authorized new generation, replace `--reuse-images` with
`--grant /path/to/finite-grant.json`; FFmpeg and the existing Codex login are required.
There is no separate API-key fallback. The `pastport-animate` script exposes the same CLI.

## Usage and recovery

Generation reuses `SubscriptionExecutor`: reserve before dispatch, record SDK usage,
reuse settled requests in the same workspace, stop on unknown usage and never reset
it by resume. Grant call/token thresholds limit subsequent dispatch; a single turn
can exceed the token threshold. Model token usage is not a dollar invoice or a
hard image-credit cap. No currency charge is inferred from it.

Use `--resume` only for the identical source/style/prompt/media binding. Frozen
input snapshots and cached image hashes must remain available. A changed grant or
an uncertain dispatch is rejected. There is no automatic repair/retry loop. The
workspace has a process lock. Each candidate retains original identities and
history; no fixture rebuild or deletion of review data occurs.

## Current execution evidence and remaining acceptance

The installed SDK advertised native image generation. One real subscription turn
produced a native 1254×1254 image; a bounded follow-up reused it and generated the
other five directions of one viewpoint. That run assembled a 4096×2048 panorama.
The second viewpoint was not regenerated through the SDK.

After the user selected image reuse, the actual two-viewpoint source museum passed
through `build_animation_graph` with the two existing 4096×2048 animation files and
`transport=None`. It produced a new environment and ZIP with zero new inference.
This demonstrates process execution on real material, not a new two-viewpoint model
run, Story Agent integration, visual acceptance, a public deployment or device QA.
The user performs quality, seam, object/hotspot and interaction acceptance manually.
No automated test suite or browser/device acceptance was run for this delivery.

See [the independent Agent contract and one-repair limit](STYLIZATION_AGENT.md).
