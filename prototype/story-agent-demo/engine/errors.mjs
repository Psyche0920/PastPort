/** Safe operational errors never include source text, arbitrary keys or file paths. */
export class PlayerError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "PlayerError";
    this.code = code;
  }
}

export function requirePlayer(condition, code, message) {
  if (!condition) throw new PlayerError(code, message);
}
