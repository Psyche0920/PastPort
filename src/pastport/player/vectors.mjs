// Node-only conformance harness; the runtime itself has no filesystem imports.
import { readFile, readdir } from "node:fs/promises";
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import { applyAction } from "./runtime.mjs";
import { contentHash } from "./validation.mjs";

export async function runVectors(directory) {
  const packages = await Promise.all(["runtime.json", "conflict-runtime.json"].map(async name => {
    const packageData = JSON.parse(await readFile(new URL(name, directory), "utf8"));
    return { packageData, hash: await contentHash(packageData) };
  }));
  const paths = (await readdir(directory)).filter(name => /^vector-.*\.json$/u.test(name)).sort();
  assert.equal(paths.length, 5, "The five frozen vectors must all execute");
  const results = [];
  for (const path of paths) {
    const vector = JSON.parse(await readFile(new URL(path, directory), "utf8"));
    const chosen = packages.find(item => item.hash === vector.initial_state.package_hash);
    assert.ok(chosen, "Vector requires a known package hash");
    const packageData = chosen.packageData;
    const reference = { artifact_id: "vector-runtime", project_id: packageData.project_id, kind: "runtime", schema_version: packageData.schema_version, content_version: packageData.content_version, sha256: chosen.hash };
    let state = structuredClone(vector.initial_state);
    let errorCode = null;
    for (const request of vector.actions) {
      const before = structuredClone(state);
      try {
        state = (await applyAction({ operation: "apply_action", package: packageData, reference, release_id: state.release_id, state, action_request: request })).state;
      } catch (error) {
        assert.deepEqual(state, before, "Failed action must leave its input unchanged");
        errorCode = error.code;
        break;
      }
    }
    assert.equal(errorCode, vector.expected_error, `${vector.vector_id} error differs`);
    if (vector.expected_state !== null) assert.deepEqual(state, vector.expected_state, `${vector.vector_id} state differs`);
    results.push({ vector_id: vector.vector_id, status: "passed" });
  }
  return results;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const directory = new URL("../../../tests/fixtures/reference/", import.meta.url);
  console.log(JSON.stringify({ action_vectors: await runVectors(directory) }));
}
