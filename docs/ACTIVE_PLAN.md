# Matched PDF + new VR delivery

Owner: wehan. Branch: `codex/pdf-to-vr-standalone`.

| Work | Dependencies | Deliverable / acceptance | Status |
|---|---|---|---|
| Single-workflow cleanup | Existing matched-PDF generation, metered SDK, reference review/VR runtime | Remove photo-to-PDF, raw-history matching and replay entrypoints and exclusive implementations; preserve upload, budget, source provenance, isolated saves, edits and recovery | Implemented; no automated tests, model calls or service launch in this cleanup, as requested by the user. Manual runtime/output acceptance belongs to the user |
| Generation automation | Matched PDF, fresh schema 4 static tour, Poppler and local SDK login | Browser upload reaches fresh localization, structural review and demonstrated review/VR output | Previously integrated; cleanup retains this chain. Prior checks and real-run evidence are recorded in CHANGELOG and do not validate the cleaned version |

Existing source files, runtime databases, prior jobs and the user's saved Git stash
are not deleted. Jobs from removed workflows are hidden without rewriting their data.
Different inputs must be localized again; old coordinates are not business defaults.
The user reports targeted manual findings for subsequent fixes. No other workflow,
main integration, 360 video, arbitrary vendor adapter or cloud deployment is included.

## Optional 3D stage

Owner: wehan. Branch: `codex/pdf-to-3d-standalone`. Dependencies: an existing matched
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
