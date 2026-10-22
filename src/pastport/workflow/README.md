# workflow — Durable scheduling and stage execution

Single executor/graph; orchestrates application services, preserves authoritative business state. Framework owner: wehan. Evidence/narrative professional implementations remain their respective owners' responsibility; see [current guide](../../../docs/PastPort_PRD_EN.md#s2-9-1). Start at [worker.py](worker.py); import from the module's public boundary, not a sibling adapter's internals.

## Files and responsibilities

| File | Purpose |
|---|---|
| [__init__.py](__init__.py) | Package namespace; no independent service lifecycle. |
| [branching.py](branching.py) | Bounded research, revision and professional review within the existing graph nodes. |
| [stages.py](stages.py) | Persist each stage result before graph checkpointing; human gates query business records. |
| [worker.py](worker.py) | One durable local graph executor. Business records remain the authority at human gates. |

## Use and checks

From repository root after installing locked dependencies:

```bash
uv run --no-sync pytest tests/test_service.py tests/test_workflow_branches.py tests/test_f9_faults.py
```

[Current guide](../../../docs/IMPLEMENTATION_GUIDE.md): contracts/composition §§4–5; workflow/recovery §§6–9; runtime/workbench/API §§10–12; logging/checks §§13–14; development rules in PRD 2.11. Preserve typed errors, cancellation, cleanup, exact identities and shared approval/budget authority. Library-only packages have no independent service/factory. Formal module/real-material/paid/human acceptance requires its own evidence. Keep this file inventory current; shared delivery records belong in [Change Log](../../../docs/CHANGELOG.md), not module histories.
