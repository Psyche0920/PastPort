# Photo-to-Document Automation

Owner: wehan. Dedicated module on `codex/pdf-evidence-review-prd`.
Specification: [Photo preparation PRD](../../docs/technical/PRD_PDF_EVIDENCE_REVIEW.md).

**Input:** one historical PDF and a folder of multi-angle ordinary photographs.
**Output:** a comparison PDF and editable IDML, with matching pictures, object numbers, descriptions
and source references. There is no review backend, VR command, server, or downstream data API.

## Install

Requires macOS or Linux, Python 3.12, [uv](https://docs.astral.sh/uv/), Poppler (`pdftoppm`) and an existing local
Codex ChatGPT login for real inference. On macOS install Poppler with `brew install poppler`.
Run from this module directory, not the repository root:

```sh
uv sync --locked --extra codex
codex login
cp grant.example.json my-grant.json
```

Login is unnecessary if already signed in locally. The SDK uses the operator's account; neither
credentials nor a developer's account is embedded. The explicit grant contains only a model and
finite limits. Edit its project and grant identities before each independent authorized job.

## Generate

This command uses your Codex subscription allowance:

```sh
uv run --locked --extra codex pastport-evidence \
  --pdf '/path/to/heritage.pdf' \
  --photos '/path/to/multi-angle-photos' \
  --workspace .runtime/my-project \
  --grant my-grant.json \
  --run-id first-build
```

Use `--large-pdf` explicitly for a source over 64 MiB (up to 512 MiB). Photographs are JPEG, PNG or
WebP. Keep the folder free of unrelated files. The command prints its stage transitions and final
PDF/IDML paths. It does not start a web server or invoke any VR software.

Keep the whole resulting export directory: `mapping.pdf`, `mapping.idml`, `Links/`,
`Document fonts/`, `source.pdf` and the short read-me. Moving the IDML alone breaks its relative
image links. `source.pdf` is the original registered source, supplied for page/context inspection.
The export is a machine-generated draft, not a rights or historical-accuracy approval.

Internal state and model receipts live in the ignored workspace; they are not an exported
structured handoff. Do not delete SQLite files to recover a job or reset usage. Identical successful
inputs/run IDs reuse completed stages; changed inputs require a new run ID. Interrupted uncertain
model dispatch requires operator reconciliation and is never silently retried. Output folders are
immutable; edits to an existing export are detected rather than overwritten.

The grant's token count is a stopping threshold for later calls, not a prepaid charge, exact
subscription percentage or hard ceiling on a running response. A small grant can finish with
unassigned objects and explicit coverage/budget findings rather than a fabricated complete mapping.

## Module ownership and purposes

| Path | Purpose |
| --- | --- |
| `domain/` | Immutable photo, historical evidence, matching and internal layout records |
| `ports/` | Asset, PDF, semantic execution and persistent identity boundaries |
| `application/photo_mapping.py` | Fixed photo registration, identification, matching, evidence and paired export |
| `application/preparation.py`, `evidence.py` | Candidate selection, exact passages and independent scope validation |
| `application/document_package.py` | Atomic complete export and integrity checks |
| `adapters/report_layout.py` | One paginated layout with adjacent images, introductions and provenance |
| `adapters/document_export.py` | PDF and editable text/image IDML renderers |
| `adapters/codex_*`, `execution.py` | Injected local subscription transport, immutable grants and usage receipts |
| `workflow/graph.py` | Fixed LangGraph stages and authoritative stage journal |
| `prompts/` | Versioned photo identity, historical matching and evidence rules |
| `fonts/` | Licensed Noto Sans SC font for portable Chinese rendering |

The bounded metered/photo/evidence components were extracted from the existing standalone work,
not from the manual demo database. No main application or shared schemas are changed. Main model
and resource gateway integration is not claimed. The original Game Environment Demo remains the
reference for visual/semantic behavior, not a preloaded source of inferred answers.

## Validation boundary

Native InDesign opening/editing and full fresh real-material matching must be reported separately
from static checks and offline PDF/XML inspection. Neither valid XML nor a rendered PDF alone
proves IDML native compatibility or real historical correctness. Current acceptance evidence and
remaining work are recorded in the repository active plan; no new live inference was launched
while splitting this module.

Offline acceptance exercised real PDF extraction/Poppler, two photo appearances sharing one ID,
the complete fixed graph, PDF/IDML generation, all image links and repeat execution without
additional fixture dispatch. Semantic responses were explicit fixtures, not model inference.
Strict mypy (41 Python files), Ruff and the installed command entry passed. The repository-wide
checker remains failing on its existing explicit-HTML-anchor limitation; it is not reported green.
The final real-material model run and InDesign native open/edit check remain pending.
