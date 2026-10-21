/** Deterministic synthetic reference plugin. No historical or live-model validation. */
const fail = (message) => { throw new Error(message); };
const clone = (value) => JSON.parse(JSON.stringify(value));
const freeze = (value) => {
  if (value && typeof value === "object") {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
};
export function validateConfig(config) {
  if (!config || !Array.isArray(config.pairs) || config.pairs.length < 1 || config.pairs.length > 8) fail("Invalid pair count");
  for (const key of ["left_id", "right_id"]) {
    const ids = config.pairs.map((pair) => pair[key]);
    if (ids.some((id) => typeof id !== "string" || !/^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$/.test(id)) || new Set(ids).size !== ids.length) fail("Invalid or duplicate pair identity");
  }
  return true;
}
export function validateState(config, state) {
  validateConfig(config);
  if (!state || !Array.isArray(state.matched_left_ids) || !Number.isSafeInteger(state.attempts) || state.attempts < 0) fail("Invalid plugin state");
  if (new Set(state.matched_left_ids).size !== state.matched_left_ids.length || state.matched_left_ids.some((id) => !config.pairs.some((pair) => pair.left_id === id))) fail("Invalid matched identity");
  if (state.attempts < state.matched_left_ids.length) fail("State attempts cannot precede progress");
  return true;
}
export function initialize(config, _context) {
  validateConfig(config);
  return freeze({ matched_left_ids: [], attempts: 0 });
}
export function result(config, state) {
  validateState(config, state);
  const complete = state.matched_left_ids.length === config.pairs.length;
  return freeze({ status: complete ? "completed" : "running", outcome: complete ? "passed" : null, score: state.matched_left_ids.length });
}
export function reduce(config, state, action, _context) {
  validateState(config, state);
  if (!action || action.type !== "select_pair" || Object.keys(action).sort().join(",") !== "left_id,right_id,type") fail("Unsupported plugin action");
  const pair = config.pairs.find((item) => item.left_id === action.left_id);
  if (!pair || !config.pairs.some((item) => item.right_id === action.right_id)) fail("Action identity is unknown");
  const next = clone(state);
  if (!next.matched_left_ids.includes(pair.left_id)) {
    if (next.attempts >= Number.MAX_SAFE_INTEGER) fail("Attempt limit exhausted");
    next.attempts += 1;
    if (pair.right_id === action.right_id) next.matched_left_ids = [...next.matched_left_ids, pair.left_id].sort();
  }
  validateState(config, next);
  return freeze({ state: next, result: result(config, next) });
}
export function serialize(config, state) {
  validateState(config, state);
  return JSON.stringify({ matched_left_ids: [...state.matched_left_ids].sort(), attempts: state.attempts });
}
export function restore(config, snapshot, _context) {
  if (typeof snapshot !== "string" || snapshot.length > 65536) fail("Invalid snapshot size");
  const state = JSON.parse(snapshot);
  validateState(config, state);
  if (Object.keys(state).sort().join(",") !== "attempts,matched_left_ids") fail("Unknown snapshot field");
  return freeze(state);
}
