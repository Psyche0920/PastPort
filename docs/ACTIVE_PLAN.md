# Standalone PDF-to-VR implementation

Owner: wehan. Branch: `codex/pdf-to-vr-standalone`. Current user-approved delivery: runnable offline replay, followed by Codex SDK integration and a bounded real-material sample. Interface compatibility follows the main PRD, while behavior follows the existing demo. No complete main integration is claimed.

| Work | Owner | Dependencies | Deliverable and acceptance | Status |
|---|---|---|---|---|
| Specification/boundaries | wehan | Main PRD and demo rules | Fixed workflow, typed boundaries and explicit compatibility gaps | Specified; main counterpart/checkers not frozen here |
| Core/PDF/projection | wehan | Registered assets, Poppler for PDF | Bounded immutable inputs, positioned text, panorama transforms/seams | Implemented and isolated checks pass; full actual PDF exceeds input profile |
| Recognition/evidence services | wehan | Injected semantic ports | Stable identities, all-view records, bounded missed-target recheck, exact evidence/scope | Implemented with offline counterparts; fresh inference not evaluated |
| Durable editorial state | wehan | SQLite and exact project/media bindings | Human copy/position precedence, CAS, idempotency, edit audit, rerun protection | Implemented; isolated and API integration checks pass |
| Tour/replay workflow | wehan | Existing HTML export, explicitly supplied report; optional legacy DB | Data-only import, three fixed LangGraph stages, receipts and immutable local snapshots | Runnable; actual two-view material imported as 37 objects / 66 anchors |
| Automatic build entry | wehan | PDF, supported tour export, local Codex login, finite subscription grant | One command creates numbered VR and linked review without handwritten intermediate requests | Implemented; full fixed graph tested with semantic counterparts; native generated-PDF/Poppler path verified; whole real-material live run not performed |
| Browser upload and generation | wehan | Existing automatic build, local SDK login/Poppler | PDF + HTML/folder/ZIP upload, bounded background job, stage progress, fixed project VR/review links, preserved edits | Implemented; offline API and browser checks completed; no fresh live-model inference in this delivery |
| Linked VR/workbench | wehan | Tour and editorial state | Transparent numbered markers, click-to-read latest copy, workbench editing, drag-release autosave | Implemented; browser popup and drag-save checked; representative display checked |
| Standalone subscription semantic adapter | wehan | Local ChatGPT login, official Codex SDK and explicit finite grant | Existing semantic ports, image inputs, strict payloads, usage receipts, no API fallback | Implemented; SDK login/model/image capability and synthetic live image call verified; not main gateway integration |
| Second-site/main integration | wehan and affected main owners | Second materials, frozen shared schemas/checkers | Configuration-only reuse and compatible SDK export | Pending; replay does not prove these |

## Verification

- Twenty-five tests pass, covering content hashing, projection/seams/pixel sampling, distinct similar objects, cross-view IDs, missed-target recheck, omissions, bounded evidence expansion, exact quotes, background scope, human precedence, editorial conflicts, idempotency, changed media/assignment, replay and uncertain-dispatch stop.
- The synthetic full replay/API test imports a two-view HTML export, does not execute its script, preserves navigation and media, rejects arbitrary DB/media access and cross-origin edits, saves text/position, and reruns both the same and a new run ID without duplicate anchors or overwritten human values.
- Strict mypy, Ruff lint/format and whitespace checks are separate from live semantic acceptance. Main repository/SDK checkers are absent and cannot be reported as passing.
- Actual offline material uses the existing tour/report and read-only legacy database. Source quotations are verified against legacy normalized page text; no new PDF/image semantic judgment is claimed. The chair's removed historical assignment stays removed. Source media and runtime databases remain ignored, outside tracked deliverables.
- Browser inspection confirms numbered popup text, links to the corresponding review object, and drag-release save confirmation. Browser interaction checks do not establish that all 66 historical/position associations are correct.
- Earlier reader-only PDF checks covered the first two pages of the actual 62-page PDF. The original is 334,610,743 bytes and exceeds the default 64 MiB profile. The new build command permits an explicit --large-pdf 512 MiB profile; no complete run on that large original is claimed.

## Remaining limits and next action

1. The replay command remains explicit prior-result replay. The separate Codex SDK command now executes typed semantic requests, but the unified build command now composes whole-PDF/tour processing. Main metered gateway integration, OCR, arbitrary vendor import and complete live-material acceptance remain incomplete.
2. HTML schema 3/4 import and safe ZIP/folder packaging are supported; uploaded scripts, arbitrary vendor tours, IDML parsing, 3D processing and cloud hosting are not. Preview server is localhost-only and separate from the old 8793 demo.
3. Local immutable snapshots are not main-compatible museum bundles. Freeze the counterpart and validate the adapter before integration.
4. A second site's PDF/VR must be supplied and run before claiming cross-site reuse or accuracy.
5. Git delivery is limited to source, tests, configuration examples and documentation on the standalone branch. No main code, original demo data, credentials or media is included; no deployment is claimed. Remote push status is reported separately after verification.

## Codex execution evidence

- Official SDK 0.163.0 is an optional pinned dependency. Readiness used the local ChatGPT login and confirmed Sol 6.1 image capability without exposing account identifiers or credentials.
- A synthetic panel image returned a valid location and actual SDK usage. Its first request was rejected for schema incompatibility; the adapter now converts all object properties to explicitly required fields. The failed dispatch record remains unresolved, not silently retried or reset.
- Five additional isolated tests cover immutable grant/cap enforcement, cache reuse, uncertain-dispatch blocking, recorded-token threshold, strict nested schemas and project/image bindings. These transport doubles do not prove live model accuracy.
- The user subsequently authorized a small real-panorama sample. Its results are stored separately; existing human copy and coordinates remain authoritative and are not replaced by sample outputs.

### Bounded real sample and stop

Two real panorama inspection requests completed using Sol 6.1 and a single two-call grant. They supplied the existing identities for laptop 01, illuminated column 24 and horizontal window 29, without prior coordinates. Both returned schema-valid coordinates (six located proposals), with 37,363 SDK-reported tokens total. The user then requested stopping after one and inspecting its output; no further calls were dispatched. These are candidate files, not edits to the review DB.

Visual inspection of the first panorama overlay places its three regions on the intended visible features. The second panorama's column proposal appears on another column across the wood-room block, so physical-identity correctness is not established by schema/coordinate validity. It must remain unapplied pending focused identity review. No accuracy percentage, complete fresh PDF evidence run or full-site success is claimed. The existing VR and human overrides are unchanged.

## Final automatic entry acceptance

The unified `build --pdf --tour --grant --workspace --run-id --serve` command composes ingest, overview/detail recognition with bounded missed-target review, page/object mapping, independently scoped evidence, copy composition, editable preview and immutable snapshot stages. The user no longer needs to author semantic request JSON. Mapping modes explicitly separate same-site identity from campus demonstration substitutes. Missing evidence and budget limits produce visible gaps.

The complete graph test uses explicit PDF-reader and semantic fixtures. A separate verification exercised actual generated-PDF extraction and Poppler, data-only tour import, the complete graph, source crop/full-page media and review API with semantic fixtures. Both the same and new run ID retain human copy/position without duplicate inference. This does not establish correctness of an entire live model-backed build. Final delivery remains standalone, not integrated into main or cloud-deployed.


## Browser generation delivery

The user requested nontechnical upload/generate operation in the same workbench. The accepted conservative browser defaults are now 20 calls / 250,000 recorded tokens, applied consistently to HTML and submission-model defaults. Existing grants are immutable and unchanged. This does not guarantee completing a large source corpus; budget gaps remain explicit. The new `studio` entry starts an empty-project portal, accepts PDF plus supported 360 HTML/folder/ZIP, creates finite per-run subscription grants after explicit UI authorization, launches the existing fixed workflow in one owned subprocess, and reads persisted stage receipts for progress. Finished projects expose stable linked review and VR routes. Existing project rebuilds retain applicable human overrides. Restart/interruption never automatically redispatches uncertain calls.

Source format inspection found PDF, IDML, INDD and Links JPG/JPEG in the official II. Murat Drive folder. Only PDF and supported 360 exports are enabled today. IDML/Links and 3D remain visibly reserved capabilities; INDD requires conversion. Main integration, IDML extraction, surface-anchor geometry and cloud authentication remain separate pending work.

Acceptance evidence: isolated upload/job/API checks with fake semantic transport; browser file chooser, submit/progress/completion, generated numbered popup and evidence-editor navigation on a separate offline fixture server. Full real-material live inference was deliberately not rerun. Check counts and remote delivery are recorded after completion, without changing the original demo data.

## Scope rejection and authorized recovery — 2026-10-24

Owner: wehan. Dependencies: immutable model receipts, source selectors and the original finite
grant. Deliverable: isolate semantic claim/association rejections, preserve usable evidence, and
resume the diagnosed evidence failure without repeating completed inference or resetting usage.
Acceptance: missing-parent background remains excluded with a diagnostic; valid claims survive;
explicit recovery is input-bound and audited; uncertain dispatch remains blocked.

Implemented and verified locally. The actual Ulucamii run resumed its evidence stage, completed
publish/export, and produced 14 scene objects / 21 anchors. Three unsupported parent-background
claims for the minbar balustrade remain explicit gaps. All 23 original model receipt rows stayed
byte-for-byte unchanged; no new model calls were issued (634,536 recorded tokens remain).
This is a completed-with-gaps build, not confirmation that all source objects are mapped or that
all semantic/position proposals are correct. Three historical assignments were selected; the
other scene objects remain unbound. Parent discovery is not invented or silently repaired.

Evidence: 33 behavioral tests, strict mypy over 63 source/test files, Ruff lint/format and whitespace
checks pass. Existing local job, review, VR, summary and snapshot endpoints return successfully.
The main repository checker is absent. Changes remain local until a separate commit/push;
second-site accuracy and main integration remain pending.
