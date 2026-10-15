# Photographic narrative runtime

- `data/muradiye.json`: site catalogue, historical claims, sources and raw Drive index references.
- `data/muradiye-story.json`: a complete versioned chapter consumed by both the browser and database builder.
- `data/task-overrides.json`: published editor task overrides; only reviewed overrides bound to the same scene facts may replace default tasks. Narrative transitions, costs and outcomes remain controlled by the chapter.
- `prototype/assets/`: five local JPEG derivatives of the supplied inventory publication, retaining complete framing and recording the PDF page and image index. These are not generated images or undocumented Drive file matches.
- `prototype/engine.mjs`: deterministic task gates, evidence collection, immutable choices, simulated time, branch consequences and session snapshots.
- `prototype/app.js`: photographic observation, accessibility region buttons, document/ledger actions, notebook, evidence board and responsive presentation.
- `scripts/story_import.py`: validates approved facts, existing sources and local photographs; imports the same chapter bytes, hash, derivative provenance and scene bindings into SQLite.
- `scripts/extract_scene_photos.py`: repeatable photograph extraction. Requires PyMuPDF and Pillow; run only when the source publication and approved image selections change.

## Verification

Run `python3 -m unittest discover -s tests -v` and `node --test tests/test_story_engine.mjs`. The latter verifies locked scenes, irreversible decisions, false modern clues, photograph-gated ledger tasks, witness-dependent outcomes, service consequences and save/resume.

## Editor task override example

An override must have `scene_id`, `state: "published"`, `approved_by`, approved `claim_ids` and a `task` with the same kind as the default. Observation tasks declare normalized x/y coordinates, required hotspot IDs, visible labels, observation text and per-hotspot `claim_id`. Draft overrides are ignored. The photo, evidence truth, narrative costs and choice results cannot be overridden through this file.

## Deployment boundaries

This remains an online local prototype. No GPS, LLM, authenticated administration or 3D service is connected. Publication image source records are separate from the 93 original Drive entries; rendering a publication photograph does not verify an unrelated raw photograph. A future backend should deliver the same versioned chapter contract and replace localStorage with authenticated session storage.
