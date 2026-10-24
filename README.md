# Photo-to-PDF and IDML

Generate a comparison **PDF** and editable **IDML** from a historical PDF and your multi-angle
photographs. Scene photographs represent historical objects; they are explicitly labelled
substitutes, not the actual artifacts. Owner: wehan.

This branch is an independent document tool. It does not include a review backend, VR viewer,
game, main-framework integration or downstream data API.

## 1. Install

Requirements: macOS or Linux, Python 3.12, [uv](https://docs.astral.sh/uv/), Poppler and a local
Codex ChatGPT login. On macOS, install Poppler with `brew install poppler`.

```sh
git clone --branch codex/pdf-evidence-review-prd --single-branch https://github.com/Psyche0920/PastPort.git
cd PastPort
uv sync --locked --extra codex
```

If you already have this repository, switch to this branch and run `uv sync` from its root.
If this computer is not already signed into Codex, run `codex login` first. The SDK uses the
operator's account; no account credentials are bundled or shared.

## 2. Set the run limits

```sh
cp grant.example.json my-grant.json
```

Edit `my-grant.json`:

- Set your own `project_id` and unique `grant_ref` for an independently authorized job.
- Default model: Sol 6.1 Medium (`gpt-6.1-sol`). No automatic model/provider fallback.
- The example permits 20 calls and 250,000 recorded tokens. Change these deliberately if needed.
- This is a finite execution grant, not an API key. Keep credentials out of it.

Generating documents uses your Codex subscription allowance. Installing the tool or opening
existing outputs does not invoke a model. Token limits stop subsequent calls; a running response
can exceed the threshold. A small budget can leave objects unassigned with explicit findings.

## 3. Generate

Place ordinary JPEG/PNG/WebP photographs in one folder, without unrelated files. Run:

```sh
uv run --locked --extra codex pastport-evidence \
  --pdf '/path/to/heritage.pdf' \
  --photos '/path/to/multi-angle-photos' \
  --workspace .runtime/my-project \
  --grant my-grant.json \
  --run-id first-build
```

The command reports stages and prints the final PDF/IDML paths. No web server needs to be started.
Input limits: 1–100 photos, 30 MiB each, 200 MiB total and 40 megapixels each. PDF defaults to
64 MiB and at most 500 pages. Add `--large-pdf` explicitly for a source up to 512 MiB. Native-text
pages are supported; pages without usable text are marked OCR-needed, not silently transcribed.

## 4. Open the result

Keep the entire completed export folder:

| File | Use |
| --- | --- |
| `mapping.pdf` | Numbered photo overview and adjacent historical image/description comparisons |
| `mapping.idml` | Editable text frames and separately linked pictures |
| `Links/` | Pictures required by IDML; do not move the IDML alone |
| `Document fonts/` | Licensed Chinese font and its license |
| `source.pdf` | Original registered PDF for source-page/context links |
| `READ_ME.txt` | Export notes |

The PDF and IDML are generated from the same layout. Exact original excerpts are separate from
Chinese generated descriptions. Missing sources and uncertain identities remain labelled.
Outputs are machine-generated drafts, not historical or publication-rights approval.

If upgrading from the earlier nested layout, keep the existing workspace and grant files.
Pass their original absolute paths to reuse those records; do not delete or recreate the runtime
just because the source code moved to the repository root.

## 5. Repeat or troubleshoot

- Reuse the same workspace/run ID only with identical inputs and settings. Completed inference
  is cached; repeat execution does not renumber established objects.
- For changed inputs, use a new run ID. Keep old runtime state and receipts.
- Completed exports are immutable. Modified/missing files are detected, not silently overwritten.
- An uncertain/interrupted model dispatch stops for reconciliation. Do not delete SQLite files
  or change a grant under the same ID to reset usage.
- Keep `.runtime/` and `my-grant.json` private. Internal records are not a downstream interface.
- Use `uv run --locked --extra codex pastport-evidence --help` for command options.

## Validation status

Offline acceptance exercised actual PDF extraction/Poppler, two photo appearances sharing one
ID, the complete graph, paired export, IDML image-link closure and repeat execution without
additional fixture dispatch. Semantic responses were explicit fixtures, not real inference.
Strict mypy and Ruff passed for the document tool. Full fresh real-material matching and native
Adobe InDesign opening/editing remain pending; valid XML alone does not prove native compatibility.

Requirements and matching rules: [technical PRD](docs/technical/PRD_PDF_EVIDENCE_REVIEW.md).
Current acceptance status: [active plan](docs/ACTIVE_PLAN.md).
