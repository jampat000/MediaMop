import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import process from "node:process";

const webRoot = process.cwd();
const repoRoot = path.resolve(webRoot, "..", "..");
const exportScript = path.resolve(repoRoot, "scripts", "export-openapi.py");
const outputPath = path.resolve(webRoot, "openapi", "mediamop-openapi.json");

const candidates = [
  process.env.MEDIAMOP_PYTHON,
  path.resolve(webRoot, "..", "backend", ".venv", "Scripts", "python.exe"),
  path.resolve(webRoot, "..", "backend", ".venv", "bin", "python"),
  "python3",
  "python",
].filter(Boolean);

for (const cmd of candidates) {
  const isPath = cmd.includes(path.sep) || cmd.endsWith(".exe");
  if (isPath && !existsSync(cmd)) continue;

  const result = spawnSync(cmd, [exportScript, "--output", outputPath], {
    cwd: repoRoot,
    stdio: "inherit",
    shell: false,
  });
  if (result.status === 0) {
    process.exit(0);
  }
}

console.error("Failed to export OpenAPI schema: no usable Python interpreter found.");
console.error("Set MEDIAMOP_PYTHON or create apps/backend/.venv first.");
process.exit(1);
