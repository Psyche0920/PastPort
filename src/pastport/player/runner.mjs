// Node-only transport. Browser actions import runtime.mjs directly.
import { applyAction } from "./runtime.mjs";
import { prepare } from "./preparation.mjs";
import { PlayerError } from "./errors.mjs";

const maximumBytes = 16 * 1024 * 1024;
let size = 0;
const chunks = [];
try {
  for await (const chunk of process.stdin) {
    size += chunk.length;
    if (size > maximumBytes) throw new PlayerError("PLAYER_INPUT_TOO_LARGE", "Component input exceeds the byte limit");
    chunks.push(chunk);
  }
  const command = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(Buffer.concat(chunks)));
  const response = JSON.stringify({ ok: true, result: command.operation === "apply_action" ? await applyAction(command) : await prepare(command), code: null, message: null });
  if (Buffer.byteLength(response) > maximumBytes) throw new PlayerError("PLAYER_OUTPUT_TOO_LARGE", "Component output exceeds the byte limit");
  process.stdout.write(response);
} catch (error) {
  const safe = error instanceof PlayerError ? error : new PlayerError("PLAYER_COMPONENT_FAILED", "Component input or execution failed");
  process.stdout.write(JSON.stringify({ ok: false, result: null, code: safe.code, message: safe.message }));
  process.exitCode = 1;
}
