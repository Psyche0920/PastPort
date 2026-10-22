# adapters — SQLite, files, providers and subprocess implementations

Implements ports for real I/O; must not create a second workflow or approval policy. Framework owner: wehan. Evidence/narrative professional implementations remain their respective owners' responsibility; see [current guide](../../../docs/PastPort_PRD_EN.md#s2-9-1). Start at [database.py](database.py); import from the module's public boundary, not a sibling adapter's internals.

## Files and responsibilities

| File | Purpose |
|---|---|
| [__init__.py](__init__.py) | Package namespace; no independent service lifecycle. |
| [assembly.py](assembly.py) | Build media manifests from reviewed asset identities; never from a prebuilt runtime template. |
| [content.py](content.py) | Offline adapters for explicitly supplied authored content; no model generation is implied. |
| [database.py](database.py) | Short SQLite transactions with optimistic revisions and durable command consumption. |
| [model_provider.py](model_provider.py) | Bounded Responses HTTP adapter and explicit deterministic test provider. |
| [package_files.py](package_files.py) | Read regular local package files without following a file symlink or blocking on a pipe. |
| [player_process.py](player_process.py) | Bounded Node transport for the shared browser/headless preparation components. |
| [player_saves.py](player_saves.py) | Durable, version-checked SQLite saves with one transaction for state and receipts. |
| [previews.py](previews.py) | Private SQLite preview metadata and atomic player state, outside release storage. |
| [resources.py](resources.py) | Explicit local asset catalog and source URI adapter, bounded to one configured directory. |
| [skills.py](skills.py) | Read only server-approved Skill paths and fingerprint every included file. |

## Use and checks

From repository root after installing locked dependencies:

```bash
uv run --no-sync pytest tests/test_resources.py tests/test_model_provider.py tests/test_reliability.py
```

[Current guide](../../../docs/IMPLEMENTATION_GUIDE.md): contracts/composition §§4–5; workflow/recovery §§6–9; runtime/workbench/API §§10–12; logging/checks §§13–14; development rules in PRD 2.11. Preserve typed errors, cancellation, cleanup, exact identities and shared approval/budget authority. Library-only packages have no independent service/factory. Formal module/real-material/paid/human acceptance requires its own evidence. Keep this file inventory current; shared delivery records belong in [Change Log](../../../docs/CHANGELOG.md), not module histories.
