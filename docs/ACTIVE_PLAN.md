# Matched PDF + new VR delivery

Owner: wehan. Branch: `codex/vr-animation-workflow` (based on `codex/pdf-to-vr-standalone`).

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
