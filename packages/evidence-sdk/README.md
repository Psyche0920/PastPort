# PastPort Evidence SDK

## Current integration contract

| Item | Current behavior |
|---|---|
| Inputs | Original registered PDF, site photos, source scope and bounded grant. |
| Outputs | RegisteredPDF, matched/evidence documents, locators, media and unresolved findings. |
| Workflow | Validate/register → extract → semantic recognition/mapping when authorized → export. |
| Technology | Python 3.12, typed models, PDF/image tools, bounded semantic transport. |

Unified architecture and exact current verification scope: [Technical PRD](../../docs/TECHNICAL_PRD.md#sdk-modules). Main reuses the registered upstream outputs and saved Story in its current replay entry; this is not a new recognition/rendering/model run.

Independent distribution: `pastport-evidence==0.1.0`; import namespace: `pastport_evidence`.
Source revision and notices: [UPSTREAM](UPSTREAM.md), [license](LICENSE).

Input: one historical PDF, ordinary multi-angle photographs, an isolated workspace
and an explicit finite subscription grant. Output: a comparison PDF, editable IDML,
source provenance and unresolved gaps. Modern substitutes are labelled as such.
This package neither builds a game nor claims a structured museum handoff.

## Install independently

```sh
uv pip install './packages/evidence-sdk[codex]'
pastport-evidence --help
```

From inside this package directory, use `uv pip install '.[codex]'` instead.
Python 3.12 and Poppler `pdftoppm` are required. Installation/import/help does not
authorize generation. Supply the existing bounded grant explicitly for real work;
retain the original ledger on resume. Never place credentials in a grant file.

## Python boundary

`pastport_evidence.sdk` exports `PhotoMappingWorkflow`, `SubscriptionGrant`,
`OutputPaths`, `PDFDocumentReader` and `SemanticTransport`. Inject a reader and
transport into the workflow. Its existing typed `run(pdf, photo_folder, workspace,
grant, run_id, large_pdf=False)` returns stage outputs and writes the final typed
`OutputPaths` to the workspace's `result.json`. Exact signatures live in code.
Default transports are optional; imports do not launch a model or service.

## Historical display boundary

The repository evidence-review Skill is editorial guidance; this SDK executes its packaged, versioned prompts. PDF mapping explanations are review metadata, not the player's historical popup body. The environment presentation layer displays source-supported historical content and the original locator, preserving manual overrides. The current evidence adapter can expand retrieval within the registered PDF; it does not implement autonomous external research. External supplements need a separately authorized retrieval path and inspected, claim-level source references.

## Source responsibilities

| Source | Purpose |
|---|---|
| `src/pastport_evidence/sdk.py` | Stable public re-exports without duplicate business logic |
| `src/pastport_evidence/cli.py` | Explicit command-line generation entry |
| `src/pastport_evidence/application/` | Photo identification, evidence, document assembly |
| `src/pastport_evidence/domain/`, `ports/` | Immutable models and injected contracts |
| `src/pastport_evidence/adapters/` | Bounded SDK execution, PDF I/O and rendering |
| `src/pastport_evidence/workflow/` | Durable bounded stage execution |
| `src/pastport_evidence/prompts/`, `fonts/` | Versioned prompts and licensed PDF resources |

Package tests verify the installed SDK boundary; real evidence quality, model
execution, rights and human document acceptance require separate verification.

Run the offline boundary checks from this package root with
`python -m unittest discover -s tests -t . -v`.

<!-- BEGIN FILE INVENTORY -->
## 文件结构与用途

每个文件的用途直接写在同一行。以下覆盖本范围内的 **55 个维护文件**；依赖环境、缓存、私有产物和历史备份不属于源码清单。

```text
evidence-sdk/
├── src/
│   └── pastport_evidence/
│       ├── adapters/
│       │   ├── __init__.py  # Python 包初始化；标记该目录为 Python 包，无额外运行逻辑。
│       │   ├── assets.py  # Content-addressed local asset storage with atomic, size-bounded registration.
│       │   ├── codex_sdk.py  # Official Codex SDK transport using the operator's existing ChatGPT login.
│       │   ├── codex_semantics.py  # Bind existing semantic ports to one grant-scoped, metered Codex executor.
│       │   ├── document_export.py  # Render one layout as a PDF and an editable IDML package with relative image links.
│       │   ├── execution.py  # Durable grant reservations: uncertain dispatch consumes its slot until reconciled.
│       │   ├── identity.py  # Transactional scene identity allocation without category/name-based merging.
│       │   ├── pdf.py  # Native PDF text, positioned line and embedded image extraction plus Poppler rendering.
│       │   ├── report_layout.py  # Lay out supported text beside target and source images without truncating quotations.
│       │   └── structured_output.py  # Translate Pydantic schemas to the provider's strict structured-output subset.
│       ├── application/
│       │   ├── __init__.py  # Python 包初始化；标记该目录为 Python 包，无额外运行逻辑。
│       │   ├── bootstrap.py  # Atomic writes for owned pipeline checkpoints.
│       │   ├── document_package.py  # Atomically complete both human documents without exposing a downstream data interface.
│       │   ├── evidence.py  # Retrieve across the corpus, verify exact selectors and enforce display-copy scope.
│       │   ├── inputs.py  # Validate local source PDF before registration or model execution.
│       │   ├── pdf_ingestion.py  # Register a source PDF and persist page text and rendered-page references.
│       │   ├── photo_mapping.py  # Photo-first substitution preparation; VR localization is a separate downstream consumer.
│       │   ├── photos.py  # Register photos and identify repeated objects without interpreting them as panoramas.
│       │   ├── preparation.py  # Photo target to historical source assignment and scoped evidence preparation.
│       │   └── prompting.py  # Load explicit packaged policy versions for injected semantic adapters.
│       ├── domain/
│       │   ├── __init__.py  # Python 包初始化；标记该目录为 Python 包，无额外运行逻辑。
│       │   ├── build.py  # Automatic PDF/tour build requests and source-bound mapping proposals.
│       │   ├── evidence.py  # Exact quotations, independently scoped claims and editable display copy.
│       │   ├── execution.py  # Bounded standalone subscription execution; no fabricated dollar accounting.
│       │   ├── geometry.py  # Coordinate contracts: image edges, top-left pixels, yaw-zero forward and pitch-up.
│       │   ├── mapping.py  # Internal assigned-object and source-evidence records.
│       │   ├── models.py  # Immutable domain records shared by input, workflow and export boundaries.
│       │   ├── pdf.py  # Typed records produced while reading and rendering a registered PDF.
│       │   ├── photos.py  # Ordinary photographs and pixel observations, independent of panorama geometry.
│       │   ├── recognition.py  # Scene identities, image-bound proposals and complete per-view dispositions.
│       │   └── report.py  # Internal layout shared by the two document renderers, not a downstream API.
│       ├── fonts/
│       │   ├── NotoSansSC-Regular.ttf  # Noto Sans SC 字体，支持导出 PDF 中的简体中文。
│       │   ├── OFL.txt  # 随附字体的 SIL Open Font License。
│       │   └── README.txt  # 随附字体的来源及使用说明。
│       ├── ports/
│       │   ├── __init__.py  # Python 包初始化；标记该目录为 Python 包，无额外运行逻辑。
│       │   ├── assets.py  # Asset storage contract used by application services.
│       │   ├── execution.py  # Transport boundary keeps the SDK outside domain/application services.
│       │   ├── identity.py  # Persistent identity allocation boundary.
│       │   ├── pdf.py  # PDF processing contract independent of the chosen extraction/render libraries.
│       │   └── semantics.py  # Inject a shared metered gateway; application services never instantiate paid SDKs.
│       ├── prompts/
│       │   ├── evidence_association_v2.txt  # 证据关联模型提示词，约束史料与对象关联输出。
│       │   ├── pdf_matching_v2.txt  # PDF 匹配模型提示词，约束匹配字段与证据表达。
│       │   └── photo_inspection_v1.txt  # 现场照片检查模型提示词，约束可见物体观察输出。
│       ├── workflow/
│       │   ├── __init__.py  # Python 包初始化；标记该目录为 Python 包，无额外运行逻辑。
│       │   └── graph.py  # Fixed LangGraph stages backed by authoritative transactional stage receipts.
│       ├── __init__.py  # Python 包初始化；标记该目录为 Python 包，无额外运行逻辑。
│       ├── cli.py  # Run the photo-to-document pipeline; no review server or VR command is included.
│       ├── py.typed  # PEP 561 类型标记，让安装方的类型检查器识别本包类型。
│       └── sdk.py  # Public library surface; implementations retain injected readers and metered transports.
├── tests/
│   ├── __init__.py  # Offline distribution-boundary checks for the evidence SDK.
│   └── test_sdk.py  # 回归测试，覆盖 EvidenceSdkBoundaryTests。
├── LICENSE  # 本模块的许可证；分发源码或安装包时保留。
├── README.md  # 本模块的使用入口、输入输出及完整文件用途说明。
├── UPSTREAM.md  # 上游来源、提取范围及归属说明；不是运行入口。
└── pyproject.toml  # 本项目的包名、依赖、命令入口与构建配置。
```
<!-- END FILE INVENTORY -->

New workspaces pin [evidence_association_v3.txt](src/pastport_evidence/prompts/evidence_association_v3.txt): PDF-supported historical content stays separate from proxy/matching explanations. Existing workspaces retain v2, so a prompt update does not mutate paid execution identities. [test_prompt_policy.py](tests/test_prompt_policy.py) checks new/legacy policy pinning and unknown-version rejection without model calls.

New workspaces also pin [photo_inspection_v2.txt](src/pastport_evidence/prompts/photo_inspection_v2.txt): two photos per batch, at most 12 new entity proposals and 24 sightings, bounded labels/features/basis/gaps, and a 120-second photo-call deadline (or the grant's shorter deadline). This is an execution bound, not a required object count. Explicit incomplete-inventory gaps stop acceptance rather than silently omit objects. Legacy v1 policies, saved requests and paid receipts stay unchanged; no automatic retry or budget increase. Operational failure code and cause type are stored separately in the execution ledger without prompts, credentials or arbitrary exception text.

[Compact policy regression](tests/test_photo_bounds.py) checks schema overflow, short deadlines, sanitized failure diagnostics and blocked redispatch.

Manual interrupted-call recovery uses `SubscriptionExecutor.approve_interrupted_retry(binding, reason)` only after the original worker has stopped and the operator has explicitly authorized replacement. It records a separate replacement binding and audit reason; completed results remain cache hits, the interrupted row/result stays unchanged, and both original and replacement count against the same grant call limit. Actual interrupted token usage remains unknown; recorded-token accounting is not a claim of total billed usage. `StageJournal.reconcile` records the interrupted running stage separately before Admin continuation. No automatic retry or implicit grant reset is introduced. Recovery regression checks preserve the original unknown row, enforce call ceilings and verify successful responses are not dispatched again.

Admin's shared PDF workflow automates the earlier mapping method: recognize current photos, retrieve candidate pages from a source-bound text index, match the actual PDF images, validate exact source selectors locally, then export the mapping PDF for human review. VR and raw 3D uploads use this same Evidence entry point. One bounded text-only request selects at most twelve candidate pages; visual matching uses at most four three-page batches. Exact quotation validation does not dispatch a separate model request for every object. Historical associations remain candidates pending human review; source-exact text is not proof of a physical identity match. Uncovered objects, truncated extraction and non-exhaustive page coverage remain explicit gaps.

The candidate plan and recognition checkpoints are cached only within the same immutable inputs/revision. New indexed revisions copy registered source/photo inputs and recognition checkpoints, leaving previous PDFs, journals, grants and receipts intact. Legacy non-indexed workspaces remain replayable. New materials are matched anew: the shared processing method never imports another project's object/subject associations.

Admin explicitly supplies --no-token-threshold. This appends an audited token-threshold override without changing the grant or clearing usage. Zero denotes disabled threshold internally, not zero usage. New output revisions replay completed calls; standalone calls without this flag keep their original threshold.

Generated mapping PDFs include internal numbered evidence links for source-supported candidates. The existing environment SDK reads this index and inspects the linked detail pages; unassigned objects remain visible in the PDF as gaps and are excluded from historical attachment. This is a processing index, not historical approval. Re-exporting a linked revision preserves prior PDFs and paid results. Raw-3D environment runs bind the mapping hash in their run ID while sharing the original grant ledger and call ceiling.

New workspaces pin PDF matching policy `v3`: every recognized object is evaluated for visual, functional or explicitly documented narrative-proxy candidates. Missing evidence remains a numbered gap; this does not approve historical identity or relax 3D localization. Existing workspaces retain their pinned policy and receipts.

### Native IDML source input

The IDML path inspects all photo batches rather than stopping at 20 identities. It reserves two grant calls for matching/audit; incomplete initial coverage blocks downstream work. Object contact sheets are paginated at 16 identities per sheet. Use a new workspace revision for the changed policy and retain previous receipts and saved anchors.

Overlapping boxes remain pending unless `--identity-reviews reviews.json` supplies current-inventory-bound distinct-object decisions (`inventory_sha256`, two stable `object_ids`, and `basis`). Repeated historical names alone do not invalidate distinct physical objects. Handoffs retain all dispositions and mapping coverage; mapping counts are not saved 3D anchor counts. The 3D API separately reports eligible saved anchors in the current viewpoint; 15 saved positions still need surface and reopen acceptance.

`python -m pastport_evidence.idml_cli --idml source.idml --links Links.zip --output source-index.json` performs local extraction only. Complete matching uses `--workspace`, `--photos` and a finite `--grant` instead of `--output`, reusing photo identities and the subscription ledger. Linked graphics are read from a directory or ZIP (3 GiB archive / 4 GiB expanded / 128 MiB per graphic), without following original workstation paths or external URLs. Text retains Story member and character selectors; threaded frames do not imply composed text offsets per printed page. Shared groups and page proximity produce candidates, not historical-image approval. Matching returns every recognized identity and compiles only exact quoted substrings, followed by independent semantic review. No PDF parser, Marble generation or external historical search is used. A native handoff retains the source IDML, selected graphics, real photo observations, full matching results and source selectors.

Current evidence: full local import of the supplied 62-page IDML and 93 linked graphics succeeded with zero model calls; semantic matching is covered by deterministic counterparts, not a fresh full-material model acceptance.
