import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { PlayerContext } from "../src/pastport/player/context.mjs";
import { PlayerRuntime, applyAction } from "../src/pastport/player/runtime.mjs";
import { contentHash } from "../src/pastport/player/validation.mjs";
import { runVectors } from "../src/pastport/player/vectors.mjs";

const fixture = JSON.parse(await readFile(new URL("./fixtures/reference/runtime.json", import.meta.url), "utf8"));
const code = expected => error => error.code === expected;
async function runtime(change = () => {}) {
  const pkg = structuredClone(fixture); change(pkg.game);
  const reference = { artifact_id: "runtime-test", project_id: pkg.project_id, kind: "runtime", schema_version: pkg.schema_version, content_version: pkg.content_version, sha256: await contentHash(pkg) };
  const ctx = await PlayerContext.create(pkg, reference, "release-test-1");
  return { ctx, engine: new PlayerRuntime(ctx), state: ctx.initialState() };
}
const action = (state, kind, target, fields = {}, id = `${kind}-${state.revision}`) => ({ project_id: state.project_id, release_id: state.release_id, package_hash: state.package_hash, action: { kind, target_id: target, action_id: id, expected_revision: state.revision, ...fields } });
const observe = state => action(state, "observe", "inspect-hatch", { spot_id: "hatch" });
const choose = state => action(state, "choose", "witness-choice", { option_id: "help" });
const rawRule = (id, effects, guard = { kind: "observed_all", scene_id: "observe-scene", spot_ids: ["hatch"] }) => ({ rule_id: id, priority: 0, event: "spot_observed", target_id: "inspect-hatch", guard, effects, once_key: `once:${id}` });

test("all five frozen action vectors execute without modifying fixture flags", async () => {
  const results = await runVectors(new URL("./fixtures/reference/", import.meta.url));
  assert.equal(results.length, 5); assert.ok(results.every(item => item.status === "passed"));
});

test("whole chapter, late stale replay and conflicting payload preserve current state", async () => {
  const { engine, state } = await runtime(); const first = observe(state);
  let current = (await engine.apply(state, first)).state;
  current = (await engine.apply(current, choose(current))).state;
  assert.equal(current.elapsed_minutes, 2); assert.equal(current.current_scene_id, "observe-scene");
  current = (await engine.apply(current, action(current, "advance", "later-scene"))).state;
  const ended = await engine.apply(current, action(current, "submit_evidence", "check-record", { prop_ids: ["delivery-note"] }));
  assert.equal(ended.state.ending_id, "default"); assert.equal(ended.state.revision, 4);
  assert.ok(ended.feedback_keys.includes("outcome-help"));
  const replay = await engine.apply(ended.state, first);
  assert.deepEqual(replay.state, ended.state); assert.deepEqual(replay.feedback_keys, ["observe-feedback"]);
  assert.deepEqual(replay.emitted_events, []); assert.deepEqual(replay.trace, []);
  await assert.rejects(engine.apply(ended.state, { ...first, action: { ...first.action, expected_revision: 4 } }), code("ACTION_ID_CONFLICT"));
  assert.equal(state.revision, 0); assert.deepEqual(state.processed_actions, []);
});

test("semantic repeats create new receipts without time, effects or duplicate events", async () => {
  const { engine, state } = await runtime();
  const seen = (await engine.apply(state, observe(state))).state;
  const repeat = await engine.apply(seen, observe(seen));
  assert.deepEqual(repeat.emitted_events, []); assert.deepEqual(repeat.trace, []);
  assert.deepEqual(repeat.state.inventory, ["delivery-note"]); assert.equal(repeat.state.revision, 2);
  const chosen = (await engine.apply(repeat.state, choose(repeat.state))).state;
  const same = await engine.apply(chosen, choose(chosen));
  assert.equal(same.state.elapsed_minutes, 2); assert.deepEqual(same.trace, []);
  assert.deepEqual(same.state.applied_rule_keys, chosen.applied_rule_keys);
});

test("one event uses one guard snapshot; later FIFO event sees previous effects", async () => {
  const { engine, state } = await runtime(game => {
    game.rules.push(rawRule("raw-set", [{ kind: "set_variable", name: "witness", value: true }]));
    game.rules.push({ ...rawRule("later-time", [{ kind: "add_story_time", minutes: 3 }], { kind: "variable_equals", name: "witness", value: true }), event: "task_completed" });
    game.rules.push({ ...rawRule("same-event-hidden", [{ kind: "add_story_time", minutes: 100 }], { kind: "variable_equals", name: "witness", value: true }), priority: 1 });
  });
  const result = await engine.apply(state, observe(state));
  assert.equal(result.state.elapsed_minutes, 3);
  assert.deepEqual(result.trace.map(item => item.rule_id), ["raw-set", "grant-note", "later-time"]);
});

test("writes conflict across the whole action and rollback all handler/effect/receipt mutations", async () => {
  const { engine, state } = await runtime(game => {
    game.rules.push(rawRule("raw-set", [{ kind: "set_variable", name: "witness", value: true }]));
    game.rules.push({ ...rawRule("later-reset", [{ kind: "set_variable", name: "witness", value: false }]), event: "task_completed" });
  });
  const before = structuredClone(state);
  await assert.rejects(engine.apply(state, observe(state)), code("EFFECT_CONFLICT"));
  assert.deepEqual(state, before);
});

test("same values merge and the 64-effect limit covers all events together", async () => {
  const merged = await runtime(game => {
    game.rules.push(rawRule("same-one", [{ kind: "set_variable", name: "witness", value: true }]));
    game.rules.push(rawRule("same-two", [{ kind: "set_variable", name: "witness", value: true }]));
  });
  assert.equal((await merged.engine.apply(merged.state, observe(merged.state))).state.variables[0].value, true);
  const bounded = await runtime(game => {
    for (const id of ["raw-many-a", "raw-many-b"]) game.rules.push(rawRule(id, Array.from({ length: 32 }, () => ({ kind: "add_story_time", minutes: 1 }))));
  });
  await assert.rejects(bounded.engine.apply(bounded.state, observe(bounded.state)), code("PLAYER_EFFECT_LIMIT"));
  assert.equal(bounded.state.elapsed_minutes, 0); assert.equal(bounded.state.revision, 0);
});

test("incompatible ending resolutions conflict; same ending and variant order are deterministic", async () => {
  const changed = await runtime(game => {
    const copy = structuredClone(game.endings[0]); copy.ending_table_id = "other-table"; copy.endings[0].ending_id = "other-ending";
    game.endings.push(copy);
    game.rules.push(rawRule("ending-one", [{ kind: "resolve_ending", ending_table_id: "delivery-endings" }]));
    game.rules.push(rawRule("ending-two", [{ kind: "resolve_ending", ending_table_id: "other-table" }]));
  });
  await assert.rejects(changed.engine.apply(changed.state, observe(changed.state)), code("EFFECT_CONFLICT"));
  const ordered = await runtime(game => {
    const base = game.endings[0].endings[0];
    game.endings[0].endings.unshift(...["z", "A"].map(id => ({ ...structuredClone(base), ending_id: id, priority: 0, fallback: false, guard: { kind: "observed_all", scene_id: "observe-scene", spot_ids: ["hatch"] } })));
    game.rules.push(rawRule("finish", [{ kind: "resolve_ending", ending_table_id: "delivery-endings" }]));
  });
  assert.equal((await ordered.engine.apply(ordered.state, observe(ordered.state))).state.ending_id, "A");
});

test("English and Chinese use the same action sequence and runtime output", async () => {
  const { ctx, state } = await runtime(); const command = { operation: "apply_action", package: ctx.package, reference: ctx.reference, release_id: ctx.releaseId, state, action_request: observe(state) };
  const outputs = [];
  for (const locale of ["en", "zh"]) {
    assert.ok(ctx.game.locales.some(item => item.locale === locale));
    outputs.push(await applyAction(command));
  }
  assert.deepEqual(outputs[0], outputs[1]);
});

test("max-length action identities stay distinct and inconsistent revisions never commit", async () => {
  const { engine, state } = await runtime();
  const first = await engine.apply(state, action(state, "observe", "inspect-hatch", { spot_id: "hatch" }, "a".repeat(160)));
  assert.ok(first.emitted_events.every(event => event.event_id.length <= 160));
  await assert.rejects(engine.apply(first.state, observe(state)), code("STATE_STALE"));
  await assert.rejects(engine.apply({ ...state, revision: Number.MAX_SAFE_INTEGER }, action({ ...state, revision: Number.MAX_SAFE_INTEGER }, "observe", "inspect-hatch", { spot_id: "hatch" })), code("PLAYER_STATE_INVALID"));
});

test("task guards, unheld evidence and ended chapters reject fresh actions without changes", async () => {
  const guarded = await runtime(game => {
    game.scenes[0].tasks[0].guard = { kind: "has_evidence", item_id: "delivery-note" };
  });
  await assert.rejects(guarded.engine.apply(guarded.state, observe(guarded.state)), code("PLAYER_TASK_LOCKED"));
  assert.equal(guarded.state.revision, 0);
  const ended = await runtime(game => {
    game.rules.push(rawRule("finish-now", [{ kind: "resolve_ending", ending_table_id: "delivery-endings" }]));
  });
  const final = (await ended.engine.apply(ended.state, observe(ended.state))).state;
  await assert.rejects(ended.engine.apply(final, observe(final)), code("PLAYER_ALREADY_ENDED"));
});

test("exactly 64 effects succeed; relationship writes share the same conflict identity", async () => {
  const exact = await runtime(game => {
    game.rules = ["a", "b"].map(id => rawRule(id, Array.from({ length: 32 }, () => ({ kind: "add_story_time", minutes: 1 }))));
  });
  assert.equal((await exact.engine.apply(exact.state, observe(exact.state))).state.elapsed_minutes, 64);
  const conflict = await runtime(game => {
    game.variables.push({ name: "friendship", initial: "neutral" });
    game.rules.push(rawRule("friendship-a", [{ kind: "set_variable", name: "friendship", value: "good" }]));
    game.rules.push(rawRule("friendship-b", [{ kind: "set_relationship", name: "friendship", value: "bad" }]));
  });
  await assert.rejects(conflict.engine.apply(conflict.state, observe(conflict.state)), code("EFFECT_CONFLICT"));
});


test("legacy action IDs cannot alias digest-based event identities", async () => {
  const { engine, state } = await runtime();
  const first = action(state, "observe", "inspect-hatch", { spot_id: "hatch" }, "a".repeat(160));
  const seen = (await engine.apply(state, first)).state;
  const alias = `event:${await contentHash(first.action)}`;
  const next = await engine.apply(seen, action(seen, "choose", "witness-choice", { option_id: "help" }, alias));
  const identities = next.state.processed_actions.flatMap(receipt => receipt.event_ids);
  assert.equal(new Set(identities).size, identities.length);
  assert.ok(next.emitted_events[0].event_id !== seen.processed_actions[0].event_ids[0]);
});
