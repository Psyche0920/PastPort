# PastPort Evidence SDK

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
