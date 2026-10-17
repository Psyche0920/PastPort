# player — Shared JavaScript gameplay interpreter

Single deterministic rules engine used from Node and the browser; no LLM gameplay or Python reimplementation. Framework owner: Wehan/Weijia. Evidence/narrative professional implementations remain their respective owners' responsibility; see [current guide](../../../docs/README.md#2-architecture-ownership-and-module-map). Start at [runtime.mjs](runtime.mjs); import from the module's public boundary, not a sibling adapter's internals.

## Files and responsibilities

| File | Purpose |
|---|---|
| [__init__.py](__init__.py) | Package namespace; no independent service lifecycle. |
| [actions.mjs](actions.mjs) | Validates and applies supported player action handlers. |
| [context.mjs](context.mjs) | Shared immutable runtime lookup/context helpers. |
| [contracts.d.ts](contracts.d.ts) | Generated TypeScript declarations for shared Python wire contracts. |
| [errors.mjs](errors.mjs) | Typed player error codes and failures. |
| [generated-schemas.mjs](generated-schemas.mjs) | Generated bounded JSON schemas; regenerate from Python, do not hand-edit. |
| [preparation.d.mts](preparation.d.mts) | Type declarations for preparation components. |
| [preparation.mjs](preparation.mjs) | Builds and validates the initial shared runtime context/state. |
| [rules.mjs](rules.mjs) | Shared condition evaluation and ordered rule/effect semantics. |
| [runner.mjs](runner.mjs) | Bounded JSON stdin/stdout Node entry point used by the Python bridge. |
| [runtime.d.mts](runtime.d.mts) | Type declarations for the runtime API. |
| [runtime.mjs](runtime.mjs) | Coordinates deterministic action transactions, receipts, events and endings. |
| [validation.mjs](validation.mjs) | Validates typed game references, preparation and runtime prerequisites. |
| [vectors.mjs](vectors.mjs) | Executes frozen conformance vectors against the shared runtime. |

## Use and checks

From repository root after installing locked dependencies:

```bash
uv run --no-sync pytest tests/test_player_components.py tests/test_player_runtime.py
```

[Current guide](../../../docs/README.md): contracts/composition §§4–5; workflow/recovery §§6–9; runtime/workbench/API §§10–12; logging/checks §§13–15. Preserve typed errors, cancellation, cleanup, exact identities and shared approval/budget authority. Library-only packages have no independent service/factory. Formal module/real-material/paid/human acceptance requires its own evidence. Keep this file inventory current; shared delivery records belong in [Change Log](../../../docs/CHANGELOG.md), not module histories.
