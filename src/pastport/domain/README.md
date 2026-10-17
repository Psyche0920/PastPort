# domain — Immutable shared contracts and content identities

Framework/SDK-independent models and validation. No database, server or paid calls. Framework owner: Wehan/Weijia. Evidence/narrative professional implementations remain their respective owners' responsibility; see [current guide](../../../docs/README.md#2-architecture-ownership-and-module-map). Start at [modules.py](modules.py); import from the module's public boundary, not a sibling adapter's internals.

## Files and responsibilities

| File | Purpose |
|---|---|
| [__init__.py](__init__.py) | Package namespace; no independent service lifecycle. |
| [capabilities.py](capabilities.py) | Explicit capabilities for the existing contract profile, independent of sample content. |
| [common.py](common.py) | Immutable wire contracts and content identity; no framework or provider imports. |
| [evidence.py](evidence.py) | Evidence candidates and snapshots; validation never grants human approval. |
| [game.py](game.py) | Bounded, declarative game data. This module does not interpret actions. |
| [modules.py](modules.py) | Typed module messages for independent implementation against contract 0.1.0. |
| [package_loading.py](package_loading.py) | Safe, stable failures for package consumers, independent of HTTP or storage. |
| [packages.py](packages.py) | Cross-package contract checking, distinct from authorisation and runtime execution. |
| [player_saves.py](player_saves.py) | Player save ownership and immutable persistence identities. |
| [resources.py](resources.py) | Resource identities and local registrations, independent of provider or filesystem APIs. |
| [workflow.py](workflow.py) | Workflow messages express intent and observations, never authentication proof. |

## Use and checks

From repository root after installing locked dependencies:

```bash
uv run --no-sync pytest tests/test_contracts.py
```

[Current guide](../../../docs/README.md): contracts/composition §§4–5; workflow/recovery §§6–9; runtime/workbench/API §§10–12; logging/checks §§13–15. Preserve typed errors, cancellation, cleanup, exact identities and shared approval/budget authority. Library-only packages have no independent service/factory. Formal module/real-material/paid/human acceptance requires its own evidence. Keep this file inventory current; shared delivery records belong in [Change Log](../../../docs/CHANGELOG.md), not module histories.
