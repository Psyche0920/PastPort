# Content Workflow

## From source to playable chapter

1. **Collect:** record the source title, URL, publication date, page, rights status, and file checksum where available.
2. **Extract:** identify structures, claims, photos, and candidate coordinates. Keep publication page numbers distinct from PDF page indexes.
3. **Review:** assign each claim and photo a review state. Record uncertainty and caveats instead of filling gaps with guesses.
4. **Design:** connect each task to a sourced place or object and to a character decision. Clearly label invented props and events.
5. **Override:** editorially approved tasks take priority. AI tasks may be considered only after validation against approved sources and answer truth.
6. **Build:** import the catalogue, chapter, media manifests, and task candidates into SQLite. The builder validates references and records the narrative hash.
7. **Verify:** run the database and story tests, then play the chapter in a browser at desktop and mobile widths.
8. **Publish:** retain the source manifest and content version so the released text and media can be reproduced.

## Current boundaries

The browser saves progress locally. There is no account service or content administration UI. Runtime AI generation, GPS, and 3D are not connected. Keep these as independent integrations so the online 2D pilot remains playable.
