---
name: environment-localization-review
description: Prepare and review source-bound object locations in existing PastPort environments, including 3D attachment and spatial relationships. Use after evidence matching; do not use for historical-source matching, story writing, or publishing.
metadata:
  version: "1.1.0"
  owner: PastPort
---

# Environment localization and review

Use the registered evidence handoff and the current scene to produce traceable, unapproved location candidates. Preserve source, object, scene and review identities and existing human edits. Evidence matching establishes a candidate association; localization establishes where that particular scene object is visible. Neither establishes historical identity or human approval by itself.

## Workflow

1. Verify the registered input hashes, scene binding and capture provenance. Describe generated scene views as derived observations, not original field photographs. Do not transfer coordinates from another scene or reuse an old viewpoint as a fresh observation.
2. Locate each supplied object independently against the current overview and detail views. Use distinctive visual features and cross-view context; similar appearance, a screen image, a reflection or a nearby marker alone is not proof of physical identity. Keep invisible and uncertain objects as explicit gaps.
3. Audit each proposed point against the same source object and actual scene views. A point must lie on the intended object's own surface or supported boundary. Convert detail-view coordinates using the recorded projection; never guess geometry or calibration.
4. Review an asserted whole/part or containment relationship separately, using observable physical evidence for both modern objects. Preserve rejected or uncertain evidence and explain any effect on candidate hotspots; do not infer a relationship solely from semantic similarity, overlapping boxes or a database parent key.
5. Record the source and scene bindings, per-object dispositions, audit reasons, unresolved gaps and actual model usage. Mark spatial alignment, geometry and all historical associations as pending review unless supported by an explicit human decision. Stop safely on insufficient evidence or budget; preserve prior receipts and never silently retry.

The SDK's versioned environment prompt and executable validation remain the runtime authority. New environment runs load a pinned version of this skill into model calls. This skill does not authorize external actions or approve results; existing runs retain their original policy. Consult `packages/matched-environment-sdk/src/pastport_matched_environment/prompts/environment_policy_v1.txt` and `packages/matched-environment-sdk/src/pastport_matched_environment/application/environment_build.py` for the active implementation, and preserve saved policy versions and paid-call identities.

## Visible identity decision threshold

Recognize identity from the combination of overall shape, proportions, material/color and surrounding scene context. Missing visibility of a small mark, sticker, logo, accessory or fine texture is not a contradiction and must not alone cause uncertain or rejected identity. Confirm an otherwise recognizable same object and list these details as limitations. Reserve uncertainty for ambiguity about the object itself, inadequate visible geometry or insufficient support for a location; reject visible contradictions in defining shape or structure. Context supports visible appearance but never replaces it. Never infer an unseen object or substitute shared function. Model confirmation is a visual finding, not human approval or permission to publish. Do not request additional views, retries or functional matching under this policy.
