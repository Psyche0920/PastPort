# PastPort — PRD and Current Codebase Guide

This is the authoritative product/architecture and current codebase guide (the team's PRD). It separates product intent, implemented capabilities and unverified acceptance. Exact field definitions/signatures live in code and generated schemas; each module README lists its files. Current work belongs in [Active Plan](ACTIVE_PLAN.md), important choices in [Decision Log](DECISION_LOG.md), and verified deliveries in [Change Log](CHANGELOG.md). Read the relevant section only; collaboration rules are in §15.

## Contents

1. [Scope, current capabilities and limits](#1-scope-current-capabilities-and-limits)
2. [Architecture, ownership and module map](#2-architecture-ownership-and-module-map)
3. [Install, accounts, startup and configuration](#3-install-accounts-startup-and-configuration)
4. [Shared contracts, evidence and resources](#4-shared-contracts-evidence-and-resources)
5. [Independent modules and composition](#5-independent-modules-and-composition)
6. [Workflow, reviews, edits and bounded routing](#6-workflow-reviews-edits-and-bounded-routing)
7. [Skill protocol and content-quality boundary](#7-skill-protocol-and-content-quality-boundary)
8. [Shared model and tool execution](#8-shared-model-and-tool-execution)
9. [Budget, operator commands and recovery](#9-budget-operator-commands-and-recovery)
10. [Game runtime, actions and saves](#10-game-runtime-actions-and-saves)
11. [Workbench, previews and original sources](#11-workbench-previews-and-original-sources)
12. [HTTP interface and errors](#12-http-interface-and-errors)
13. [Logging and operational diagnostics](#13-logging-and-operational-diagnostics)
14. [Checks, CI and acceptance](#14-checks-ci-and-acceptance)
15. [Coding Agent and documentation rules](#15-coding-agent-and-documentation-rules)

## 1. Scope, current capabilities and limits

PastPort turns traceable heritage material into structured interactive stories: evidence supports an inference, a character choice has a cost, and a later state/consequence makes that choice visible. A project corresponds to an explicitly registered source-folder scope; source-folder organization, actual places and the player's route are separate identities. Preserve all in-scope places and reasons for inclusion/exclusion rather than silently discarding material. Official origin does not prove historical truth, image rights or readiness for a chapter.

Product acceptance target: produce a short playable heritage story where a source-supported observation is necessary for an inference, a character choice changes a later state, and a second independent project runs on the same workflow/player without site-specific engine branches. Historical truth/rights and player understanding require professional review and human playtesting; this is a target, not a claim of completed acceptance. Current pending verification is tracked in [Active Plan](ACTIVE_PLAN.md).

The current code is a modular Python backend with a shared JavaScript player engine. It implements local authenticated authoring, persistent workflow, independent evidence/narrative injection, source/media registration, bounded research/revision/review, metered model/tool services, human approval gates, budget/operator recovery, deterministic assembly, private test releases, playable drafts and isolated durable saves. Browser/player actions do not call a model.

| Identity | Current value |
|---|---|
| Python package/API implementation | 0.2.0 |
| Shared wire contract | 0.1.0 |
| Gameplay capability profile | t1a-single-task |
| Policy / graph | local-4 / editorial-4 |
| Editorial database / player store / preview store | 4 / 1 / 1 |
| Runtime languages | Python 3.12; native JS ES modules on Node/browser |

Formal Weng/Mert adapters and their joint professional output are not certified by reference tests. Real-material truth/rights, live paid-provider behavior/billing, human play quality, remote CI and production deployment require separate evidence. Default model/tool access is disabled. Public publication is unavailable; production publication returns `PUBLICATION_NOT_READY`. The current local adapters import authored JSON; they do not automatically extract/OCR a PDF or generate a story. Paid search, remote folder connectors, a cloud account system, multi-instance deployment and advanced gameplay are not implemented here.

## 2. Architecture, ownership and module map

```text
HTTP/workbench → application use cases → typed domain/ports
                         ↑                 ↑
              workflow scheduling     I/O adapters
                         ↓
             metered services / assembly / publication
                         ↓
             private runtime package → shared JS player
```

| Module | Responsibility / important entry files | All source-file purposes |
|---|---|---|
| Package root | `__main__.py` CLI; `contracts.py` exports; `observability.py` diagnostics | [package](../src/pastport/README.md) |
| domain | Immutable models, package/evidence/game/workflow identities and validation | [domain](../src/pastport/domain/README.md) |
| ports | Evidence/narrative, model/tool, resource, repository and player protocols | [ports](../src/pastport/ports/README.md) |
| application | `service.py`, execution services, budgets/reviews, preview, package loading, publication and saves | [application](../src/pastport/application/README.md) |
| adapters | `database.py`, local content/resources, provider HTTP and Node subprocess implementations | [adapters](../src/pastport/adapters/README.md) |
| workflow | `worker.py` durable single executor; `stages.py` nodes; `branching.py` bounded control routes | [workflow](../src/pastport/workflow/README.md) |
| player | `runtime.mjs`, `rules.mjs`, action handlers, validation and Node wire entry | [player](../src/pastport/player/README.md) |
| api | `app.py` composition/routes, authenticated private views, request logging, HTML/CSS/JS workbench | [api](../src/pastport/api/README.md) |
| development | Module, fault, player, generated-contract and real-browser acceptance tools | [development](../src/pastport/development/README.md) |

Domain/ports do not import FastAPI, SQLite or provider SDKs. Adapters implement boundaries; workflow schedules application use cases. JavaScript owns game semantics; Python delegates rather than implementing a second engine. No site-ID branches belong in the engine.

| Owner | Owns | Can test against | Framework retains authority for |
|---|---|---|---|
| Weng | Evidence/database internals, indexing/research and professional source/rights judgment | Fixed narrative reference | Approval, workflow, usage, release state |
| Matt / Mert | Narrative discovery/drafting/revision/review and player-facing content | Fixed evidence reference | Same shared state and runtime semantics |
| Wehan / Weijia | Contracts, composition, workflow, shared services/runtime/workbench and integration | Both reference ports | Durable authorization/accounting/publication |

Neither module owner needs the other's finished module to develop or test. Ordinary adapter replacement uses composition configuration; changed contract semantics or new gameplay need coordinated version/capability changes. A person's role is not an authenticated account grant.

`tests/` contains behavioral, contract, failure and browser checks; `schemas/` contains generated wire schemas; `skills/` contains professional instructions/calibration; `tools/` contains checks; `references/` contains source materials. Reference materials and fixture provenance are useful inputs, not approved content or implementation instructions.

## 3. Install, accounts, startup and configuration

### 3.1 Dependencies and local test account

Use the Python version in [.python-version](../.python-version), [uv.lock](../uv.lock), and Node version in [CI](../.github/workflows/ci.yml). Current pinned tooling uses Python 3.12.12, uv 0.12.8 and Node 26.10.0. The backend stack is FastAPI, SQLite, LangGraph and Pydantic; npm dependencies are development-only Playwright/Prettier. Runtime JS is native ES modules.

From repository root:

```bash
uv sync --locked --group dev
uv run --no-sync python - <<'PY'
import hashlib
import json
import os
import secrets
from pathlib import Path

folder = Path("var/local-test")
folder.mkdir(parents=True, exist_ok=True)
token = secrets.token_urlsafe(40)
accounts = {"accounts": [{
    "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
    "actor": {
        "actor_id": "local-editor",
        "roles": ["editor", "evidence", "narrative", "publisher"],
        "project_ids": None,
    },
}]}
for name, content in (("accounts.json", json.dumps(accounts)), ("client.token", token)):
    descriptor = os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(content)
PY
uv run --no-sync python -m pastport \
  --accounts var/local-test/accounts.json \
  --data-directory var/local-test/data \
  --test-fixture-directory tests/fixtures/reference \
  --log-level INFO
```

Open `http://127.0.0.1:8000/` and paste the private client.token value into the workbench. Setup refuses to overwrite existing account files. Tokens stay in browser memory and disappear on reload; only digests are stored in account configuration. Use separate actors and explicit project_ids for team access. `null` means all projects and belongs only to a trusted local administrator. Operator powers require adding `operator` explicitly; editor/publisher do not inherit them. Never commit account/token files.

### 3.2 Configuration and embedding

| CLI option | Meaning |
|---|---|
| `--accounts PATH` | Required private server-owned account/digest JSON |
| `--data-directory PATH` | Own service state; default var/editorial; never an authoritative legacy/demo DB |
| `--test-fixture-directory PATH` | Explicit synthetic test mode; separate data directory |
| `--content-directory PATH` | Authored local output import, mutually exclusive with fixture mode |
| `--resource-directory PATH` | Registered resources.json and controlled bytes |
| `--evidence-mode`, `--narrative-mode`, `--resources-mode` | CLI local or disabled selection; injected implementations use Python composition |
| `--execution-config PATH` | Pinned model/tool/price configuration; no secrets in the file |
| `--skill-directory PATH` | Approved Skill files, hashed into execution bindings |
| `--port`, `--log-level` | Local port, default 8000; safe diagnostics level, default INFO |

The supported CLI binds localhost and runs one worker. It is not an internet-facing auth deployment. Without a fixture flag the environment is production; synthetic sources are rejected there and public/production publication is disabled. Authored directories supply inventory/index/discover/research/draft result JSON plus registered resources. Folder identity must match the project; imports do not extract or create content. Missing dependencies block at the node that needs them.

Programmatic embedding uses [create_app](../src/pastport/api/app.py) and [AppSettings](../src/pastport/api/settings.py). It does not configure the host's logging or enable fake providers in production. Configure LoggingConfiguration around the server lifetime and disable the host's raw access logging.

## 4. Shared contracts, evidence and resources

### 4.1 Identity and immutable models

Authoritative models are [domain](../src/pastport/domain/README.md), exported by [contracts.py](../src/pastport/contracts.py), with generated [schemas](../schemas/README.md). Do not duplicate them inside a module. Contracts are strict/frozen, reject unknown fields and use immutable tuples/typed entry arrays. Validate JSON with model_validate_json; do not bypass boundary validation using model_construct or an unvalidated model_copy update. [updated](../src/pastport/application/updates.py) revalidates changed records.

Preserve project_id, run_id, source/site/route/artifact IDs, content_version, expected_revision, request/operation IDs and sha256 across modules. Raw source/media references hash raw bytes; payload references hash canonical sorted compact UTF-8 JSON including versions/dependencies. They are different hashes. A filename, folder name, URI or self-reported approval is not identity or authorization.

| Artifact | Role |
|---|---|
| Source manifest/index | Registered materials, locations/statuses and gaps, available before claims/story |
| EvidencePackage | Traceable claims, sources/assets and route evidence |
| RouteRecord | Explicit place sequence/coverage and sourced passage facts; human-approved dependency for drafting |
| NarrativePackage / NarrativeDraft | Game plus authoring issues/unresolved needs; depends on approved evidence/direction/route |
| RuntimePackage | Validated unchanged game, compatibility and generated media manifest |
| ReviewSnapshot / ApprovedEvidenceView | Framework-reconstructed approval views, not bearer credentials |
| PackageBundle | Cross-package project/hash/route/review/media consistency; not proof of truth, solvability or live rights |

Unknown/missing extraction, source access, spatial conditions and rights remain explicit. Keep historical fact, interpretation and original fiction distinct. Preserve support and contrary evidence separately. Official availability does not grant media redistribution rights. A changed source/hash/right or reviewer permission can invalidate approval/release validity; do not silently retain an old decision for a new hash.

### 4.2 Resource boundary and assembly

[ResourceReader](../src/pastport/ports/resources.py) reads a typed ResourceReference `(project_id, resource_id, kind, version, sha256, source_uri)` with maximum_bytes and returns ResourceData with exact identity, bytes and media type. References do not accept arbitrary client filesystem paths. A custom reader must enforce scope, bounded I/O, deterministic cleanup and hash/size integrity; opaque URIs are not local paths.

The local reader uses [ResourceCatalog](../src/pastport/domain/resources.py) in resources.json: registered sources/assets carry project, stable ID, version/hash, controlled relative path and permitted type. It rejects traversal, symlinks, non-regular files, wrong identities and oversized/mismatched bytes. Test-mode project rebinding is synthetic-only. Caller-visible asset types are SVG/PNG/JPEG/WebP; raw originals are delivered inertly as attachments.

The deterministic assembler consumes approved evidence/narrative and registered bytes, generates the runtime media manifest, and preserves NarrativePackage.game. It does not require runtime.json or generate narrative. Injection cannot bypass identity, review, capability or resource checks. The loader defaults to an 8 MiB runtime package limit, parses strict data, checks exact trusted reference/hash/schema/profile/capabilities and rejects unsupported gameplay. Release validation separately checks all recorded media/source bytes and dependencies.

## 5. Independent modules and composition

### 5.1 Seven operations

Every operation is async, takes `(typed_request, context: ExecutionContext)` and returns `ModuleResult[Payload]`. [Port definitions](../src/pastport/ports/modules.py) and [request/results](../src/pastport/domain/modules.py) are authoritative.

| Operation | Request | Payload |
|---|---|---|
| Evidence.inventory | InventoryRequest | SourceManifestDraft |
| Evidence.index | IndexRequest | SourceIndexDraft |
| Evidence.research | ResearchRequest | EvidenceFindings |
| Narrative.discover | DiscoverRequest | CandidateSetDraft |
| Narrative.draft | DraftRequest | NarrativeDraft |
| Narrative.revise | ReviseRequest | NarrativeDraft, or an explicit evidence need/outcome |
| Narrative.review | NarrativeReviewRequest | NarrativeReview; never a human ReviewDecision |

Module outcomes are completed, research_required, changes_required, blocked, no_feasible_story. Completed needs a valid typed payload; research needs concrete questions and changes need affected IDs. Failed/gap work must not be disguised as completed. Context provides immutable project/run/input/Skill/policy identity, cancellation, deadline, tools and remaining limits. Modules own algorithms/internal storage, not shared workflow tables, approvals, budgets or release pointers.

### 5.2 Two different factories

| Boundary | Signature | Use |
|---|---|---|
| Offline checker | `build(fixtures: Path) -> EvidencePort/NarrativePort/ResourceReader` | Explicit trusted offline/test implementation |
| Application composition | `build(services: ModuleServices) -> EvidencePort/NarrativePort` | Construct a module with shared metered services and explicit module configuration |

Do not pass an offline Path factory as an application service factory. The app accepts `create_app(settings, evidence=..., narrative=..., resources=..., assembly=..., validator=...)`, or the corresponding evidence_factory/narrative_factory. Passing both an object and its factory is invalid. Local/injected/disabled selection is explicit; conflicts or missing selected implementations fail instead of silently falling back, including falsey supplied objects.

The single-module checker expects a direct port. The combined checker also supports a synchronous context manager yielding a port and closes it on exit. Direct products manage their own resources; arbitrary factory-created subprocesses are the factory owner's responsibility. Trusted local Python is not a filesystem/network/security sandbox; offline mode must not create paid calls or overwrite official DBs.

### 5.3 Independent checks and four combinations

```bash
uv run --no-sync python -m pastport.development.module_check evidence
uv run --no-sync python -m pastport.development.module_check narrative
# Install your own trusted package first; these external names are placeholders:
uv pip install --python .venv/bin/python -e /absolute/path/to/your-module
uv run --no-sync python -m pastport.development.module_check evidence \
  --factory your_evidence_package.handoff:build
uv run --no-sync python -m pastport.development.module_check narrative \
  --factory your_narrative_package.handoff:build
uv run --no-sync python -m pastport.development.module_acceptance \
  --output acceptance-artifacts/reference.json
```

Default commands use explicitly synthetic examples and request-bound reference implementations; they do not certify formal team modules. Smoke checks cover the seven operations' completed/cancelled paths, typed output, JSON roundtrip and project identity. The simple checker uses cooperative call timeout (default 2s, maximum 60s); it cannot stop blocking factory initialization.

The combined checker runs two smoke gates and local/local, selected/local, local/selected, selected/selected workflows. It selects a direction, issues synthetic review commands, opens a draft preview before narrative approval, checks private package/media and durable save restoration, and confirms public publication remains unavailable. Resources are injected independently; dual selected ports receive no framework local content directory, and runtime.json is removed from the copied input tree.

Use --evidence-factory for Weng, --narrative-factory for Matt/Mert and both for joint testing; leave the counterpart fixed. Optional --resource-factory supplies custom storage. --evidence-version/--narrative-version/--resource-version are explicit implementation declarations; absent versions stay unreported. --fixtures selects a complete consistent synthetic bundle, not an authoritative DB.

The combined runner copies/hash-checks a regular-file tree (512 files/64 MiB maximum), rejects symlinks, checks mutations, bounds each process (default 60s, maximum 300s), and deletes temporary state. --timeout bounds cooperative calls/workflow waits (default 10s, maximum 60s). Failed selected smoke gates make dependent combinations not_run, never a fallback success. Output reports are private files and never overwrite previous output. Exit codes: 0 all requested cases passed, 1 failures/not_run, 2 top-level input/config/report error. Reports are generated test results when needed, not a tracked historical documentation collection.

## 6. Workflow, reviews, edits and bounded routing

### 6.1 Main path and authority

```text
register_project → inventory_sources → extract_candidates → discover_story
  → select_candidate (human)
  → research_evidence → evidence_review (human)
  → draft_narrative → narrative_review (human)
  → assemble_package → validate_package → publish_review (human)
  → publish_package (private test release)
```

[StageRunner](../src/pastport/workflow/stages.py), [branching](../src/pastport/workflow/branching.py) and [worker](../src/pastport/workflow/worker.py) own execution. Typical statuses are queued, running, waiting_review, needs_review, needs_changes, blocked, budget_exhausted, failed, cancelled, no_feasible_story, published. Show actual status/error/owner rather than treating every wait as an exception. Same-project concurrent writable runs are constrained; no implicit second production queue is created.

Candidate ranking recommends; a current authorized narrative-role actor records candidate-set hash, chosen ID and reason. Model output cannot choose authoritatively. Evidence, narrative and publication gates record actor/gate/target/version/hash/reason through authenticated commands. Server accounts and the business DB grant authority, never client fields, content metadata, raw Skill text or graph resume values. Current roles/project/environment and exact target dependencies are rechecked when decisions are reused or published.

### 6.2 Gaps, revisions and professional review

Research purpose=scope_gap can run before selection and must have candidate_id=null; direction research must bind the selected candidate. The cumulative run limit is two research rounds, including scope and direction work; a round freezes up to eight concrete questions and persists each result independently. Retry resumes unfinished work, not a newly invented question list. There are at most two automatic narrative revision rounds; initial drafting is not a revision. Changing node/source/query or restarting/resuming does not reset counters.

`POST /runs/{run_id}/narrative-requests` is narrative-role-only during story review; action revise/review requires current expected_revision, current target IDs, feedback and idempotency. Explicit professional review and subsequent review after requested automatic revision do not create a fourth human approval gate. A returned evidence need routes through the evidence workflow before another draft; changed dependencies invalidate downstream reviews.

Manual `revisions` accepts a complete typed replacement, expected revision and reason. It saves an immutable version and fresh narrative request. JSON Pointer field locks are passed to modules and enforced against actual returned/manual changes. facts_changed=true is rejected by this endpoint with `EVIDENCE_REVIEW_REQUIRED`; use the evidence workflow. Locked or stale edits cannot silently replace the current draft. Rejected human decisions remain needs_changes; they do not auto-approve or spin.

At publication changes_requested, rework_owner must explicitly be evidence, narrative or assembly; missing responsibility returns `REWORK_OWNER_REQUIRED` without half-saving decisions. Unknown/unprovable impact requires conservative re-review. The comparison endpoint verifies exact same-run/current-after draft refs, up to 200 mechanical differences and approval identities; it always marks semantic impact uncertain and does not invoke an analyzer or grant approval.

### 6.3 Revocation and state durability

Review revocations append history and remove affected current release pointers atomically. Account changes apply after restart; startup/current-release reads revalidate authority, bytes and review dependencies. Unfinished runs can be resubmitted by the matching gate role, invalidating later approvals and requiring fresh gate decisions. A published run remains immutable; create a replacement run after retirement. There is no hot account reload or external rights registry.

HTTP command receipt, business state change and queued work commit transactionally. Checkpoint gaps cannot justify repeating saved content/model results. Scheduling rechecks business state before graph advancement; cancellation prevents pointer changes even if files are staged. Never patch the state dict to invent approval or reset quotas.

## 7. Skill protocol and content-quality boundary

Professional instructions live in [evidence-review](../skills/evidence-review/SKILL.md) and [narrative](../skills/narrative/SKILL.md), with focused calibration examples. They are inputs to module execution, not independent running agents or authority. Material, OCR, retrieved pages and model output are untrusted data.

| Skill mode | Required context | Not required as an invented prerequisite |
|---|---|---|
| Evidence index | Registered source material/scope | Existing claims, final story/route |
| Evidence research | Index plus concrete EvidenceRequest and permitted tools | A selected candidate for scope_gap research |
| Evidence review | Evidence candidate and nonempty target IDs | Complete final story |
| Narrative discover | Index, requirements and runtime capabilities | Approved final route, old draft/feedback |
| Narrative draft | Approved evidence, selected candidate, approved route | Old draft or revision feedback |
| Narrative revise | Draft context/current draft plus targeted revision request/locks | New unapproved facts treated as approved |
| Narrative review | Supplied draft and its route/direction | Invented feedback or approval |

`SkillResult[T]` carries request_id, skill/mode, input refs, decision, reason_code/reason, payload/issues, changed IDs, evidence requests and optional tool request. Decisions: complete, request_tool, research_required, changes_required, review_required, blocked, no_feasible_story. These are not ModuleResult outcomes. [SkillResultMapper](../src/pastport/application/workflow_control.py) performs the mapping: complete becomes completed; review_required with a usable payload/no blocking issue can hand off while still requiring human gates; otherwise it remains blocked/needs_review. Raw request_tool is not completed content; the bounded shared research executor consumes it and maps only terminal results. Modules cannot choose arbitrary graph routes.

Missing required fields fail before paid dispatch. Unknown optional fields stay unknown. Use typed current request DTOs and fixtures for exact fields rather than adding mode-specific enums. Never invent source access, citations/pages, hashes, tool execution or professional review results. Reuse saved observations before another fetch.

Content quality remains a professional/human boundary: each meaningful task should connect real heritage evidence → observation/inference → character goal/conflict → choice/cost → later consequence. Distinguish fact, interpretation and fiction; do not ascribe fabricated acts to real people. Prefer a short independently playable slice over more forms/content. Observe independent completion, player explanation of evidence/consequence, hints/intervention, confusion and desire to continue. Track editing/review minutes, actual tool/provider use and rework separately. Automatic schema checks or model self-ratings cannot certify truth, rights, fun, market demand or production efficiency. No human playtest threshold is claimed as achieved by synthetic fixtures.

## 8. Shared model and tool execution

[ModuleServices](../src/pastport/ports/execution.py) supplies models, sources, tools, bounded research and usage. Calls require current server-created execution grants with project/run/input refs, Skill/policy/model binding, cancellation, deadline, allowed tools and remaining budget. Forged contexts, wrong projects, stale Skills/policies, non-active parent reservations or stage-disallowed operations fail before dispatch.

[ExecutionSettings/ModelPolicy](../src/pastport/application/execution_models.py) pin one model per research/story role, provider/model, price_version, integer input/output rates, maximum reservation and approved Skill references. Default models and tools are empty. CLI supports OpenAI via the server-owned `PASTPORT_OPENAI_API_KEY`; it rejects fake-provider CLI configuration. Fake providers are explicit Python test injection and are forbidden in production. No automatic model substitution or direct module-owned paid SDK call is permitted.

| Setting | Current constraint |
|---|---|
| timeout_seconds | 1–120, also limited by execution deadline |
| maximum_source_bytes | 1–262144; default 262144 |
| maximum_input/output_tokens | Positive bounded reservations that must fit remaining limits |
| Allowed tools | Explicit read_source / lookup_local; search_web has no connector |
| Skill references | Explicit approved files; default none |

Only research has its bounded tool loop; index/story stages cannot invent research tool permissions. Repeated no-progress, unregistered sources, invalid questions or exceeded step/round/tool/cost limits stop explicitly. Original response/source/tool observations and known usage persist before returning output or advancing the workflow. Schema-invalid output or post-dispatch cancellation still preserves known usage. If a call's execution/usage is unknown, hold it and do not redispatch automatically.

Cost uses integer micro-USD: `ceil((input_tokens × input_rate + output_tokens × output_rate) / 1_000_000)`. Rates are micro-USD per million tokens; 1 USD = 1,000,000 micro-USD. Tokens come from provider receipts when reliable; calculated spend is not a reconciled invoice. Fake cost is test data. Cached-input rates, discounts and tier pricing are not modeled; extend explicit pricing contracts before relying on them.

Input limits are conservative UTF-8 byte-based bounds with margin, not tokenizer accuracy. Over-limit input returns MODEL_CONTEXT_LIMIT; select relevant permitted material instead of silently truncating evidence or increasing budget. Each run freezes execution configuration and Skill text/version/hash; changed configuration or Skill files require a new compatible run. Do not reinterpret old bindings/checkpoints under new rules.

## 9. Budget, operator commands and recovery

### 9.1 Ledger and activity

BudgetPolicy covers model requests, input/output tokens, search/fetch counts, automatic active seconds and cost. Usage stores integer counts, milliseconds and micro-USD. Short `BEGIN IMMEDIATE` transactions reserve maximum usage against settled plus held totals; concurrent calls cannot spend the same remaining allowance. Each operation has at most two total attempts. Actual overruns are recorded as actual facts, not clipped to a limit.

Automatic node/gate-processing wall time is measured once; nested model/tool time is not double-counted. Human/queue waiting, server startup and HTTP/UI time are excluded. It is not CPU profiling. Interrupted activity can be unknown independently of a known model receipt; reconcile all unknown reservations before scheduling new work. A budget increase or resume cannot release unknown usage, reset attempts/research rounds or imply approval.

### 9.2 Authenticated interventions

[Intervention models](../src/pastport/application/operations.py) and [service](../src/pastport/application/operational_service.py) define exact payloads. Every mutation requires current expected_revision, reason and Idempotency-Key; it persists command/audit/receipt atomically. Current actor/project authority is checked before idempotent replay.

| Action | Permission and binding | Result |
|---|---|---|
| GET interventions | Explicit operator and project scope | Budget/hash, unknown entries/hash and audit records |
| usage-reconciliations | Operator; reservation_id, entry_hash, action, settlement, evidence | Resolve the original reservation without inventing output |
| budget-amendments | Operator; budget_hash, complete policy, current revision | Append new authorization; preserve original policy and used/held usage |
| review-resubmissions | Matching evidence/narrative/publisher role; revoked decision/current revision | Reopen stopped unfinished run at the human gate, invalidate downstream reviews |

Reconciliation settlement.source must be operator. Evidence includes kind/reference/description; external calls require provider_receipt, appropriate local work may use local_execution_record. There is no automatic invoice/receipt-truth connector. Do not treat timeout, lost response or 429 alone as proof of free/non-executed work.

| Reconciliation action | Preconditions and effect |
|---|---|
| recover | Saved original response plus matching request/token/price evidence; derive settlement, reuse original response, retain original receipt and all schema/review gates |
| retry | Evidence confirms no execution, actual usage all zero, no saved response; settle that hold and permit only a remaining bounded attempt using saved request |
| settle | Usage known but output not recoverable; record spend, abandon content work without fake success; reconcile activity independently |

Known persisted receipts can finish the original settlement automatically; genuinely unknown calls/activity need operator evidence. Multiple unknown entries are resolved individually. Once safe and no unknowns remain, a stopped run may become blocked; editor separately resumes it. Reconciliation never approves content or restarts cancelled/terminal work. Budget amendments are for eligible stopped unfinished work, preserve initial policy/history, cannot go below used+held usage and do not auto-resume.

### 9.3 Storage, process recovery and private publication

The service data directory contains editorial.sqlite3/WAL, checkpoints.sqlite3, player.sqlite3, previews.sqlite3, instance.lock and immutable releases. Only one worker may own it, enforced by an OS lock; never delete the lock to bypass ownership. Test/production cannot share a bound DB. Unsupported/unrelated schemas fail. Editorial schema 1/2/3 can migrate transactionally to 4; incompatible graph/policy checkpoints are refused before execution. No legacy/demo review-DB rebuild/import is provided.

Stop the service and back up its complete data directory before operational migrations. Business records, not graph checkpoints or logs, remain authoritative. Persisted responses/results/settlements are reused; absent responses remain unknown. Process restarts reconcile state before scheduling. Cancellation propagates and preserves usage already incurred.

Publication validates approvals/rights/source bytes, stages immutable runtime/media/manifest bytes, then rechecks current run revision, current authority, activity allowance and expected old release pointer before atomic commit. Failure before pointer commit cannot expose a staged release; after commit cannot undo it. Hash tampering, revoked approval, permission loss, changed source bytes or cancellation must block/retire the pointer. No public static directory exposes sources, DBs or releases. Local process-exit tests are not a guarantee against power loss or arbitrary storage corruption.

## 10. Game runtime, actions and saves

### 10.1 Supported profile

The shared JS interpreter is [player/runtime.mjs](../src/pastport/player/runtime.mjs); Python [bridge](../src/pastport/application/player_runtime.py) delegates to it. Browser visibility imports the same condition helper, and state mutation always goes through server action authority. No per-site branches or model waits belong here.

| Category | Supported |
|---|---|
| Tasks | One inspect or caseboard task per scene |
| Actions | observe, choose, submit_evidence, advance |
| Conditions | observed_all, choice_equals, variable_equals, has_evidence, elapsed_gt, all, any, not |
| Effects | grant_item, set_variable, set_relationship, add_story_time, unlock_scene, resolve_ending |
| Events | spot_observed, board_submitted, option_chosen, task_completed |
| Languages | en/zh text resources with the same IDs/rules/answers/effects |
| Bounds | Two events and 64 effects per action; condition depth eight, plus strict bounded schemas |

Inspect hotspots use normalized 0–10000 coordinates and equivalent accessible text controls. Caseboard submission uses exact owned evidence. Decisions are immutable, movement requires a linked/unlocked scene and task guards, and feedback/endings reflect confirmed state. Unlocking is not moving. Document/sorting/multi-task dependencies, new discriminators and unsupported route/capability declarations are rejected rather than approximated.

### 10.2 Determinism, receipts and saves

Action processing validates project/release/package, handles an existing action receipt before stale-revision checks, then applies current-scene/target guards, FIFO events, deterministic priority/ID order and per-event guard snapshots. Effects execute in the frozen order. Duplicate once/event identities are suppressed; conflicting writes or bounds errors roll back the entire action. A failed action cannot leave partial state/receipt/revision changes. Ending resolution and localized feedback are deterministic.

Save ownership binds environment/actor/project/save slot plus release/package/chapter/schema. SQLite CAS commits state, action receipt and revision atomically. Same action ID/body returns the persisted original result; changed body conflicts. A new action requires the confirmed revision. Lost HTTP response is an unknown save result: explicitly retry the original request, not a new action. Restore revalidates exact identity/state, not the latest package silently substituted into an old save. Generated JS declarations/schemas come from Python contracts and must pass drift checks.

## 11. Workbench, previews and original sources

| Section | Current use |
|---|---|
| Overview | Register input, start/load run, inspect stage/blocker, choose a direction with reason |
| Evidence | Claims/support/refutation, exact source version/hash/locator, stored original fragments and registered download |
| Story and changes | Localized edits/full typed draft, reasons, factual-premise declaration, locks, saved-version diff |
| Play preview | Draft-before-approval, inspect/evidence/choices/feedback/ending, language, retry/reload/restore and legal replay |
| Review and release | Exact current gate targets, decisions/reasons, publication rework owner, history/revocation and private release |
| Activity and budget | Ordered events, used/held/unknown usage, cancel/resume and role-limited recovery forms |

Changing project/run/account clears old private content, pending operations and preview context. Tokens never enter query strings/localStorage. UI uses safe text rendering; source/model content never becomes trusted HTML/JS. Media is fetched with authenticated headers into short-lived blob URLs and revoked on replacement/disconnect. Static JS/CSS is an explicit trusted allowlist, not a public repository/filesystem mount.

Draft preview projects an exact current NarrativeDraft into a validated test-only runtime without manufacturing approval or a ReleaseRecord. It is stored separately from formal release saves, binds owner/project/environment/run/source/runtime hash, expires after one hour and caps active sessions at ten. Access/source/draft changes, cancellation and expiry invalidate use; PREVIEW_EXPIRED is explicit. Creating/playing it does not advance run revision, settle editorial spend or approve content.

After refresh reauthenticate, load the exact run, enter the exact preview ID and restore. Requests have a 30-second client timeout; unknown outcomes keep the serialized original operation identity/body for explicit retry. Do not silently rewrite a stale action/review. Branch comparison creates another isolated preview and replays a selected legal prefix recorded since initial state, then allows another real option. A restored partial history is not a full replay; there is no arbitrary state patch.

Original-source endpoints require the run's registered source_id/source_version/file_sha256. Show stored fragments/status/locator; missing/failed/needs_ocr remains explicit. Claim wording is not substituted for original text; this view adds no OCR, web fetch or model call. Registered raw bytes are bounded/hash-checked and downloaded as inert no-store/nosniff/sandbox attachments. Private release resources similarly revalidate the still-current release and controlled media manifest.

## 12. HTTP interface and errors

All paths below are under /api/v1 unless stated. Health and deliberately unavailable public release are unauthenticated; trusted static modules and the root workbench shell are public but contain no private data. Authenticated routes use `Authorization: Bearer ...`, server actor roles and project scope. Request JSON is bounded and validated; no self-declared owner/approval or arbitrary filesystem path is accepted.

Editorial mutations require Idempotency-Key (1–160 characters); same key/body returns original receipt, changed body conflicts. Run commands also require expected_revision/reason as defined by their DTO. Player creation uses save_id; actions use action_id/body identity plus expected_revision. Authentication/current authority remains necessary for replay. Every response handled by the request middleware receives a server-generated X-Request-ID.

| Method / path | Purpose / payload reference |
|---|---|
| GET /health | Worker readiness/environment and selected modes |
| GET /session | Current actor roles/project scope/environment; no token digest/account list |
| GET, POST /projects | Accessible projects / CreateProject |
| GET /projects/{project_id} | Project requirements |
| GET /projects/{project_id}/policy | Current server policy ref for CreateRun |
| POST /projects/{project_id}/runs | CreateRun; persist command and policy/budget binding |
| GET /runs/{run_id} | RunRecord: state, artifacts, reviews, control and current identities |
| GET /runs/{run_id}/events, /reviews, /budget | Ordered events, exact review requests/history, settled/held usage |
| GET /runs/{run_id}/executions | Safe execution summaries; excludes prompt/raw provider bodies |
| GET /runs/{run_id}/artifacts | Artifact refs |
| GET /artifacts/{artifact_id} | Stored payload, optional content_version; owning-run auth |
| POST /runs/{run_id}/candidate-selections | SelectCandidate against current candidate-set hash |
| POST /runs/{run_id}/review-decisions | SubmitReview exact targets; rework_owner when required |
| POST /runs/{run_id}/review-revocations, /review-resubmissions | RevokeReview / ResubmitReview with current gate authority |
| POST /runs/{run_id}/narrative-requests | Revise/review action with current targets/feedback |
| POST /runs/{run_id}/locks, /revisions | SetLocks / SubmitRevision, enforce current draft/locks |
| POST /runs/{run_id}/cancel, /resume | RunCommand; resume is not approval/reconciliation |
| GET /runs/{run_id}/interventions | Operator snapshot and audit targets |
| POST /runs/{run_id}/usage-reconciliations, /budget-amendments | ReconcileUsage / AmendBudget |
| POST /runs/{run_id}/change-impact | Read-only CompareChanges for exact stored/current draft refs |
| POST /runs/{run_id}/previews | CreatePreview expected_revision/source_ref and editorial request key |
| GET /runs/{run_id}/previews/{preview_id} | Exact owner-bound PreviewView/confirmed state |
| POST /runs/{run_id}/previews/{preview_id}/actions | Shared ActionRequest; no direct state patch |
| GET /runs/{run_id}/previews/{preview_id}/assets/{asset_id} | Registered preview media only |
| GET /runs/{run_id}/sources/{source_id}, /sources/{source_id}/content | Exact source metadata/fragments or original bytes; version/hash query required |
| GET /projects/{project_id}/release | Revalidated current private ReleaseRecord |
| GET /projects/{project_id}/releases/{release_id}/package, /assets/{asset_id} | Exact current private package/media |
| GET /projects/{project_id}/player-initial-state | Unsaved initial state for valid private release |
| POST /projects/{project_id}/player-saves | CreatePlayerSave with save_id |
| GET /projects/{project_id}/player-saves/{save_id} | Restore bound PlayerSaveView |
| POST /projects/{project_id}/player-saves/{save_id}/actions | Shared action and persisted result |
| GET /public/projects/{project_id}/release | Always unavailable; no public publishing feature |

Root GET / serves the workbench. GET /static/{group}/{module_name} serves only allowlisted workbench/player deployment files. Exact input types are in [application models](../src/pastport/application/models.py), [operations](../src/pastport/application/operations.py), [previews](../src/pastport/application/previews.py) and [game/action](../src/pastport/domain/game.py); transport behavior is in [app](../src/pastport/api/app.py) and [private views](../src/pastport/api/private_views.py).

Errors distinguish 401 authentication, 403 project/role denial, 404 absent/unregistered, 409 stale/conflict/invalid authority, 410 expired preview, 413 oversized bytes, 422 invalid input and 503 unavailable I/O/process. Editorial errors carry safe code/message/owner/retryable/field details; player errors can use a smaller safe envelope. UI preserves the actual code/status. Retryability is not permission to repeat an unknown external call or reconstruct a new request.

## 13. Logging and operational diagnostics

[LoggingConfiguration/SafeJsonFormatter](../src/pastport/observability.py) own JSON stderr for pastport and Uvicorn namespaces in the supported CLI. Modules use logging.getLogger(__name__), not handlers/basicConfig at import time. The manager restores host handlers/levels/propagation on exit and leaves the root logger untouched. Embedded hosts must configure it explicitly; independently installed child handlers/raw host logs remain the host's responsibility. CLI stdout stays available for development result JSON.

| Field | Safe meaning |
|---|---|
| timestamp, level, logger, event | UTC ISO time, severity, module and bounded snake_case event |
| request_id, environment | Server-generated opaque HTTP correlation and actual environment |
| project_id, run_id, operation_id, stage, status | Applicable safe business/phase identity, not body dumps |
| error_code, error_type | Explicit domain code and exception class; no raw exception body/traceback |
| package_hash, content_version, contract_version | Exact applicable content binding |
| method, status_code, duration_ms, attempt, count | Non-negative integer counters and monotonic duration |

Arbitrary log messages/arguments/objects, unapproved extras and invalid identities are dropped; unsafe text becomes diagnostic_event. Only safe syntactic IDs/events are accepted—do not hide secrets in an otherwise valid ID. Never log credentials, connection strings, raw URLs/queries/headers, environment dumps, private filesystem paths, source/player text, prompts or provider request/response bodies. DEBUG has the same rules. Broad exception handling rethrows or records safe type/code context; cancellation propagates.

Current events: request_completed for successful mutations, request_rejected for handled error responses, request_failed/request_cancelled for propagated failure/cancellation, stage_failed with safe run/project/stage/status/error and worker_stopped with type. Successful GET/HEAD/OPTIONS polling/static reads are quiet. A completed HTTP command is not a finished background workflow. INFO is meaningful lifecycle, WARNING attention/recoverable rejections, ERROR unexpected blocking/5xx and CRITICAL unsafe continuation.

Raw Uvicorn access logs are disabled; generic free-text Uvicorn diagnostics are filtered rather than printed verbatim. This limits free-text startup detail intentionally; use configured port and /health readiness. No collector, rotation, retention policy, dashboard or production shipping is enabled. Configure those in the eventual process supervisor with explicit access/retention. Logs never replace the durable audit/ledger/receipt/checkpoint/release store.

## 14. Checks, CI and acceptance

### 14.1 Reproducible checks

```bash
uv sync --locked --group dev
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync mypy --strict src/pastport tools/check_contracts.py tools/check_handoff.py tests
uv run --no-sync python tools/check_contracts.py
uv run --no-sync python -m pastport.development.player_contracts --check
uv run --no-sync python tools/check_repository.py
uv run --no-sync python tools/check_handoff.py
uv run --no-sync pytest
```

Regenerate schemas only after an intended model change using `python tools/check_contracts.py --write`; inspect generated diff. Player declarations use `python -m pastport.development.player_contracts` with --check in validation mode. Do not hand-edit generated schemas/declarations or weaken checks. Fixture/vector metadata marked not_run is a declaration, not a passing execution report.

For JS/browser checks:

```bash
npm ci --ignore-scripts --no-audit --no-fund
npm run check:js
npm run format:check
npx playwright install chromium
uv run --no-sync python -m pastport.development.browser_check --artifacts browser-artifacts
```

Linux CI uses `npx playwright install --with-deps chromium`. The runner creates temporary synthetic DBs/random accounts and an isolated localhost service, bounds execution and shuts it down. Optional PASTPORT_CHROMIUM_EXECUTABLE chooses an installed local browser; normal CI installs the matching locked browser. Syntax/rendering guards plus Prettier are not a complete JS type/security audit. Chromium automation is not Firefox/WebKit certification or human accessibility/playtesting.

Combined module and fault acceptance:

```bash
uv run --no-sync python -m pastport.development.module_acceptance \
  --output acceptance-artifacts/framework.json
uv run --no-sync python -m pastport.development.fault_acceptance \
  --output acceptance-artifacts/faults.json
```

Use fresh output names; neither overwrites prior evidence. Outputs can remain under ignored artifact directories rather than tracked docs history. Fault acceptance executes fixed approval/budget/shared-execution/reliability suites, including real subprocess death boundaries, checks source identity before/after, rejects empty/skipped/failed results and strips raw private failure bodies. The gate timeout is 240s; malformed/config/report errors fail explicitly. No paid providers are needed.

### 14.2 Coverage and limits

| Checks | What they establish |
|---|---|
| Contracts/fixtures | Wire/semantic validation, project/dependency/hash consistency, deliberate invalid samples |
| Independent module/matrix | Seven operation completed/cancelled checks, actual four-combination workflow/assembly/private package/save behavior |
| Workflow/operations/shared execution | Bounded questions/revisions, locks/routes/reviews, stage grants, fake HTTP/provider receipts, budget/unknown/CAS/reconciliation |
| Reliability/process faults | Revocation at commit across reference combinations; process death before/after release commit and response receipt; no duplicate dispatch, held unknown time, immutable files/pointer integrity |
| Player/Node | Shared components, frozen vectors, full supported-profile actions, conflicts/rollback, receipts, isolated CAS saves and crash restoration |
| Browser | Direction/reviews, original unavailable state, preapproval play, lost committed-response retry, legal branch replay, language/keyboard, ending, refresh/restore, edit/diff/invalidation, private release, mobile/access isolation |
| Logging/handoff | Privacy/correlation/cancellation/handler restoration, complete module inventories, four canonical documents and shared Agent routes |

All synthetic test approvals stay in disposable test DBs; they do not grant professional acceptance. Automated completion does not certify historical truth, rights, narrative quality, paid provider reliability/billing, real player understanding or production operations. Record actual current command results when handing off, rather than copying an old stage's passing status.

### 14.3 CI

[ci.yml](../.github/workflows/ci.yml) defines quality (structure/handoff, Ruff, mypy, schemas), python-tests (pytest/module/fault checks), browser-tests and aggregate ci. Dependencies/actions are pinned, permissions read-only, jobs bounded and failure propagated. CI configuration exists; remote run/branch protection is confirmed only from actual remote evidence. No untrusted PR code receives production secrets or unnecessary write permissions.

## 15. Coding Agent and documentation rules

### 15.1 Document authority and reading

| Document | Authority | Update trigger |
|---|---|---|
| This guide (PRD) | Product intent, architectural boundaries, current capabilities, interfaces/operations | Approved behavior/scope/architecture or actual implementation changes |
| [Active Plan](ACTIVE_PLAN.md) | Current milestone scope/limits, small tasks, owners, dependencies, acceptance and blockers | Task selection, progress, handoff, failure, acceptance or a new finding |
| [Decision Log](DECISION_LOG.md) | Important choices, rationale, alternatives/consequences and supersession | Explicit approval of a significant choice or its replacement |
| [Change Log](CHANGELOG.md) | Verified major deliveries and links to acceptance evidence | Acceptance of a meaningful delivery; distinguish implemented/integrated/released |

Wehan maintains cross-module guidance; Weng owns evidence acceptance, Mert/Matt owns narrative/player acceptance, and each task has one accountable owner. Code/models/schemas define actual signatures; this PRD defines approved intent. Report contradictions and fix the affected authority through the agreed scope; plan/log entries cannot override contracts, rights, budgets or approval policy. Do not claim implementation from prose.

Start with root AGENTS, git status, the current task and affected module README/code. Fetch only relevant PRD sections and applicable accepted decisions. Changelog/history is not a default execution context. Preserve unchanged context; do not preload the whole repository, sources or chat. Skills package reusable procedures, not task status or authority; scripts perform deterministic checks. Do not introduce a new agent platform, extra agents or a Skill for each task.

These instructions apply to agents in this checkout. A separately maintained module repository does not automatically inherit them: its owner supplies a short root-agent pointer to this repository's AGENTS, current contracts and the assigned task, and checks the relevant boundary before handoff. Do not copy the whole PRD into another agent's always-loaded instructions.

### 15.2 Task, handoff and acceptance

A task records **owner, dependencies, deliverable, acceptance and status**; add scope/limits, affected paths/contracts and a short approach only where needed. Unknown external status stays unknown. Break large work into independently verifiable increments; do not assign an entire module as one unchecked task. Work one coherent increment at a time; independent team members may work in parallel.

For meaningful newly authorized work, add or update a small plan task before implementation, then proceed within that authorization. Routine tiny edits need no separate task or decision entry. A plan row is not permission to change shared scope, spend money or publish; unresolved product/contract choices go to the affected owner.

Normal flow: **todo → in_progress → accepted**. Cross-module work adds **awaiting_integration → verifying** before acceptance. On failure use **blocked/needs_changes**, record the concrete cause and next action, then re-enter the appropriate step. Do not force minor edits through unnecessary ceremony. When a session ends unfinished, keep the current status, changed paths, verification performed and next action in the task; do not call it delivered or create a new handoff document.

Before cross-module implementation/integration, confirm typed inputs/outputs, schema/capability/implementation versions, errors/cancellation/resource lifecycle, a fixed reference counterpart and the relevant acceptance command (§5). Shared semantic changes require affected owners' confirmation and compatible caller updates. Handoff names the exact implementation/contract revision, factory/entry point, delivered files, check results and remaining limits. Use existing module checks and the four-combination runner; approved professional content remains a separate decision.

The owner supplies evidence; the acceptance owner checks the agreed conditions against the delivered revision. For this three-person team, cross-module work uses the relevant counterpart/Wehan for integration; professional evidence/content approval remains with the assigned human role. No one silently lowers acceptance to obtain a pass. An agreed change to acceptance updates the task and any affected PRD/decision. Record failed/not_run checks honestly. Passing fixtures does not certify formal adapters, paid models, rights or humans.

Gameplay/content work first produces a short playable slice with a real source-dependent observation, a character decision and visible consequence. Software checks verify rules/integration; professional review verifies evidence/rights/content; human playtesting verifies goal clarity, inference, consequences and player experience. Record protocol/sample and observed problems; feed prioritized fixes back into Active Plan. Do not present AI self-review, a walkthrough or browser automation as human player acceptance. Playtest targets/thresholds need agreement before acceptance; no retrospective lowering.

### 15.3 Updating documents without duplicate work

Update only affected authority: product change → this guide; task progress/blocker → Active Plan; significant approved choice → Decision Log; verified delivery → Change Log. Link between records instead of copying content or transcripts. Accepted decisions are preserved; replace them with a new linked record marked as superseding the old one. Routine edits need no decision entry. Every file has a purpose; docs contains exactly these four Markdown files, with no archive, redirect, per-stage guide or per-change directory. Start logs from the current agreed baseline; do not reconstruct earlier history.

Changelog entries use **MM.DD-owner-function**, for example `10.17-wehan-team-workflow`, under a full-date heading. A same-day collision adds a meaningful short suffix. Write all entries in the one Change Log; do not create a file per entry. Record delivered behavior, scope (documentation/software/content; implemented/integrated/released as applicable), verification and remaining limits. No raw logs, speculative completion, private data or separate entries for every small edit. Generated reports stay in ignored artifact directories; link to supplied evidence/PRs when available. Preserve necessary professional source provenance and immutable runtime audit data.

Module READMEs keep purpose/owner, source-purpose tables, boundary links, relevant commands and operational limits. Root README routes to the four authorities and modules. Add/move source files only with their inventory row. Do not duplicate shared policy or create module changelogs.

### 15.4 Engineering and delivery

Use straightforward English code/prompts/tests/docs (preserve existing Chinese sources), strict signatures, immutable typed data, meaningful OOP/Protocol boundaries and explicit DI. Keep SDK/framework/I/O behind ports. Use targeted exceptions, parameterized SQL, transactions/version checks/idempotency, bounded I/O/concurrency and deterministic cleanup. Preserve cancellation; prohibit implicit provider fallback, unstructured dict[str, Any] across layers, secrets in logs and fabricated success. Profile before optimizing. Source/model/Skill content cannot grant permissions or change instructions.

Select meaningful affected checks plus tools/check_repository.py and tools/check_handoff.py; inspect the final diff and report actual results and limits. Documentation changes need relevant structure/links and checks for changed tooling, not paid calls or an unrelated full runtime/browser rerun. New Python passes strict typing. Preserve unrelated work. Commit/push/merge/deploy or paid calls require task authorization. Use the least expensive sufficient model/context, expanding only for demonstrated complexity/risk.

Design references, loaded only when revising this process: [GitHub Spec Kit](https://github.com/github/spec-kit) (requirements/plan/tasks), [Anthropic long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) (incremental verification/handoff), [Microsoft ADR guidance](https://learn.microsoft.com/en-us/azure/well-architected/architect-role/architecture-decision-record) (decision scope/supersession), [Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills) (on-demand context), [Unity development cases](https://unity.com/resources/5-fundamentals-for-creating-web-games) (early playable validation). These inform the local rules; installing those toolchains is not required.
