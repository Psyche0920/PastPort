import { schemas } from "./generated-schemas.mjs";
import { PlayerError, requirePlayer } from "./errors.mjs";

class SchemaMismatch extends Error {}
const mismatch = () => { throw new SchemaMismatch(); };

/** Implements only the explicitly generated schema vocabulary, with bounded traversal. */
export class SchemaValidator {
  constructor(root = schemas.PlayerComponentCommand) {
    this.root = root;
  }

  assertDefinition(name, value, code = "PLAYER_INPUT_INVALID") {
    requirePlayer(Object.hasOwn(this.root.$defs, name), "PLAYER_SCHEMA_UNSUPPORTED", "Unknown component definition");
    this.assertSchema(this.root.$defs[name], value, code);
  }

  assertSchema(schema, value, code = "PLAYER_INPUT_INVALID") {
    const budget = { visits: 0 };
    try {
      this.check(schema, value, 0, budget);
    } catch (error) {
      if (!(error instanceof SchemaMismatch)) throw error;
      throw new PlayerError(code, "Component input failed its generated schema");
    }
  }

  check(schema, value, depth, budget) {
    budget.visits += 1;
    requirePlayer(depth <= 160 && budget.visits <= 100000, "PLAYER_INPUT_TOO_COMPLEX", "Component input exceeds validation limits");
    if (schema.$ref) {
      requirePlayer(schema.$ref.startsWith("#/$defs/"), "PLAYER_SCHEMA_UNSUPPORTED", "External schemas are not supported");
      return this.check(this.root.$defs[schema.$ref.slice(8)], value, depth + 1, budget);
    }
    for (const keyword of ["anyOf", "oneOf"]) {
      if (!schema[keyword]) continue;
      let matches = 0;
      for (const option of schema[keyword]) {
        try { this.check(option, value, depth + 1, budget); matches += 1; }
        catch (error) { if (!(error instanceof SchemaMismatch)) throw error; }
      }
      if (matches === 0 || (keyword === "oneOf" && matches !== 1)) mismatch();
      return;
    }
    if (Object.hasOwn(schema, "const") && value !== schema.const) mismatch();
    if (schema.enum && !schema.enum.includes(value)) mismatch();
    if (schema.type === "null" && value !== null) mismatch();
    if (schema.type === "boolean" && typeof value !== "boolean") mismatch();
    if (schema.type === "integer") {
      if (!Number.isSafeInteger(value)) mismatch();
      if (schema.minimum !== undefined && value < schema.minimum) mismatch();
      if (schema.maximum !== undefined && value > schema.maximum) mismatch();
      if (schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum) mismatch();
    }
    if (schema.type === "string") {
      if (typeof value !== "string" || /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(value)) mismatch();
      const length = Array.from(value).length;
      if (schema.minLength !== undefined && length < schema.minLength) mismatch();
      if (schema.maxLength !== undefined && length > schema.maxLength) mismatch();
      if (schema.pattern && !(new RegExp(schema.pattern, "u")).test(value)) mismatch();
    }
    if (schema.type === "array") {
      if (!Array.isArray(value)) mismatch();
      if (schema.minItems !== undefined && value.length < schema.minItems) mismatch();
      if (schema.maxItems !== undefined && value.length > schema.maxItems) mismatch();
      for (const item of value) this.check(schema.items, item, depth + 1, budget);
    }
    if (schema.type === "object") {
      if (value === null || typeof value !== "object" || Array.isArray(value)) mismatch();
      for (const key of schema.required ?? []) if (!Object.hasOwn(value, key)) mismatch();
      for (const [key, item] of Object.entries(value)) {
        if (Object.hasOwn(schema.properties ?? {}, key)) this.check(schema.properties[key], item, depth + 1, budget);
        else if (schema.additionalProperties === false) mismatch();
      }
    }
  }
}

export function freezeData(value) {
  if (value !== null && typeof value === "object") {
    for (const item of Object.values(value)) freezeData(item);
    Object.freeze(value);
  }
  return value;
}

export function sortedUnique(values) { return [...new Set(values)].sort(); }
export function sameSet(left, right) {
  return left.length === new Set(left).size && right.length === new Set(right).size && left.length === right.length && left.every(value => right.includes(value));
}

function compareCodePoints(left, right) {
  const a = Array.from(left, character => character.codePointAt(0));
  const b = Array.from(right, character => character.codePointAt(0));
  for (let index = 0; index < Math.min(a.length, b.length); index += 1) {
    if (a[index] !== b[index]) return a[index] - b[index];
  }
  return a.length - b.length;
}

export function canonicalJSON(value) {
  if (Array.isArray(value)) return "[" + value.map(canonicalJSON).join(",") + "]";
  if (value !== null && typeof value === "object") {
    return "{" + Object.keys(value).sort(compareCodePoints).map(key => JSON.stringify(key) + ":" + canonicalJSON(value[key])).join(",") + "}";
  }
  requirePlayer(typeof value !== "number" || Number.isSafeInteger(value), "PLAYER_INPUT_INVALID", "Only safe integer values are supported");
  return JSON.stringify(value);
}

export async function contentHash(value) {
  requirePlayer(Boolean(globalThis.crypto?.subtle), "PLAYER_RUNTIME_UNAVAILABLE", "Web Crypto is required for package identity");
  const digest = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonicalJSON(value)));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
}
