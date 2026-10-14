# PastPort · 最后两袋 / The Last Two Sacks

A photographic, online narrative prototype set in the Muradiye complex in Bursa. The player is a fictional probationary clerk whose own cargo classification has put his guarantor under suspicion. Five scenes combine real heritage photographs with clearly labeled fictional case documents, consequential choices, witness collection and ledger reconciliation.

## Run

```bash
python3 -m http.server 8000 --bind 127.0.0.1
```

Open `http://127.0.0.1:8000/prototype/`. The current desktop preview uses port 8765.

## Content and modules

- `data/muradiye.json`: sourced heritage catalogue; 18 works and 16 fact/fiction claims.
- `data/muradiye-story.json`: versioned playable chapter, cast, five scenes, photographic hotspots, evidence and three major decisions.
- `data/task-overrides.json`: published editorial task overrides take priority; runtime AI task generation remains unconnected.
- `data/pastport.sqlite3`: relational catalogue plus the exact narrative content/hash and photo provenance.
- `data/media_manifest.csv`, `data/drive_file_ids.csv`: 93 original Drive photographs with review states and stable IDs. The game additionally uses five locally extracted publication photographs with confirmed page/structure associations.
- `prototype/engine.mjs`: deterministic task gates, evidence, irrevocable choices, story time and outcome rules.
- `prototype/app.js`, `style.css`: photographic UI, notebook, sorting, evidence board, source views, site map and searchable original photo archive.
- `sources/`: reference PDFs retained without edits; all game props and dialogue are original fiction.
- `docs/`: story logic, content workflow, spatial limits and evaluation evidence.

The main viewpoint stays fixed through a playthrough. Helping or detaining the apprentice changes later dialogue and relationship consequences. Helping the witness changes which evidence is available and whether the apprentice can be immediately cleared. Keeping, replacing or blaming the ledger changes the protagonist's career and service consequences. Story time is simulated, never a real-time countdown. Progress persists locally in the same browser origin.

## Build and verify

```bash
python3 scripts/build_database.py --replace
python3 -m unittest discover -s tests -v
node --test tests/test_story_engine.mjs
```

The database builder imports the same narrative JSON used by the browser and validates historical references, local photo files, relational integrity and candidate-task priority. To re-export the five approved photographs from the inventory PDF, run `python3 scripts/extract_scene_photos.py` (PyMuPDF and Pillow required).

## Scope

This is the Muradiye pilot, not the complete Bursa archive. The five local photographs are contemporary views, not a visual reconstruction of the 1430s. Glass covers, restaurant signs and furnishings are not accepted as period clues. Fictional receipts, quantities and witness accounts are not historical documents. GPS, 3D, runtime LLM generation and an authenticated administration UI remain separate future integrations. Human-player engagement has not been validated by a playtest yet.

## Source PDF storage

The 319 MB high-resolution inventory PDF remains local under `sources/inventory/` and is excluded from Git. Its source link, size and SHA-256 are recorded in `sources/inventory/source-manifest.json`. The five scene JPEGs are included, so a fresh checkout can run the complete game without the PDF. Download the publication from the recorded organizer archive if you need page-level local references or photograph re-export.
