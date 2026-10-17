import { PlayerContext } from "./context.mjs";
import { ActionHandler } from "./actions.mjs";
import { EffectEvaluator, RuleMatcher } from "./rules.mjs";
import { requirePlayer } from "./errors.mjs";
import { freezeData, SchemaValidator } from "./validation.mjs";

/**
 * Browser and headless callers share this preparation entry point. No actions are committed.
 * @param {import("./contracts").PlayerComponentCommand} command
 * @returns {Promise<import("./contracts").PlayerComponentResult>}
 */
export async function prepare(command) {
  const validator = new SchemaValidator();
  validator.assertSchema(validator.root, command, "PLAYER_COMMAND_INVALID");
  const required = { initialize: [], validate_state: ["state"], propose_action: ["state", "action_request"], match_rules: ["state", "event"], evaluate_effect: ["state", "effect"] }[command.operation];
  requirePlayer(["state", "action_request", "event", "effect"].every(key => required.includes(key) === (command[key] != null)), "PLAYER_COMMAND_INVALID", "Command fields differ from the requested operation");
  const context = await PlayerContext.create(command.package, command.reference, command.release_id);
  const state = command.operation === "initialize" ? context.initialState() : command.state;
  context.validateState(state);
  let result = { status: "prepared", committed: false, state, emitted_events: [], feedback_keys: [], matched_rules: [] };
  switch (command.operation) {
    case "initialize": case "validate_state": break;
    case "propose_action": result = { ...result, ...await new ActionHandler(context).propose(state, command.action_request) }; break;
    case "match_rules": result.matched_rules = new RuleMatcher(context).match(state, command.event); break;
    case "evaluate_effect": result = { ...result, ...new EffectEvaluator(context).evaluate(state, command.effect) }; break;
  }
  // The result schema has its own definitions root.
  const { schemas } = await import("./generated-schemas.mjs");
  new SchemaValidator(schemas.PlayerComponentResult).assertSchema(schemas.PlayerComponentResult, result, "PLAYER_RESULT_INVALID");
  return freezeData(structuredClone(result));
}
