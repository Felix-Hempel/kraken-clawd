#!/usr/bin/env bash
# Spielt alle Zustände gegen den laufenden Daemon durch.
set -euo pipefail
URL="${CLAWD_URL:-http://127.0.0.1:7377/hook}"
SID="demo-$$"
hook() { curl -fsS -o /dev/null -X POST "$URL" -H 'Content-Type: application/json' -d "$1"; }
ev() { hook "{\"session_id\":\"$SID\",\"hook_event_name\":\"$1\"${2:+,$2}}"; echo "→ $1 ${2:-}"; sleep "${3:-3}"; }

ev SessionStart
ev UserPromptSubmit
ev PreToolUse '"tool_name":"Read"'
ev PreToolUse '"tool_name":"Edit"'
ev PreToolUse '"tool_name":"Bash"'
ev PreToolUse '"tool_name":"mcp__server__server_run"'
ev PostToolUseFailure '"tool_name":"Bash"' 2
ev PreToolUse '"tool_name":"Agent"' 1
for a in s1 s2 s3 s4; do ev SubagentStart "\"agent_id\":\"$a\"" 1; done
sleep 3
for a in s1 s2 s3 s4; do ev SubagentStop "\"agent_id\":\"$a\"" 0.5; done
hook "{\"session_id\":\"$SID-b\",\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"Edit\"}"
hook "{\"session_id\":\"$SID-c\",\"hook_event_name\":\"UserPromptSubmit\"}"
echo "→ zwei weitere Sessions (Mini-Clawds)"
ev PermissionRequest '"tool_name":"Bash"' 4
ev PostToolUse '"tool_name":"Bash"' 1
ev Stop '"stop_hook_active":false' 3
ev UserPromptSubmit '' 1
ev StopFailure '"error":"rate_limit","error_details":"429 Too Many Requests"' 5
ev UserPromptSubmit '' 1
for s in "$SID" "$SID-b" "$SID-c"; do hook "{\"session_id\":\"$s\",\"hook_event_name\":\"SessionEnd\"}"; done
echo "→ alle Sessions beendet: Clawd schläft"
