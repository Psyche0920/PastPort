import { ApiClient, ApiError } from "./api-client.mjs";
import { PlayerView } from "./player-view.mjs";
import {
  node,
  button,
  detail,
  localized,
  safeJSON,
  labeled,
  latest,
} from "./views.mjs";

const $ = (id) => document.getElementById(id);
const budgetLabels = {
  max_model_requests: "Model requests",
  max_input_tokens: "Input tokens",
  max_output_tokens: "Output tokens",
  max_search_requests: "Searches",
  max_fetch_requests: "Source reads",
  max_active_seconds: "Automatic processing seconds",
  max_cost_microusd: "Maximum cost (micro USD)",
};
const usageLabels = {
  model_requests: "Model requests",
  input_tokens: "Input tokens",
  output_tokens: "Output tokens",
  search_requests: "Searches",
  fetch_requests: "Source reads",
  active_milliseconds: "Processing milliseconds",
  cost_microusd: "Cost (micro USD)",
};
const defaultBudget = {
  max_model_requests: 2,
  max_input_tokens: 10000,
  max_output_tokens: 10000,
  max_search_requests: 0,
  max_fetch_requests: 0,
  max_active_seconds: 120,
  max_cost_microusd: 100000,
};

class WorkbenchController {
  constructor() {
    this.api = null;
    this.session = null;
    this.run = null;
    this.epoch = 0;
    this.busy = false;
    this.pending = null;
    this.reviewChoices = [];
    this.reviewSignature = undefined;
    this.draft = null;
    this.loadedDraftHash = null;
    this.interventions = null;
    this.urls = [];
    this.dirty = false;
    this.player = null;
    this.timer = null;
    this.numberFields("runBudget", budgetLabels, "run-", defaultBudget);
    this.numberFields("budgetFields", budgetLabels, "limit-", {});
    this.numberFields("usageFields", usageLabels, "actual-", {});
    this.wire();
  }
  message(text, error = false) {
    $("message").textContent = text;
    $("message").className = error ? "error" : "";
  }
  report(error) {
    if (!error) {
      this.message("Player state saved.");
      return;
    }
    if (error.name === "AbortError") return;
    if (error.status === 401) {
      this.disconnect();
      this.message("Session ended. Connect again.", true);
      return;
    }
    this.message((error.code ? error.code + ": " : "") + error.message, true);
  }
  async perform(action) {
    if (this.busy || this.pending) return;
    this.busy = true;
    try {
      await action();
    } catch (error) {
      this.report(error);
    } finally {
      this.busy = false;
    }
  }
  async command(path, payload, completed = async () => this.loadRun()) {
    if (this.pending)
      throw new Error(
        "Resolve the exact pending command before another change.",
      );
    this.pending = {
      operation: this.api.operation(path, payload),
      completed,
      epoch: this.epoch,
    };
    this.lockEditing(true);
    await this.sendPending();
  }
  async sendPending() {
    const pending = this.pending;
    if (!pending || !this.api) return;
    try {
      const response = await this.api.request(
        pending.operation.path,
        pending.operation,
      );
      if (pending.epoch !== this.epoch) return;
      this.pending = null;
      this.lockEditing(false);
      $("retryCommand").hidden = true;
      await pending.completed(response);
      this.message("Saved.");
    } catch (error) {
      if (pending.epoch !== this.epoch) return;
      if (error.status && error.status < 500) {
        this.pending = null;
        this.lockEditing(false);
        $("retryCommand").hidden = true;
      } else {
        $("retryCommand").hidden = false;
      }
      throw error;
    }
  }
  lockEditing(locked) {
    for (const control of document.querySelectorAll(
      "#storyEditor textarea,#draftJSON,#editReason,#factsChanged",
    ))
      control.disabled = locked;
  }
  clearContext() {
    this.lockEditing(false);
    this.epoch++;
    clearTimeout(this.timer);
    this.api?.cancel();
    this.pending = null;
    this.run = null;
    this.reviewChoices = [];
    this.reviewSignature = undefined;
    this.draft = null;
    this.loadedDraftHash = null;
    this.dirty = false;
    this.interventions = null;
    this.player?.clear();
    $("retryCommand").hidden = true;
    for (const url of this.urls) URL.revokeObjectURL(url);
    this.urls = [];
    for (const id of [
      "runSummary",
      "candidates",
      "claims",
      "sourceContent",
      "artifacts",
      "storyContent",
      "storyEditor",
      "reviews",
      "reviewHistory",
      "releaseSummary",
      "budgetSummary",
      "events",
      "changeImpact",
    ])
      $(id).replaceChildren();
    for (const id of [
      "artifactDetails",
      "budget",
      "interventionDetails",
      "context",
    ])
      $(id).textContent = "";
    for (const id of [
      "draftJSON",
      "lockPaths",
      "editReason",
      "previewId",
      "revokedDecision",
      "unknownReservation",
      "revokeDecision",
      "beforeVersion",
    ]) {
      const item = $(id);
      if (item.tagName === "SELECT") item.replaceChildren();
      else item.value = "";
    }
  }
  disconnect() {
    this.clearContext();
    this.api?.disconnect();
    this.api = null;
    this.session = null;
    this.player = null;
    $("workspace").hidden = true;
    $("disconnect").hidden = true;
    $("token").value = "";
    $("projects").replaceChildren();
    $("runId").value = "";
    $("mode").textContent = "Disconnected. Private content cleared.";
  }
  async connect() {
    const token = $("token").value;
    this.disconnect();
    this.api = new ApiClient(token);
    const epoch = this.epoch;
    const session = await this.api.request("/api/v1/session");
    if (epoch !== this.epoch) return;
    this.session = session;
    this.player = new PlayerView(
      this.api,
      {
        content: $("playerContent"),
        binding: $("playerBinding"),
        status: $("playerStatus"),
        retry: $("retryPlayer"),
        reload: $("reloadPlayer"),
        trace: $("ruleTrace"),
        record: $("replayRecord"),
        difference: $("branchDifference"),
      },
      (error) => this.report(error),
    );
    $("workspace").hidden = false;
    $("disconnect").hidden = false;
    $("mode").textContent =
      `${this.session.environment.toUpperCase()} · ${this.session.actor_id} · ${this.session.roles.join(", ")} · Private workspace`;
    await this.projects();
    if (epoch !== this.epoch) return;
    this.authorities();
    this.message("Connected.");
  }
  async projects() {
    const epoch = this.epoch;
    const projects = await this.api.request("/api/v1/projects");
    if (epoch !== this.epoch) return;
    $("projects").replaceChildren(
      node("option", "Select a project", { value: "" }),
    );
    for (const project of projects)
      $("projects").append(
        node("option", project.name + " · " + project.project_id, {
          value: project.project_id,
        }),
      );
  }
  section(name) {
    for (const item of document.querySelectorAll("nav button")) {
      const active = item.dataset.section === name;
      item.setAttribute("aria-current", active ? "page" : "false");
      $(item.dataset.section).hidden = !active;
    }
  }
  path() {
    if (!this.run) throw new Error("Load a run first.");
    return "/api/v1/runs/" + encodeURIComponent(this.run.state.run_id);
  }
  revision() {
    if (!this.run) throw new Error("Load a run first.");
    return this.run.state.revision;
  }
  has(role) {
    return this.session?.roles.includes(role);
  }
  authorities() {
    for (const id of ["createProject", "createRun", "cancel", "resume"])
      $(id).disabled = !this.has("editor");
    for (const id of ["saveStory", "saveLocks", "requestNarrative"])
      $(id).disabled = !this.has("narrative") || !this.run;
    for (const id of ["loadInterventions", "amendBudget", "reconcileUsage"])
      $(id).disabled = !this.has("operator") || !this.run;
    const pending = this.run?.review_requests.find(
      (item) => item.request_id === this.run.state.pending_review_id,
    );
    $("saveReviews").disabled =
      !pending ||
      !this.has(pending.gate === "publication" ? "publisher" : pending.gate) ||
      this.run.state.status !== "waiting_review";
    $("newPreview").disabled = !latest(this.run, "draft");
    $("restorePreview").disabled = !this.run;
    $("openRelease").disabled = !this.run;
    $("compareChanges").disabled = !this.draft;
  }
  async loadRun() {
    if (!this.api) throw new Error("Connect first.");
    const runId = $("runId").value.trim();
    if (!runId) throw new Error("Enter a run ID.");
    if (this.run && this.run.state.run_id !== runId) this.clearContext();
    const epoch = this.epoch;
    const result = await this.api.request(
      "/api/v1/runs/" + encodeURIComponent(runId),
    );
    if (epoch !== this.epoch) return;
    if (
      this.dirty &&
      this.loadedDraftHash &&
      latest(result, "draft")?.reference.sha256 !== this.loadedDraftHash
    ) {
      this.message(
        "Current draft changed. Your unsaved text is retained; explicitly reload the edit form before saving.",
        true,
      );
    }
    this.run = result;
    $("projectId").value = result.state.project_id;
    $("context").textContent =
      `${result.state.project_id} · ${runId} · revision ${result.state.revision}`;
    this.renderOverview();
    this.renderEvidence();
    this.renderStory();
    this.renderReview();
    this.authorities();
    const [events, budget] = await Promise.all([
      this.api.request(this.path() + "/events"),
      this.api.request(this.path() + "/budget"),
    ]);
    if (epoch !== this.epoch) return;
    this.renderActivity(events, budget);
    const player = this.player?.binding;
    if (
      player?.kind !== "private release" &&
      player?.sourceHash &&
      latest(result, "draft")?.reference.sha256 !== player.sourceHash
    ) {
      this.player.clear();
      $("playerStatus").textContent =
        "Draft changed. Open a new preview for the new version.";
    }
    clearTimeout(this.timer);
    if (["queued", "running"].includes(result.state.status))
      this.watchRun(epoch);
  }
  watchRun(epoch) {
    this.timer = setTimeout(() => {
      if (epoch !== this.epoch) return;
      if (this.busy || this.pending || this.dirty) this.watchRun(epoch);
      else this.loadRun().catch((error) => this.report(error));
    }, 800);
  }
  renderOverview() {
    const { state } = this.run;
    $("runSummary").replaceChildren(
      detail("Stage", state.node),
      detail("Status", state.status),
    );
    if (state.error)
      $("runSummary").append(detail("Blocker", safeJSON(state.error)));
    $("candidates").replaceChildren();
    const artifact =
      latest(this.run, "candidates") ??
      this.run.artifacts.find(
        (item) => item.reference.kind === "candidate_set",
      );
    if (artifact)
      for (const candidate of JSON.parse(artifact.payload_json).candidates) {
        const article = node("article");
        article.append(
          node("h3", candidate.premise),
          node("p", candidate.recommendation_reason),
        );
        for (const [key, value] of Object.entries(candidate))
          if (
            [
              "gaps",
              "unresolved_items",
              "manual_work",
              "rejection_conditions",
            ].includes(key)
          )
            article.append(detail(key, safeJSON(value)));
        const reason = node("input", "", {
          "aria-label": "Reason for choosing " + candidate.candidate_id,
        });
        article.append(labeled("Direction selection reason", reason));
        const control = button("Choose direction", () =>
          this.perform(async () => {
            if (!reason.value.trim())
              throw new Error("Enter a direction reason.");
            await this.command(this.path() + "/candidate-selections", {
              expected_revision: this.revision(),
              candidate_set_hash: artifact.reference.sha256,
              candidate_id: candidate.candidate_id,
              reason: reason.value,
            });
          }),
        );
        control.disabled =
          !this.has("narrative") ||
          state.node !== "select_candidate" ||
          state.status !== "needs_review";
        article.append(control);
        $("candidates").append(article);
      }
  }
  renderEvidence() {
    $("claims").replaceChildren();
    const artifact = latest(this.run, "evidence");
    if (!artifact) {
      $("claims").append(node("p", "No evidence snapshot yet."));
      return;
    }
    const evidence = JSON.parse(artifact.payload_json);
    for (const claim of evidence.claims) {
      const article = node("article");
      article.append(
        node("h3", claim.text),
        detail("Content kind", claim.content_kind),
        detail("Judgment", claim.judgment),
        node("p", claim.reason),
      );
      for (const relation of ["support", "refute"])
        for (const locator of claim[relation]) {
          const source = evidence.sources.find(
            (item) => item.source_id === locator.source_id,
          );
          article.append(
            button(
              `${relation}: ${source?.title ?? locator.source_id} · ${locator.printed_page ?? locator.page_index ?? locator.paragraph_or_region}`,
              () => this.perform(() => this.source(locator)),
            ),
          );
        }
      $("claims").append(article);
    }
    for (const asset of evidence.assets)
      $("claims").append(
        detail(
          "Media mapping / rights",
          `${asset.asset_id}: ${asset.mapping_state} / ${asset.rights_state} · ${asset.rights_basis}`,
        ),
      );
    $("artifacts").replaceChildren();
    for (const item of this.run.artifacts)
      $("artifacts").append(
        button(
          item.reference.kind + " · " + item.reference.content_version,
          () => {
            $("artifactDetails").textContent = safeJSON(
              JSON.parse(item.payload_json),
            );
          },
        ),
      );
  }
  async source(locator) {
    const epoch = this.epoch;
    const path =
      this.path() +
      "/sources/" +
      encodeURIComponent(locator.source_id) +
      "?" +
      new URLSearchParams({
        source_version: locator.source_version,
        file_sha256: locator.file_sha256,
      });
    const document = await this.api.request(path);
    if (epoch !== this.epoch) return;
    for (const url of this.urls) URL.revokeObjectURL(url);
    this.urls = [];
    $("sourceContent").replaceChildren(
      node("h3", document.source.title),
      detail("Source status", document.status),
      detail("Source version", locator.source_version),
      detail("Source hash", locator.file_sha256),
      detail("Page index (zero based)", locator.page_index),
      detail("Printed page", locator.printed_page),
      detail("Paragraph / region", locator.paragraph_or_region),
    );
    for (const fragment of document.fragments) {
      const panel = node("article");
      panel.append(
        detail(
          "Fragment location",
          fragment.locator.paragraph_or_region ??
            fragment.locator.printed_page ??
            fragment.locator.page_index,
        ),
        node("p", fragment.text),
      );
      $("sourceContent").append(panel);
    }
    if (!document.fragments.length)
      $("sourceContent").append(
        node(
          "p",
          "No saved original text is available. Claim wording is not substituted for the source.",
        ),
      );
    $("sourceContent").append(
      button("Download registered original", () =>
        this.perform(async () => {
          const blob = await this.api.request(
            path.replace("?", "/content?"),
            null,
            true,
          );
          if (epoch !== this.epoch) return;
          const url = URL.createObjectURL(blob);
          this.urls.push(url);
          const link = node("a", "Download original source", {
            href: url,
            download: locator.source_id + ".bin",
          });
          $("sourceContent").append(link);
          link.click();
        }),
      ),
    );
  }
  renderStory() {
    const drafts = this.run.artifacts.filter((item) =>
      item.reference.artifact_id.endsWith(":draft"),
    );
    const artifact = drafts.at(-1);
    if (!artifact) {
      $("storyContent").replaceChildren(node("p", "No narrative draft yet."));
      return;
    }
    $("beforeVersion").replaceChildren();
    for (const item of drafts)
      $("beforeVersion").append(
        node(
          "option",
          item.reference.content_version +
            " · " +
            item.reference.sha256.slice(0, 12),
          { value: item.reference.sha256 },
        ),
      );
    if (drafts.length > 1) $("beforeVersion").selectedIndex = drafts.length - 2;
    if (!this.dirty && this.loadedDraftHash !== artifact.reference.sha256)
      this.loadDraft(
        JSON.parse(artifact.payload_json),
        artifact.reference.sha256,
      );
    $("storyContent").replaceChildren(
      detail("Current version", artifact.reference.content_version),
      detail("Hash", artifact.reference.sha256),
    );
    for (const item of JSON.parse(artifact.payload_json).unresolved_items)
      $("storyContent").append(node("p", item, { class: "notice" }));
    $("lockPaths").value = this.run.locked_fields
      .map((item) => item.json_pointer)
      .join("\n");
  }
  loadDraft(draft, hash) {
    this.draft = structuredClone(draft);
    this.loadedDraftHash = hash;
    this.dirty = false;
    const expanded = new Set(
      [...$("storyEditor").querySelectorAll("details[open] summary")].map(
        (item) => item.textContent,
      ),
    );
    $("storyEditor").replaceChildren();
    for (const table of this.draft.package.game.locales)
      for (const entry of table.entries) {
        const input = node("textarea", "", {
          "aria-label": table.locale + " / " + entry.key,
        });
        input.value = entry.text;
        input.oninput = () => {
          entry.text = input.value;
          this.dirty = true;
          $("draftJSON").value = safeJSON(this.draft);
          this.message("Unsaved text changes.");
        };
        const details = node("details");
        details.open = expanded.has(table.locale + " · " + entry.key);
        details.append(
          node("summary", table.locale + " · " + entry.key),
          labeled("Localized text", input),
        );
        $("storyEditor").append(details);
      }
    $("draftJSON").value = safeJSON(this.draft);
  }
  renderReview() {
    const previousChoices = new Map(
      this.reviewChoices.map((item) => [
        item.target.target_id + ":" + item.target.sha256,
        { decision: item.choice.value, reason: item.reason.value },
      ]),
    );
    const pending = this.run.review_requests.find(
      (item) => item.request_id === this.run.state.pending_review_id,
    );
    const reviewSignature = JSON.stringify(pending ?? null);
    if (this.reviewSignature !== reviewSignature) {
      this.reviewSignature = reviewSignature;
      $("reviews").replaceChildren();
      this.reviewChoices = [];
      if (!pending) {
        $("reviews").append(node("p", "No pending review."));
      } else {
        $("reviews").append(node("h3", pending.gate + " review"));
        for (const target of pending.targets) {
          const article = node("article");
          article.append(
            detail("Target", target.target_id),
            detail("Version", target.version),
            detail("Hash", target.sha256),
          );
          const choice = node("select", "", {
            "aria-label": "Decision for " + target.target_id,
          });
          for (const [value, label] of [
            ["", "Choose a decision"],
            ["approved", "Approve"],
            ["changes_requested", "Request changes"],
            ["rejected", "Reject"],
          ])
            choice.append(node("option", label, { value }));
          const reason = node("input", "", {
            "aria-label": "Review reason for " + target.target_id,
          });
          const previous = previousChoices.get(
            target.target_id + ":" + target.sha256,
          );
          if (previous) {
            choice.value = previous.decision;
            reason.value = previous.reason;
          }
          article.append(
            labeled("Decision", choice),
            labeled("Reason", reason),
          );
          $("reviews").append(article);
          this.reviewChoices.push({ target, choice, reason });
        }
      }
    }
    $("reviewHistory").replaceChildren(node("h3", "Decision history"));
    $("revokeDecision").replaceChildren();
    for (const decision of this.run.review_decisions) {
      $("reviewHistory").append(
        detail(
          decision.gate + " · " + decision.decision,
          decision.target_id +
            " · " +
            decision.target_version +
            " · " +
            decision.reason,
        ),
      );
      $("revokeDecision").append(
        node("option", decision.decision_id, { value: decision.decision_id }),
      );
    }
    $("releaseSummary").replaceChildren(
      detail(
        "Private release",
        this.run.current_release_id ??
          "Not available; complete the existing gates first.",
      ),
    );
  }
  renderActivity(events, budget) {
    $("budget").textContent = safeJSON(budget);
    $("budgetSummary").replaceChildren();
    const table = node("table");
    const head = node("tr");
    for (const text of ["Usage", "Used", "Held", "Limit"])
      head.append(node("th", text));
    table.append(head);
    for (const [key, label] of Object.entries(usageLabels)) {
      const row = node("tr");
      for (const value of [
        label,
        budget.used[key],
        budget.held[key],
        budget.limit[key],
      ])
        row.append(node("td", String(value)));
      table.append(row);
    }
    $("budgetSummary").append(table);
    const unknown = budget.entries.filter(
      (item) => item.state === "unknown",
    ).length;
    $("budgetSummary").append(
      node(
        "p",
        `Unknown outcomes: ${unknown}. Held reservations are not zero usage.`,
      ),
    );
    $("events").replaceChildren();
    for (const event of events)
      $("events").append(
        detail(event.node + " / " + event.status, event.message),
      );
  }
  numberFields(container, labels, prefix, defaults) {
    for (const [name, label] of Object.entries(labels)) {
      const input = node("input", "", {
        type: "number",
        min: 0,
        step: 1,
        id: prefix + name,
      });
      input.value = defaults[name] ?? 0;
      $(container).append(labeled(label, input));
    }
  }
  numbers(labels, prefix) {
    return Object.fromEntries(
      Object.keys(labels).map((name) => {
        const value = Number($(prefix + name).value);
        if (!Number.isSafeInteger(value) || value < 0)
          throw new Error("Enter non-negative whole numbers.");
        return [name, value];
      }),
    );
  }
  requireReason(id) {
    const value = $(id).value.trim();
    if (!value) throw new Error("Enter a reason.");
    return value;
  }
  previewBinding(view) {
    const path = this.path() + "/previews/" + view.preview_id;
    return {
      kind: view.kind,
      package: view.runtime_package.game,
      hash: view.runtime_ref.sha256,
      sourceHash: view.source_ref.sha256,
      statePath: path,
      actionPath: path + "/actions",
      assetPath: path + "/assets",
      previewId: view.preview_id,
    };
  }
  async newPreview() {
    const draft = latest(this.run, "draft");
    if (!draft) throw new Error("No current draft to preview.");
    await this.command(
      this.path() + "/previews",
      { expected_revision: this.revision(), source_ref: draft.reference },
      async (view) => {
        this.player.adopt(this.previewBinding(view), view.state);
        $("previewId").value = view.preview_id;
        this.section("play");
      },
    );
  }
  async restorePreview() {
    const epoch = this.epoch;
    const id = $("previewId").value.trim();
    if (!id) throw new Error("Enter a preview ID.");
    const view = await this.api.request(
      this.path() + "/previews/" + encodeURIComponent(id),
    );
    if (epoch === this.epoch)
      this.player.adopt(this.previewBinding(view), view.state);
  }
  async openRelease() {
    const project = this.run.state.project_id;
    const epoch = this.epoch;
    const release = await this.api.request(
      "/api/v1/projects/" + project + "/release",
    );
    const prefix = "/api/v1/projects/" + project;
    const packageView = await this.api.request(
      prefix + "/releases/" + release.manifest.release_id + "/package",
    );
    if (epoch !== this.epoch) return;
    const saveId = $("saveId").value.trim();
    if (!/^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,159}$/u.test(saveId))
      throw new Error("Enter a valid save ID.");
    await this.command(
      prefix + "/player-saves",
      { save_id: saveId },
      async (result) =>
        this.player.adopt(
          {
            kind: "private release",
            package: packageView.runtime_package.game,
            hash: packageView.runtime_ref.sha256,
            statePath: prefix + "/player-saves/" + saveId,
            actionPath: prefix + "/player-saves/" + saveId + "/actions",
            assetPath:
              prefix + "/releases/" + release.manifest.release_id + "/assets",
          },
          result.state,
        ),
    );
  }
  async forkPreview() {
    if (
      !this.player.binding?.previewId ||
      this.player.pending ||
      this.player.busy
    )
      throw new Error("Open a settled draft preview first.");
    const length =
      $("replayLength").value === ""
        ? this.player.record.length
        : Number($("replayLength").value);
    if (
      !Number.isSafeInteger(length) ||
      length < 0 ||
      length > this.player.record.length
    )
      throw new Error("Choose a valid recorded prefix length.");
    if (!this.player.record.length && this.player.state.revision > 0)
      throw new Error(
        "This restored session has no recorded initial action history; open a new preview to record a replay.",
      );
    const prefix = structuredClone(this.player.record.slice(0, length));
    if (prefix[0]?.action.expected_revision > 0)
      throw new Error(
        "A restored partial history cannot prove a legal replay from the initial state.",
      );
    const oldState = structuredClone(this.player.state);
    const hash = this.player.binding.hash;
    await this.newPreview();
    if (this.player.binding.hash !== hash)
      throw new Error("Package changed; a branch cannot reuse this recording.");
    for (const request of prefix) {
      const { kind, target_id, ...parameters } = request.action;
      delete parameters.action_id;
      delete parameters.expected_revision;
      await this.player.action(kind, target_id, parameters);
      if (this.player.pending || this.player.needsReload)
        throw new Error("Replay stopped at an unconfirmed action.");
    }
    this.player.comparison = oldState;
    this.player.render();
  }
  async loadInterventions() {
    this.interventions = await this.api.request(this.path() + "/interventions");
    $("interventionDetails").textContent = safeJSON(this.interventions);
    for (const [name, value] of Object.entries(
      this.interventions.budget_policy,
    ))
      $("limit-" + name).value = value;
    $("unknownReservation").replaceChildren();
    for (const item of this.interventions.unknown_entries)
      $("unknownReservation").append(
        node("option", item.entry.operation_id, {
          value: item.entry.reservation_id,
        }),
      );
  }
  wire() {
    const bind = (id, action) => ($(id).onclick = () => this.perform(action));
    for (const item of document.querySelectorAll("nav button"))
      item.onclick = () => this.section(item.dataset.section);
    bind("connect", () => this.connect());
    $("disconnect").onclick = () => this.disconnect();
    $("retryCommand").onclick = async () => {
      if (this.busy) return;
      this.busy = true;
      try {
        await this.sendPending();
      } catch (error) {
        this.report(error);
      } finally {
        this.busy = false;
      }
    };
    $("projects").onchange = () => {
      const value = $("projects").value;
      if (value) {
        this.clearContext();
        $("projectId").value = value;
        $("runId").value = "";
        this.authorities();
      }
    };
    $("projectId").onchange = () => {
      this.clearContext();
      $("runId").value = "";
      this.authorities();
    };
    $("runId").oninput = () => {
      if (this.run && $("runId").value.trim() !== this.run.state.run_id) {
        this.clearContext();
        this.authorities();
      }
    };
    bind("createProject", () =>
      this.command(
        "/api/v1/projects",
        {
          name: $("projectName").value,
          provider: "local_manifest",
          folder_id: $("folderId").value,
          requirements: {
            project_id: $("projectId").value.trim(),
            schema_version: "0.1.0",
            content_version: "1",
            scope_site_ids: null,
            languages: ["en", "zh"],
            target_story_minutes: 5,
            theme_brief: "Review a locally authored heritage chapter",
            accessibility_requirements: ["Equivalent text observation"],
            distribution_scope: "internal_preview",
          },
        },
        async () => this.projects(),
      ),
    );
    bind("createRun", async () => {
      const project = encodeURIComponent($("projectId").value.trim());
      const policy = await this.api.request(
        "/api/v1/projects/" + project + "/policy",
      );
      await this.command(
        "/api/v1/projects/" + project + "/runs",
        {
          budget_policy: this.numbers(budgetLabels, "run-"),
          policy_ref: policy,
        },
        async (result) => {
          $("runId").value = result.state.run_id;
          await this.loadRun();
        },
      );
    });
    bind("refresh", () => this.loadRun());
    for (const action of ["cancel", "resume"])
      bind(action, () =>
        this.command(this.path() + "/" + action, {
          expected_revision: this.revision(),
          reason: this.requireReason("commandReason"),
        }),
      );
    bind("saveReviews", async () => {
      if (
        this.reviewChoices.some(
          (item) => !item.choice.value || !item.reason.value.trim(),
        )
      )
        throw new Error("Choose a decision and reason for every target.");
      const gate = this.run.review_requests.find(
        (item) => item.request_id === this.run.state.pending_review_id,
      ).gate;
      const payload = {
        expected_revision: this.revision(),
        request_id: this.run.state.pending_review_id,
        decisions: this.reviewChoices.map((item) => ({
          target_id: item.target.target_id,
          target_version: item.target.version,
          target_hash: item.target.sha256,
          decision: item.choice.value,
          reason: item.reason.value,
        })),
      };
      if (
        gate === "publication" &&
        payload.decisions.some((item) => item.decision !== "approved")
      ) {
        if (!$("reworkOwner").value)
          throw new Error(
            "Choose the responsible module for publication rework.",
          );
        payload.rework_owner = $("reworkOwner").value;
      }
      await this.command(this.path() + "/review-decisions", payload);
    });
    bind("saveStory", async () => {
      const current = latest(this.run, "draft");
      if (!this.draft || current.reference.sha256 !== this.loadedDraftHash)
        throw new Error("Reload the current draft before saving these edits.");
      await this.command(
        this.path() + "/revisions",
        {
          expected_revision: this.revision(),
          reason: this.requireReason("editReason"),
          replacement_story: this.draft,
          facts_changed: $("factsChanged").checked,
        },
        async () => {
          this.dirty = false;
          await this.loadRun();
        },
      );
    });
    bind("reloadDraft", async () => {
      const current = latest(this.run, "draft");
      if (!current) throw new Error("No saved draft is available.");
      this.dirty = false;
      this.loadDraft(
        JSON.parse(current.payload_json),
        current.reference.sha256,
      );
      this.message(
        "Edit form reloaded from the current saved draft; unsaved edits discarded.",
      );
    });
    bind("applyDraftJSON", async () => {
      const hash = this.loadedDraftHash;
      this.loadDraft(JSON.parse($("draftJSON").value), hash);
      this.dirty = true;
      this.message("Unsaved advanced draft loaded.");
    });
    bind("saveLocks", () =>
      this.command(this.path() + "/locks", {
        expected_revision: this.revision(),
        reason: this.requireReason("commandReason"),
        json_pointers: $("lockPaths")
          .value.split("\n")
          .map((value) => value.trim())
          .filter(Boolean),
      }),
    );
    bind("compareChanges", async () => {
      const before = this.run.artifacts.find(
        (item) => item.reference.sha256 === $("beforeVersion").value,
      );
      const after = latest(this.run, "draft");
      const path = this.path() + "/change-impact";
      const result = await this.api.request(
        path,
        this.api.operation(path, {
          before_ref: before.reference,
          after_ref: after.reference,
        }),
      );
      $("changeImpact").replaceChildren(
        detail("Analysis", result.status),
        node("p", result.reason),
      );
      if (result.report) {
        $("changeImpact").append(
          detail(
            "Approvals not applicable",
            result.report.invalidated_decision_ids.join(", ") || "None",
          ),
          detail(
            "Unchanged current approval identities",
            result.report.reusable_decision_ids.join(", ") || "None",
          ),
        );
      }
      for (const item of result.differences)
        $("changeImpact").append(
          detail(
            item.json_pointer,
            `${safeJSON(item.before)} → ${safeJSON(item.after)}`,
          ),
        );
      if (result.truncated)
        $("changeImpact").append(
          node("p", "Only the first 200 differences are shown."),
        );
    });
    bind("newPreview", () => this.newPreview());
    bind("restorePreview", () => this.restorePreview());
    bind("openRelease", () => this.openRelease());
    bind("forkPreview", () => this.forkPreview());
    $("gameLanguage").onchange = () =>
      this.player?.setLanguage($("gameLanguage").value);
    bind("requestNarrative", () =>
      this.command(this.path() + "/narrative-requests", {
        expected_revision: this.revision(),
        action: $("narrativeAction").value,
        feedback: this.requireReason("narrativeFeedback"),
        target_ids: $("narrativeTargets")
          .value.split("\n")
          .map((value) => value.trim())
          .filter(Boolean),
      }),
    );
    bind("revokeReview", () => {
      const decision = this.run.review_decisions.find(
        (item) => item.decision_id === $("revokeDecision").value,
      );
      return this.command(this.path() + "/review-revocations", {
        expected_revision: this.revision(),
        decision_id: decision.decision_id,
        reason: this.requireReason("revokeReason"),
      });
    });
    bind("loadInterventions", () => this.loadInterventions());
    bind("amendBudget", () => {
      if (!this.interventions) throw new Error("Load operator records first.");
      return this.command(this.path() + "/budget-amendments", {
        expected_revision: this.revision(),
        budget_hash: this.interventions.budget_hash,
        budget_policy: this.numbers(budgetLabels, "limit-"),
        reason: this.requireReason("budgetReason"),
      });
    });
    bind("reconcileUsage", () => {
      const target = this.interventions?.unknown_entries.find(
        (item) => item.entry.reservation_id === $("unknownReservation").value,
      );
      if (!target) throw new Error("Select an unknown reservation.");
      return this.command(this.path() + "/usage-reconciliations", {
        expected_revision: this.revision(),
        reservation_id: target.entry.reservation_id,
        entry_hash: target.entry_hash,
        action: $("resolutionAction").value,
        settlement: {
          actual: this.numbers(usageLabels, "actual-"),
          provider_request_id: $("providerRequestId").value.trim() || null,
          source: "operator",
        },
        evidence: {
          kind: $("evidenceKind").value,
          reference: this.requireReason("evidenceReference"),
          description: this.requireReason("evidenceDescription"),
        },
        reason: this.requireReason("reconciliationReason"),
      });
    });
    bind("loadRevocations", async () => {
      const reviews = await this.api.request(this.path() + "/reviews");
      $("revokedDecision").replaceChildren();
      for (const decision of reviews.decisions)
        if (reviews.revoked_decision_ids.includes(decision.decision_id))
          $("revokedDecision").append(
            node("option", decision.gate + " · " + decision.decision_id, {
              value: decision.decision_id,
            }),
          );
    });
    bind("resubmitReview", () =>
      this.command(this.path() + "/review-resubmissions", {
        expected_revision: this.revision(),
        decision_id: $("revokedDecision").value,
        reason: this.requireReason("resubmissionReason"),
      }),
    );
  }
}

const workbench = new WorkbenchController();
window.addEventListener("pagehide", () => workbench.disconnect());
