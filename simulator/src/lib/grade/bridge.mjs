// Tiny Node bridge that runs the simulator grader over a batch of rubric
// cases fed on stdin, and prints per-case {marks, max_marks, verdict} on stdout.
//
// Usage (from evals/run.py):
//   node simulator/src/lib/grade/bridge.mjs < cases.json > results.json

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import esbuild from "esbuild";

const __dirname = dirname(fileURLToPath(import.meta.url));

// Bundle the TS grader once so we can import it without requiring a full
// Vite build. Writes an in-memory bundle and imports it via a data URL.
async function loadGrader() {
  const entry = resolve(__dirname, "index.ts");
  const result = await esbuild.build({
    entryPoints: [entry],
    bundle: true,
    platform: "node",
    format: "esm",
    target: "es2022",
    write: false,
    external: [],
    loader: { ".ts": "ts" },
    tsconfig: resolve(__dirname, "../../../tsconfig.app.json"),
  });
  const code = result.outputFiles[0].text;
  const dataUrl = "data:text/javascript;base64," + Buffer.from(code).toString("base64");
  const mod = await import(dataUrl);
  return mod;
}

async function main() {
  const grader = await loadGrader();
  const stdin = readFileSync(0, "utf-8");
  const cases = JSON.parse(stdin);
  const out = [];
  for (const c of cases) {
    const normalized = {};
    for (const [partId, ans] of Object.entries(c.student_answers)) {
      normalized[partId] = { part_id: partId, ...ans };
    }
    const grade = await grader.gradeQuestion(c.rubric, normalized);
    out.push({
      id: c.id,
      marks: grade.marks_awarded,
      max_marks: grade.max_marks,
      verdict: grade.verdict,
    });
  }
  process.stdout.write(JSON.stringify(out));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

// Keep an unused import of createRequire so ESM lint is happy in older tooling.
void createRequire(import.meta.url);
void pathToFileURL;
