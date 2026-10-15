# Narrative calibration: Muradiye

All game paths/behaviors here refer to the demo-muradiye branch, not main. These are editorial examples and proposed improvements, not edits to the current game or proof of player enjoyment. Source-specific facts remain subject to Weng's review. Original names, supplies, motives and records in The Last Two Sacks are fiction.

## Cases to evaluate

| Case | Weak design | Stronger target and observable check |
|---|---|---|
| N01: generic photograph clue | Click a star; receive a receipt with no reasoning about the heritage | A locator can pace exploration but cannot alone satisfy heritage reasoning. A pivotal task must use supported building function, layout or object meaning to change what the player concludes/does |
| N02: NPC as dispenser | Halime gives a signature after an unrelated trivia answer | Halime wants an accurate statement and refuses a blank record. The player's choice to help/own responsibility changes obtainable evidence and its later consequence |
| N03: cosmetic branch | Two options lead to the same state and differently worded praise | A choice consumes story time, changes access/evidence/relationship, and has a later read point. Verify both the actual state transition and what the player sees |
| N04: mystery certainty | A receipt proves stock totals, therefore automatically clears the carrier | Distinguish what was delivered, where it was recorded and who carried it. The receipt and witness support different propositions; missing testimony changes the ending without denying known totals |
| N05: detached character arc | Find five features and receive a generic badge | Connect classification, evidence collection and signed correction to Yusuf's temptation to shift blame and his responsibility for an inaccurate record |
| N06: geography as plot convenience | Move between distant/unknown entrances to keep a five-scene structure | Reorder/chop scenes or mark an explicit non-spatial transition; never fabricate adjacency. The five-scene Muradiye template is not mandatory for another site |
| N07: translated rules diverge | English has witness evidence; Chinese changes the answer condition | One shared decision/effect graph with separate locale text; recheck translation when the source text or supporting evidence changes |

## A bounded improvement to the existing delivery mystery

Current locator: observing the imaret's star detail grants an invented kitchen receipt. It uses a real photo but does not require understanding the building. Keep it as an optional locator if useful, and add a pivotal reasoning task only if supporting evidence exists.

Proposed direction: the protagonist must distinguish different documented service functions before classifying fictional delivery records. The player compares approved descriptions of the imaret and other relevant spaces, identifies which institutional function is relevant to a meal-service record, then explains why a record labelled solely as grain may misrepresent the fictional delivery. Recognition of an attractive ornament alone does not solve that decision. Distinguishing building function also makes the service consequence understandable to the player.

Evidence boundary: verified source text supplies only the building function/identity and any permitted spatial relation. Sacks, quantities, testimony and blame remain fiction. A photograph does not prove the actual 1430s delivery path. If the sources cannot support the required functional distinctions, submit an EvidenceRequest or choose a different task; do not force this design.

This is an editorial direction, not an approved finished puzzle. The author must still demonstrate that the player can obtain all premises, that changing the heritage information changes a meaningful inference, and that the classification is not merely a hidden-answer quiz.

## Authoring quality report

For each pivotal task record:

- heritage_refs and property_used: approved claim/asset IDs and the exact supported property;
- player_premises, inference, accepted_answer and wrong_answer_feedback;
- character_goal, tradeoff, effect_ids and later_read_points;
- removal_test: what cannot be inferred if the heritage evidence is removed; substitution_test: what changes when the property is different;
- spatial_edge_refs, unknowns, accessible_alternative and new research requests.

These are authoring metadata, not extra questions in the player UI. Reusable heritage properties can legitimately recur at different sites: do not demand an invented unique feature just to pass substitution. The test targets substantive use of documented heritage rather than exact naming or decorative clicks.

## Initial editorial rubric

After factual, rights, route and logic blockers are cleared, rate clarity, curiosity/tension, NPC motivation, heritage reasoning and meaningful consequences from 0–4. Anchors: 0 absent/broken; 1 only asserted; 2 observable but weak/generic; 3 supported and coherent; 4 strongly integrated with a specific player action and consequence. This is an initial review aid, not a calibrated enjoyment metric or an alternative to the Discovery scoring policy.

A pivotal task below 2 for heritage reasoning, motivation or consequences needs revision with an identified cause. Critical evidence/logic failures cannot be offset by good prose. Preserve disagreements between model recommendation and human judgment.

## Mert's first pilot

After workflow recovery works with fixtures, generate one short playable beat from real source excerpts before building the full editing UI. It must contain a relevant image, an evidence-dependent inference, an NPC choice and a later visible result. Use normal evidence/story/publication gates for any public package; internal preview never masquerades as approved history. Record Weng's evidence corrections and Mert's design changes separately.

Evaluate N01–N07 using saved input/output/config snapshots. Then run a real player session without explaining the intended answer: observe whether the player can state why the clue matters and what their choice changed. No such model trial or player session has been completed merely by writing these cases.

Use the canonical input/result protocol and the [quality pilot requirements](../../../docs/WORKFLOW.md#18-故事质量防止字段填满就通过) for mode-specific fields, observable action/consequence evidence, A/B ordering and not_run/model/player status. Do not add a second scoring/approval workflow inside this reference.
