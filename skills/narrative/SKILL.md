---
name: narrative
description: Discover, draft or revise evidence-grounded PastPort heritage games with playable tasks, character consequences and continuous spatial progression. Use for story candidates and narrative review; not for approving history, changing engine code or publishing packages.
metadata:
  version: "0.9.0"
  owner: Matt
---

# Heritage narrative production

## Content-only compiled plan

When the server pins `structure_profile=compiled_plan_v1`, return the supplied
`StoryPlanResult` schema. Design ordered tasks and final choices with bilingual
content, explicit supported gameplay requirements, reasoning and consequences.
Select only registered object assets, source claims and views from the four input
constraints. Do not emit runtime rule/scene/task IDs, variables, condition trees,
locale keys, package identities or a SkillResult envelope: the compiler owns them.
Each task's feedback makes its consequence visible. Coverage requirements must
remain grounded in the selected source and exactly match the capability catalog.
If this profile cannot express the requested story, return `no_feasible_story`
with a reason instead of inventing unsupported control flow.

When the server explicitly pins `compiled_branch_v1`, return the supplied
`BranchStoryPlanResult`: 1–3 opening tasks, 2–4 exclusive investigations of 1–3
tasks each, then 1–3 reunion tasks and 2–4 final choices. Each investigation supplies
a bilingual label, fictional notebook finding, reunion feedback and a consequence
for every final choice in choice order. Design different investigations and visible
carry-over, not renamed copies. The compiler owns route identities, exclusive
unlocking, retained findings and conditional reunion/ending text. Source, spatial
and gameplay checks still apply to every task and every possible graph edge.
Nested branches, cross-route visits, arbitrary relationship writes and new puzzle
mechanics are outside this profile; report infeasibility instead of inventing them.
This profile is opt-in and does not replace v1 or grant generation approval.

Legacy `authored_graph` runs retain their pinned NarrativeDraft contract; do not
reinterpret old responses as plans or rewrite an old failed output to claim a
fresh-generation pass. The server-supplied schema determines the active mode.

Create an experience in which understanding heritage changes a decision, relationship or consequence. Use the declared runtime and approved scope. Muradiye is a compatibility reference with weaknesses, not a story to reskin at every site.

## Read selectively

- Interfaces and rules: [workflow contract](../../docs/TECHNICAL_PRD.md#permissions-and-recovery), current guide §§4–7 and 10 as needed.
- Mode inputs and control-result mapping: [skill protocol](../../docs/TECHNICAL_PRD.md#story-and-agents), current guide §7; runtime limits are in §10.
- For pivotal puzzles, character integration or review: [design calibration](references/design-calibration.md).
- For a new PDF/museum production run: follow the narrative steps in the [reusable production workflow](../../docs/TECHNICAL_PRD.md#architecture-and-ownership). Evidence indexing, gameplay preparation and presentation have separate owners.
- Professional content constraints: [reference review](../../docs/TECHNICAL_PRD.md#story-and-agents); read when changing the method, not per scene.

## Inputs and modes

Use the mode-specific request in the skill protocol. Discover requires an index, requirements and runtime capabilities; a final route, approved evidence, old draft and feedback are not prerequisites. Draft requires approved evidence, a selected direction and approved spatial sequence, but no old draft/feedback. Revise also requires the current draft and a targeted revision request. Review reads route/direction from the supplied draft and does not require feedback. Locked fields default to an empty list. Do not block early discovery for information it is meant to propose.

- Discover may read explicitly unapproved candidate material to propose 2–3 hypotheses and gaps. It cannot turn them into final historical assertions.
- If Discovery cannot form a grounded candidate, return a specific scope_gap EvidenceRequest with candidate_id=null; do not fabricate a direction or demand one before research. Draft uses the RouteRecord approved at the evidence gate, not its own proposed route; changed route dependencies require re-review.
- Draft/revise uses approved evidence and permitted wording. Fictional testimony may be unreliable inside the story, but stays separate from historical evidence.
- Review recommends corrections. It cannot grant human approval or claim a playtest happened.

When the trusted DraftRequest declares authoring_mode=internal_preview, follow the owner's authorized unattended-preview policy. Keep unverified historical statements, mapping doubts and route limitations visible in unresolved_items and authoring notes; uncertainty alone is a warning and does not block writing a complete draft. Use source-attributed wording and clearly original fictional incidents. A machine's preview-continuation decision is not human approval or a claim that history is verified. Block only an actual dependency/reference error or an indispensable premise that cannot be represented honestly. Follow the supplied host_constraints; gameplay and presentation implementations remain separate.

## Design process

First form the background, character conflict and complete causal arc from the source index; then use the pinned museum to make that arc playable. Narrative Discover proposes story directions from indexed material; it does not perform exhaustive PDF object extraction. A missing source index returns to evidence indexing, rather than prompting a story from a few previously selected objects.

Treat the source candidate count, eligible museum count and story-used object count as different quantities. The upstream search target of 15 mappings is not a minimum input count, task count or dialogue count for Narrative. Use the actual valid snapshot. Record which available objects were used, omitted or need revision and why; do not force irrelevant objects into tasks to reach a count.

1. Define an urgent player problem and personal stakes: protagonist want, avoided responsibility and possible growth. Give key NPCs independent goals, constraints and reasons to refuse.
2. Select supported site properties that enable action: function, layout, material, visible feature or documented social relationship. Separate established facts from fiction. A modern feature cannot establish an ancient use.
3. Outline causality before dialogue: scene/location → available clue → inference/action → character pressure → state change → later consequence. Follow verified adjacency; mark non-spatial transitions explicitly. Do not force a return merely to report completion.
4. For each pivotal heritage task, explain what changes if its heritage evidence is removed or replaced. Clicking arbitrary decoration to reveal an invented receipt is a locator, not sufficient heritage reasoning. Revise the task or request evidence.
5. Specify the player's meaningful action, prerequisites, evidence-based reasoning, intended result and useful feedback. Do not select a concrete plugin or prescribe its code; gameplay preparation maps this semantic task to a supported mechanic. Do not hide a required premise in an unreachable scene or require external trivia.
6. Make choices understandable trade-offs: beneficiary, loss, immediate response and later state read. Cosmetic ending text alone is inadequate. Responses must fit each NPC's knowledge and motives.
7. Draft only the target scene/affected causal region. Dialogue should add information, pressure, relationship change or a decision; remove repeated summaries. Heritage knowledge should help the player act.
8. Check clue availability, state paths, time, fiction boundaries, route and locale keys. A local change may affect later knowledge, relationships and endings; identify that closure and preserve unaffected text and manual locks.

For each task, preserve a trace from stable object/evidence identity and a reachable clue, through the player's inference/action and answer rule, to a declared state effect and a later visible consequence. A source-backed object can still be irrelevant to a task. Return a targeted evidence request or revise that task instead of attaching a disclaimer to an unrelated object reference.

## Request-scoped story direction and localization

Preserve the user's accepted premise, causal truth and consequential choices as a
project brief supplied with the run. Separate reusable quality rules from that
brief: a particular cast, genre, four-act structure or duration is not a template
for every site. An accepted creative outline does not approve source claims,
spatial bindings, executable gameplay or publication.

When requested, use a mystery with a specific contradiction, competing motives,
secrets that reframe earlier clues and a coherent reveal. Inspiration from a
series concerns pacing and inference, not copied characters, cases or dialogue.
Controversy must arise from credible conflicting interests and consequences;
shock alone is not an engaging investigation. Keep established past events fixed
across routes, and distinguish testimony, inference and demonstrated facts.

For requested mid-story branching, design different playable investigations,
evidence access and NPC responses. At reconvergence retain acquired knowledge,
permissions and actions, with later visible reads; do not reset relationships or
replace branches with alternate wording of the same scene. Specify prerequisites,
trade-offs and recovery from mistaken deductions. Check the pinned schema and
capability catalog before promising execution. If unsupported, preserve the full
brief and report the capability gap through the active result contract; never
silently flatten it into final-choice-only branching or invent runtime fields.

Use stable character/evidence IDs with locale-specific display names when asked.
Localize names consistently across dialogue, recordings and documents. English
and Chinese must reveal the same premises, preserve uncertainty and dramatic
turns, and drive the same choices and effects. Avoid name-based ciphers or wordplay
that loses its solution in another locale unless an equivalent is designed and
checked. A language switch must not alter progress or evidence meaning.

Modern school objects remain modern objects. Fictional messages and incidents
must be explicitly separate from source-backed descriptions. If a heritage-task
contract cannot represent the requested contemporary fiction honestly, report the
scope mismatch rather than inventing historical claims. Use readable linked
panels for text when supported; new task semantics still require gameplay binding.
For mystery/branching review, read the request-scoped cases in
[design calibration](references/design-calibration.md#request-scoped-branching-mystery).

## Spatial task authoring

Read the pinned museum's object identities, review states, per-view coordinates, calibration status, navigation and supplied interaction checks before grounding tasks. Keep exact spatial data in the input; use the declared queries/summaries rather than inferring metric coordinates or collision from prose or a panorama alone.

- Separate localization from interaction permission. A correctly located object may be blocked from approach. Glass, rails, walls and floor discontinuities must remain effective movement constraints; a blocked direct route does not prove wrong localization or that every alternative route is impossible.
- Declare each task's intended action: observe remotely, inspect/click, approach or touch. Do not require approach for every museum object. A staircase behind glass can support a remote-observation task if the relevant features are actually visible and legible from the designated observation area.
- Walking and observation need different checks. Walking must follow continuous supported ground and the host's collision, body-clearance, step/slope and interaction-distance rules. Remote observation requires appropriate sight lines, transparency/occlusion handling and sufficient detail. Neither a blocked approach nor an expired movement check automatically proves visibility, clickability or successful observation.
- Preserve continuity across the task sequence: the previous completion location must connect to the next observation/interaction area. Cross-view travel uses registered directed links and valid destination spawn/arrival headings. Independent worlds need not share one coordinate frame; do not invent geometric stitching, teleport through obstacles or narrate an undeclared transfer as ordinary walking.
- Distinguish unknown, allowed and blocked per action. Unknown position/calibration/route evidence stays unknown; it is not a failed whole story, an approval, or permission to bypass collision. Authorized private-preview authoring may continue with conditional requirements and unresolved notes. Do not assert that an indispensable movement/observation step is executable until its corresponding check supports that action.
- Use the same pinned object/view/world identities, content and spatial revisions, coordinate conventions and rule version throughout. Coordinate, calibration, navigation, collision-asset or host-rule changes invalidate affected checks. A projection-aligned label alone does not establish metric depth.

For every spatially dependent task, use the existing authoring report to record the target object and viewpoint, intended action, observation/interaction area, preceding-to-next route dependencies, required spatial/rule checks, supplied result or unknown status, and any supported alternative. Do not add undeclared fields to the wire format or replace a meaningful task with a weaker one silently. Narrative owns these semantic requirements; the environment/spatial checker supplies geometry and interaction evidence, Gameplay Preparation verifies executable binding, and the host enforces movement and completion.

## Deliverables

Discover: candidate IDs, premise, character arc, evidence/index refs, pivotal task opportunity, route/coverage proposal, five dimension scores with reasons, hard failures and research gaps. The deterministic policy filters and ranks recommendations. Reviewed production retains its direction confirmation gate; owner-authorized internal-preview runs may automatically select a direction while preserving the candidate's uncertainty. Include supported opportunities, blocked premises, proposed player actions, estimated human work (unknown when unmeasured), recommendation reasons and conditions that would reverse the recommendation. Model scores cannot grant human approval or prove fun.

Draft/revise: candidate NarrativePackage and an authoring-only quality report with task→heritage→character links, inference premises/answers, heritage-removal checks, choice consequences/read points, changed IDs, EvidenceRequests, unresolved issues and concise revision reasons. The application validates this report before persistence. Keep editorial notes out of player dialogue. English and Chinese locales share one answer/state model. Use declared outcome IDs and locale keys; career/friend/service/growth are legacy examples, not mandatory dimensions for every site. Describe semantic player actions and story consequences; concrete mechanic requests, plugin selection/code and task/plugin binding belong to the separate gameplay-preparation role.

All modes return the canonical SkillResult envelope. Use complete/research_required/changes_required/review_required/blocked/no_feasible_story as applicable; request_tool is forbidden in narrative modes. Do not return pass/revise/continue aliases or choose a graph node. In review, complete means the report is complete, not that a human approved the story; use changes_required for concrete corrections and research_required for missing evidence. Never average away unsupported facts, rights blockers, inaccessible clues or broken paths. Do not emit human approval, run scripts or publish.

## Observed generation failure taxonomy and gates

Use these failure types when inspecting a generated draft. A schema-valid JSON response is only a structural check; it is not a valid NarrativeDraft, an accepted story or a playable package.

| Failure type | Detection | Required handling |
|---|---|---|
| `OUTPUT_CONTRACT_MISMATCH` | A Draft result is not the canonical SkillResult envelope with `skill=narrative`, `mode=draft` and the exact pinned input refs, or its payload is not a NarrativeDraft containing a NarrativePackage and an authoring report covering every pivotal heritage task. | Validate against the registered typed schema before persistence. Reject ad-hoc outlines and partial payloads; never label them `complete` or send them to assembly. |
| `EVIDENCE_REFERENCE_MISMATCH` | A reference uses only a display number/name, points to another object/version, or its evidence does not support the task's inference. A number existing in the input does not establish semantic identity. | Bind each task to stable object/evidence identities from the pinned, accepted museum snapshot and source package. Verify task relevance and provenance. Remove unrelated references; if no suitable object exists, record the gap. |
| `UNREVIEWED_MATCH_USED_AS_FACT` | A candidate museum mapping is unreviewed, or a modern substitute is narrated as the historical object/use. | Unreviewed mappings may inform Discover hypotheses only. Draft/revise must stop or request evidence until the relevant mapping is approved. Keep the contemporary object, historical interpretation and fiction distinct; preserve the scope warning. |
| `STORY_CAUSALITY_INCOMPLETE` | A task lacks supported premises or an answer rule; a choice has no declared state effect; or its later consequence has no observable read point. | Require the authoring report's evidence-removal/substitution checks and verify each effect is declared by the runtime and read by a later scene/ending. A list of choices or prose-only consequence is not a complete branch. Record unresolved logic instead of inventing a successful path. |
| `PREPARATION_ARTIFACT_MISSING` | Narrative text is present, but no versioned gameplay/presentation preparation artifact is pinned to the exact narrative hash and museum snapshot. | Stop playable-package assembly and report the missing dependency. Narrative owns story and task semantics; Gameplay Preparation owns mechanic matching/build requests/task bindings; Frontend Presentation owns render-ready scene/dialogue/layout data; the shared game host owns execution/state. Do not make Narrative fabricate those outputs. |
| `END_TO_END_NOT_VERIFIED` | Generation or local structure checks pass, but package build, runtime traversal, branches or save/restore have not been exercised with this generated story. | Report only the checks actually run. Do not label a direct one-off model call or old-story conversion as automated new-story acceptance. |

Before Draft, require the mode's declared inputs pinned to the current run. Reviewed production requires a selected direction and approved evidence/route/spatial sequence. Internal preview may use an automatically selected direction and machine-authorized continuation records, with unverified dependencies retained as such; do not claim a human approved them. Missing immutable identities or executable dependencies still require repair. Preserve model output and input hashes, then apply schema/reference/causality checks and the review appropriate to the run mode before independent gameplay/presentation preparation, build and runtime checks. An uncertainty warning alone does not block internal-preview continuation. Story length and dialogue count are content-driven; never force the prior Demo's chapter or turn count. Do not retry a failed model turn implicitly; report failure and actual usage under the run policy.

Quality reports must link a player's actual action and reasoning premises to a later visible state consequence; a filled-in character_goal string is insufficient. Use the protocol's short A/B pilot, observed comprehension and critical blockers rather than treating self-scores as validated enjoyment. Preserve not_run status until each calibration/model/player evaluation actually happens.

## Stop and cost

Stop at run limits, indispensable unsupported facts, unresolved task logic or mechanics outside declared capabilities. Report the gap and owner; do not add a new engine, GPS dependency or unlimited NPC agent. Human edits take priority but still pass the same evidence/rule gates.

Return a focused delta and necessary supporting excerpts, not the complete archive/history. Internal-preview drafts retain pending human review and playtesting as status rather than stopping automatic authoring; do not call them human-accepted or published.

Treat supplied automatic geometry as conditional evidence: `clear` direct-route samples
support only the recorded start/end under the pinned movement policy; `direct_obstructed`
does not rule out another route. A `clear_to_anchor` ray does not establish target identity,
glass transparency, full-object visibility or readable detail. Read the geometry input and
algorithm hashes, calibration/placement basis and explicit unknowns. Use the computed
ordered route edges for task continuity; absent edges are unresolved, not implicit travel.


Use the precomputed `geometry.result.objects[].planning` facts before authoring tasks:
choose supported observation stations from the supplied sight checks, use the recorded
approach station and ordered route edges for movement continuity, and reuse declared
`inspect`/`navigate` interactions. Inspect opens linked content; it does not mean touching,
picking up or reading an inscription in the world. Preserve task-specific detail and
unregistered-touch reasons, and request refinement only for a task that needs those facts.
Do not repeat upstream matching or reopen all object approvals to consume registered input.

## Optional investigation interaction patterns

When the brief requests visual differences, reconstructing an image/chat screenshot, arranging a timeline or searching scene objects, consult [the gameplay pattern reference](../gameplay-preparation/references/investigation-patterns.md). Specify the causal question, available information, supported inference, completion semantics and later consequence. Image comparison requires actual pictures and meaningful visual changes; a wording question is a different mechanic. Let Gameplay Preparation bind the approved task to the checked blueprint and registered plugin. Preserve private-passage consent and known/unknown times.

Use the supplied schema/catalog as the execution boundary. These blueprint patterns do not by themselves expand an older typed Story intent union. If that output contract cannot express the requested mechanic, retain it in the approved task brief/blueprint or report the capability gap; do not invent fields, claim fresh automatic generation, or silently replace the requested image/scene action with reading. Do not force all four patterns into unrelated stories.
