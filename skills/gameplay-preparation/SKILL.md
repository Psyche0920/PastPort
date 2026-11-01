---
name: gameplay-preparation
description: Map approved story tasks to compatible gameplay plugins, request bounded implementation for genuine mechanic gaps, and bind validated plugin configurations to tasks. Does not write story content, presentation code or game-host rules.
metadata:
  version: "0.1.2"
  owner: maslan
---

# Gameplay preparation

Prepare executable local mechanics from an approved narrative/task package. This is a separate production role from Narrative: consume the story's semantic task intent without rewriting its plot, dialogue, evidence claims, choices or consequences.

## Inputs

- Current NarrativePackage and its exact artifact reference/hash.
- FilterReport for that same narrative revision and pinned museum reference.
- Declared host/runtime capabilities and a version-pinned plugin registry.
- Run policy, coding-worker grant, budget and cancellation context when plugin implementation may be requested.

Reject cross-project, stale or mismatched refs. Do not assume a plugin, host capability, scene coordinate or asset that is absent from these inputs.

## Preparation sequence

1. For every task, derive a typed `MechanicRequest`: task ID; player intent/actions; prerequisites; completion/result semantics; bounded config/state/action/result schemas; feedback and accessibility needs; required host capabilities. Keep the request faithful to the narrative's intended inference and consequence.
2. Match against registered plugins by API version, declared host capabilities, manifest integrity and config-schema compatibility. Prefer a compatible existing plugin and record its exact version and configuration.
3. If no registered plugin fits, return a typed capability gap. When the run grant explicitly permits bounded coding work, produce a `PluginBuildRequest` for the coding worker. Never put executable source code in the narrative/task package or accept generated code directly into the trusted registry.
4. Stage generated code in an isolated workspace. Require manifest/schema validation, lint/type checks, deterministic lifecycle checks (initialize, action, pause/resume, serialize/restore, result, abort), malformed-input rejection, resource limits and file hashes before registration. Do not add capabilities by weakening the host contract.
5. Bind each exact plugin version/config to one existing task ID. Reject missing/duplicate/foreign task IDs, unsupported effects, mismatched package revisions and unfulfilled required capabilities.
6. Emit a `GameplayPlan` containing task-to-plugin bindings, config/build receipt refs, validation results and unresolved gaps. The shared game host remains authoritative for global story state and saved task completion.

## Spatial checks before binding

Consume Narrative's intended observe/inspect/approach/touch action, pinned object/view/world refs and preceding-to-next route requirements. Obtain the corresponding spatial/rule evidence from the environment/host checker; plugin matching cannot establish it. A remote-observation task need not pass approach, but must pass its own visibility/detail conditions. Never convert blocked approach or a timeout into observation completion. Preserve collision, continuous ground and registered cross-view arrivals. Keep unknown results explicit; an unrelated private draft can continue, while an unsupported indispensable execution dependency remains unresolved. Do not rewrite the story or infer human approval to make a binding pass.

## Stop conditions

- No compatible plugin and no authorized coding-worker grant: return `capability_gap` with the task and missing behavior.
- Build or validation fails: allow only the bounded repair policy for the identified check; otherwise retain the blocker and previous valid artifacts.
- Plugin requires unsupported host behavior, unsafe permissions or undeclared resources: do not install or bind it.
- A missing plugin cannot be hidden by replacing the intended mechanic with a weaker task or by claiming the package is playable.

Main now reads and fingerprints this Skill through the Gameplay Preparation SDK. The registered local host supports source reading and source-gated rectangular coverage, with executable configuration checks, lifecycle verification and presentation binding. These operations run in deterministic code, not a separate model Agent. A general production plugin registry, isolated coding worker and automatic construction of arbitrary missing plugins remain unimplemented; the build-request steps above describe that extension boundary, not current execution capability.


Treat supplied automatic geometry as conditional evidence: `clear` direct-route samples
support only the recorded start/end under the pinned movement policy; `direct_obstructed`
does not rule out another route. A `clear_to_anchor` ray does not establish target identity,
glass transparency, full-object visibility or readable detail. Read the geometry input and
algorithm hashes, calibration/placement basis and explicit unknowns. Use the computed
ordered route edges for task continuity; absent edges are unresolved, not implicit travel.
