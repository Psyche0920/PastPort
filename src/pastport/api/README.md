# api — Authenticated HTTP and browser workbench

Transport/composition; depends on application/ports, never implements game rules. Framework owner: Wehan/Weijia. Evidence/narrative professional implementations remain their respective owners' responsibility; see [current guide](../../../docs/README.md#2-architecture-ownership-and-module-map). Start at [app.py](app.py); import from the module's public boundary, not a sibling adapter's internals.

## Files and responsibilities

| File | Purpose |
|---|---|
| [__init__.py](__init__.py) | Package namespace; no independent service lifecycle. |
| [api-client.mjs](api-client.mjs) | In-memory authentication, bounded requests, immutable operations and explicit retries. |
| [app.py](app.py) | Local authenticated editorial API with strict JSON transport and a durable background worker. |
| [player-view.mjs](player-view.mjs) | Renders confirmed player state and sends authoritative server actions. |
| [private_views.py](private_views.py) | Private content routes; all bytes resolve through server-selected package/source identities. |
| [request_logging.py](request_logging.py) | Request correlation without retaining URLs, bodies, headers or client identities. |
| [settings.py](settings.py) | Server-side accounts and explicit test configuration. |
| [transport.py](transport.py) | Bounded strict JSON request parsing shared by authenticated routes. |
| [views.mjs](views.mjs) | Safe text-based DOM helpers and localized artifact display. |
| [workbench.css](workbench.css) | Responsive workbench and player layout, focus and hotspot styling. |
| [workbench.html](workbench.html) | Authenticated six-section authoring/review/play shell. |
| [workbench.mjs](workbench.mjs) | Coordinates project/run context, source/story/review/activity and preview interactions. |

## Use and checks

From repository root after installing locked dependencies:

```bash
uv run --no-sync pytest tests/test_service.py tests/test_previews.py tests/test_observability.py
```

[Current guide](../../../docs/README.md): contracts/composition §§4–5; workflow/recovery §§6–9; runtime/workbench/API §§10–12; logging/checks §§13–15. Preserve typed errors, cancellation, cleanup, exact identities and shared approval/budget authority. Library-only packages have no independent service/factory. Formal module/real-material/paid/human acceptance requires its own evidence. Keep this file inventory current; shared delivery records belong in [Change Log](../../../docs/CHANGELOG.md), not module histories.
