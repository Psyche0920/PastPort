# Environment stylization: panorama and 3D paths

Owner: wehan. Branch: `codex/environment-stylization`.

The existing panorama animation implementation remains available. The additional
3D path consumes one native complete-tour ZIP and returns one styled complete-tour
ZIP. Its independent scenes retain source order, object identities, evidence,
saved spatial edits and arrow-plane navigation. It does not geometrically stitch
the worlds. `workflow/environment_stylization.py` exposes both typed paths for a
parent LangGraph; the existing `AnimationNode` API remains compatible.

## Appearance implementation and limits

This version uses source-bound, full-resolution painted panoramas. Callers can reuse
existing artwork or authorize the existing bounded animation stage to paint new maps. The actual SPZ DC appearance coefficients are changed:
this is a three-dimensional asset output, not a screenshot or a postprocessing
filter. Original Gaussian centers, scales, orientations, opacities and point count
are retained. The full-resolution registered variant is preferred.

Projection uses the saved source camera when available. Otherwise the current
viewer's automatic camera estimate is used and processing continues, as requested
by the user. That estimate is recorded, never labelled as human-confirmed. A coarse
angular depth buffer limits foreground texture projection onto hidden surfaces;
hidden splats receive a palette derived from paired original/painted panorama
pixels. This is not a verified visibility solution or consistent multi-view texture
optimization. Moving around can expose projection misalignment or texture defects.

The supported input is bounded gzip SPZ v2 with degree-zero spherical harmonics,
matching the two current Marble assets. Other SPZ versions/SH degrees and textured
mesh painting are explicitly rejected rather than silently converted. Source
panoramas and painted maps must retain their original 2:1 dimensions and SHA-256
bindings. Geometry fabrication and high-quality mesh export are not included.

**Structural corrections, missing geometry and far-view geometric inconsistencies
are not solved by appearance baking.** Those remain unresolved acceptance items.
The current deliverable is an initial appearance candidate, not fulfillment of
the full repair/quality acceptance target. All generated imagery remains
illustrative and cannot become historical evidence.

## Tour and content contract

Export the native complete tour with `application.scene3d_tour.export_tour`.
Each native developer ZIP now retains the original clean source panorama, data-only
source tour, attachment, source import manifest and the registered render variant,
alongside evidence and a current review snapshot. Older ZIPs without these bindings
must be exported again from the saved result; no new generation is needed.

The importer checks archive paths, duplicate entries, symlinks, expansion bounds,
per-view checksums and exact viewpoint coverage. Uploaded HTML/Python is never run;
the viewer/review runtime comes from the trusted current package.

The isolated candidate has one tour-level review snapshot and retains the shared
content authority implementation from `codex/matched-environment`. Legacy linear
human histories are reconciled in this isolated snapshot; divergent histories stop
without overwriting either copy. Each scene keeps its own position, alignment and
navigation database. Candidate edits are shared across its two 3D/VR views but do
not mutate the original saved tour's authority. A portable tour is a project
snapshot, not a live link back to the author's source database.

## Run and handoff

The typed `Style3DTourRun` takes `source_archive`, a fresh `workspace`, and either an exact
tuple of `ExistingPanorama` bindings or an explicit subscription grant plus the injected
animation workflow. A calling graph can construct these from its
existing panorama animation delivery; the user does not have to author IDs/JSON.
This 3D baking stage has no SDK/API transport and cannot dispatch paid generation.
New painted maps remain the responsibility of the existing bounded 2D animation
stage. This delivery reuses both existing maps and makes zero new model calls.

```sh
uv run --locked pastport-style3d --tour-request /absolute/path/to/request.json
uv run --locked python -m pastport_pdf_vr.application.stylization3d_preview \
  --delivery /absolute/path/to/candidate/delivery.json
```

The delivery contains the complete archive and per-view manifests plus one
candidate content authority. `Style3DNode` is the low-level single-view callable;
`EnvironmentStylizationNode` accepts a panorama request or a whole-tour 3D request.
The standalone preview serves only loopback, starts owned per-view preview children,
rewrites only isolated navigation URLs and cleans up children when stopped. It
offers original/stylized appearance comparison from the same camera. It does not
start or restart the user's Studio. The download is a native developer asset tour,
not a self-contained offline executable or a Unity project.

## Current delivery evidence

The real Muradiye complete tour was exported from the two saved results and passed
through this whole-tour path with the two existing 4096x2048 painted panoramas.
It produced a complete ZIP and full-resolution styled SPZ assets without inference.
Automatic camera estimates were used. Source scene files, source databases and the
existing workbench were not replaced. New Python code has scoped strict typing,
Ruff and diff checks; no automated runtime/browser tests were added or run for
stylization. Startup of the isolated delivery preview is not visual acceptance.

User acceptance covers animation appearance, source fidelity, far/hidden regions,
shared content, original comparison, numbered-object placement, arrow edits,
bidirectional transitions and package usability. The existing Muradiye demo remains
the minimum quality baseline until a better candidate is explicitly accepted.

## Source-purpose map

| Source | Purpose |
|---|---|
| `domain/stylization3d.py` | Source/camera/appearance bindings and delivery records |
| `adapters/spz_style.py` | Bounded SPZ v2 appearance baking with preserved geometry |
| `application/stylization3d.py` | Isolated single-view snapshot and registered appearance |
| `application/stylization3d_tour.py` | Safe complete-tour import, one shared authority and package output |
| `application/stylization3d_preview.py` | Owned local multi-view acceptance preview |
| `workflow/environment_stylization.py` | Typed panorama/3D route for parent graphs |

Format references: [SPZ source](https://github.com/nianticlabs/spz),
[SPZ color packing](https://github.com/nianticlabs/spz/blob/main/src/cc/splat-utils.h).

## Upload and automatic generation

Run `uv run --locked pastport-stylize-studio --workspace .runtime/stylization-studio --port 8795`
and open `http://127.0.0.1:8795/stylization`. The integrated Studio also exposes
`/stylization`; an already running Studio must be restarted to load new code.
The separate entry does not restart or replace the original workbench.

Upload one complete native ZIP, at most 2 GiB. Supported formats are labelled
schema-4 VR exports with their review database and native 3D tour archives retaining
clean source panoramas and source-tour metadata. Inputs support 1–16 viewpoints,
2:1 panoramas up to 4096x2048, and the SPZ v2/SH0 subset above. Standalone meshes,
arbitrary vendor files and higher-resolution inputs require adapters; they are
rejected before generation rather than silently downsampled. Uploaded code is not run.

Every upload displays a whole-tour estimate before generation. Each viewpoint needs
six image turns. Historical one-view usage was 336,406 recorded tokens; this is an
estimate basis, not a guaranteed price or quota conversion. Displayed estimates use
56,068–85,000 tokens per turn. Image-turn and recorded-token fields are optional;
blank values use the visibly disclosed suggestions of six turns per viewpoint and
100,000 recorded tokens per turn. Users can enter their own limits. Starting requires
explicit consent. A budget too small for the full estimated tour does not start.
The token threshold gates subsequent turns, so an in-flight turn can exceed it;
the image-turn limit is bounded. No automatic budget increases or extra variants.

`application/automatic_stylization.py` routes supported uploads through the existing
metered subscription adapter, then assembles VR or bakes and packages 3D. Identical
upload bytes reuse the saved job. Resume retains its original grant, usage ledger
and completed artwork; uncertain calls are not automatically retried. Fresh input
model generation through this entry has not been live-validated. User performs
runtime and visual acceptance. This is not a claim of universal 3D conversion or
structural repair.

| Additional source | Purpose |
|---|---|
| `api/stylization_studio.py` | Local uploads, estimates, optional limits, explicit consent and owned jobs |
| `application/automatic_stylization.py` | Native input preflight and metered VR/3D orchestration |
| `web/stylization.html`, `web/stylization.js` | English upload and manual acceptance entry |

The VR upload adapter requires a portable review snapshot. A package containing a
live `shared-content.json` authority pointer is retained and rejected before any
generation; it is not deleted or rebound by the upload adapter.

## Staff preview interface

The stylization module uses the shared Studio stylesheet and workspace navigation.
Completed records open in an embedded preview, with a separate-window option,
fullscreen and ZIP download. A complete 3D tour opens its first viewpoint directly
and offers viewpoint buttons inside the preview. This is a module of the planned
single staff website, not a separate product. The standalone loopback entry remains
for local development. Preview quality and interaction acceptance are manual.

| Preview source | Purpose |
|---|---|
| `web/studio.css` | Shared workspace appearance and navigation |
| `web/stylization.css` | Stylization layout and embedded preview controls |
| `web/styled-tour-preview.html` | Trusted first-view 3D preview and viewpoint toolbar |
