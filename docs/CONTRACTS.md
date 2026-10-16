# Contract baseline 0.1.0 — T1a

This is the first executable contract baseline for independent module development. It provides immutable Pydantic models, process-local Protocols, deterministic JSON Schemas, complete wire samples and semantic consistency checks. Team acceptance of the shared interface remains a human review; a passing contract does not certify history, permissions, story quality or a working workflow.

## Entry points and ownership

| Owner | Start here | Independent inputs and outputs |
|---|---|---|
| Weng | `EvidencePort` in [module ports](../src/pastport/ports/modules.py) | inventory/index/research request and result fixtures |
| Matt | `NarrativePort` in the same file | discover/draft/revise/review request and result fixtures |
| Matt, integrated by Weijia | `PlayerRuntimePort` | runtime package, player state, typed actions and future-runtime vectors |
| Weijia | `AssemblyPort`, `PackageValidatorPort`, execution context | assembly/validation requests, assembly result and bundle consistency checks |

Shared data lives in [domain models](../src/pastport/domain/), the public export list in [contracts.py](../src/pastport/contracts.py), and committed [schemas](../schemas/). Do not duplicate these types inside individual modules. `ModelGateway`, `SourceReader`, cancellation and tool execution are injected ports. No provider SDK, database, FastAPI, LangGraph or player interpreter is implemented in T1a.

## Reproducible checks

Python is pinned by [.python-version](../.python-version); dependencies and hashes are in [uv.lock](../uv.lock). Use uv 0.12.8, then run from the repository root:

```bash
uv sync --locked --group dev
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy --strict src/pastport tools/check_contracts.py tests
uv run --no-sync python tools/check_contracts.py
uv run --no-sync pytest
uv run --no-sync python tools/check_repository.py
```

Regenerate schemas after an intentional model change with `uv run --no-sync python tools/check_contracts.py --write`. Review the generated diff. Default check mode never rewrites schemas or fixtures. Schema checks and unit tests use local files, isolated synthetic data and no provider credentials. They do not create an editorial DB or a release.

## What the baseline freezes

- Contract version is `0.1.0`; content versions remain independent. Unknown fields and unsupported discriminators fail. Python boundaries accept strict models and tuples; JSON boundaries use `model_validate_json`. Do not bypass validation with `model_construct` or unvalidated `model_copy(update=...)`.
- All nested wire collections are immutable tuples. Logical maps are represented as typed entry arrays, including locales, player observations, decisions, variables and action receipts. Models reject duplicate identities where declared. Consumers must use the same schema version.
- `NarrativePackage.game` holds protagonist, characters, scenes, props, decisions, variables, rules, endings, initial state and locales. `RuntimePackage.game` must equal it. This makes the shared game shape explicit instead of copying fields between authoring and runtime contracts.
- The `t1a-single-task` profile supports one inspect or caseboard task per scene. Document, inspect-sort, multi-task dependencies and their action/event discriminators are deliberately rejected until T1b. The profile specifies both languages and fixed limits: two events, 64 effects per action, condition depth eight. This is a data capability contract, not proof that a player implementation supports it.
- Source file references hash raw bytes; validated payload references hash sorted compact UTF-8 JSON, including versions and dependencies. Separate approval records and external storage/acquisition metadata do not enter payload identity; every field actually present in a payload, including source URI/status, is hashed. Files and referenced source versions are checked separately where applicable.
- `PackageBundle` validates project/hash/dependency/review bindings, task evidence, mapped and permitted media, route references and unchanged game content. It does not load media bytes, prove every path solvable, authenticate an actor or query live rights/revocations.
- `ReviewSnapshot` and `ApprovedEvidenceView` check supplied snapshot consistency. They are not bearer tokens or authentication proof. T2/T3 services must reconstruct them from the authoritative authenticated review DB and current policy, never trust a client/model's self-declared approval. Synthetic approvals and synthetic sources cannot be promoted to a public/production bundle.
- Safe game integers fit JavaScript's exact integer range. Chinese and English share rule IDs, answer conditions and effects, with matching locale key sets.

## Fixture provenance and validation levels

The [reference fixture guide](../tests/fixtures/reference/README.md) identifies the fixed demo reference, regenerated identities and synthetic text/SVG. No demo application, original media, database or history approval was copied. The package is internal/test only.

The fixture manifest declares complete valid and invalid wire samples. JSON Schema validates wire shape. Pydantic and `BundleValidator` add cross-field and cross-package checks that JSON Schema cannot express. Run both; passing a generic JSON Schema validator alone is insufficient.

Future-runtime vectors cover observation completion, identical action replay, stale revision, locked scene and conflicting effects. Event IDs are `action_id:zero_based_ordinal`; the first task completion emits its task feedback key once. Each vector is `not_run`: T1a validates its shape and package identity, while T6 must run it against the shared JS interpreter. The help/hurry mapping separately specifies the expected time, witness state and later feedback. No Python gameplay interpreter is added to simulate a T6 pass.

## Interface behavior and compatibility

I/O ports are async and receive immutable `ExecutionContext` metadata plus a cancellation interface. Deterministic assembly/validation ports are synchronous. Modules return candidates through `ModuleResult[T]`; the application owns IDs, stored versions, workflow transitions, retries, budget and approvals. Provider responses/usage must be persisted by shared execution adapters before a later node failure can discard them.

`completed` requires a typed payload; research and change outcomes require concrete requests or IDs. Cancellation must propagate. A consumer checks output identity against its execution context before persistence. Tool access, public distribution, current approval status and actual budget enforcement remain T2/T3 work.

Strict extra-field rejection means even an added optional field is not automatically compatible with an old consumer. Internal algorithm or prompt improvements may retain these interfaces; wire changes require consumer tests, a declared contract/profile version and an explicit upgrade/adapter plan. Existing published payloads and approvals are never edited in place.

## Remaining implementation

T2: repositories, migrations, authenticated authoritative reviews. T3: actual graph, execution/usage ledger, tool/role enforcement and recovery. T4: operating pages and commands. T5: real provider/source integration and professional evaluation. T6: deterministic assembly service, media-byte verification, JS interpreter and actual vector execution. T7: a second real project and player validation.

T1a completion establishes contracts for that work; it does not establish a connected production framework. Any new mode must be made explicit with full positive/negative samples before its adapter is enabled.

## Local verification record — 2026-10-16

Contract baseline 0.1.0: 39 deterministic Schema exports; 42 declared complete wire samples (34 valid, 8 intentionally invalid); 128 offline tests passed. Ruff check/format and strict mypy passed for all new Python source, tests and the contract checker. These are local results on the pinned Python environment. GitHub Actions has not run for this change, and future-runtime vectors remain not_run.
