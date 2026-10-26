import { ConditionEvaluator } from "./rules.mjs";
import { requirePlayer } from "./errors.mjs";
import { contentHash, freezeData, sameSet, sortedUnique } from "./validation.mjs";

/** Produces an uncommitted action candidate. No rule execution, receipt or revision mutation. */
export class ActionHandler {
  constructor(context, conditions = new ConditionEvaluator()) { this.context = context; this.conditions = conditions; }
  async propose(state, request) {
    this.context.validateState(state);
    this.context.validator.assertDefinition("ActionRequest", request, "PLAYER_ACTION_INVALID");
    requirePlayer(request.project_id === state.project_id && request.release_id === state.release_id && request.package_hash === state.package_hash, "PLAYER_IDENTITY_MISMATCH", "Action belongs to another package or release");
    const action = request.action;
    requirePlayer(!state.processed_actions.some(receipt => receipt.action_id === action.action_id), "PLAYER_REPLAY_REQUIRES_COMMIT", "Replay must be handled by the full runtime transaction layer");
    requirePlayer(action.expected_revision === state.revision, "PLAYER_STALE_REVISION", "Action revision is stale");
    requirePlayer(state.ending_id === null, "PLAYER_ALREADY_ENDED", "This chapter has already ended");
    const candidate = structuredClone(state);
    const scene = this.context.scene(state.current_scene_id);
    const eventPrefix = await contentHash(action);
    const events = [];
    const feedback = [];
    const emit = (kind, target) => {
      // Content digest preserves the full action identity without truncation collisions.
      events.push({ event_id: action.action_id.length <= 158 ? `${action.action_id}:${events.length}` : `event:${eventPrefix}:${events.length}`, kind, target_id: target });
    };
    const completed = task => {
      if (!candidate.completed_task_ids.includes(task.task_id)) {
        candidate.completed_task_ids = sortedUnique([...candidate.completed_task_ids, task.task_id]);
        emit("task_completed", task.task_id);
        feedback.push(task.feedback_key);
      }
    };
    const requireProgress = () => {
      requirePlayer(scene.required_task_ids.every(id => candidate.completed_task_ids.includes(id)), "PLAYER_TASK_INCOMPLETE", "Required scene tasks are incomplete");
    };
    if (action.kind === "observe" || action.kind === "submit_evidence") {
      const task = this.context.find(scene.tasks, "task_id", action.target_id);
      requirePlayer(task.guard === null || this.conditions.evaluate(task.guard, state), "PLAYER_TASK_LOCKED", "Task guard is not satisfied");
      if (action.kind === "observe") {
        requirePlayer(task.kind === "inspect", "PLAYER_ACTION_TARGET", "Observe requires an inspect task");
        this.context.find(task.spots, "spot_id", action.spot_id);
        let observed = candidate.observations.find(item => item.scene_id === scene.scene_id);
        if (!observed) { observed = { scene_id: scene.scene_id, spot_ids: [] }; candidate.observations.push(observed); candidate.observations.sort((a, b) => a.scene_id < b.scene_id ? -1 : 1); }
        if (!observed.spot_ids.includes(action.spot_id)) {
          observed.spot_ids = sortedUnique([...observed.spot_ids, action.spot_id]);
          emit("spot_observed", task.task_id);
        }
        if (task.required_spot_ids.every(id => observed.spot_ids.includes(id))) completed(task);
      } else {
        requirePlayer(task.kind === "caseboard", "PLAYER_ACTION_TARGET", "Submit evidence requires a caseboard task");
        requirePlayer(action.prop_ids.every(id => candidate.inventory.includes(id)) && sameSet(action.prop_ids, task.required_prop_ids), "PLAYER_EVIDENCE_INVALID", "Evidence must be held and exactly match the task requirements");
        if (!candidate.completed_task_ids.includes(task.task_id)) {
          candidate.selected_evidence = candidate.selected_evidence.filter(item => item.task_id !== task.task_id);
          candidate.selected_evidence.push({ task_id: task.task_id, prop_ids: sortedUnique(action.prop_ids) });
          candidate.selected_evidence.sort((a, b) => a.task_id < b.task_id ? -1 : 1);
          emit("board_submitted", task.task_id); completed(task);
        }
      }
    } else if (action.kind === "choose") {
      requireProgress();
      requirePlayer(scene.decision_id === action.target_id, "PLAYER_ACTION_TARGET", "Decision must belong to the current scene");
      const decision = this.context.find(this.context.game.decisions, "decision_id", action.target_id);
      this.context.find(decision.options, "option_id", action.option_id);
      const existing = candidate.decisions.find(item => item.decision_id === action.target_id);
      requirePlayer(!existing || existing.option_id === action.option_id, "PLAYER_DECISION_FINAL", "An existing decision cannot be changed");
      if (!existing) {
        candidate.decisions.push({ decision_id: action.target_id, option_id: action.option_id });
        candidate.decisions.sort((a, b) => a.decision_id < b.decision_id ? -1 : 1);
        emit("option_chosen", action.target_id);
      }
    } else {
      requireProgress();
      requirePlayer(scene.decision_id === null || candidate.decisions.some(item => item.decision_id === scene.decision_id), "PLAYER_DECISION_REQUIRED", "The scene decision must be completed");
      requirePlayer(scene.next_scene_ids.includes(action.target_id) && candidate.unlocked_scene_ids.includes(action.target_id), "PLAYER_SCENE_LOCKED", "Next scene is not linked and unlocked");
      candidate.current_scene_id = action.target_id;
    }
    requirePlayer(events.length <= 2, "PLAYER_EVENT_LIMIT", "Action exceeds the event limit");
    this.context.validateState(candidate);
    return freezeData({ state: candidate, emitted_events: events, feedback_keys: feedback });
  }
}
