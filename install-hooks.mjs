#!/usr/bin/env node
// Trägt die kraken-clawd-HTTP-Hooks in ~/.claude/settings.json ein (idempotent) oder entfernt sie (--remove).
import { copyFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const URL = "http://127.0.0.1:7377/hook";
const EVENTS = [
  "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse",
  "PostToolUseFailure", "PermissionRequest", "Notification", "Stop", "StopFailure",
  "SubagentStart", "SubagentStop",
];

const args = process.argv.slice(2);
const remove = args.includes("--remove");
const i = args.indexOf("--settings");
const path = i >= 0 ? args[i + 1] : join(homedir(), ".claude", "settings.json");

const settings = existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : {};
if (existsSync(path) && !existsSync(`${path}.bak-kraken-clawd`)) copyFileSync(path, `${path}.bak-kraken-clawd`);
settings.hooks ??= {};

const ours = (group) => (group.hooks ?? []).some((h) => h.type === "http" && h.url === URL);

for (const ev of Object.keys(settings.hooks)) {
  const groups = (settings.hooks[ev] ?? []).filter((g) => !ours(g));
  if (groups.length) settings.hooks[ev] = groups;
  else delete settings.hooks[ev];
}
if (!remove) {
  for (const ev of EVENTS) {
    settings.hooks[ev] = [...(settings.hooks[ev] ?? []), { hooks: [{ type: "http", url: URL, timeout: 1 }] }];
  }
}
if (!Object.keys(settings.hooks).length) delete settings.hooks;

writeFileSync(path, JSON.stringify(settings, null, 2) + "\n");
console.log(`${remove ? "entfernt" : "eingetragen"}: ${EVENTS.length} Events in ${path}`);
