"""Find the real model and settings behind a note edit in the app's own logs.

Claude Code logs every step to ~/.claude/projects/<project>/<session>.jsonl with the
model, reasoning effort and app version. Codex logs ~/.codex/sessions/**/*.jsonl with
thread settings (model, reasoning effort, approval policy). For an edit recorded by
the relay we look for the matching tool call there. Apps without a readable log
return None, and their edits stay self-reported.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Optional

WINDOW = timedelta(minutes=15)


def _when(entry) -> Optional[datetime]:
    try:
        return datetime.strptime(entry["time"], "%Y-%m-%dT%H:%M:%S%z")
    except Exception:
        return None


def _recent(root: Path, glob: str, since: datetime) -> Iterable[Path]:
    cutoff = since.timestamp() - 120
    try:
        return [p for p in root.glob(glob) if p.stat().st_mtime >= cutoff]
    except Exception:
        return []


def _matches(tool_name: str, tool_input: Dict, entry) -> bool:
    if not entry.get("tool") or not tool_name.endswith(entry["tool"]):
        return False
    wanted = {str(v) for v in (entry.get("identifier"), entry.get("directory")) if v}
    got = {str(v) for v in tool_input.values() if isinstance(v, str)}
    return bool(wanted & got)


def claude_code(entry, home: Path) -> Optional[Dict]:
    when = _when(entry)
    if not when:
        return None
    for f in _recent(home / ".claude" / "projects", "*/*.jsonl", when):
        try:
            lines = f.read_text(errors="replace").splitlines()
        except Exception:
            continue
        for line in reversed(lines):
            if entry["tool"] not in line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            msg = d.get("message") or {}
            if d.get("type") != "assistant" or not isinstance(msg.get("content"), list):
                continue
            try:
                ts = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00"))
            except Exception:
                continue
            if not (when - WINDOW <= ts <= when + timedelta(minutes=1)):
                continue
            for c in msg["content"]:
                if (isinstance(c, dict) and c.get("type") == "tool_use"
                        and _matches(c.get("name", ""), c.get("input") or {}, entry)):
                    return {"source": "Claude Code log",
                            "model": msg.get("model") or d.get("requestedModel"),
                            "reasoning_effort": d.get("perTurnEffort") or d.get("effort"),
                            "app_version": d.get("version"),
                            "surface": d.get("entrypoint"),
                            "session": f.stem}
    return None


def codex(entry, home: Path) -> Optional[Dict]:
    when = _when(entry)
    if not when:
        return None
    needle = entry.get("identifier") or "\0"
    for f in _recent(home / ".codex" / "sessions", "**/*.jsonl", when):
        settings, found = None, None
        try:
            fh = open(f, errors="replace")
        except Exception:
            continue
        with fh:
            for line in fh:
                if "thread_settings" in line:
                    try:
                        s = (json.loads(line).get("payload") or {}).get("thread_settings") or {}
                        settings = s or settings
                    except Exception:
                        pass
                elif entry["tool"] in line and needle in line:
                    found = dict(settings or {})
        if found is not None:
            return {"source": "Codex log",
                    "model": found.get("model"),
                    "reasoning_effort": found.get("reasoning_effort"),
                    "approval_policy": found.get("approval_policy"),
                    "mode": (found.get("collaboration_mode") or {}).get("mode"),
                    "session": f.stem}
    return None


def verify(entry, home: Path) -> Optional[Dict]:
    app = entry.get("app") or ""
    try:
        if app in ("claude-code", "claude-desktop"):
            return claude_code(entry, home)
        if app == "codex":
            return codex(entry, home)
    except Exception:
        return None
    return None
