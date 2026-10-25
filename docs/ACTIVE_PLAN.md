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
