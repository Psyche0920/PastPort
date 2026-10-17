import test from "node:test";
import assert from "node:assert/strict";
import { ApiClient, ApiError } from "../src/pastport/api/api-client.mjs";

test("uncertain result retries use exactly the same payload and operation identity", async () => {
  const requests = [];
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async (path, options) => {
      requests.push({
        path,
        body: options.body,
        key: options.headers["Idempotency-Key"],
        authorization: options.headers.Authorization,
      });
      if (requests.length === 1) throw new TypeError("Network disconnected");
      return new Response(JSON.stringify({ persisted: true }), { status: 200 });
    };
    const client = new ApiClient("memory-only-token");
    const payload = { expected_revision: 2, action_id: "original" };
    const operation = client.operation(
      "/api/v1/runs/run-1/previews",
      payload,
      "same-key",
    );
    payload.expected_revision = 3;
    await assert.rejects(
      client.request(operation.path, operation),
      /Network disconnected/u,
    );
    assert.deepEqual(await client.request(operation.path, operation), {
      persisted: true,
    });
    assert.deepEqual(requests[0], requests[1]);
    assert.equal(JSON.parse(requests[1].body).expected_revision, 2);
    assert.equal(requests[1].authorization, "Bearer memory-only-token");
    client.disconnect();
    await assert.rejects(client.request("/api/v1/session"), /Connect/u);
  } finally {
    globalThis.fetch = original;
  }
});

test("both server error envelopes work and no silent stale request rewrite occurs", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () =>
      new Response(
        JSON.stringify({
          code: "STATE_STALE",
          message: "Reload before retry",
          owner: "runtime",
          retryable: false,
        }),
        { status: 409 },
      );
    await assert.rejects(
      new ApiClient("token").request("/api/v1/session"),
      (error) =>
        error instanceof ApiError &&
        error.code === "STATE_STALE" &&
        error.status === 409 &&
        !error.retryable,
    );
  } finally {
    globalThis.fetch = original;
  }
});

test("client rejects external/path traversal targets and disconnect aborts pending requests", async () => {
  const original = globalThis.fetch;
  try {
    const client = new ApiClient("secret");
    let count = 0;
    globalThis.fetch = async (path, options) => {
      count++;
      return new Promise((resolve, reject) =>
        options.signal.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        ),
      );
    };
    for (const path of [
      "https://other.invalid",
      "//other.invalid",
      "/api/v1/../session",
      "/api/v1/%2e%2e/session",
      "/api/v1/\\host",
    ]) {
      await assert.rejects(client.request(path));
    }
    assert.equal(count, 0);
    const pending = client.request("/api/v1/session");
    client.disconnect();
    await assert.rejects(pending, (error) => error.name === "AbortError");
    assert.equal(count, 1);
  } finally {
    globalThis.fetch = original;
  }
});

test("hung requests abort within a configured bound while the original operation remains reusable", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async (_path, options) =>
      new Promise((_resolve, reject) => {
        options.signal.addEventListener(
          "abort",
          () => reject(new DOMException("Aborted", "AbortError")),
          { once: true },
        );
      });
    const client = new ApiClient("token", 5);
    const operation = client.operation(
      "/api/v1/runs/run-1/previews",
      { expected_revision: 1 },
      "timeout-key",
    );
    await assert.rejects(
      client.request(operation.path, operation),
      (error) => error.name === "AbortError",
    );
    assert.equal(operation.requestKey, "timeout-key");
    globalThis.fetch = async () =>
      new Response(JSON.stringify({ persisted: true }));
    assert.deepEqual(await client.request(operation.path, operation), {
      persisted: true,
    });
    client.disconnect();
    assert.throws(() => new ApiClient("token", 0), /timeout/u);
  } finally {
    globalThis.fetch = original;
  }
});
