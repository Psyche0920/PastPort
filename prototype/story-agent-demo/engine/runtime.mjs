import { PlayerContext } from "./context.mjs";
import { ActionHandler } from "./actions.mjs";
import { ConditionEvaluator, EffectEvaluator, RuleMatcher } from "./rules.mjs";
import { PlayerError, requirePlayer } from "./errors.mjs";
import { contentHash, freezeData, SchemaValidator, sortedUnique } from "./validation.mjs";
import { schemas } from "./generated-schemas.mjs";

/** Atomic in-memory transition. Durable callers must CAS the complete result, never a patch. */
export class PlayerRuntime {
  constructor(context) {
    this.context = context;
    this.handlers = new ActionHandler(context);
    this.matcher = new RuleMatcher(context);
    this.effects = new EffectEvaluator(context);
  }

  async apply(state, request) {
    this.context.validateState(state);
    this.context.validator.assertDefinition("ActionRequest", request, "PLAYER_ACTION_INVALID");
    requirePlayer(request.project_id === state.project_id && request.release_id === state.release_id && request.package_hash === state.package_hash, "PLAYER_IDENTITY_MISMATCH", "Action belongs to another package or release");
    const action = request.action;
    const payloadHash = await contentHash(action);
    const receipt = state.processed_actions.find(item => item.action_id === action.action_id);
    if (receipt) {
      requirePlayer(receipt.payload_hash === payloadHash, "ACTION_ID_CONFLICT", "Action identity was already used for another payload");
      // Return current state and original feedback; replay never re-emits events or effects.
      return freezeData({ state: structuredClone(state), emitted_events: [], feedback_keys: [...receipt.feedback_keys], trace: [] });
    }
    requirePlayer(action.expected_revision === state.revision, "STATE_STALE", "Action revision is stale");
    if (action.kind === "advance") {
      const scene = this.context.scene(state.current_scene_id);
      requirePlayer(scene.next_scene_ids.includes(action.target_id) && state.unlocked_scene_ids.includes(action.target_id), "SCENE_LOCKED", "Next scene is not linked and unlocked");
    }
    const proposal = await this.handlers.propose(state, request);
    const events = structuredClone(proposal.emitted_events);
    const usedEventIds = new Set(state.processed_actions.flatMap(item => item.event_ids));
    for (let ordinal = 0; ordinal < events.length; ordinal += 1) {
      let attempt = 0;
      while (usedEventIds.has(events[ordinal].event_id)) {
        events[ordinal].event_id = `event:${payloadHash}:${ordinal}:${attempt}`;
        attempt += 1;
      }
      usedEventIds.add(events[ordinal].event_id);
    }
    let candidate = structuredClone(proposal.state);
    const feedback = [...proposal.feedback_keys];
    const trace = [];
    const writes = new Map();
    let effectCount = 0;
    // Handler order is original event followed by the new task completion event.
    for (const event of events) {
      const snapshot = freezeData(structuredClone(candidate));
      const matches = this.matcher.match(snapshot, event);
      for (const match of matches) {
        effectCount += match.effects.length;
        requirePlayer(effectCount <= 64, "PLAYER_EFFECT_LIMIT", "Action exceeds the total effect limit");
        for (const effect of match.effects) {
          const evaluated = this.effects.evaluate(candidate, effect);
          const key = effect.kind === "set_variable" || effect.kind === "set_relationship" ? `variable:${effect.name}` : effect.kind === "resolve_ending" ? "ending" : null;
          if (key !== null) {
            const value = key === "ending" ? evaluated.state.ending_id : effect.value;
            requirePlayer(!writes.has(key) || writes.get(key) === value, "EFFECT_CONFLICT", "Action contains incompatible writes");
            writes.set(key, value);
          }
          candidate = structuredClone(evaluated.state);
          feedback.push(...evaluated.feedback_keys);
        }
        const rule = this.context.find(this.context.game.rules, "rule_id", match.rule_id);
        candidate.applied_rule_keys = sortedUnique([...candidate.applied_rule_keys, rule.once_key]);
        trace.push(match);
      }
    }
    const conditions = new ConditionEvaluator();
    for (const item of this.context.scene(candidate.current_scene_id).feedback) {
      if (conditions.evaluate(item.guard, candidate)) feedback.push(item.text_key);
    }
    const feedbackKeys = [...new Set(feedback)];
    requirePlayer(Number.isSafeInteger(candidate.revision + 1), "PLAYER_REVISION_OVERFLOW", "Player revision exceeds safe integer bounds");
    candidate.revision += 1;
    candidate.processed_actions.push({ action_id: action.action_id, payload_hash: payloadHash, feedback_keys: feedbackKeys, event_ids: events.map(event => event.event_id) });
    this.context.validateState(candidate);
    const result = { state: candidate, emitted_events: events, feedback_keys: feedbackKeys, trace: structuredClone(trace) };
    new SchemaValidator(schemas.ActionResult).assertSchema(schemas.ActionResult, result, "PLAYER_RESULT_INVALID");
    return freezeData(result);
  }
}

/**
 * Shared browser/headless action entry; package/reference must come from a trusted loader.
 * @param {import("./contracts").PlayerRuntimeCommand} command
 * @returns {Promise<import("./contracts").ActionResult>}
 */
export async function applyAction(command) {
  new SchemaValidator(schemas.PlayerRuntimeCommand).assertSchema(schemas.PlayerRuntimeCommand, command, "PLAYER_COMMAND_INVALID");
  const context = await PlayerContext.create(command.package, command.reference, command.release_id);
  try {
    return await new PlayerRuntime(context).apply(command.state, command.action_request);
  } catch (error) {
    // Preserve the frozen full-runtime error names while retaining component diagnostics.
    if (error instanceof PlayerError && error.code === "PLAYER_SCENE_LOCKED") {
      throw new PlayerError("SCENE_LOCKED", error.message);
    }
    throw error;
  }
}
