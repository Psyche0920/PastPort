# PastPort Matched Environment SDK

Independent distribution: `pastport-matched-environment==0.1.0`; import namespace: `pastport_matched_environment`.
Source revision and notices: [UPSTREAM](UPSTREAM.md), [license](LICENSE).

Inputs: a matched PDF and a new VR tour for environment generation; Outputs: a source-bound museum/review candidate with stable identity and explicit
acceptance limits. Shared review and 3D remain in Matched Environment; appearance execution is
owned by the separate `pastport-stylization` distribution, which depends on Matched Environment.
Matched Environment does not depend on Stylization.
No Story Demo, UI-trial game, live database or private scene is bundled.

The upstream branch sequence matters: `pdf-to-vr-standalone` supplies the 360°
PDF-to-tour workflow; `matched-environment` adds 3D scene support and shared
review; the later `environment-stylization` line includes both and adds the
appearance-processing workflows. This SDK packages the former museum/environment
capabilities; appearance processing is in the separate Stylization SDK. The
standalone branch by itself is not the 3D SDK source.

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
  It owns child preview lifecycles; it is not mounted into Main's authenticated API
  here. Local staff endpoints require separate deployment/security validation.

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
