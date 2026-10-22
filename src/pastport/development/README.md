# development — Offline acceptance and generated-contract tools

Trusted local tooling with temporary synthetic data; does not certify professional content or deployment. Framework owner: wehan. Evidence/narrative professional implementations remain their respective owners' responsibility; see [current guide](../../../docs/PastPort_PRD_EN.md#s2-9-1). Start at [module_acceptance.py](module_acceptance.py); import from the module's public boundary, not a sibling adapter's internals.

## Files and responsibilities

| File | Purpose |
|---|---|
| [__init__.py](__init__.py) | Package namespace; no independent service lifecycle. |
| [acceptance_models.py](acceptance_models.py) | Versioned development reports, separate from shared content and runtime contracts. |
| [acceptance_scenario.py](acceptance_scenario.py) | Authenticated test-only workflow scenario for interchangeable offline ports. |
| [browser_check.py](browser_check.py) | Run real-browser acceptance against a fresh synthetic localhost service. |
| [browser_fixture.py](browser_fixture.py) | Dedicated synthetic localhost server for browser acceptance, never production data. |
| [fault_acceptance.py](fault_acceptance.py) | Run fixed F9 fault gates and retain a safe, version-bound local test report. |
| [module_acceptance.py](module_acceptance.py) | Run the offline F9 acceptance kit with replaceable trusted local factories. |
| [module_check.py](module_check.py) | Run independent module smoke checks without an API, database or workflow worker. |
| [player_check.py](player_check.py) | Run F7 shared-JS conformance and report actual full action-vector results. |
| [player_contracts.py](player_contracts.py) | Export TypeScript declarations and the JSON schemas used by player components. |
| [reference_modules.py](reference_modules.py) | Independent, request-bound synthetic ports for the offline acceptance kit. |

## Use and checks

From repository root after installing locked dependencies:

```bash
uv run --no-sync pytest tests/test_module_check.py tests/test_module_acceptance.py tests/test_fault_acceptance.py
```

[Current guide](../../../docs/IMPLEMENTATION_GUIDE.md): contracts/composition §§4–5; workflow/recovery §§6–9; runtime/workbench/API §§10–12; logging/checks §§13–14; development rules in PRD 2.11. Preserve typed errors, cancellation, cleanup, exact identities and shared approval/budget authority. Library-only packages have no independent service/factory. Formal module/real-material/paid/human acceptance requires its own evidence. Keep this file inventory current; shared delivery records belong in [Change Log](../../../docs/CHANGELOG.md), not module histories.
