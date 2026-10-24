# Game Environment Demo

The three original PastPort reference demos, preserved together with their working data. Owner: wehan.

## Run locally

Requires Python 3.12 or later. No third-party packages or model credentials are needed.

```sh
git clone --branch Game-Environment-Demo --single-branch https://github.com/Psyche0920/PastPort.git
cd PastPort
python3 start_demo.py
```

Open http://127.0.0.1:8793/demo.html for all three entry points:

- [Mapping PDF](mapping-demo.pdf): the original 52-page Chinese comparison PDF.
- [Review backend](index.html): photos, historical sources, text context and editable VR content.
- [VR demo](vr_trial/index.html): two viewpoints with numbered popups and draggable, automatically saved positions.

If that port is occupied, run `python3 start_demo.py --port 8796` and open the same path on that port. Open the web pages through this server rather than directly from disk.

## Snapshot contents

| Resource | Purpose |
| --- | --- |
| `pastport_matching.sqlite3` | Working review database, including human text and position edits |
| `media/` | Photo observations and historical source captures |
| `vr_trial/` | Panorama viewer, numbered hotspots and matching comparison |
| `expanded_dataset.json`, `expanded_mapping.csv` | Inspectable data exports; not live database replacements |
| `review_server.py`, `vr_content.py`, `vr_positions.py` | Original local review and persistence services |
| `schema.sql` | Reference schema; startup uses the populated database |
| `start_demo.py` | Starts the initialized snapshot without regenerating user data |

The snapshot contains 39 scene objects, 20 photographs, 93 photo observations, 37 VR content records and 66 viewpoint-specific positions. The VR shows the objects located in its two panoramas, not every photographed object.

## Boundaries

This is the manually assisted reference demo, not the PDF-to-VR automation implementation. Scene objects are demonstration substitutes for historical objects; they are not claimed to be the original artifacts. The PDF is the preserved reference export, while later popup and position edits live in the database.

The full original heritage PDF is not bundled. Its provenance, extracted text and page captures remain available for review; workstation-only source paths are replaced with portable references. Local source-document links requiring that external PDF need a separately supplied copy at `external-source/heritage-source.pdf`.

Edits are saved to the bundled SQLite database. Back it up before replacing a checkout. The server binds only to this computer and has no authentication: use it locally; this branch is not a public hosted service. No model calls are made by viewing or editing the demo.
