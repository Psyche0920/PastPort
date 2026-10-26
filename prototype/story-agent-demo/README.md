# Story Agent Demo

Isolated II. Murat story-player integration candidate. This branch does not modify the shared player, review database, or stylization module. The generation-time Story Agent and Frontend Presentation Agent are specified targets; they are not implemented automation.

## Run with the existing local input

Requires Node.js and the already prepared local demo asset directory. Source PDF/museum media, private scene metadata and large 3D worlds are excluded: the input marks public redistribution as unconfirmed. They are not replaced with fabricated fixtures.

```sh
PASTPORT_LOCAL_DEMO=/absolute/path/to/prepared/demo node prototype/story-agent-demo/serve3d.mjs
```

Open `http://127.0.0.1:18824/?scene=3d`. `PASTPORT_PORT` optionally selects a different port. `PASTPORT_SCENE3D_INPUT` optionally selects the local two-world input JSON. Shared engine snapshots are included from this repository; local `data`, `assets`, `media` and `museum` come from `PASTPORT_LOCAL_DEMO`. Regeneration additionally needs the original authoring directory via `PASTPORT_AUTHORING_DIRECTORY`; `PASTPORT_REPOSITORY` can select the existing source checkout. Never rebuild the review database from a fixture.

## Current behavior

- Single click opens source information; double click approaches. Looking toward an object closes both source and underlying task windows while retaining number markers. The first task appears after opening guidance; its title can reopen it.
- Required reachable ground objects require arrival and explicit reading confirmation. High/view-only objects, or paths classified as blocked by walls, windows, floor gaps or unverified ground, permit reading confirmation without forcing an approach. Missing objects and excessive distance do not silently grant completion.
- Original and styled renderings share navigation and preserve the selected rendering across viewpoint changes. Arrow click, viewpoint buttons and the inherited boundary crossing use the source arrival yaw/pitch. The comparison control is separated from navigation.
- The 2D character standee in the 3D world is removed. Dialogue portraits remain. Natural multi-character entrance/exit choreography is pending.

## Validation and limits

The working demo passed 22 existing deterministic checks plus 7 focused bridge/observation checks. Browser checks confirmed first task → source 68 → look toward 68 → click the visible marker → source opens again; styled point 1 → point 2 automatic walking transition; original-mode bidirectional click switching; rendering-mode retention; and actual arrival camera headings matching the source values. Reverse walking auto-transition was interrupted by the Chrome connection closing and is not claimed passed. User play acceptance remains pending. The repository documentation gate was run with the project interpreter and reported 209 legacy explicit-anchor findings, with no findings under this prototype; that gate is not passing.

```sh
node --test prototype/story-agent-demo/scene3d-bridge.test.mjs
```

The full 22-check suite requires the original generated private data/manifest alongside these sources. Browser navigation evidence is local; no private screenshots or source media are published. The implementation uses local generated collider geometry, not a surveyed historical floor plan. Full chapter traversal, all viewport sizes, cross-page save conflicts and automated Story-to-Presentation generation remain open.

## Source map

| Files | Responsibility |
|---|---|
| `app.mjs`, `app.css`, `index.html`, `dialogue.mjs` | Task windows, source panels and dialogue |
| `content.mjs`, `plugins.mjs`, `session.mjs` | Authored fiction, activity behavior and isolated saves |
| `scene3d-view.mjs`, `scene3d-runtime.js`, `scene3d-navigation.mjs`, `serve3d.mjs` | Story/3D boundary, picking, observation access and source navigation |
| `cinematic-view.mjs`, `interaction.mjs`, `shots.mjs`, `navigation.mjs` | Existing fixed-view interaction adapter |
| `engine/`, `walkmesh.mjs` | Existing shared JavaScript engine and UI-trial snapshot |
| `build.mjs`, `check.mjs`, `scene3d-bridge.test.mjs` | Locked-input assembly and executable checks |
| `PRD.md` | User-confirmed interaction and staging requirements; not a completion report |
