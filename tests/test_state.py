import pytest

from kraken_clawd.state import Store


def ev(name, sid="a", **kw):
    return {"hook_event_name": name, "session_id": sid, **kw}


@pytest.fixture
def store():
    return Store(created=0.0)


def main_state(store, now):
    v = store.view(now)
    return v.main.state if v.main else None


@pytest.mark.parametrize("tool,expected", [
    ("Edit", "typing"), ("Write", "typing"), ("MultiEdit", "typing"), ("NotebookEdit", "typing"),
    ("Read", "reading"), ("Grep", "reading"), ("Glob", "reading"),
    ("WebFetch", "reading"), ("WebSearch", "reading"),
    ("Bash", "bash"), ("Agent", "conducting"), ("Task", "conducting"),
    ("mcp__server__server_run", "working"),
])
def test_pre_tool_use_maps_tool(store, tool, expected):
    store.apply(ev("PreToolUse", tool_name=tool), 1)
    assert main_state(store, 1) == expected


def test_prompt_and_post_tool_mean_thinking(store):
    store.apply(ev("UserPromptSubmit"), 1)
    assert main_state(store, 1) == "thinking"
    store.apply(ev("PreToolUse", tool_name="Bash"), 2)
    store.apply(ev("PostToolUse", tool_name="Bash"), 3)
    assert main_state(store, 3) == "thinking"


@pytest.mark.parametrize("payload", [
    ev("PermissionRequest", tool_name="Bash"),
    ev("Notification", notification_type="permission_prompt"),
    ev("Notification", notification_type="elicitation_dialog"),
    ev("Notification", notification_type="agent_needs_input"),
    ev("Notification", notification_type="elicitation_url_dialog"),
])
def test_waiting_triggers(store, payload):
    store.apply(payload, 1)
    assert main_state(store, 1) == "waiting"


def test_idle_prompt_notification_means_idle(store):
    store.apply(ev("UserPromptSubmit"), 1)
    store.apply(ev("Notification", notification_type="idle_prompt"), 2)
    assert main_state(store, 2) == "idle"


def test_unknown_notification_type_is_ignored(store):
    store.apply(ev("UserPromptSubmit"), 1)
    store.apply(ev("Notification", notification_type="sonstwas"), 2)
    assert main_state(store, 2) == "thinking"


def test_stop_shows_done_then_idle(store):
    store.apply(ev("UserPromptSubmit"), 1)
    store.apply(ev("Stop", stop_hook_active=False), 10)
    assert main_state(store, 11) == "done"
    assert main_state(store, 12.1) == "idle"


def test_stop_with_active_stop_hook_is_ignored(store):
    store.apply(ev("UserPromptSubmit"), 1)
    store.apply(ev("Stop", stop_hook_active=True), 2)
    assert main_state(store, 2) == "thinking"


def test_long_work_celebrates(store):
    store.apply(ev("UserPromptSubmit"), 0)
    store.apply(ev("PostToolUse"), 1700)
    store.apply(ev("Stop"), 1801)
    assert main_state(store, 1802) == "celebrate"
    assert main_state(store, 1805.1) == "idle"


def test_work_timer_resets_after_done(store):
    store.apply(ev("UserPromptSubmit"), 0)
    store.apply(ev("Stop"), 1801)
    store.apply(ev("UserPromptSubmit"), 1810)
    store.apply(ev("Stop"), 1820)
    assert main_state(store, 1821) == "done"


def test_error_returns_to_previous_state(store):
    store.apply(ev("PreToolUse", tool_name="Edit"), 1)
    store.apply(ev("PostToolUseFailure", tool_name="Edit"), 2)
    assert main_state(store, 2.5) == "error"
    assert main_state(store, 3.6) == "typing"


def test_rate_limit_is_sticky_until_next_prompt(store):
    store.apply(ev("UserPromptSubmit"), 1)
    store.apply(ev("StopFailure", error="rate_limit", error_details="429"), 2)
    assert main_state(store, 3) == "limit"
    store.apply(ev("Notification", notification_type="idle_prompt"), 4)
    store.apply(ev("PreToolUse", tool_name="Bash"), 5)
    assert main_state(store, 5) == "limit"
    store.apply(ev("UserPromptSubmit"), 6)
    assert main_state(store, 6) == "thinking"


def test_other_stop_failure_is_error(store):
    store.apply(ev("UserPromptSubmit"), 1)
    store.apply(ev("StopFailure", error="server_error"), 2)
    assert main_state(store, 2) == "error"


def test_waiting_session_wins_priority(store):
    store.apply(ev("PreToolUse", "a", tool_name="Edit"), 5)
    store.apply(ev("PermissionRequest", "b", tool_name="Bash"), 1)
    v = store.view(5)
    assert v.main.state == "waiting"
    assert [o.state for o in v.others] == ["typing"]


def test_limit_beats_waiting(store):
    store.apply(ev("PermissionRequest", "a"), 1)
    store.apply(ev("StopFailure", "b", error="rate_limit"), 2)
    assert main_state(store, 2) == "limit"


def test_tie_goes_to_latest_hook(store):
    store.apply(ev("PreToolUse", "a", tool_name="Edit"), 1)
    store.apply(ev("PreToolUse", "b", tool_name="Read"), 2)
    assert main_state(store, 2) == "reading"


def test_subagent_counter(store):
    store.apply(ev("PreToolUse", tool_name="Agent"), 1)
    store.apply(ev("SubagentStart", agent_id="x"), 2)
    store.apply(ev("SubagentStart", agent_id="y"), 2)
    assert store.view(2).main.subagents == 2
    store.apply(ev("SubagentStop", agent_id="x"), 3)
    store.apply(ev("SubagentStop", agent_id="x"), 3)
    store.apply(ev("SubagentStop", agent_id="nie-gestartet"), 3)
    assert store.view(3).main.subagents == 1


def test_stop_resets_subagents(store):
    store.apply(ev("SubagentStart", agent_id="x"), 1)
    store.apply(ev("Stop"), 2)
    assert store.view(2).main.subagents == 0


def test_subagent_hooks_do_not_override_main_state(store):
    store.apply(ev("PreToolUse", tool_name="Agent"), 1)
    store.apply(ev("PreToolUse", tool_name="Read", agent_id="x"), 2)
    store.apply(ev("PostToolUseFailure", tool_name="Read", agent_id="x"), 3)
    assert main_state(store, 3) == "conducting"
    store.apply(ev("PermissionRequest", tool_name="Bash", agent_id="x"), 4)
    assert main_state(store, 4) == "waiting"


def test_unknown_session_is_created_implicitly(store):
    store.apply(ev("PreToolUse", "neu", tool_name="Bash"), 1)
    assert main_state(store, 1) == "bash"


def test_sleep_after_30_min_and_dim_after_40(store):
    store.apply(ev("Stop"), 0)
    assert not store.view(1799).sleeping
    v = store.view(1801)
    assert v.sleeping and not v.dimmed and v.main is None
    assert store.view(2401).dimmed


def test_no_sessions_means_sleeping(store):
    v = store.view(1)
    assert v.sleeping and v.main is None and not v.dimmed
    assert store.view(2401).dimmed


def test_hook_wakes_up(store):
    store.view(5000)
    store.apply(ev("UserPromptSubmit"), 5000)
    v = store.view(5000)
    assert not v.sleeping and not v.dimmed and v.main.state == "thinking"


def test_waiting_session_never_sleeps(store):
    store.apply(ev("PermissionRequest"), 0)
    v = store.view(3600)
    assert not v.sleeping and v.main.state == "waiting"


def test_session_end_removes_session(store):
    store.apply(ev("UserPromptSubmit"), 1)
    store.apply(ev("SessionEnd"), 2)
    assert store.view(2).main is None


def test_session_ttl_two_hours(store):
    store.apply(ev("PermissionRequest", "alt"), 0)
    store.apply(ev("UserPromptSubmit", "neu"), 7000)
    v = store.view(7201)
    assert v.main.state == "thinking" and v.others == ()


def test_others_hide_sessions_idle_for_10_min(store):
    store.apply(ev("SessionStart", "a"), 0)
    store.apply(ev("UserPromptSubmit", "b"), 601)
    assert store.view(601).others == ()


def test_invalid_events_are_ignored(store):
    for bad in ({}, {"session_id": 1, "hook_event_name": "Stop"}, {"session_id": "a"},
                {"hook_event_name": "Stop"}, ev("Erfunden")):
        store.apply(bad, 1)
    assert store.view(1).main is None or store.view(1).main.state == "idle"


def test_state_since_kept_while_state_unchanged(store):
    store.apply(ev("PreToolUse", tool_name="Edit"), 1)
    store.apply(ev("PreToolUse", tool_name="Write"), 5)
    assert store.view(5).main.since == 1


def test_stop_keeps_background_subagents(store):
    store.apply(ev("UserPromptSubmit"), 1)
    store.apply(ev("SubagentStart", agent_id="x"), 2)
    store.apply(ev("SubagentStart", agent_id="y"), 2)
    store.apply(ev("Stop", background_tasks=[{"type": "subagent"}]), 3)
    assert store.view(3).main.subagents == 2
    assert main_state(store, 3) == "done"
    assert main_state(store, 6) == "conducting"
    store.apply(ev("SubagentStop", agent_id="x"), 7)
    assert main_state(store, 7) == "conducting"
    store.apply(ev("SubagentStop", agent_id="y"), 8)
    assert main_state(store, 8) == "idle"


@pytest.mark.parametrize("tasks", [None, "kaputt", [], [{"type": "shell"}], ["x"]])
def test_stop_without_background_subagents_clears(store, tasks):
    store.apply(ev("SubagentStart", agent_id="x"), 1)
    kw = {} if tasks is None else {"background_tasks": tasks}
    store.apply(ev("Stop", **kw), 2)
    assert store.view(2).main.subagents == 0


def test_conducting_idle_session_outranks_idle_others(store):
    store.apply(ev("SubagentStart", "a", agent_id="x"), 0)
    store.apply(ev("Stop", "a", background_tasks=[{"type": "subagent"}]), 1)
    store.apply(ev("Stop", "b"), 5)
    v = store.view(10)
    assert v.main.state == "conducting"
    assert [o.state for o in v.others] == ["idle"]


def test_subagent_hook_releases_waiting(store):
    store.apply(ev("PermissionRequest", agent_id="x"), 1)
    assert main_state(store, 1) == "waiting"
    store.apply(ev("PreToolUse", tool_name="Read", agent_id="x"), 2)
    assert main_state(store, 2) == "conducting"


def test_stop_failure_other_returns_to_idle(store):
    store.apply(ev("PreToolUse", tool_name="Edit"), 1)
    store.apply(ev("StopFailure", error="server_error"), 2)
    assert main_state(store, 2) == "error"
    assert main_state(store, 3.6) == "idle"


@pytest.mark.parametrize("err", ["rate_limit", "billing_error", "account_on_hold"])
def test_limit_errors(store, err):
    store.apply(ev("UserPromptSubmit"), 1)
    store.apply(ev("StopFailure", error=err), 2)
    assert main_state(store, 2) == "limit"


def test_no_confetti_after_limit(store):
    store.apply(ev("UserPromptSubmit"), 0)
    store.apply(ev("StopFailure", error="rate_limit"), 10)
    store.apply(ev("UserPromptSubmit"), 4000)
    store.apply(ev("Stop"), 4010)
    assert main_state(store, 4010) == "done"
