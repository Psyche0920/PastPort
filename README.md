# PastPort

Turn traceable heritage research into interactive games with characters, decisions, choices, and consequences. Python provides the workflow and shared services; native JavaScript implements game rules and browser playtests.

**The current first release includes the shared workflow, review/budget/recovery controls, the game foundation, and a browser workbench.** Weng and Mert can connect their modules and test each side independently against the other fixed reference module. Formal joint integration, real source material and permissions, paid models, human playtests, remote CI, and production each still require their own acceptance.

## Team documentation

| Document | Source of truth for |
| --- | --- |
| [PRD / current architecture and codebase guide](docs/README.md) | Product goals, overall architecture, current capabilities, interfaces, and operating rules |
| [Active Plan](docs/ACTIVE_PLAN.md) | Current scope and limits, tasks, owners, dependencies, acceptance, and blockers |
| [Decision Log](docs/DECISION_LOG.md) | Key decisions, rationale, tradeoffs, and supersession |
| [Change Log](docs/CHANGELOG.md) | Verified major deliveries, status, and evidence |

Coding Agents follow [AGENTS.md](AGENTS.md), start with the current task and affected modules, and read only relevant guidance. Do not reread all four documents for every task. Mark work complete only after acceptance; confirm contracts and the fixed reference module before cross-module delivery. Maintain shared rules in section 15 of the current codebase guide instead of duplicating them.

## Modules and file responsibilities

Each module README lists the purpose of its direct source files. The main guide owns cross-module rules to avoid duplication.

| Module | Responsibility | Key files | Inventory |
| --- | --- | --- | --- |
| Package entry | Startup, type exports, shared diagnostics | `__main__.py` startup; `contracts.py` exports; `observability.py` JSON logging | [Package README](src/pastport/README.md) |
| domain | Framework-independent immutable contracts, validation, and identity | `modules.py` module messages; `evidence.py` evidence; `game.py` gameplay; `workflow.py` state/budgets | [domain](src/pastport/domain/README.md) |
| ports | Replaceable module, storage, model, and runtime boundaries | `modules.py` business Protocols; `execution.py` shared services; `resources.py` resource reads | [ports](src/pastport/ports/README.md) |
| application | Use cases, approvals/budgets, models/tools, assembly/publication, preview/saves | `service.py` editing use cases; `execution_runtime.py` service assembly; `publication.py` publication; `player_service.py` saves | [application](src/pastport/application/README.md) |
| adapters | I/O implementations for SQLite, files, providers, and Node processes | `database.py` business persistence; `content.py` local modules; `model_provider.py` providers; `player_process.py` JS bridge | [adapters](src/pastport/adapters/README.md) |
| workflow | Single-worker execution, persisted graph, and legal stage scheduling | `worker.py` execution/recovery; `stages.py` nodes; `branching.py` rework/evidence requests | [workflow](src/pastport/workflow/README.md) |
| player | Deterministic gameplay interpreter shared by browsers and Node | `runtime.mjs` atomic actions; `rules.mjs` conditions/effects; `runner.mjs` Python protocol entry | [player](src/pastport/player/README.md) |
| api | Authenticated HTTP, private resources, and browser workbench | `app.py` composition/routes; `private_views.py` previews/source text; `workbench.mjs` workbench; `request_logging.py` request correlation | [api](src/pastport/api/README.md) |
| development | Offline module, fault, browser acceptance, and contract-generation tools | `module_check.py` single module; `module_acceptance.py` four combinations; `fault_acceptance.py` faults; `browser_check.py` browser | [development](src/pastport/development/README.md) |

`tests/` contains behavior, contract, fault, and browser tests; `schemas/` contains generated contracts; `skills/` contains specialist methods; `tools/` contains repository checks; `references/` contains source references. Keep required provenance and runtime audit records. Record key decisions and major deliveries from the current baseline; do not backfill older history or add archives or one file per change.

## Quick checks

```bash
uv sync --locked --group dev
uv run --no-sync python tools/check_repository.py
uv run --no-sync python tools/check_handoff.py
uv run --no-sync python -m pastport.development.module_acceptance --output acceptance-artifacts/framework.json
```

See sections 3 and 14 of the main guide for complete startup and test commands. Runtime logs use safe JSON on stderr; remote log collection, retention/rotation, and production deployment are not enabled. Do not commit, push, merge, make paid calls, or deploy without authorization.
