# Photo-to-PDF and IDML Preparation — Technical PRD

Owner: wehan. Scope revision: 2026-10-24, confirmed in the product discussion.
Branch: `codex/pdf-evidence-review-prd`. Implementation: repository-root `src/pastport_evidence`.
This revision supersedes the earlier review-workbench and structured-handoff scope in this file.

## 1. Product outcome and boundary

Input: one heritage source PDF and a folder of ordinary multi-angle photographs of demonstration
substitutes. Output: a comparison PDF and editable IDML, containing the same selected pictures,
object numbers, descriptions and source references. The documents stand on their own.

The original manually assisted Game Environment Demo mapping PDF is the behavioral reference.
The official source's PDF/IDML is a reference for adjacent pictures and descriptions, not a mandate
to reproduce the whole original publication or import its unrelated content and metadata.

Do not build an evidence-review backend, VR recognition/viewer/hotspots, a game, a structured
handoff API or a downstream consumer in this phase. Next-stage software treats the generated PDF
as an ordinary source PDF. Internal inventories, immutable assets, SQLite ledgers and checkpoints
exist only to run safely and resume; they are not a downstream product contract.

## 2. User-visible content

1. Ordinary photographs are primary; a crop must be traceable to its whole photograph and view.
2. Assign one persistent object number across all appearances of the same physical object.
   Similar-looking but distinct doors, columns, trees and equipment remain distinct.
3. Display a historical counterpart image beside the proxy, or explicitly state that it is absent.
   A context photograph or a text screenshot must not pretend to depict a specific unseen artifact.
4. Put the relevant historical introduction beside those images. The proxy does not acquire the
   historical object's identity or history.
5. Show exact original excerpts separately from generated Chinese paraphrases. Preserve the
   cited PDF page and a way to open the original source and inspect surrounding context.
6. Prefer the related image/text unit on the same page. Cross-page background is an exception
   that identifies its own page and applicability. Never infer semantic identity from adjacency alone.
7. Preserve useful original text; long text continues onto another page rather than silently being
   cut off or reduced to illegibly small text. Page count is content-dependent, not fixed at 52.
8. PDF and IDML share one layout. IDML retains editable text frames and independently linked
   images. Deliver required `Links`, licensed document fonts and `source.pdf` alongside it.
9. Machine-generated output is a draft, not human approval or permission for public redistribution.

## 3. Matching and evidence rules from the demo

- First establish physical-object identities from distinctive features and different views, then
  choose historical subjects. Categories or labels alone cannot authorize an identity merge.
- Prefer documented functions, users, activities and events that can support narrative material;
  visual resemblance helps choose an understandable substitute. Do not invent a story to justify it.
- Preserve reasonable accepted imaginative proxies. Do not turn the rejected chair-to-whole-room
  proposal into a blanket ban on category differences. A whole room must not accidentally be
  described as the chair's own identity or experience.
- A multi-object photograph can contain separate or overlapping whole/part regions.
- Give uncertain or missed matches bounded focused re-examination within the original grant;
  record coverage and remaining uncertainty. Unconfirmed is not proof an object is absent.
- No forced assignment or invented numeric confidence. Some targets remain unassigned.
- Keep direct facts, parent background and general historical context separate. Building dimensions
  do not become wall dimensions; a restoration date does not date each present stone; bowl recesses
  are not movable bowls. Parent background requires an identified parent.
- Every accepted quote resolves to exact Unicode character offsets in the registered page text.
  A generated translation/paraphrase is not an original quotation.
- Reject an invalid claim with its diagnostic while retaining valid independent claims. Do not let
  one missing parent relationship erase the entire batch, invent a parent, or mislabel unsupported prose.

## 4. Fixed automated workflow

| Stage | Work | Execution |
| --- | --- | --- |
| Register | Validate PDF/photo bytes; immutable hashes; EXIF orientation; bounded images | Deterministic |
| Photo inventory | Identify several objects per photo; resolve cross-view IDs; focused uncertainty pass | Bounded model calls plus identity validation |
| Historical matching | Render PDF pages; provide target crop reference sheets; propose image/subject links | Model calls, explicit supplied evidence only |
| Evidence | Retrieve exact same-page clauses first and supported wider context; classify scope | Text extraction/search plus bounded model assessment |
| Document layout | Target/source image comparison; introduction, original excerpts, locators and limitations | Deterministic shared layout |
| Export | Stage PDF, IDML, images, fonts and source; check closure; atomically complete | Deterministic |

Use LangGraph for fixed order and durable stage receipts. The graph does not grant a model freedom
to skip stages, change the budget, overwrite identities or invoke outside tools.
Default semantic configuration is Sol 6.1 Medium through the running operator's existing Codex
ChatGPT login. Keep the transport injectable and metered. No implicit provider/model fallback.
No live subscription calls are authorized merely by installing or viewing this code.

## 5. Independent architecture

The independent module has typed immutable domain records, asset/PDF/semantic/identity ports,
application preparation services, and I/O adapters. SDKs, PDF renderers and SQLite stay outside
the domain. Reuse the existing isolated metered transport, exact-evidence logic and photo work;
do not import the legacy demo database or silently seed fixtures as inferred results.

This branch is a standalone tool and will not integrate into main. Main framework/game/VR code
and unrelated documentation are not part of this source tree. There is no public museum schema
or structured handoff. Downstream software treats the PDF as an ordinary source document.
Changes on this branch do not change the main branch or the separate VR implementation.

## 6. Operational invariants

- PDF: 64 MiB by default; explicit large profile up to 512 MiB, at most 500 pages.
- Photos: 1–100 JPEG/PNG/WebP files, at most 30 MiB each, 200 MiB total, 40 megapixels each.
- Reject symlinks, unsupported content, duplicate photo bytes and mutable input mismatches.
- Render model images within finite byte/dimension limits. Call and recorded-token ceilings belong
  to an explicit immutable subscription grant. Token thresholds stop subsequent dispatch; they are
  not a guaranteed upper bound on the final in-flight response or a subscription-percent conversion.
- Keep IDs and completed model receipts on repeats. Same run ID with changed input is a conflict.
- Uncertain model dispatch is blocked pending reconciliation; never infer zero usage or reset ledgers.
- Missing native text is explicitly OCR-needed; no OCR or historical facts are fabricated.
- New exports use immutable fingerprinted directories. A failed PDF/IDML render cannot expose a
  half-completed pair. A modified completed output is detected and not silently overwritten.
- Do not alter the running original demo, its human edits or the separate VR branch.

## 7. Acceptance and reporting

| Check | Required observation |
| --- | --- |
| Input integrity | Originals unchanged; byte identity, bounds and unsafe inputs handled explicitly |
| Cross-view identity | Same physical object keeps its number; uncertain correspondence stays labelled |
| Semantic support | Supported counterpart image and applicable text; exact excerpt/page resolve |
| Scope isolation | Parent/whole-building claims cannot silently appear as component facts |
| No forced fill | Unassigned targets and exhausted-budget/coverage findings remain visible |
| Document parity | Both formats use the same layout, text, image content and object numbers |
| Portability | IDML image links resolve within the delivered folder; fonts/source context supplied |
| Atomic output | Only the complete PDF/IDML pair is announced; prior export is preserved |
| Repeatability | Same completed input/run does not redispatch cached inference or renumber objects |
| Reuse | Another site's real sample must run before claiming cross-site semantic acceptance |

Report separately: static checks, offline document rendering/inspection, real-model semantic runs,
Adobe InDesign opening/editing, and human acceptance. XML/ZIP validation alone does not prove that
InDesign opens the document or that its typography matches the PDF. A synthetic run does not prove
real historical matching quality. Do not label implementation complete if those limits are hidden.

## 8. Source ownership and purpose

| Path | Responsibility |
| --- | --- |
| `src/pastport_evidence/domain/` | Immutable photo, identity, evidence and private layout records |
| `src/pastport_evidence/ports/` | Asset, PDF, semantic and identity contracts |
| `src/pastport_evidence/application/` | Fixed preparation, exact-source/scope checks and atomic export |
| `src/pastport_evidence/adapters/` | Assets, PDF extraction, metered Codex, SQLite, layout and renderers |
| `src/pastport_evidence/workflow/` | Fixed LangGraph order and durable stage receipts |
| `src/pastport_evidence/prompts/` | Versioned identity, mapping and evidence rules |
| `src/pastport_evidence/fonts/` | Licensed Chinese font and provenance |
| `src/pastport_evidence/cli.py` | Input/grant handling and document-generation entrypoint |
| `tools/check_repository.py` | Independent source syntax, boundary and documentation-link checks |
