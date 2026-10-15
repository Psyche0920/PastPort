---
name: narrative
description: Discover, draft or revise evidence-grounded PastPort heritage games with playable tasks, character consequences and continuous spatial progression. Use for story candidates and narrative review; not for approving history, changing engine code or publishing packages.
metadata:
  version: "0.3.0"
  owner: Mert
---

# Heritage narrative production

Create an experience in which understanding heritage changes a decision, relationship or consequence. Use the declared runtime and approved scope. Muradiye is a compatibility reference with weaknesses, not a story to reskin at every site.

## Read selectively

- Interfaces and rules: [workflow contract](../../docs/WORKFLOW.md), sections 3–4 and 9–10 as needed.
- Mode inputs and control-result mapping: [skill protocol](../../docs/WORKFLOW.md), sections 14–15; use section 18 for actual quality evaluation.
- For pivotal puzzles, character integration or review: [design calibration](references/design-calibration.md).
- Research origins: [reference review](../../docs/REFERENCES.md); read when changing the method, not per scene.

## Inputs and modes

Use the mode-specific request in the skill protocol. Discover requires an index, requirements and runtime capabilities; a final route, approved evidence, old draft and feedback are not prerequisites. Draft requires approved evidence, a selected direction and approved spatial sequence, but no old draft/feedback. Revise also requires the current draft and a targeted revision request. Review reads route/direction from the supplied draft and does not require feedback. Locked fields default to an empty list. Do not block early discovery for information it is meant to propose.

- Discover may read explicitly unapproved candidate material to propose 2–3 hypotheses and gaps. It cannot turn them into final historical assertions.
- If Discovery cannot form a grounded candidate, return a specific scope_gap EvidenceRequest with candidate_id=null; do not fabricate a direction or demand one before research. Draft uses the RouteRecord approved at the evidence gate, not its own proposed route; changed route dependencies require re-review.
- Draft/revise uses approved evidence and permitted wording. Fictional testimony may be unreliable inside the story, but stays separate from historical evidence.
- Review recommends corrections. It cannot grant human approval or claim a playtest happened.

## Design process

1. Define an urgent player problem and personal stakes: protagonist want, avoided responsibility and possible growth. Give key NPCs independent goals, constraints and reasons to refuse.
2. Select supported site properties that enable action: function, layout, material, visible feature or documented social relationship. Separate established facts from fiction. A modern feature cannot establish an ancient use.
3. Outline causality before dialogue: scene/location → available clue → inference/action → character pressure → state change → later consequence. Follow verified adjacency; mark non-spatial transitions explicitly. Do not force a return merely to report completion.
4. For each pivotal heritage task, explain what changes if its heritage evidence is removed or replaced. Clicking arbitrary decoration to reveal an invented receipt is a locator, not sufficient heritage reasoning. Revise the task or request evidence.
5. Use document, inspect, inspect-sort or caseboard. Specify prerequisites, answer rules, effects, wrong-answer feedback and accessible equivalents. Do not hide a required premise in an unreachable scene or require external trivia.
6. Make choices understandable trade-offs: beneficiary, loss, immediate response and later state read. Cosmetic ending text alone is inadequate. Responses must fit each NPC's knowledge and motives.
7. Draft only the target scene/affected causal region. Dialogue should add information, pressure, relationship change or a decision; remove repeated summaries. Heritage knowledge should help the player act.
8. Check clue availability, state paths, time, fiction boundaries, route and locale keys. A local change may affect later knowledge, relationships and endings; identify that closure and preserve unaffected text and manual locks.

## Deliverables

Discover: candidate IDs, premise, character arc, evidence/index refs, pivotal task opportunity, route/coverage proposal, five dimension scores with reasons, hard failures and research gaps. Deterministic policy selects; model scores do not prove fun.

Draft/revise: candidate NarrativePackage and an authoring-only quality report with task→heritage→character links, inference premises/answers, heritage-removal checks, choice consequences/read points, changed IDs, EvidenceRequests, unresolved issues and concise revision reasons. The application validates this report before persistence. Keep editorial notes out of player dialogue. English and Chinese locales share one answer/state model.

All modes return the canonical SkillResult envelope. Use complete/research_required/changes_required/review_required/blocked/no_feasible_story as applicable; request_tool is forbidden in narrative modes. Do not return pass/revise/continue aliases or choose a graph node. In review, complete means the report is complete, not that a human approved the story; use changes_required for concrete corrections and research_required for missing evidence. Never average away unsupported facts, rights blockers, inaccessible clues or broken paths. Do not emit human approval, run scripts or publish.

Quality reports must link a player's actual action and reasoning premises to a later visible state consequence; a filled-in character_goal string is insufficient. Use the protocol's short A/B pilot, observed comprehension and critical blockers rather than treating self-scores as validated enjoyment. Preserve not_run status until each calibration/model/player evaluation actually happens.

## Stop and cost

Stop at run limits, indispensable unsupported facts, unresolved task logic or mechanics outside declared capabilities. Report the gap and owner; do not add a new engine, GPS dependency or unlimited NPC agent. Human edits take priority but still pass the same evidence/rule gates.

Return a focused delta and necessary supporting excerpts, not the complete archive/history. A valid draft still needs human review and actual playtesting.
