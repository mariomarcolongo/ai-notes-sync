import json
from datetime import datetime, timedelta, timezone

from ai_notes_sync.verify import verify
from conftest import write

WHEN = datetime.now(timezone.utc).replace(microsecond=0)
JUST_BEFORE = (WHEN - timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def entry(app, tool="bm_write", identifier="Plan"):
    return {"app": app, "tool": tool, "identifier": identifier,
            "time": WHEN.strftime("%Y-%m-%dT%H:%M:%S%z")}


def test_claude_code_log(tmp_path):
    line = {"type": "assistant", "timestamp": JUST_BEFORE, "version": "2.1.0",
            "entrypoint": "cli", "effort": "medium", "perTurnEffort": "high",
            "message": {"model": "claude-x", "content": [
                {"type": "tool_use", "name": "mcp__basic-memory__bm_write",
                 "input": {"title": "Plan", "content": "..."}}]}}
    write(tmp_path / ".claude/projects/p/s1.jsonl", "{}\n" + json.dumps(line) + "\n")
    v = verify(entry("claude-code"), tmp_path)
    assert v["model"] == "claude-x"
    assert v["reasoning_effort"] == "high"
    assert v["app_version"] == "2.1.0" and v["session"] == "s1"


def test_claude_code_log_ignores_other_notes(tmp_path):
    line = {"type": "assistant", "timestamp": JUST_BEFORE,
            "message": {"model": "claude-x", "content": [
                {"type": "tool_use", "name": "mcp__basic-memory__bm_write", "input": {"title": "Other"}}]}}
    write(tmp_path / ".claude/projects/p/s1.jsonl", json.dumps(line) + "\n")
    assert verify(entry("claude-code"), tmp_path) is None


def test_codex_log(tmp_path):
    settings = {"type": "event_msg", "payload": {"type": "thread_settings_applied", "thread_settings": {
        "model": "gpt-y", "reasoning_effort": "max", "approval_policy": "never",
        "collaboration_mode": {"mode": "default"}}}}
    call = {"type": "response_item", "payload": {"type": "function_call", "name": "basic-memory.bm_write",
                                                  "arguments": json.dumps({"title": "Plan"})}}
    write(tmp_path / ".codex/sessions/2026/11/06/r.jsonl", json.dumps(settings) + "\n" + json.dumps(call) + "\n")
    v = verify(entry("codex"), tmp_path)
    assert v["model"] == "gpt-y" and v["reasoning_effort"] == "max" and v["mode"] == "default"


def test_apps_without_logs(tmp_path):
    assert verify(entry("cursor"), tmp_path) is None
