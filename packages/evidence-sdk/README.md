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
