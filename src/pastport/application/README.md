# application — Business use cases and shared services

Coordinates typed domain/port operations, approvals/usage/publication/player lifecycles; no provider-specific SDK policy. Framework owner: wehan. Evidence/narrative professional implementations remain their respective owners' responsibility; see [current guide](../../../docs/PastPort_PRD_EN.md#s2-9-1). Start at [service.py](service.py); import from the module's public boundary, not a sibling adapter's internals.

## Files and responsibilities

| File | Purpose |
|---|---|
| [__init__.py](__init__.py) | Package namespace; no independent service lifecycle. |
| [activity.py](activity.py) | Meter automatic workflow wall time once, excluding human and queue waiting. |
| [change_impact.py](change_impact.py) | Version-bound mechanical comparison; uncertainty never grants human approval. |
| [execution_guard.py](execution_guard.py) | Validate persisted server grants before any shared child operation. |
| [execution_models.py](execution_models.py) | Pinned execution configuration and durable receipts, independent of provider SDKs. |
| [execution_runtime.py](execution_runtime.py) | Composition root for grants, provider configuration and services given to module factories. |
| [model_gateway.py](model_gateway.py) | Account for a bounded model call before validating or returning its typed output. |
| [models.py](models.py) | Application records use clear names and reuse the frozen shared contracts. |
| [module_selection.py](module_selection.py) | Explicit composition choices; injected implementations never silently fall back. |
| [operational_service.py](operational_service.py) | Human interventions preserve spending facts, review history and execution limits. |
| [operations.py](operations.py) | Authenticated intervention commands and immutable audit records. |
| [package_loader.py](package_loader.py) | Load a runtime package against trusted identity and explicit consumer capabilities. |
| [player_components.py](player_components.py) | Bind shared JS preparation components to a trusted runtime package and release. |
| [player_preparation.py](player_preparation.py) | Typed preparation protocol, separate from committed player actions and saves. |
| [player_runtime.py](player_runtime.py) | Trusted shared-JS runtime contracts and the implementation of PlayerRuntimePort. |
| [player_service.py](player_service.py) | Saved player sessions; JS owns gameplay and the repository owns atomic durability. |
| [preview_service.py](preview_service.py) | Preview-only assembly and sessions; no review or release mutations occur here. |
| [previews.py](previews.py) | Typed private preview boundaries, independent of approval and publication. |
| [publication.py](publication.py) | Stage durable immutable files, then atomically publish their recorded identity. |
| [reliability.py](reliability.py) | Typed authority, accounting and release records shared by local service boundaries. |
| [research_execution.py](research_execution.py) | One bounded research role: durable steps, no tool-invented permissions or new questions. |
| [resources.py](resources.py) | Enforce identity, size and raw-byte hashes for all injected resource readers. |
| [routing.py](routing.py) | Application-owned legal routes and cumulative research/revision limits. |
| [service.py](service.py) | Application operations enforce identity, review authority and optimistic versions. |
| [source_tools.py](source_tools.py) | Registered-source reading and deterministic local tools, bounded by frozen questions. |
| [source_views.py](source_views.py) | Read registered source bytes and saved extraction records without research/model calls. |
| [story_editing.py](story_editing.py) | Stable game field locks and declared targets, shared by manual and module revisions. |
| [updates.py](updates.py) | Revalidate immutable records rather than bypassing their boundary validators. |
| [workflow_control.py](workflow_control.py) | Durable control manifests; module suggestions cannot grant approval or reset limits. |

## Use and checks

From repository root after installing locked dependencies:

```bash
uv run --no-sync pytest tests/test_operations.py tests/test_shared_execution.py tests/test_reliability.py
```

[Current guide](../../../docs/IMPLEMENTATION_GUIDE.md): contracts/composition §§4–5; workflow/recovery §§6–9; runtime/workbench/API §§10–12; logging/checks §§13–14; development rules in PRD 2.11. Preserve typed errors, cancellation, cleanup, exact identities and shared approval/budget authority. Library-only packages have no independent service/factory. Formal module/real-material/paid/human acceptance requires its own evidence. Keep this file inventory current; shared delivery records belong in [Change Log](../../../docs/CHANGELOG.md), not module histories.
