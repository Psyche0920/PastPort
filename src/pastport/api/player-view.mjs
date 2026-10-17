import {
  node,
  button,
  detail,
  localized,
  safeJSON,
  labeled,
} from "./views.mjs";
import { ConditionEvaluator } from "/static/player/rules.mjs";

/** Render confirmed state only. All mutations go through the authoritative F7 action route. */
export class PlayerView {
  constructor(api, elements, report) {
    this.api = api;
    this.elements = elements;
    this.report = report;
    this.language = "en";
    this.generation = 0;
    this.urls = [];
    this.pending = null;
    this.binding = null;
    this.busy = false;
    this.needsReload = false;
    this.record = [];
    this.trace = [];
    this.feedback = [];
    this.comparison = null;
    elements.retry.onclick = () => this.sendPending();
    elements.reload.onclick = () => this.reload().catch(report);
  }
  clear() {
    this.generation++;
    this.binding = null;
    this.pending = null;
    this.busy = false;
    this.needsReload = false;
    this.record = [];
    this.feedback = [];
    this.trace = [];
    this.comparison = null;
    for (const url of this.urls) URL.revokeObjectURL(url);
    this.urls = [];
    this.elements.content.replaceChildren();
    this.elements.binding.textContent = "";
    this.elements.status.textContent = "";
    this.elements.retry.hidden = true;
    this.elements.reload.hidden = true;
    this.elements.trace.textContent = "";
    this.elements.record.value = "";
    this.elements.difference.replaceChildren();
  }
  adopt(binding, state) {
    this.clear();
    this.binding = binding;
    this.state = state;
    this.elements.reload.hidden = false;
    this.render();
  }
  text(key) {
    return localized(this.binding.package, this.language, key);
  }
  setLanguage(language) {
    this.language = language;
    if (this.binding) this.render();
  }
  async reload() {
    if (!this.binding || this.busy || this.pending)
      throw new Error("Resolve the pending action before reloading state.");
    const generation = this.generation;
    const result = await this.api.request(this.binding.statePath);
    if (generation !== this.generation) return;
    if (
      result.state.package_hash !== this.binding.hash ||
      result.state.release_id !== this.state.release_id
    )
      throw new Error("Player binding changed; open the exact package again.");
    this.state = result.state;
    this.needsReload = false;
    this.render();
  }
  action(kind, target, parameters = {}) {
    if (this.busy || this.pending || this.needsReload || !this.binding) return;
    const request = {
      project_id: this.state.project_id,
      release_id: this.state.release_id,
      package_hash: this.state.package_hash,
      action: {
        action_id: crypto.randomUUID(),
        expected_revision: this.state.revision,
        kind,
        target_id: target,
        ...parameters,
      },
    };
    this.pending = {
      request,
      operation: this.api.operation(this.binding.actionPath, request),
    };
    return this.sendPending();
  }
  async sendPending() {
    if (!this.pending || this.busy || !this.binding) return;
    const pending = this.pending;
    const generation = this.generation;
    this.busy = true;
    this.elements.status.textContent = "Saving action…";
    this.renderControls();
    try {
      const response = await this.api.request(
        this.binding.actionPath,
        pending.operation,
      );
      if (generation !== this.generation) return;
      const result = response.result;
      if (
        !response.persisted ||
        result.state.package_hash !== this.binding.hash ||
        result.state.release_id !== this.state.release_id
      )
        throw new Error("Save confirmation does not match the player binding.");
      this.state = result.state;
      this.feedback = result.feedback_keys;
      this.trace = result.trace;
      this.record.push(pending.request);
      this.pending = null;
      this.elements.status.textContent =
        "Saved · revision " + this.state.revision;
      this.render();
      this.report(null);
    } catch (error) {
      if (generation !== this.generation) return;
      if (error.status && error.status < 500) {
        this.pending = null;
        this.needsReload = true;
      }
      this.elements.status.textContent =
        (this.pending
          ? "Save result unknown. Retry the same action. "
          : "Action rejected; reload confirmed state. ") + error.message;
      this.report(error);
    } finally {
      if (generation === this.generation) {
        this.busy = false;
        this.renderControls();
      }
    }
  }
  renderControls() {
    const locked = this.busy || Boolean(this.pending) || this.needsReload;
    for (const control of this.elements.content.querySelectorAll(
      "button,input",
    ))
      control.disabled = locked || control.dataset.locked === "true";
    this.elements.retry.hidden = !this.pending;
    this.elements.retry.disabled = this.busy;
    this.elements.reload.disabled = this.busy || Boolean(this.pending);
  }
  render() {
    if (!this.binding) return;
    const generation = this.generation;
    for (const url of this.urls) URL.revokeObjectURL(url);
    this.urls = [];
    const { content, binding, trace, record } = this.elements;
    content.replaceChildren();
    const game = this.binding.package;
    const state = this.state;
    binding.textContent = `${this.binding.kind.toUpperCase()} · ${state.release_id} · package ${this.binding.hash}`;
    content.append(
      detail("Story time", state.elapsed_minutes + " minutes"),
      detail(
        "Inventory",
        state.inventory
          .map((id) =>
            this.text(game.props.find((item) => item.prop_id === id).text_key),
          )
          .join(", ") || "Empty",
      ),
    );
    const scene = game.scenes.find(
      (item) => item.scene_id === state.current_scene_id,
    );
    content.append(
      node("h3", this.text(scene.title_key)),
      node("p", this.text(scene.body_key)),
    );
    if (this.feedback.length) {
      const feedback = node("div", "", { class: "feedback", role: "status" });
      for (const key of this.feedback)
        feedback.append(node("p", this.text(key)));
      content.append(feedback);
    }
    if (state.ending_id) {
      const ending = game.endings
        .flatMap((item) => item.endings)
        .find((item) => item.ending_id === state.ending_id);
      content.append(
        node("h3", this.language === "zh" ? "结局" : "Chapter complete"),
      );
      for (const outcome of ending.outcomes) {
        const variant = [...outcome.variants]
          .sort(
            (a, b) =>
              a.priority - b.priority || (a.variant_id < b.variant_id ? -1 : 1),
          )
          .find((item) => new ConditionEvaluator().evaluate(item.guard, state));
        content.append(
          detail(
            this.text(outcome.label_key),
            this.text(variant?.text_key ?? outcome.text_key),
          ),
        );
      }
    } else {
      for (const task of scene.tasks) {
        const completed = state.completed_task_ids.includes(task.task_id);
        const enabled =
          !task.guard || new ConditionEvaluator().evaluate(task.guard, state);
        const block = node("article");
        block.append(
          node("h4", this.text(task.objective_key)),
          node("p", this.text(task.accessibility_key)),
        );
        const lock = (control) => {
          control.dataset.locked = String(completed || !enabled);
          return control;
        };
        if (task.kind === "inspect") {
          const stage = node("div", "", { class: "image-stage" });
          const image = node("img", "", {
            alt: this.text(task.accessibility_key),
          });
          stage.append(image);
          const spots =
            state.observations.find((item) => item.scene_id === scene.scene_id)
              ?.spot_ids ?? [];
          for (const spot of task.spots) {
            const observed = spots.includes(spot.spot_id);
            const label = this.text(spot.text_key);
            const act = () =>
              this.action("observe", task.task_id, { spot_id: spot.spot_id });
            const hotspot = lock(
              button("●", act, {
                class: "hotspot",
                "aria-label": "Observe " + label,
              }),
            );
            hotspot.style.left = `${spot.x / 100}%`;
            hotspot.style.top = `${spot.y / 100}%`;
            hotspot.dataset.locked = String(observed || !enabled || completed);
            stage.append(hotspot);
            const equivalent = lock(
              button((observed ? "✓ " : "Observe: ") + label, act),
            );
            equivalent.dataset.locked = hotspot.dataset.locked;
            block.append(equivalent);
          }
          block.prepend(stage);
          this.api
            .request(
              this.binding.assetPath + "/" + encodeURIComponent(task.asset_id),
              null,
              true,
            )
            .then((blob) => {
              if (generation !== this.generation || !image.isConnected) return;
              const url = URL.createObjectURL(blob);
              this.urls.push(url);
              image.src = url;
            })
            .catch((error) => {
              if (generation === this.generation && image.isConnected) {
                image.replaceWith(
                  node(
                    "p",
                    "Image unavailable. Equivalent observation controls remain available.",
                  ),
                );
                this.report(error);
              }
            });
        } else if (task.kind === "caseboard") {
          const selections = [];
          for (const id of state.inventory) {
            const input = node("input", "", { type: "checkbox", value: id });
            selections.push(input);
            block.append(
              labeled(
                this.text(
                  game.props.find((item) => item.prop_id === id).text_key,
                ),
                lock(input),
              ),
            );
          }
          block.append(
            lock(
              button("Submit evidence", () =>
                this.action("submit_evidence", task.task_id, {
                  prop_ids: selections
                    .filter((item) => item.checked)
                    .map((item) => item.value),
                }),
              ),
            ),
          );
        }
        if (completed) block.append(node("p", "Task completed ✓"));
        content.append(block);
      }
      const tasksDone = scene.required_task_ids.every((id) =>
        state.completed_task_ids.includes(id),
      );
      if (scene.decision_id) {
        const decision = game.decisions.find(
          (item) => item.decision_id === scene.decision_id,
        );
        const chosen = state.decisions.find(
          (item) => item.decision_id === scene.decision_id,
        );
        for (const option of decision.options) {
          const control = button(
            this.text(option.text_key) +
              (chosen?.option_id === option.option_id ? " ✓" : ""),
            () =>
              this.action("choose", decision.decision_id, {
                option_id: option.option_id,
              }),
          );
          control.dataset.optionId = option.option_id;
          control.dataset.locked = String(!tasksDone || Boolean(chosen));
          content.append(control);
        }
      }
      for (const id of scene.next_scene_ids) {
        const control = button(
          "Continue: " +
            this.text(
              game.scenes.find((item) => item.scene_id === id).title_key,
            ),
          () => this.action("advance", id),
        );
        control.dataset.locked = String(
          !tasksDone ||
            !state.unlocked_scene_ids.includes(id) ||
            (scene.decision_id &&
              !state.decisions.some(
                (item) => item.decision_id === scene.decision_id,
              )),
        );
        content.append(control);
      }
    }
    trace.textContent = safeJSON(this.trace);
    record.value = safeJSON({
      package_hash: this.binding.hash,
      starting_revision:
        this.record[0]?.action.expected_revision ?? this.state.revision,
      actions: this.record,
    });
    if (this.comparison) {
      this.elements.difference.replaceChildren(
        node("h4", "Branch comparison"),
        detail("Original story time", this.comparison.elapsed_minutes),
        detail("Current story time", state.elapsed_minutes),
        detail("Original decisions", safeJSON(this.comparison.decisions)),
        detail("Current decisions", safeJSON(state.decisions)),
      );
    }
    this.renderControls();
  }
}
