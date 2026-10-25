# Matched PDF + new VR delivery

Owner: wehan. Branch: `codex/environment-stylization` (based on `codex/pdf-to-vr-standalone`).

| Work | Dependencies | Deliverable / acceptance | Status |
|---|---|---|---|
| Single-workflow cleanup | Existing matched-PDF generation, metered SDK, reference review/VR runtime | Remove photo-to-PDF, raw-history matching and replay entrypoints and exclusive implementations; preserve upload, budget, source provenance, isolated saves, edits and recovery | Implemented; no automated tests, model calls or service launch in this cleanup, as requested by the user. Manual runtime/output acceptance belongs to the user |
| Generation automation | Matched PDF, fresh schema 4 static tour, Poppler and local SDK login | Browser upload reaches fresh localization, structural review and demonstrated review/VR output | Previously integrated; cleanup retains this chain. Prior checks and real-run evidence are recorded in CHANGELOG and do not validate the cleaned version |

Existing source files, runtime databases, prior jobs and the user's saved Git stash
are not deleted. Jobs from removed workflows are hidden without rewriting their data.
Different inputs must be localized again; old coordinates are not business defaults.
The user reports targeted manual findings for subsequent fixes. No other workflow,
main integration, 360 video, arbitrary vendor adapter or cloud deployment is included.

## Animation workflow

Owner: wehan. Dependencies: labelled reference museum, existing generated panoramas
or an explicitly authorized finite Codex subscription grant, pinned style reference.
Deliverable: isolated animated museum/ZIP with retained evidence, edits, object and
viewpoint bindings; callable LangGraph node and self-contained Skill.

Status: implementation and real two-viewpoint existing-image graph execution complete;
zero new inference in that graph run. A prior bounded one-viewpoint SDK image probe
also completed. User performs all output acceptance manually. No new Studio animation
upload page, Story Agent integration, public deployment or device acceptance claimed.
Next: user manual feedback; later parent-graph wiring uses `AnimationNode` and
`AnimationDelivery` without changing the museum identities or source evidence.
## Optional 3D stage

Owner: wehan. Branch: `codex/matched-environment`. Dependencies: an existing matched
environment and either an existing Marble export or later explicit local-key/credit
authorization. Deliverable: preserve matches, freeze data, generate/import a world,
compute geometric candidates, manually calibrate and save into a 3D review result.

Status: implementation integrated; one unrelated real Marble export attached with
zero new inference. Added modules have local static checks. No paid generation,
browser/device or same-scene museum acceptance claimed. User supplies the key for
the final manual trial; current source images, VR behavior and saved databases are
preserved. See SCENE3D.md for startup, coordinate assumptions and recovery.

3D frontend follow-up: separate homepage VR/3D records, unify the duplicate 3D entry,
expose persisted task state and output downloads, and add an in-memory API-key dialog.
Owner: wehan; dependencies: existing portal/runtime. Acceptance: user can configure
the key and obtain the 3D output from the frontend; real generation remains pending
explicit user trial. No paid call or automated provider retry is part of this change.

Frontend refinement: each completed VR record owns its “Generate 3D” entry, source
IDs are automatic, main form is project/key/generate only, existing-export import
is retained in a collapsed form, and 3D record cards show status and their output.
No generation is triggered by refresh, key entry or record listing.

Pre-payment follow-up: fixed source-backup parent creation and duplicate paid-job
creation on frontend reconnect. Ten network-disabled simulated-provider checks pass;
portable ZIP assets/IDs/null anchors checked. Faithful source-only request policy is
input-bound. Native SPZ, collision GLB and versioned JSON export is implemented; full
textured mesh and engine import acceptance are not claimed. No real key or credits used.

The user has now submitted one real Marble trial from the frontend. Its frozen
source and preservation-policy binding were confirmed. Only its existing saved
operation has been queried; no second generation was dispatched. The trial has now completed and its assets/result were saved. The settled cost is
1,500 credits (0 for panorama generation, 1,500 for world generation). The service
was not restarted while this operation/key session is active. Source-level ownership
protection is also enforced in the child workflow, so stale frontend code cannot
bypass the one-source/one-generation guard. Three committed offline regressions pass.

Viewer follow-up: fixed the missing pinned Three.js Pass dependency and its import-map
and static-route registration. The existing generated result was repaired in place
without touching scene bytes or review data. Browser rendering and camera movement
were observed after restarting only the owned preview child; no new generation.
Hotspot alignment, object fidelity and user/game acceptance remain pending.

Matched-output correction: the earlier result had 14 source hotspots but zero 3D
anchors and therefore did not fulfill the requested mounted-output behavior. The
viewer now automatically computes/persists ray-derived candidates, displays numbers,
reads original effective content and deep-links to the same review object. Current
result: 14/14 proposals hit collider surfaces; confirmed spatial acceptance remains
zero. Browser checks verified visible labels, object 35 popup and review identity.
Two targeted regressions pass. User manual spatial/identity review remains required;
this is a mounted candidate output, not a claim of verified precise 3D matching.

Review editing follow-up: shared introduction editing and same-object 3D review links are implemented. Dragging a 3D marker saves its independent position; panorama coordinates remain unchanged. Applied to the existing derived result. User requested no further automated verification and will manually accept behavior. No generation or paid calls.

Second-view generation: source panorama verified at 4096 × 2048 (1,371,493 bytes). Added source-order viewpoint selection and per-view durable job ownership; existing per-image submission ledger remains unchanged. Second paid generation not dispatched. Running Studio needs restart to load the endpoint change; session key must be entered in the UI after restart. User manual validation pending.

Navigation editor — owner: wehan; dependency: existing matched panorama links. Implemented arrow dragging with automatic position saves, target-view orientation preview/save, source/destination identity binding, SQLite version checks and idempotent retries. Deliverable: existing panorama editor. User manual acceptance pending; no paid calls or 3D stitching.

## Separate 3D viewpoint navigation (current)

Owner: wehan. User stopped composition and restored the pre-composition separate-view
version; that experiment is retained in a recoverable Git stash, not active code.
Deliverable: a player approaching a projected navigation arrow changes to the next
independent 3D result, using saved VR entry yaw/pitch. No world blending or generation.

Implemented: original source navigation lookup, completed same-project target lookup,
loopback-owned preview CORS, typed bounded arrival parameters, transparent arrows,
proximity/click transitions, spawn cooldown and exit-zone arming, editing guards.
Source panorama position and saved introductions remain unchanged.
Evidence: strict typing on three affected Python files, JS syntax and diff checks;
read-only real-data route calls found one transition in each direction and preserved
both saved entry angles. Both original SPZ hashes still match generation manifests.
No model calls, source review edits or service startup. Browser movement/trigger/
placement acceptance is pending user manual testing after Studio restart.

Arrow independence correction: VR is an initialization reference only. The 3D
result persists its own navigation seed, projected position and subsequent manual
drag edits with binding/version/idempotency checks. VR edits do not overwrite the
3D arrow after initialization, and 3D drags do not write VR. Temporary-data checks
cover seed independence, restart persistence, operation replay and stale writes;
strict typing and JS syntax pass. Browser dragging remains for user acceptance.

Viewer delivery follow-up: found a new-HTML/old-preview mismatch: the active result
returned 404 for the new arrow endpoint. Seeded each existing result from its saved
VR navigation and recycled only the two owned result preview children; the user
Studio and key session were retained. Both arrow endpoints now return 200. Chrome
verified point 1 → point 2 and point 2 → point 1 through the visible navigation
control, preserving the corresponding saved arrival angles. Proximity walking is
not claimed as browser-verified by this check.

User-requested UI cleanup: primary view now shows only scene/title/fullscreen and
start-view/switch-view/edit actions; all technical calibration is under Advanced
in the hidden edit drawer. Shared introductions and position saves are preserved.
An offscreen direction hint explains where the navigation arrow is. No model or
review content changes, and no generation.

Plane-trigger correction: the user requires an unbounded vertical cross-section
through the arrow, not point proximity. The trigger now uses signed X/Z plane
crossing with hysteresis, no altitude/radius bounds, and resets automatically
when the user drags the arrow. Closing the edit drawer disables position-edit
checkboxes and restores navigation. Deterministic checks cover high/low paths,
full width, slow crossings, editing suppression and a moved arrow. Found/fixed
an introduced asset 404 by serving the pure boundary helper through the existing
root JS route; both active preview URLs return 200 without restarting Studio.
The browser page was reloaded to the new assets; real proximity walking remains
user manual acceptance, not inferred from these checks.

Browser walking follow-up: actual held-W movement crossed the saved point-2 arrow plane and opened point 1 with its saved entry angles. Low rendering frame rate exposed a 50 ms movement-delta cap, slowing travel substantially; raised the bounded delta to 250 ms and reset timing/keys on visibility changes. Full module import-chain cache versions are updated for existing result pages. After the timing/cache fix, actual held-key walking passed point 1 to point 2 and point 2 to point 1, preserving both saved arrival angles. Existing manual arrow coordinates and model files were not changed. User acceptance remains pending.

Source-ordered delivery follow-up — owner: wehan; dependencies: completed source VR and per-view 3D outputs. Deliverable: original VR point numbers in records, a single full-tour card with completion count, playback and portable multi-world ZIP. All source views must be complete before download; reuse existing assets and saved arrow snapshots, no generation. Strict typing on three affected Python files, Ruff, JS syntax and diff checks passed. Read-only delivery-route calls verified the existing outputs are points 1/2 of 2 in original VR order. A temporary real-asset export retained both scenes and saved navigation (856,295,544 bytes). Browser acceptance pending; live Studio requires restart to load the added endpoint.

Site grouping refinement: group the full-tour card and source-ordered viewpoint records under their corresponding VR result title and job identity; different sites/results never share a module. Existing per-view operations and package links remain available. No generation or service restart.
Display refinement: hide legacy imported-match count suffixes in VR/3D headings and selectors without changing stored names or bindings. Ready 3D cards omit redundant success descriptions; error/recovery messages remain visible.

## User-approved minimum acceptance baseline

Decision: the current Muradiye two-view independent 3D demo is the minimum
comparison baseline until the user explicitly adopts a more satisfactory demo.
Reference: delivered code at 3416840 and existing result runs
26e3d8a44e30430f87af2a3eb2a9652e / e696a8f8b790058b88198bf6ac7acd92.

Acceptance priorities: correct object/evidence matching; generated 3D must remain
faithful to the source 360 panoramas in object identity, layout and appearance.
Future deliveries must meet or improve this baseline, not regress. Existing blur,
invented details and known errors are defects to improve, not approved accuracy.
No numerical accuracy rate or universal input success is established by this decision.
A future user-approved demo may replace the baseline. Automatic generation/display
does not constitute human acceptance. Use new material and targeted reported bugs
for further validation rather than repeatedly rerunning this same sample.

## VR and 3D environment stylization (in progress)

Owner: style-transfer chat. Branch: `codex/environment-stylization`.
The original panorama animation path is retained. Existing 3D viewer, anchors and
independent viewpoint navigation are integrated from `codex/matched-environment`.
Initial source-bound SPZ v2 appearance baking, immutable source snapshots, typed
LangGraph/CLI entry and render/export hooks are implemented but not delivered.
Automatic alignment proceeds without a human gate, explicitly marked as estimated.
No geometry correction is claimed. Whole-tour package handling and the two-view
candidate remain unfinished. Five new Python modules pass strict typing; earlier
format errors were reformatted but the final integrated static checks are pending.
No automated runtime tests, new inference, paid calls, service restart or final
quality acceptance. User performs runtime/visual acceptance.
Dependency first: matching-environment owner must restore one shared object/content
authority across independent 3D viewpoints; per-view spatial edits remain independent.
Current code is checkpointed so that owner can work in the shared original checkout.
Next: consume the shared-content contract, finish whole-tour input/output, then
produce one isolated complete candidate without replacing the approved baseline.
## Shared content repair before stylization

Owner: wehan. Branch: codex/matched-environment. Dependency: original source VR
result is content authority; per-view spatial stores remain separate. Deliverable:
shared review/evidence/introduction reads and versioned writes across VR and 3D;
input/stable identity isolation, preservation of linear legacy edits and explicit
blocking of divergent histories; current shared semantics in portable exports.
Implemented with source bindings, authority-backed services, cross-port revision
polling and current packaged viewer bridges for existing results. Ten targeted
offline checks passed; eight changed Python/test files passed strict typing.
Final browser behavior, real legacy migration and human acceptance remain pending
user tests. No provider call, regenerated asset or service restart. Stylization
can integrate this fixed contract after the repair commit; conflicts must not be
resolved silently.

Legacy two-view preview repair (2026-10-25): the original ports 50194 and 50215
were still serving isolated copies. Both existing results are now bound to the
same source content authority; linear human edits and audit history were merged
with the existing conflict-checking service, and both previews were restarted
on their original ports. Object 86 version 2 matches exactly through all four
VR/3D content endpoints, including the user edit; the point-2 review page also
shows that human version. Five shared-content unittest checks passed. No
geometry, spatial state, generated assets or source evidence was changed.

### Whole-tour 3D appearance candidate delivery

Shared content fix 0b52cd5 is integrated. The actual two-view Muradiye source tour
was exported and processed as one archive with both existing 4096x2048 animation
maps. Output: `.runtime/style3d-acceptance-01/candidate/styled-tour.zip`, plus
`delivery.json`, one isolated shared review authority and two registered styled
SPZ assets. Zero new model calls. Automatic camera estimates continue without
human gates and retain their unconfirmed status. Original assets/data/workbench
were not replaced or restarted. The owned loopback preview was started for user
acceptance; no automated browser/runtime tests were run. Typed graph and complete
tour CLI route exist; no Studio stylization-upload page is claimed. Structural
repair, far-view geometry correction and visual acceptance remain unfinished.
Next: user manual feedback on this candidate, then targeted repairs; do not call
the full user objective complete or replace the approved minimum baseline.

### Automatic upload and optional budgets

Owner: style-transfer chat. Dependency: current native VR/3D contracts, pinned style,
local Codex subscription adapter and shared semantic authority. Deliverable: upload,
format preflight, full-tour estimate, optional manual budgets, explicit run consent,
metered artwork generation and isolated corresponding VR/3D ZIP. Implemented in the
stylization portal and automatic orchestration. Blank budgets use displayed finite
suggestions; resume retains the original grant/ledger. No new model call performed.
Acceptance: user manually starts a supported package and reviews the output. Fresh
upload-to-generation runtime, universal format adapters and structural repair remain
unverified or unfinished; no claim of complete target acceptance. Existing two-view
appearance candidate and source assets are retained.

### Staff workspace and embedded preview

Owner: style-transfer chat. Dependency: existing saved stylization records and trusted
preview services. Deliverable: project-consistent styling/navigation, a preview window
inside the stylization page, viewpoint switching/fullscreen/download, and plain-language
staff task states. The long-term product remains one website with module routes;
standalone loopback launch is a development entry, not a separate product site.
Uses the shared Studio stylesheet and retains generation authorization and optional
budget behavior. Only UI/preview changes; no new model calls or asset generation.
Acceptance: user checks the staff workflow, preview controls and visual consistency.

### High-detail candidate after user rejection

Owner: style-transfer chat. The user rejected current sharpness and set
`demo-muradiye-ui-trial` (6e65a44) as the minimum visual-detail/style reference.
The user then approved a newly rendered front view and authorized quality-first
complete generation without another budget discussion. One built-in reference
render is saved at `.runtime/style3d-hd-01/approved-front.png`; reference-only work
does not prove a complete panorama or 3D result. A separate two-view candidate is
running through the existing metered SDK route, maximum 12 directional calls,
no automatic retry/variants, original inputs preserved.

Added an opt-in projective-surface appearance mode to retain panorama texture detail
on the existing collider geometry instead of only changing Gaussian DC colors.
This does not reconstruct geometry or unseen surfaces. Shared style references and
physical invariants constrain cross-view distant scenery; consistency, projection
alignment and walking artifacts still require user review. Four affected Python
modules pass strict typing and Ruff; viewer syntax passes. Acceptance: one complete
interactive two-view package with retained content/navigation, detail at least the
named reference, and no conflicting shared distant structures. Not yet accepted.

User scope correction: stop full-tour expansion and establish a single style sample.
The whole-tour worker was interrupted; its ledger retains four completed calls and
one recovery-required call. No reset or retry is authorized. A single built-in image
edit now preserves the accepted sharpness while moving to the user's uploaded
animation-background reference. Saved sample/provenance/prompt:
`material-workspace/work/style-transfer/hd-style-sample-02/`.
Native output is 1254x1254, not an inferred 2K/4K claim. Style feedback is pending;
complete panorama/3D sharpness and cross-view consistency remain unaccepted.

### Independent reference-guided stylization Agent

Owner: style-transfer chat. User approved viewpoint-two style sample for code
integration, then requested an independent Agent: plan and generate once, compare
against the actual reference, pass if satisfactory, repair only severe supported
problems, and permit at most one repair round. No new generation is authorized by
this implementation task. Deliverable: frozen v2 style/policy, typed Agent and
LangGraph node, shared metered execution, saved planning/review reports, bounded
one-repair branch, existing staff entry and upfront worst-case estimates. Legacy
jobs/grants/style snapshots remain unchanged; cache identity includes the new
profile so old-style results cannot impersonate the approved style.

Implemented; 13 affected Python files pass strict mypy and Ruff; viewer and staff
JavaScript syntax plus diff checks pass. No live Agent
run or automated runtime/visual test has been performed. Human output acceptance,
3D walking/geometry, projection quality and all non-adjacent view comparisons
remain unverified. Model review covers panorama imagery and adjacent view pairs.
New Agent jobs support at most six viewpoints within the existing 100-call grant.
Original incomplete quality-run usage remains retained and is not resumed/reset.

### Environment-grouped records and renamed-upload feedback

Owner: style-transfer chat. The user found three cards for one environment and
could not find a renamed identical ZIP. Records now group by immutable import
fingerprint and viewpoint identities, not ZIP name or archive bytes. Latest task
and latest completed preview remain accessible; earlier versions are expandable.
Identical uploads retain the same task/grant/usage but show the latest filename,
retained aliases and an explicit reuse message. Three existing versions were
identified as one environment and retained. No generation or semantic DB changes.
Three affected Python modules passed strict typing; Ruff, JS syntax and diff checks
passed. User checks the UI behavior manually; no automated runtime/model test.
