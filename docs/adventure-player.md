# Muradiye illustrated adventure player

## Run and scope

Serve the repository root with `python3 -m http.server 8876 --bind 127.0.0.1`, then open `/prototype/adventure.html`.

This is a complete frontend for the existing five-scene Chinese chapter, with point-and-click locomotion, WASD/arrow controls, proximity interactions, the original evidence tasks, consequential decisions, a notebook, source photographs, a route panel, endings and save recovery. The original story engine and evidence identities are reused. No external panorama iframe is involved.

The building interiors and four background compositions are artistic interpretations, not surveyed historical reconstructions. The current scope is five linked scene spaces. Scene exits represent narrative transitions; there is no continuous, verified site-wide street model. Relative building locations are supported by the existing inventory and the [TDV architectural account](https://islamansiklopedisi.org.tr/muradiye-kulliyesi--bursa); exact historical gates, circulation, dimensions and interiors remain unverified. Later tombs are excluded from the 1430s story. Modern additions such as the glass roof and restaurant signage are excluded from the illustrations, but that exclusion does not validate all remaining details.

## Runtime contracts

- `prototype/walkmesh.mjs`: polygon walkability, collision sampling, bounded A* navigation and locomotion. Water and solid scene obstacles are excluded from walkable polygons. Both keyboard and pointer movement use the same boundary checks.
- `data/adventure.zh.json`: authored presentation layouts, walk areas, object approach points and links to stable observation IDs. Coordinates are game-screen percentages, not latitude/longitude or survey measurements. Required interactions are checked for walkability before play.
- `prototype/adventure-session.mjs`: a separately namespaced save stores a versioned action log and scene positions. Reload reconstructs the deterministic engine by replaying allowlisted actions. Invalid or incompatible logs are reported and preserved until the user explicitly starts over. Existing photo-player saves are not modified.
- `prototype/adventure.mjs`: local content loading, approved task overrides, world rendering, dialogue, inspection, classification, caseboard, endings and storage feedback. Local fetches have a 12-second timeout. Game code, not image generation, drives progression.
- Walking and reading do not consume story time. Costs remain the existing engine's action/choice costs. Movement pauses during dialogue, modal inspection and background-tab inactivity.
- Walking near a character or unfinished task automatically opens that encounter. An unlocked exit automatically advances the story on approach. `prototype/proximity-trigger.mjs` uses entry/release radii (78/130 game pixels) so standing still after closing a dialogue cannot reopen it, and overlapping targets cannot form a popup chain. Blocked sight lines, completed tasks, locked exits and locked classification tasks do not auto-trigger. Entering an existing saved spawn consumes nearby entries until the player moves away and returns. These radii are game-space values, not physical measurements.
- Clicking a world target remains an optional shortcut to its authored approach point; that route does not trigger unrelated encounters on the way. Keyboard E requires proximity. Tab and Enter can activate the same targets. Touch supports ground movement and automatic encounters. Portrait mode follows the player with a cropped camera.
- Original photographs remain available during architectural inspection. Generated art never replaces source evidence. Optional modern details remain in the original observation records rather than becoming historical props.
- All three architectural observation tasks use the same matching interaction: numbered descriptions (1–3), shuffled letter markers at the original photo coordinates, one-to-one assignment and explicit submission. Wrong/incomplete drafts do not emit engine actions or grant evidence. Only a fully correct submission records observations; original character decisions and imaret classification still remain required. Marker placement stays fixed while revising or reopening a question in the same page session. Reload may reshuffle an unfinished draft; previously earned story progress is preserved.
- Art direction applies to the Chinese player; the original English and Chinese photo players remain available. There is no new English adventure localization yet.

## Art and provenance

Assets were generated with the built-in image generation tool, without an additional API key, then copied into the repository:

- `prototype/assets/adventure/worlds.png`: four equal quadrants (courtyard, fountain, imaret exterior, imaret interior). The browser selects quadrants directly; the file is not a flattened UI screenshot.
- `prototype/assets/adventure/cast.png`: an alpha sprite sheet with four Yusuf walking frames and four idle NPCs (Cem, Halime, steward, kitchen helper). CSS animates the walking frames; characters are separate from the environment.

Reference material: the accepted illustrated UI concept and the existing courtyard, fountain, imaret exterior and imaret interior publication photographs. No official-tour tiles, audio or scripts were copied. Generated output does not establish rights to the original source photographs or grant publication approval. Source-photo rights retain their existing project status.

Condensed final prompt record:

1. **Worlds**: Create a borderless 2×2 atlas of four equal landscape game backgrounds in the accepted warm painterly 2D animation style. No UI, text, people or animals. Preserve recognizable Muradiye brickwork, pointed iwan and octagonal pool; depict the two cup recesses at the fountain; use the imaret facade and star-patterned window heads; interpret a modest accounting room from the interior reference. Keep walkable lower floor areas. Exclude modern glass/steel roofs, restaurant signage, flues, electric lighting and modern furnishings. Treat the result as an artistic 1430s interpretation.
2. **Cast**: Create an alpha 4×2 sprite sheet. Top row: four right-facing walking frames of Yusuf in an ochre coat, cream trousers, headwrap and satchel. Bottom row: full-body idle Cem in teal holding a slip, Halime in muted red with a cup, an indigo-robed steward with a ledger, and a kitchen helper. Use consistent scale, alignment and animation illustration style; no scenery, UI, text, grid lines or shadows.

## Verification boundary

Meaningful automated checks cover all interaction approach points, pool detours, collision boundaries, keyboard axes, speed, action replay, impossible save actions and full five-scene ending replay. The existing story regression suite also covers original branch consequences. Browser checks must separately verify visible character movement, source inspection, sorting, board submission, reload, desktop and mobile layout. Neither those checks nor the art validate historical accuracy or actual on-site access.

Matching regressions additionally cover shuffled marker coordinates in all observation scenes, duplicate-assignment replacement, stable markers during retries, incorrect/incomplete submissions, explicit-submit requirements, evidence gating and save replay. Run `node --test tests/test_story_engine.mjs tests/test_adventure.mjs tests/test_observation_match.mjs`.

The matching update passed 19 JavaScript tests and syntax/whitespace checks. Browser verification used a separate localhost save: an incomplete submission was rejected; an incorrect full submission retained the original evidence count and locked exit; a corrected but unsubmitted draft retained that count; successful submission granted the loading slip while still requiring the original friend decision. Fountain photo/marker alignment was visually checked at the desktop viewport and at 390 CSS pixels, without horizontal overflow. The original 127.0.0.1 player save was not used for these matching checks.

The proximity update passed 25 JavaScript tests in total, including six new cases for ground/keyboard locomotion entry, one-shot triggering, release hysteresis, adjacent encounters, locked targets, saved spawns and blocked geometry. Run the previous command with `tests/test_proximity_trigger.mjs` added. A browser check also moved through the fountain scene using only ground clicks: walking near a clue opened the matching task, and closing it did not reopen it while stationary. Dialogue choices and puzzle submission still require deliberate player input.
