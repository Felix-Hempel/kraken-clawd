"""Zustandsmodell: Claude-Code-Hook-Events pro Session → ein Anzeige-Modell (View)."""
from __future__ import annotations

from dataclasses import dataclass, field

TOOL_STATES = {
    "Edit": "typing", "Write": "typing", "MultiEdit": "typing", "NotebookEdit": "typing",
    "Read": "reading", "Grep": "reading", "Glob": "reading", "WebFetch": "reading", "WebSearch": "reading",
    "Bash": "bash", "Agent": "conducting", "Task": "conducting",
}
WAIT_TYPES = {"permission_prompt", "elicitation_dialog", "agent_needs_input"}
WORKING = ("thinking", "typing", "reading", "bash", "conducting", "working")
PRIORITY = {"limit": 0, "waiting": 1, "error": 2, **{s: 3 for s in WORKING},
            "celebrate": 4, "done": 4, "idle": 5}

ERROR_SECONDS = 1.5
DONE_SECONDS = 2.0
CELEBRATE_SECONDS = 4.0
CELEBRATE_AFTER = 30 * 60
SLEEP_AFTER = 30 * 60
DIM_AFTER = 40 * 60
OTHERS_IDLE_HIDE = 10 * 60
SESSION_TTL = 2 * 3600


@dataclass(frozen=True)
class SessionView:
    state: str
    subagents: int
    since: float


@dataclass(frozen=True)
class View:
    main: SessionView | None
    others: tuple[SessionView, ...]
    sleeping: bool
    dimmed: bool


@dataclass
class _Session:
    state: str
    since: float
    last: float
    prev: str = "idle"
    work_start: float | None = None
    subagents: set[str] = field(default_factory=set)

    def view(self) -> SessionView:
        return SessionView(self.state, len(self.subagents), self.since)


def _map(name: str, ev: dict) -> str | None:
    match name:
        case "SessionStart":
            return "idle"
        case "UserPromptSubmit" | "PostToolUse":
            return "thinking"
        case "PreToolUse":
            return TOOL_STATES.get(ev.get("tool_name"), "working")
        case "PostToolUseFailure":
            return "error"
        case "PermissionRequest":
            return "waiting"
        case "Notification":
            t = ev.get("notification_type")
            return "waiting" if t in WAIT_TYPES else "idle" if t == "idle_prompt" else None
        case "Stop":
            return None if ev.get("stop_hook_active") else "done"
        case "StopFailure":
            return "limit" if ev.get("error") == "rate_limit" else "error"
    return None


class Store:
    def __init__(self, created: float):
        self._sessions: dict[str, _Session] = {}
        self._quiet_since = created

    def apply(self, ev: dict, now: float) -> None:
        sid, name = ev.get("session_id"), ev.get("hook_event_name")
        if not isinstance(sid, str) or not isinstance(name, str):
            return
        self._quiet_since = now
        if name == "SessionEnd":
            self._sessions.pop(sid, None)
            return
        s = self._sessions.get(sid)
        if s is None:
            s = self._sessions[sid] = _Session(state="idle", since=now, last=now)
        s.last = now
        self._settle(s, now)

        agent = ev.get("agent_id")
        if name == "SubagentStart":
            if agent:
                s.subagents.add(str(agent))
            return
        if name == "SubagentStop":
            s.subagents.discard(str(agent))
            return

        new = _map(name, ev)
        if new is None or (agent and new != "waiting"):
            return
        if s.state == "limit" and name != "UserPromptSubmit":
            return
        if name == "UserPromptSubmit" and s.work_start is None:
            s.work_start = now
        if new == "error" and s.state != "error":
            s.prev = s.state
        if new == "done":
            if s.work_start is not None and now - s.work_start > CELEBRATE_AFTER:
                new = "celebrate"
            s.work_start = None
            s.subagents.clear()
        self._set(s, new, now)

    @staticmethod
    def _set(s: _Session, state: str, now: float) -> None:
        if s.state != state:
            s.state, s.since = state, now

    def _settle(self, s: _Session, now: float) -> None:
        age = now - s.since
        if s.state == "error" and age >= ERROR_SECONDS:
            self._set(s, s.prev, now)
        elif s.state == "done" and age >= DONE_SECONDS:
            self._set(s, "idle", now)
        elif s.state == "celebrate" and age >= CELEBRATE_SECONDS:
            self._set(s, "idle", now)

    def view(self, now: float) -> View:
        for sid, s in list(self._sessions.items()):
            if now - s.last > SESSION_TTL:
                del self._sessions[sid]
            else:
                self._settle(s, now)
        sessions = list(self._sessions.values())
        sleeping = not any(s.state == "waiting" or now - s.last < SLEEP_AFTER for s in sessions)
        dimmed = sleeping and now - self._quiet_since >= DIM_AFTER
        if sleeping:
            return View(None, (), True, dimmed)
        ranked = sorted(sessions, key=lambda s: (PRIORITY[s.state], -s.last))
        others = tuple(s.view() for s in ranked[1:]
                       if not (s.state == "idle" and now - s.since > OTHERS_IDLE_HIDE))
        return View(ranked[0].view(), others, False, False)
