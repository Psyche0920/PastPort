/** Syntax and content-rendering guard for the native JS surfaces. */
import { readdir, readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { join } from "node:path";

async function files(directory) {
  const results = [];
  for (const item of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, item.name);
    if (item.isDirectory()) results.push(...(await files(path)));
    else if (item.name.endsWith(".mjs")) results.push(path);
  }
  return results;
}
let count = 0;
for (const path of [
  ...(await files("src/pastport")),
  ...(await files("tests")),
]) {
  const result = spawnSync(process.execPath, ["--check", path], {
    encoding: "utf8",
  });
  if (result.status !== 0) throw new Error(`${path}: ${result.stderr}`);
  if (path.startsWith("src/pastport/api/")) {
    const source = await readFile(path, "utf8");
    if (/\.innerHTML\s*=|\beval\s*\(|\bnew\s+Function\s*\(/u.test(source))
      throw new Error(`${path}: executable content rendering is prohibited`);
  }
  count++;
}
console.log(
  `JavaScript syntax passed for ${count} modules; API rendering guard passed.`,
);
