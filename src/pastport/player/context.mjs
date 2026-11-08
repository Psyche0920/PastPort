import { SchemaValidator, contentHash, freezeData, sameSet, sortedUnique } from "./validation.mjs";
import { requirePlayer } from "./errors.mjs";

const CONDITIONS = ["all", "any", "not", "observed_all", "choice_equals", "variable_equals", "has_evidence", "elapsed_gt"];
const EFFECTS = ["grant_item", "set_variable", "set_relationship", "add_story_time", "unlock_scene", "resolve_ending"];
const EVENTS = ["spot_observed", "board_submitted", "option_chosen", "task_completed"];

/** Packages arrive through the Python loader or an equally trusted validated-package boundary. */
export class PlayerContext {
  constructor(packageData, reference, releaseId) {
    this.package = freezeData(structuredClone(packageData));
    this.reference = freezeData(structuredClone(reference));
    this.releaseId = releaseId;
    this.game = this.package.game;
    this.validator = new SchemaValidator();
  }

  static async create(packageData, reference, releaseId) {
    const validator = new SchemaValidator();
    validator.assertDefinition("RuntimePackage", packageData, "PLAYER_PACKAGE_INVALID");
    validator.assertDefinition("ArtifactRef", reference, "PLAYER_IDENTITY_MISMATCH");
    requirePlayer(typeof releaseId === "string" && /^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}$/u.test(releaseId), "PLAYER_IDENTITY_MISMATCH", "Release identity is invalid");
    requirePlayer(reference.kind === "runtime" && reference.project_id === packageData.project_id && reference.schema_version === packageData.schema_version && reference.content_version === packageData.content_version, "PLAYER_IDENTITY_MISMATCH", "Package differs from its trusted identity");
    requirePlayer(await contentHash(packageData) === reference.sha256, "PLAYER_HASH_MISMATCH", "Package differs from its trusted content hash");
    const capability = packageData.runtime_compatibility;
    requirePlayer(capability.profile === "t1a-single-task" && capability.contract_version === "0.1.0" && sameSet(capability.task_kinds, ["inspect", "caseboard"]) && sameSet(capability.condition_kinds, CONDITIONS) && sameSet(capability.effect_kinds, EFFECTS) && sameSet(capability.event_kinds, EVENTS) && (sameSet(capability.locales, ["en", "zh"]) || sameSet(capability.locales, ["en", "tr"])) && capability.max_events_per_action === 2 && capability.max_effects_per_action === 64 && capability.max_condition_depth === 8, "PLAYER_CAPABILITY_UNSUPPORTED", "Package capability profile is unsupported");
    requirePlayer(packageData.game.scenes.every(scene => scene.tasks.length === 1 && scene.tasks.every(task => task.prerequisite_task_ids.length === 0)), "PLAYER_CAPABILITY_UNSUPPORTED", "Task dependencies and multi-task scenes are not supported");
    return new PlayerContext(packageData, reference, releaseId);
  }

  find(items, key, identity) {
    const result = items.find(item => item[key] === identity);
    requirePlayer(Boolean(result), "PLAYER_REFERENCE_INVALID", "A gameplay identity is not declared by the package");
    return result;
  }

  scene(identity) { return this.find(this.game.scenes, "scene_id", identity); }
  task(identity) { return this.find(this.game.scenes.flatMap(scene => scene.tasks), "task_id", identity); }

  initialState() {
    const initial = this.game.initial_state;
    const state = {
      project_id: this.package.project_id, release_id: this.releaseId, package_hash: this.reference.sha256,
      chapter_id: this.game.chapter_id, schema_version: this.package.schema_version, revision: 0,
      current_scene_id: initial.current_scene_id, elapsed_minutes: initial.elapsed_minutes,
      observations: [], completed_task_ids: [], decisions: [], inventory: sortedUnique(initial.inventory),
      assignments: [], selected_evidence: [], variables: this.game.variables.map(variable => ({ name: variable.name, value: variable.initial })).sort((a, b) => a.name < b.name ? -1 : 1),
      unlocked_scene_ids: sortedUnique(initial.unlocked_scene_ids), applied_rule_keys: [], processed_actions: [], ending_id: null,
    };
    this.validateState(state);
    return freezeData(state);
  }

  validateState(state) {
    this.validator.assertDefinition("PlayerState", state, "PLAYER_STATE_INVALID");
    requirePlayer(state.project_id === this.package.project_id && state.release_id === this.releaseId && state.package_hash === this.reference.sha256 && state.chapter_id === this.game.chapter_id && state.schema_version === this.package.schema_version, "PLAYER_IDENTITY_MISMATCH", "Player state belongs to another package or release");
    const unique = (values, canonical = true) => {
      const sorted = canonical ? [...values].sort() : values;
      requirePlayer(new Set(values).size === values.length && (!canonical || values.every((value, index) => value === sorted[index])), "PLAYER_STATE_INVALID", "State collections must have unique stable identities");
    };
    unique(state.inventory); unique(state.completed_task_ids); unique(state.unlocked_scene_ids); unique(state.applied_rule_keys);
    unique(state.observations.map(item => item.scene_id)); unique(state.decisions.map(item => item.decision_id));
    unique(state.variables.map(item => item.name)); unique(state.selected_evidence.map(item => item.task_id));
    unique(state.processed_actions.map(item => item.action_id), false);
    requirePlayer(state.processed_actions.length === state.revision, "PLAYER_STATE_INVALID", "Revision must agree with the complete action receipt history");
    const textKeys = new Set(this.game.locales[0].entries.map(item => item.key));
    const eventIds = [];
    for (const receipt of state.processed_actions) {
      requirePlayer(receipt.event_ids.length <= 2 && receipt.feedback_keys.every(key => textKeys.has(key)), "PLAYER_STATE_INVALID", "Receipt feedback or events are invalid");
      unique(receipt.feedback_keys, false);
      eventIds.push(...receipt.event_ids);
    }
    unique(eventIds, false);
    this.scene(state.current_scene_id);
    requirePlayer(state.unlocked_scene_ids.includes(state.current_scene_id) && state.assignments.length === 0, "PLAYER_STATE_INVALID", "Current scene must be unlocked and assignments are unsupported");
    for (const identity of state.unlocked_scene_ids) this.scene(identity);
    for (const identity of state.inventory) this.find(this.game.props, "prop_id", identity);
    for (const identity of state.completed_task_ids) this.task(identity);
    for (const identity of state.applied_rule_keys) this.find(this.game.rules, "once_key", identity);
    requirePlayer(sameSet(state.variables.map(item => item.name), this.game.variables.map(item => item.name)), "PLAYER_STATE_INVALID", "Player variables differ from package declarations");
    for (const variable of state.variables) {
      const declared = this.find(this.game.variables, "name", variable.name);
      requirePlayer(typeof declared.initial === typeof variable.value, "PLAYER_STATE_INVALID", "Player variable type differs from its declaration");
    }
    for (const observation of state.observations) {
      const scene = this.scene(observation.scene_id);
      const task = scene.tasks[0];
      requirePlayer(task.kind === "inspect", "PLAYER_STATE_INVALID", "Observations require an inspect task");
      unique(observation.spot_ids);
      for (const identity of observation.spot_ids) this.find(task.spots, "spot_id", identity);
    }
    for (const selection of state.selected_evidence) {
      requirePlayer(this.task(selection.task_id).kind === "caseboard", "PLAYER_STATE_INVALID", "Evidence selections require a caseboard task");
      unique(selection.prop_ids);
      requirePlayer(selection.prop_ids.every(identity => state.inventory.includes(identity)), "PLAYER_STATE_INVALID", "Selected evidence must already be held");
    }
    for (const choice of state.decisions) {
      const decision = this.find(this.game.decisions, "decision_id", choice.decision_id);
      this.find(decision.options, "option_id", choice.option_id);
    }
    for (const identity of state.completed_task_ids) {
      const task = this.task(identity);
      const scene = this.game.scenes.find(item => item.tasks.some(candidate => candidate.task_id === identity));
      if (task.kind === "inspect") {
        const observed = state.observations.find(item => item.scene_id === scene.scene_id)?.spot_ids ?? [];
        requirePlayer(task.required_spot_ids.every(spot => observed.includes(spot)), "PLAYER_STATE_INVALID", "Completed inspection lacks required observations");
      } else {
        const selected = state.selected_evidence.find(item => item.task_id === identity)?.prop_ids ?? [];
        requirePlayer(sameSet(selected, task.required_prop_ids), "PLAYER_STATE_INVALID", "Completed evidence task lacks its required selection");
      }
    }
    if (state.ending_id !== null) this.find(this.game.endings.flatMap(table => table.endings), "ending_id", state.ending_id);
    return true;
  }
}
