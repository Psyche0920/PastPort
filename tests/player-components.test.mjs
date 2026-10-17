import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { PlayerContext } from "../src/pastport/player/context.mjs";
import { ActionHandler } from "../src/pastport/player/actions.mjs";
import { ConditionEvaluator, EffectEvaluator, RuleMatcher } from "../src/pastport/player/rules.mjs";
import { contentHash, canonicalJSON } from "../src/pastport/player/validation.mjs";
import { prepare } from "../src/pastport/player/preparation.mjs";

const fixture = JSON.parse(await readFile(new URL("./fixtures/reference/runtime.json", import.meta.url), "utf8"));
const initial = JSON.parse(await readFile(new URL("./fixtures/reference/player-state.json", import.meta.url), "utf8"));
async function context(packageData = fixture) {
  return PlayerContext.create(packageData, { artifact_id: "runtime-fixture", kind: "runtime", project_id: packageData.project_id, schema_version: packageData.schema_version, content_version: packageData.content_version, sha256: await contentHash(packageData) }, "release-test-1");
}
const request = (state, action) => ({ project_id: state.project_id, release_id: state.release_id, package_hash: state.package_hash, action: { action_id: "test-action", expected_revision: state.revision, ...action } });
const observe = { kind: "observe", target_id: "inspect-hatch", spot_id: "hatch" };
const choose = { kind: "choose", target_id: "witness-choice", option_id: "help" };
const code = expected => error => error.code === expected;

async function inspected() {
  const ctx = await context();
  const proposal = await new ActionHandler(ctx).propose(ctx.initialState(), request(ctx.initialState(), observe));
  return { ctx, state: proposal.state };
}

test("Python hash parity, Unicode canonicalization and immutable initialization", async () => {
  const ctx = await context();
  assert.equal(ctx.reference.sha256, initial.package_hash);
  assert.deepEqual(ctx.initialState(), initial);
  assert.ok(Object.isFrozen(ctx.initialState().variables[0]));
  assert.equal(canonicalJSON({ "\u{10000}": "汉字", "\ue000": 2 }), '{"":2,"𐀀":"汉字"}');
  assert.throws(() => canonicalJSON({ number: 1.5 }), code("PLAYER_INPUT_INVALID"));
});

test("all eight condition kinds use strict scalar equality and elapsed greater-than", () => {
  const evaluate = new ConditionEvaluator();
  const state = structuredClone(initial);
  state.observations = [{ scene_id: "observe-scene", spot_ids: ["hatch"] }];
  state.decisions = [{ decision_id: "witness-choice", option_id: "help" }];
  state.inventory = ["delivery-note"]; state.elapsed_minutes = 2;
  const trueConditions = [
    { kind: "observed_all", scene_id: "observe-scene", spot_ids: ["hatch"] },
    { kind: "choice_equals", decision_id: "witness-choice", option_id: "help" },
    { kind: "variable_equals", name: "witness", value: false },
    { kind: "has_evidence", item_id: "delivery-note" }, { kind: "elapsed_gt", minutes: 1 },
  ];
  for (const condition of trueConditions) assert.equal(evaluate.evaluate(condition, state), true);
  assert.equal(evaluate.evaluate({ kind: "all", conditions: trueConditions }, state), true);
  assert.equal(evaluate.evaluate({ kind: "any", conditions: trueConditions }, state), true);
  assert.equal(evaluate.evaluate({ kind: "not", condition: trueConditions[0] }, state), false);
  assert.equal(evaluate.evaluate({ kind: "elapsed_gt", minutes: 2 }, state), false);
  assert.equal(evaluate.evaluate({ kind: "variable_equals", name: "witness", value: 0 }, state), false);
  let nested = trueConditions[0];
  for (let count = 0; count < 8; count++) nested = { kind: "not", condition: nested };
  assert.throws(() => evaluate.evaluate(nested, state), code("PLAYER_CONDITION_DEPTH"));
});

test("rule matching has stable priority/ASCII order, one snapshot and once filtering", async () => {
  const pkg = structuredClone(fixture);
  const template = pkg.game.rules[0];
  pkg.game.rules = [
    { ...template, rule_id: "z", once_key: "once:z", priority: 0 },
    { ...template, rule_id: "A", once_key: "once:A", priority: 0 },
    { ...template, rule_id: "first", once_key: "once:first", priority: 1 },
  ];
  const ctx = await context(pkg);
  const state = structuredClone(ctx.initialState());
  state.observations = [{ scene_id: "observe-scene", spot_ids: ["hatch"] }];
  const before = structuredClone(state);
  const matcher = new RuleMatcher(ctx);
  const event = { event_id: "test-event", kind: "task_completed", target_id: "inspect-hatch" };
  assert.deepEqual(matcher.match(state, event).map(item => item.rule_id), ["A", "z", "first"]);
  assert.deepEqual(state, before);
  state.applied_rule_keys = ["once:A"];
  assert.deepEqual(matcher.match(state, event).map(item => item.rule_id), ["z", "first"]);
  pkg.game.rules = Array.from({ length: 65 }, (_, index) => ({ ...template, rule_id: `rule-${index}`, once_key: `once:${index}` }));
  const large = await context(pkg);
  assert.throws(() => new RuleMatcher(large).match({ ...state, applied_rule_keys: [] }, event), code("PLAYER_EFFECT_LIMIT"));
});

test("single effects preserve input, types, safe time and unlock without movement", async () => {
  const ctx = await context(); const state = ctx.initialState(); const effects = new EffectEvaluator(ctx);
  assert.deepEqual(effects.evaluate(state, { kind: "grant_item", item_id: "delivery-note" }).state.inventory, ["delivery-note"]);
  assert.equal(state.inventory.length, 0);
  assert.equal(effects.evaluate(state, { kind: "set_variable", name: "witness", value: true }).state.variables[0].value, true);
  assert.throws(() => effects.evaluate(state, { kind: "set_variable", name: "witness", value: 1 }), code("PLAYER_VARIABLE_TYPE"));
  assert.throws(() => effects.evaluate(state, { kind: "set_relationship", name: "witness", value: true }), code("PLAYER_VARIABLE_TYPE"));
  assert.equal(effects.evaluate(state, { kind: "add_story_time", minutes: 2 }).state.elapsed_minutes, 2);
  assert.throws(() => effects.evaluate({ ...state, elapsed_minutes: Number.MAX_SAFE_INTEGER }, { kind: "add_story_time", minutes: 1 }), code("PLAYER_TIME_OVERFLOW"));
  const unlocked = effects.evaluate(state, { kind: "unlock_scene", scene_id: "later-scene" }).state;
  assert.equal(unlocked.current_scene_id, "observe-scene"); assert.ok(unlocked.unlocked_scene_ids.includes("later-scene"));
  assert.throws(() => effects.evaluate(state, { kind: "grant_item", item_id: "invented" }), code("PLAYER_REFERENCE_INVALID"));
  const pkg = structuredClone(fixture); pkg.game.variables.push({ name: "relationship", initial: "neutral" });
  const other = await context(pkg);
  assert.equal(new EffectEvaluator(other).evaluate(other.initialState(), { kind: "set_relationship", name: "relationship", value: "friendly" }).state.variables.find(item => item.name === "relationship").value, "friendly");
});

test("ending fallback and guarded variants are deterministic", async () => {
  const { ctx, state } = await inspected();
  const chosen = (await new ActionHandler(ctx).propose(state, request(state, choose))).state;
  const effect = { kind: "resolve_ending", ending_table_id: "delivery-endings" };
  assert.deepEqual(new EffectEvaluator(ctx).evaluate(chosen, effect).feedback_keys, ["outcome-label", "outcome-help"]);
  assert.deepEqual(new EffectEvaluator(ctx).evaluate(state, effect).feedback_keys, ["outcome-label", "outcome-base"]);
});

test("handlers enforce scene progress, target, locked scenes and repeat semantics", async () => {
  const ctx = await context(); const handler = new ActionHandler(ctx); const state = ctx.initialState();
  await assert.rejects(handler.propose(state, request(state, choose)), code("PLAYER_TASK_INCOMPLETE"));
  await assert.rejects(handler.propose(state, request(state, { ...observe, spot_id: "invented" })), code("PLAYER_REFERENCE_INVALID"));
  await assert.rejects(handler.propose(state, request(state, { ...observe, expected_revision: 1 })), code("PLAYER_STALE_REVISION"));
  const observed = await handler.propose(state, request(state, observe));
  assert.deepEqual(observed.emitted_events.map(item => item.kind), ["spot_observed", "task_completed"]);
  assert.equal(observed.state.revision, 0); assert.deepEqual(observed.state.processed_actions, []);
  assert.deepEqual((await handler.propose(observed.state, request(state, observe))).emitted_events, []);
  const chosen = await handler.propose(observed.state, request(state, choose));
  assert.deepEqual((await handler.propose(chosen.state, request(state, choose))).emitted_events, []);
  await assert.rejects(handler.propose(chosen.state, request(state, { ...choose, option_id: "hurry" })), code("PLAYER_DECISION_FINAL"));
  await assert.rejects(handler.propose(chosen.state, request(state, { kind: "advance", target_id: "later-scene" })), code("PLAYER_SCENE_LOCKED"));
  const unlocked = new EffectEvaluator(ctx).evaluate(chosen.state, { kind: "unlock_scene", scene_id: "later-scene" }).state;
  const advanced = await handler.propose(unlocked, request(state, { kind: "advance", target_id: "later-scene" }));
  assert.equal(advanced.state.current_scene_id, "later-scene"); assert.deepEqual(advanced.emitted_events, []);
  const submit = { kind: "submit_evidence", target_id: "check-record", prop_ids: ["delivery-note"] };
  await assert.rejects(handler.propose(advanced.state, request(state, submit)), code("PLAYER_EVIDENCE_INVALID"));
  const held = new EffectEvaluator(ctx).evaluate(advanced.state, { kind: "grant_item", item_id: "delivery-note" }).state;
  await assert.rejects(handler.propose(held, request(state, { ...submit, prop_ids: ["delivery-note", "delivery-note"] })), code("PLAYER_EVIDENCE_INVALID"));
  const board = await handler.propose(held, request(state, submit));
  assert.deepEqual(board.emitted_events.map(item => item.kind), ["board_submitted", "task_completed"]);
  assert.deepEqual((await handler.propose(board.state, request(state, submit))).emitted_events, []);
});

test("preparation rejects wrong identity, unsupported profile and excessive command fields", async () => {
  const ctx = await context();
  const command = { operation: "initialize", package: fixture, reference: ctx.reference, release_id: "release-test-1" };
  const result = await prepare(command); assert.equal(result.committed, false);
  await assert.rejects(prepare({ ...command, state: initial }), code("PLAYER_COMMAND_INVALID"));
  await assert.rejects(prepare({ ...command, reference: { ...ctx.reference, sha256: "0".repeat(64) } }), code("PLAYER_HASH_MISMATCH"));
  const unsupported = structuredClone(fixture); unsupported.runtime_compatibility.max_events_per_action = 3;
  await assert.rejects(context(unsupported), code("PLAYER_CAPABILITY_UNSUPPORTED"));
  assert.throws(() => ctx.validateState({ ...initial, release_id: "other" }), code("PLAYER_IDENTITY_MISMATCH"));
  assert.throws(() => ctx.validateState({ ...initial, variables: [{ name: "witness", value: 0 }] }), code("PLAYER_STATE_INVALID"));
});
