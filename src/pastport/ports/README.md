# ports — Replaceable boundaries

Protocols and immutable boundary types; implementations belong in adapters/modules. Framework owner: Wehan/Weijia. Evidence/narrative professional implementations remain their respective owners' responsibility; see [current guide](../../../docs/README.md#2-architecture-ownership-and-module-map). Start at [modules.py](modules.py); import from the module's public boundary, not a sibling adapter's internals.

## Files and responsibilities

| File | Purpose |
|---|---|
| [__init__.py](__init__.py) | Package namespace; no independent service lifecycle. |
| [editorial.py](editorial.py) | Storage and content boundaries for application services and the workflow. |
| [execution.py](execution.py) | Shared services supplied to independently constructed content modules. |
| [modules.py](modules.py) | Process-local boundaries. No SDK, database, retry loop or fake success lives here. |
| [package_files.py](package_files.py) | Bounded file input for runtime package loading. |
| [player_preparation.py](player_preparation.py) | A typed process boundary; engine rules remain in the shared JavaScript implementation. |
| [player_saves.py](player_saves.py) | Atomic player persistence, separate from the authoritative editorial review database. |
| [resources.py](resources.py) | A provider-independent resource boundary; implementations enforce their own storage scope. |

## Use and checks

From repository root after installing locked dependencies:

```bash
uv run --no-sync pytest tests/test_module_check.py tests/test_module_integration.py
```

[Current guide](../../../docs/README.md): contracts/composition §§4–5; workflow/recovery §§6–9; runtime/workbench/API §§10–12; logging/checks §§13–15. Preserve typed errors, cancellation, cleanup, exact identities and shared approval/budget authority. Library-only packages have no independent service/factory. Formal module/real-material/paid/human acceptance requires its own evidence. Keep this file inventory current; shared delivery records belong in [Change Log](../../../docs/CHANGELOG.md), not module histories.
