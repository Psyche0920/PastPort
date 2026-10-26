# PastPort Stylization SDK

Independent distribution `pastport-stylization==0.1.0`, namespace
`pastport_stylization`. Depends one-way on `pastport-matched-environment==0.1.0` for reviewed
museum formats, metered execution, scene geometry and shared-content authority.
Matched Environment and Evidence never import this package. Main enables it through the
optional `authoring` extra; `authoring-codex` explicitly adds the provider.
Installation alone does not execute any workflow.

Install the Matched Environment wheel first, then this wheel, or install both through the
workspace. Add `[codex]` only to use the existing subscription adapter. Poppler
and ffmpeg remain explicit external tools for the workflows that need them.
No credentials, live databases or tour data are distributed.

## Typed API and commands

`pastport_stylization.sdk` exports `EnvironmentStylizationAgent`,
`AutomaticStyleRun`, `AutomaticStyleDelivery`, `StyleInput`, `AnimationRun`,
`AnimationDelivery`, `Style3DRun`, `Style3DDelivery`, and injected transport ports.
The source-bound appearance manifest `Style3DVariant` is owned by Matched Environment so that
review and export work without installing generation code. Image capability/result
wire models also stay with Matched Environment's shared metered execution boundary.

- `pastport-stylization-agent --help`: bounded planning, generation and review.
- `pastport-animate --help`: full-sphere panorama workflow.
- `pastport-style3d --help`: appearance processing with geometry unchanged.
- `pastport-stylize-studio --help`: separate local staff portal.

Existing grants, source hashes, isolated workspaces, cancellation/receipt and
bounded repair rules remain in force. A candidate is pending human acceptance;
no installation or offline test demonstrates visual quality or production safety.
Matched Environment's studio no longer mounts the stylization portal implicitly; launch its
separate command explicitly. Each standalone portal shows only its own navigation; Main frontend integration
requires an explicit composition adapter.

## Source responsibilities

| Source | Responsibility |
|---|---|
| `sdk.py` | Typed public facade |
| `application/`, `workflow/` | Panorama/3D orchestration, progress and bounded repair |
| `domain/` | Stylization commands, plans, reviews and deliveries |
| `adapters/` | Image transport and SPZ appearance processing |
| `api/`, `web/` | Separate local staff portal and preview |
| `animation_assets/` | Existing upstream style policy/reference resources |
| `UPSTREAM.md`, `LICENSE` | Source revision and retained notices |

This is a source split from the revision in UPSTREAM, not a claim that the upstream
branch itself already has three distributions. Prior private deep imports under
`pastport_matched_environment.application.stylization*` move to this namespace; shared readers
use `pastport_matched_environment.application.appearance`.
