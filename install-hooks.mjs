#!/usr/bin/env node
// Trägt die kraken-clawd-HTTP-Hooks in ~/.claude/settings.json ein (idempotent) oder entfernt sie (--remove).
import { copyFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const URL = "http://127.0.0.1:7377/hook";
const EVENTS = [
  "SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse",
  "PostToolUseFailure", "PermissionRequest", "Notification", "Stop", "StopFailure",
  "SubagentStart", "SubagentStop",
];

const args = process.argv.slice(2);
const remove = args.includes("--remove");
const i = args.indexOf("--settings");
const path = i >= 0 ? args[i + 1] : join(homedir(), ".claude", "settings.json");

const settings = existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : {};
if (existsSync(path)) copyFileSync(path, `${path}.bak-kraken-clawd`);
settings.hooks ??= {};

const ours = (group) => (group.hooks ?? []).some((h) => h.type === "http" && h.url === URL);

for (const ev of EVENTS) {
  const groups = (settings.hooks[ev] ?? []).filter((g) => !ours(g));
  if (!remove) groups.push({ hooks: [{ type: "http", url: URL, timeout: 1 }] });
  if (groups.length) settings.hooks[ev] = groups;
  else delete settings.hooks[ev];
}
if (!Object.keys(settings.hooks).length) delete settings.hooks;

writeFileSync(path, JSON.stringify(settings, null, 2) + "\n");
console.log(`${remove ? "entfernt" : "eingetragen"}: ${EVENTS.length} Events in ${path}`);
