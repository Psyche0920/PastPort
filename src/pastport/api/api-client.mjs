/** Stable operation identities. Rendering and automatic retry policy belong to the view controller. */
export class ApiError extends Error {
  constructor(status, body) {
    super(typeof body?.message === "string" ? body.message : "Request failed");
    this.name = "ApiError";
    this.status = status;
    this.code = typeof body?.code === "string" ? body.code : "HTTP_FAILED";
    this.retryable = body?.retryable === true;
  }
}

export class ApiClient {
  #token;
  #pending = new Set();
  #timeoutMs;
  constructor(token, timeoutMs = 30000) {
    if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 120000)
      throw new Error(
        "Request timeout must be between 1 and 120000 milliseconds",
      );
    this.#token = token;
    this.#timeoutMs = timeoutMs;
  }
  cancel() {
    for (const controller of this.#pending) controller.abort();
    this.#pending.clear();
  }
  disconnect() {
    this.#token = "";
    for (const controller of this.#pending) controller.abort();
    this.#pending.clear();
  }
  operation(path, payload, requestKey = crypto.randomUUID()) {
    // Serialize once; mutating caller data later cannot change a pending operation.
    return Object.freeze({ path, body: JSON.stringify(payload), requestKey });
  }
  async request(path, operation = null, asBlob = false) {
    const route = path.split("?")[0];
    if (
      !path.startsWith("/api/v1/") ||
      path.includes("#") ||
      path.includes("\\") ||
      route.split("/").some((part) => part === ".." || part === ".") ||
      /%2f|%5c|%2e/iu.test(route)
    ) {
      throw new Error("API path must be a scoped application route");
    }
    if (operation && operation.path !== path)
      throw new Error("Operation belongs to another route");
    if (!this.#token)
      throw new Error("Connect before making an authenticated request");
    const controller = new AbortController();
    this.#pending.add(controller);
    const timeout = setTimeout(() => controller.abort(), this.#timeoutMs);
    try {
      const headers = { Authorization: `Bearer ${this.#token}` };
      const options = {
        headers,
        signal: controller.signal,
        cache: "no-store",
        redirect: "error",
      };
      if (operation) {
        options.method = "POST";
        headers["Content-Type"] = "application/json";
        headers["Idempotency-Key"] = operation.requestKey;
        options.body = operation.body;
      }
      const response = await fetch(path, options);
      if (!response.ok)
        throw new ApiError(response.status, await response.json());
      return asBlob ? await response.blob() : await response.json();
    } finally {
      clearTimeout(timeout);
      this.#pending.delete(controller);
    }
  }
}
