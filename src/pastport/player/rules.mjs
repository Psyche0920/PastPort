import { requirePlayer } from "./errors.mjs";
import { freezeData, sortedUnique } from "./validation.mjs";

export class ConditionEvaluator {
  evaluate(condition, state, depth = 1) {
    requirePlayer(depth <= 8, "PLAYER_CONDITION_DEPTH", "Condition nesting exceeds the profile limit");
    const child = value => this.evaluate(value, state, depth + 1);
    switch (condition.kind) {
      case "all": return condition.conditions.every(child);
      case "any": return condition.conditions.some(child);
      case "not": return !child(condition.condition);
      case "observed_all": return condition.spot_ids.every(spot => state.observations.find(item => item.scene_id === condition.scene_id)?.spot_ids.includes(spot));
      case "choice_equals": return state.decisions.some(item => item.decision_id === condition.decision_id && item.option_id === condition.option_id);
      case "variable_equals": return state.variables.some(item => item.name === condition.name && item.value === condition.value);
      case "has_evidence": return state.inventory.includes(condition.item_id);
      case "elapsed_gt": return state.elapsed_minutes > condition.minutes;
      default: requirePlayer(false, "PLAYER_CONDITION_UNSUPPORTED", "Condition kind is unsupported");
    }
  }
}

const ordered = (key) => (left, right) => left.priority - right.priority || (left[key] < right[key] ? -1 : left[key] > right[key] ? 1 : 0);

/** Matches one event against one unchanged snapshot; committing a queue is a separate boundary. */
export class RuleMatcher {
  constructor(context, conditions = new ConditionEvaluator()) { this.context = context; this.conditions = conditions; }
  match(state, event) {
    const rules = this.context.game.rules.filter(rule => rule.event === event.kind && rule.target_id === event.target_id && !state.applied_rule_keys.includes(rule.once_key) && this.conditions.evaluate(rule.guard, state)).sort(ordered("rule_id"));
    requirePlayer(rules.reduce((count, rule) => count + rule.effects.length, 0) <= 64, "PLAYER_EFFECT_LIMIT", "Matched rules exceed the effect limit");
    return freezeData(rules.map(rule => ({ event_id: event.event_id, rule_id: rule.rule_id, effects: structuredClone(rule.effects) })));
  }
}

/** Evaluates one effect only. This does not resolve cross-effect conflicts or commit receipts. */
export class EffectEvaluator {
  constructor(context, conditions = new ConditionEvaluator()) { this.context = context; this.conditions = conditions; }
  evaluate(state, effect) {
    const candidate = structuredClone(state);
    const feedback = [];
    switch (effect.kind) {
      case "grant_item":
        this.context.find(this.context.game.props, "prop_id", effect.item_id);
        candidate.inventory = sortedUnique([...candidate.inventory, effect.item_id]); break;
      case "set_variable":
      case "set_relationship": {
        const declared = this.context.find(this.context.game.variables, "name", effect.name);
        requirePlayer(typeof effect.value === typeof declared.initial && (effect.kind !== "set_relationship" || typeof effect.value === "string"), "PLAYER_VARIABLE_TYPE", "Effect value differs from the declared variable type");
        candidate.variables.find(item => item.name === effect.name).value = effect.value; break;
      }
      case "add_story_time":
        requirePlayer(Number.isSafeInteger(candidate.elapsed_minutes + effect.minutes), "PLAYER_TIME_OVERFLOW", "Story time exceeds safe integer bounds");
        candidate.elapsed_minutes += effect.minutes; break;
      case "unlock_scene":
        this.context.scene(effect.scene_id);
        candidate.unlocked_scene_ids = sortedUnique([...candidate.unlocked_scene_ids, effect.scene_id]); break;
      case "resolve_ending": {
        const table = this.context.find(this.context.game.endings, "ending_table_id", effect.ending_table_id);
        const ending = [...table.endings].sort(ordered("ending_id")).find(item => item.fallback || this.conditions.evaluate(item.guard, state));
        requirePlayer(Boolean(ending), "PLAYER_ENDING_INVALID", "Ending table has no matching fallback");
        candidate.ending_id = ending.ending_id;
        for (const outcome of ending.outcomes) {
          const variant = [...outcome.variants].sort(ordered("variant_id")).find(item => this.conditions.evaluate(item.guard, state));
          feedback.push(outcome.label_key, variant?.text_key ?? outcome.text_key);
        }
        break;
      }
      default: requirePlayer(false, "PLAYER_EFFECT_UNSUPPORTED", "Effect kind is unsupported");
    }
    this.context.validateState(candidate);
    return freezeData({ state: candidate, feedback_keys: feedback });
  }
}
