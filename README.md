# PastPort PDF-to-VR Automation

Standalone implementation on `codex/pdf-to-vr-standalone`. The branch has independent history; it does not copy main's application. Main compatibility is a target contract, not a completed integration.

## Matched PDF and new VR: browser generation

Run in this checkout:

```sh
uv sync --locked --extra dev --extra codex
uv run --locked pastport-pdf-vr studio --workspace .runtime/studio --port 8794
```

Open **http://127.0.0.1:8794/**. The upload page accepts an already matched PDF
plus a fresh schema 4 static panorama HTML/folder/ZIP. Authorize the finite local
Codex subscription grant and click **生成 VR 与审核后台**. No interactive Codex
session, hand-authored JSON or previously measured hotspots are needed. A local
Codex login/runtime is still required by the existing SDK transport.

The fixed workflow registers every matched-PDF page. When the PDF has internal
links to numbered evidence entries, it derives their printed identities and all
photographic selections from those links, inspects the complete evidence pages,
and avoids repeated overview cards. Unrecognized layouts use bounded full-page
inspection. It keeps the numbered identities
and exact native quotations, crops registered photographic evidence, localizes
those same modern objects in each new viewpoint, audits projected hotspot overlays,
reviews the historical catalog before positioning, checks whole/part relations
against observable modern attachment or
containment, then assembles the demonstrated review backend and VR viewer. The
model executes through the existing durable Codex SDK grant/usage ledger. It cannot
run shell commands, edit project files or silently switch providers.

Output quality is evaluated manually by the user, who reports targeted issues.
Only audited visible positions are published. Unknown identities/positions remain
gaps. Unverified or rejected structural parts retain their evidence but receive no
hotspots. A mandatory catalog relationship review must finish before publication;
otherwise the job stops. Observed proposal/audit pair costs are reserved when available to avoid starting
a pair that clearly cannot fit. Finite budgets can produce gaps or stop a run and do not
promise completion for arbitrarily large documents. Recognition remains a model
judgment; offline tests are not new-site accuracy evidence or human acceptance.

Different-input generation runs have separate databases and permanent result links.
An identical input/model/policy in the same project reuses its existing database and
human edits without additional inference. Reloading
or restarting serves that database without regenerating it. New inputs never reuse
old object coordinates, and previous run databases/human edits remain available
through their original job links. The portal starts local result servers only when
a result is opened and stops its owned servers on normal shutdown. Keep Studio
running while editing; generated `start_demo.py` also serves a saved result independently.

Only the matched-PDF + new-VR workflow is available. Photo-to-PDF generation,
raw-history matching and prior-result replay have been removed. This application
does not generate or modify the upstream matched PDF. Static schema 4 panoramas are supported here;
360 video, OCR and arbitrary vendor exports are not implemented.

For command-line automation with an explicit finite grant:

```sh
uv run --locked --extra codex pastport-pdf-vr environment-build --pdf INPUT.pdf --tour TOUR.html --grant my-grant.json --workspace .runtime/site --run-id first-run
```

The [repository Skill](.agents/skills/pastport-environment-generation/SKILL.md)
remains an optional interactive authoring/review entry with the same identity,
source and spatial rules. Its low-level preparation/assembly tools remain available:

```sh
uv run --locked pastport-pdf-vr environment-prepare --pdf INPUT.pdf --tour TOUR --workspace .runtime/new-input
uv run --locked pastport-pdf-vr environment-render --pdf INPUT.pdf --tour TOUR --evidence .runtime/new-input/evidence --locations .runtime/new-input/locations.json --output .runtime/new-result --serve
```

Preparation alone is not recognition. Assembly alone consumes checked evidence.
A diagnosed, settled semantic validation failure can be explicitly reconciled with
`environment-build --resume-validation-stage matched_pdf` (or `fresh_localization` /
`structural_review`) using the original inputs, grant, workspace and run ID. This
retains the stage-recovery audit and existing usage and does not retry unknown dispatches.

Runtime material stays under ignored `.runtime/`; no input-specific mapping or
hotspot coordinates are shipped as business rules.

| Source | Purpose |
|---|---|
| `adapters/matched_pdf.py` | Optional input-owned evidence-page and photographic-selection index; full-scan fallback |
| `application/environment_build.py`, `domain/environment.py` | Metered matched-PDF inspection, fresh localization, overlay audits and structural review |
| `application/reference_preview.py` | Owned isolated local servers using only packaged runtime code |
| `application/environment_agent.py` | Safe PDF/tour preparation with existing asset/PDF/projection adapters |
| `application/reference_environment.py` | Strict, hash-bound assembly, structural exclusions, exact source checks and isolated output |
| `reference_environment/` | Data-free demonstrated layouts and persistence runtime templates; notices retained |
| `.agents/skills/pastport-environment-generation/` | Complete Agent workflow, operational handoff reference and local UI metadata |
| `tests/test_environment_agent.py` | Input variation, stale coordinates, source fabrication, relationship and safe rendering checks |

## Requirements and operation

Requires Python 3.12, Poppler (`pdftoppm` and `pdftotext`), and the operator's
existing local Codex login/runtime. Install Poppler separately before generating.
No API-key fallback, credential copying or global configuration changes occur.
`pastport-pdf-vr codex-status` reports local SDK readiness without inference.

The browser accepts one matched PDF (64 MiB by default, 512 MiB with explicit
large-PDF opt-in), plus a supported schema 4 static panorama HTML, complete folder
or ZIP. ZIPs are limited to 150 MiB compressed / 200 MiB expanded; folders are
limited to 200 MiB. Uploaded scripts are never executed. 360 video, arbitrary
vendor exports, IDML/INDD, 3D processing and OCR are not implemented.

Enter a title, optionally select an existing project, authorize the finite grant,
and generate. New browser runs default to 20 model calls / 250,000 recorded tokens.
The threshold is checked before the next call, so one call may exceed it. Actual
usage is retained; unknown dispatches stop for reconciliation and are never reset.

Open the saved VR or review result from its job card. Changes and per-view positions
persist in that result's database. Stop Studio with Ctrl+C to release its owned
processes. Restart with the same workspace to keep the saved results. No service is
started by installation. Legacy jobs belonging to removed workflows stay on disk
but are hidden from this portal; no migration or deletion of their data is performed.

## Source map

| Source | Purpose |
|---|---|
| `api/studio.py`, `application/studio.py`, `domain/studio.py`, `web/studio.*` | Single-workflow upload, job lifecycle and result routes |
| `application/storage.py` | Atomic durable job/generation metadata writes |
| `application/inputs.py`, `pdf_ingestion.py`, `adapters/pdf.py` | Bounded source-PDF ingestion |
| `adapters/assets.py`, `tour.py`, `projection.py`, `application/projection.py` | Immutable assets, safe tour import and panorama coordinates |
| `adapters/codex_sdk.py`, `execution.py`, `structured_output.py`, `ports/execution.py` | SDK transport, finite grants, usage receipts and strict responses |
| `workflow/graph.py`, `domain/build.py`, `domain/models.py` | Durable stages, summaries and shared validated contracts |

The current cleanup was not tested or model-run at the user's request. The user
performs manual runtime and output acceptance. Earlier verification describes the
pre-cleanup version only; see the changelog. Main integration and cloud deployment
are outside this standalone delivery.

## Animated museum node

This branch adds labelled museum → animated VR automation with explicit existing-image
reuse (zero new inference) or bounded Codex subscription generation. Input/output,
LangGraph chaining and recovery are described in [VR_ANIMATION.md](docs/VR_ANIMATION.md).
The matching Studio entrypoint above is unchanged; animation currently has a Python/CLI
entrypoint, not a new Studio upload page. Visual and interaction acceptance is manual.

| Source | Purpose |
|---|---|
| `domain/animation.py`, `application/animation.py` | Hash-bound images, isolated full-tour assembly and packaging |
| `adapters/codex_image.py`, `animation_assets/` | Native subscription image events and pinned style/policy |
| `application/animation_cli.py`, `workflow/animation.py` | CLI and typed LangGraph node |
| `.agents/skills/pastport-style-transfer/` | Reusable execution skill and scope |
## Optional 3D handoff

This branch adds an optional 3D stage after existing panorama matching. The original
PDF/panorama workflow and viewer remain available. Open **追加 Marble 3D** from the
generation records, choose the completed result and its exact viewpoint, then either
import an existing Marble `world.json` or explicitly authorize one panorama generation.
The 3D page loads the actual SPZ and GLB, supports six-direction free movement,
computes ray/surface candidates after camera alignment, and saves only manually
confirmed anchors. This is not collision-constrained walking.

See [SCENE3D.md](docs/SCENE3D.md) for the key setup, CLI, saved-operation recovery,
coordinate convention, manual calibration and actual execution limits. No new paid
generation was performed for this delivery.

## Environment stylization (panorama and 3D)

The `codex/environment-stylization` branch retains panorama animation and adds a
source-bound whole-tour 3D appearance path. See [STYLIZATION3D.md](docs/STYLIZATION3D.md)
for the typed graph/CLI entry, one-package input/output, isolated preview, shared
review snapshot and unresolved geometry/quality limits. This is an appearance
candidate, not completed structural reconstruction or accepted visual quality.

## Environment stylization upload

Run `uv run --locked pastport-stylize-studio --workspace .runtime/stylization-studio --port 8795`
and open `http://127.0.0.1:8795/stylization`. Upload a complete supported native VR or
3D tour ZIP; review the estimate, optionally enter budget limits, and authorize the
run. Blank budgets use the displayed suggestions. No generation starts on upload.
See [formats, limits and validation status](docs/STYLIZATION3D.md#upload-and-automatic-generation).
