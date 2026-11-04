# Investigation patterns: pictures, reconstruction and spatial search

Read for image comparison, drag timelines, screenshot reconstruction or collecting scene-bound objects. These patterns are reusable player actions, not a requirement to use a school, detective plot, cast or all four activities in every story.

## Choose the inference before the mechanic

| Pattern | Required authored inputs | Player action and completion | Avoid |
|---|---|---|---|
| `spot-difference` | Two checked image assets, bounded paired image regions, bilingual explanation for each real visual difference | Select regions on either image; collect every unique difference once | Calling text-question comparison an image puzzle; language changes as a difference; treating an edited diagram as an authentic photo |
| `timeline` | Event cards with supported target slots; an explicit unknown lane when dates are not known | Drag or select/place cards; submit a correct arrangement | Inventing dates or forcing an uncertain event first/last; using an unexpected real countdown |
| `image-puzzle` | Localized complete screenshot/image, stable fragment IDs, grid and validated fragment-to-slot permutation | Drag image fragments or select/place them; explicitly check the reconstructed image | Substituting a list of sentence options for image pieces; exposing private source data; changing answer IDs when translated |
| `scene-search` | Existing object numbers, a common prepared view and enabled inspection, source receipts, useful bilingual visual clues | Find objects in the actual scene, confirm each record, then complete collection | Checklist buttons collecting automatically; unverified walking, new invented coordinates, a timeout counting as a find |

Connect each activity to a question the player cares about, a changed interpretation or a later consequence. Use only necessary objects. A location-bound fictional file is a locator; it is not, by itself, heritage reasoning. Do not disguise filler as source-based inference.

## Blueprint preparation

Use [the template](../assets/investigation-blueprint.template.json) as an authoring skeleton. Replace every binding, asset, hash, answer and localized copy for the target package. No placeholder is production-ready. Input and output interfaces are enforced by `tools/game-package/investigation-blueprint.mjs` and `gameplay/plugins/investigation.mjs`, rather than by this prose.

1. Pin the existing runtime-package input, museum/source snapshot and permitted view/object identities. Narrative content approval does not approve new source claims or spatial calibration.
2. Prepare image assets first. Check the actual pictures: visible differences must match both region lists; puzzle fragments must rebuild the readable image. Native SVG illustrations are suitable code-owned assets. Label illustrations/edited pictures as fiction or reconstruction. For attributed source images preserve their source claim references and alteration notice.
3. Fill bilingual `prompt`, `success`, clues/cards/labels and any new context. Preserve the same IDs, visual inference and accepted solution in both languages. Names in screenshots must follow the cast localization; do not make names into language-dependent passwords.
4. Fill the blueprint's interludes. The current binder inserts only on an existing unambiguous, non-decision edge, preserves the source task/media references, and returns an error for unsupported bindings. It does not invent graph shortcuts or patch review databases.
5. Run `prepareInvestigationBlueprint(baseInput, museum, blueprint, {assetRoot})`. It verifies local asset bytes/hashes and budgets, config schemas, deterministic solutions and lifecycle, same-view search bindings, then uses StoryPackageCompiler. Feed the returned input/compiled outputs into normal assembly; retain the receipt.
6. Verify wrong input, duplicate finds, partial save/restore, exit/resume, completion gates and every affected story route. Browser-check image regions, drag/select-place keyboard alternatives and scene-origin search; deterministic solution proof does not establish visual readability or calibrated movement.

## Current implementation boundary

The JS host registers these four activities at version 1.0.0 and accepts the blueprint preparation path. The typed Narrative/Gameplay SDK catalog still advertises its existing source-reading/coverage intents. Do not emit a new `NarrativeDraft.gameplay_intents.kind` into that older schema or claim fresh automatic generation has been verified. Preserve a requested pattern in an approved blueprint/task brief or return a typed capability gap through the active output contract. A human-approved blueprint is not authorization to call a model, generate paid assets or publish a release.

## Performance and accessibility

Use bounded DOM/SVG/image interaction, not extra 3D models or perpetual animation loops. Keep assets small; the binder enforces 2 MB per image and 12 MB per blueprint. Provide drag and select-then-place, focus indication, readable copy, undo/remove, explicit checking and no surprise timer. The image compare supports arrow-key cursor movement and Enter; do not reveal its answers through ordinary visible option buttons.

A supported renderer can freeze background drawing while a centered 2D activity is open and resume without rebuilding LOD. Scene search must keep the room active. Record whether this renderer hook exists; optional performance support is not universal. Test actual device performance separately from functional completion.

## Result and save contract

The activity owns local bounded state only. Story rewards flow exclusively through the shared task-completion event after a valid result. Search completion receives collected source numbers from the host, not caller-supplied claims. Incomplete tasks, off-image clicks, duplicate finds, invalid arrangements and exit never grant Story rewards. Preserve unknown timestamps and source/spatial uncertainty.

Changing a task mechanic invalidates that task's old save contract. Use a versioned package and preserve the previous build/saves, or implement a specific verified continuation; never silently migrate reading completion into puzzle completion.
