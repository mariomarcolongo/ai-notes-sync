"""MCP relay between an AI app and Basic Memory that records who changed which note.

An app's MCP config runs `ai-notes-sync relay <app-label>` instead of the Basic
Memory server. Messages pass through unchanged. For every write/edit/move/delete
tool call, one JSON line goes to the edit log with the app label, the client name
and version the app reports, the setup the AI reported about itself in `metadata`,
and the note paths Basic Memory says it touched.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from .config import Config

CHANGING = re.compile(r"(write|edit|move|delete)", re.I)
PATH_RE = re.compile(r"^([^\n:'\"]+?\.md)\b")
VERB_RE = re.compile(r"^\s*(Created|Updated|Edited|Moved|Deleted|Replaced|Wrote)\b", re.I | re.M)
SELF_REPORT_KEYS = ("model", "reasoning_effort", "effort", "thinking", "temperature",
                    "mode", "app_version", "settings")


class Recorder:
    """Watches JSON-RPC traffic (one message per line) and logs note changes."""

    def __init__(self, label: str, log_path, clock=time.time, read_only: bool = False):
        self.label = label
        self.log_path = log_path
        self.clock = clock
        self.read_only = read_only
        self.client: Dict[str, Any] = {}
        self.pending: Dict[Any, Dict[str, Any]] = {}
        self.lock = threading.Lock()

    def on_request(self, line: bytes) -> None:
        try:
            msg = json.loads(line)
        except Exception:
            return
        if not isinstance(msg, dict):
            return
        if msg.get("method") == "initialize":
            self.client.update((msg.get("params") or {}).get("clientInfo") or {})
        elif msg.get("method") == "tools/call":
            p = msg.get("params") or {}
            tool = p.get("name", "")
            if not CHANGING.search(tool):
                return
            args = p.get("arguments") or {}
            meta = args.get("metadata") if isinstance(args.get("metadata"), dict) else {}
            self.pending[msg.get("id")] = {
                "time": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(self.clock())),
                "app": self.label,
                "client": self.client.get("name"),
                "client_version": self.client.get("version"),
                "model": meta.get("model") or args.get("model"),
                "self_reported": {k: v for k, v in meta.items() if k in SELF_REPORT_KEYS},
                "tool": tool,
                "identifier": args.get("identifier") or args.get("title"),
                "directory": args.get("directory"),
                "destination": args.get("destination_path") or args.get("destination"),
            }

    def block(self, line: bytes) -> Optional[bytes]:
        """For a read-only app, the refusal to send back instead of forwarding a change."""
        if not self.read_only:
            return None
        try:
            msg = json.loads(line)
        except Exception:
            return None
        if not (isinstance(msg, dict) and msg.get("method") == "tools/call"
                and CHANGING.search((msg.get("params") or {}).get("name", ""))):
            return None
        entry = self.pending.pop(msg.get("id"), None) or {}
        self.write({**entry, "ok": False, "blocked": True, "paths": []})
        text = (f"Blocked: {self.label} may read the shared notes but not change them "
                "(ai-notes-sync read_only_apps). Tell the user what you wanted to save instead.")
        return (json.dumps({"jsonrpc": "2.0", "id": msg.get("id"),
                            "result": {"content": [{"type": "text", "text": text}], "isError": True}}) + "\n").encode()

    def on_response(self, line: bytes) -> Optional[Dict[str, Any]]:
        try:
            msg = json.loads(line)
        except Exception:
            return None
        if not isinstance(msg, dict):
            return None
        entry = self.pending.pop(msg.get("id"), None)
        if entry is None:
            return None
        result = msg.get("result") or {}
        text = " ".join(c.get("text", "") for c in result.get("content", []) if isinstance(c, dict))
        entry["ok"] = not result.get("isError") and "error" not in msg
        entry["paths"] = paths_from_result(text)
        entry["result"] = text[:300]
        self.write(entry)
        return entry

    def write(self, entry: Dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock, open(self.log_path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def paths_from_result(text: str) -> List[str]:
    """Note paths from Basic Memory's reply, e.g. 'Created notes/a.md' or 'Moved a.md to b.md'."""
    first = VERB_RE.search(text)
    if not first:
        return []
    verb = first.group(1).lower()
    rest = text[first.end():].splitlines()[0].strip()
    parts = rest.split(" to ", 1) if verb == "moved" else [rest]
    found = set()
    for part in parts:
        m = PATH_RE.search(part.strip())
        if m:
            found.add(m.group(1).strip())
    return sorted(found)


def run(cfg: Config, label: str) -> int:
    rec = Recorder(label, cfg.edit_log, read_only=label in cfg.read_only_apps)
    out_lock = threading.Lock()
    env = dict(os.environ, BASIC_MEMORY_NO_PROMOS=os.environ.get("BASIC_MEMORY_NO_PROMOS", "1"))
    child = subprocess.Popen(cfg.server(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, bufsize=0)

    def upstream():
        for line in child.stdout:
            with out_lock:
                sys.stdout.buffer.write(line)
                sys.stdout.buffer.flush()
            rec.on_response(line)

    threading.Thread(target=upstream, daemon=True).start()
    try:
        for line in sys.stdin.buffer:
            rec.on_request(line)
            refusal = rec.block(line)
            if refusal:
                with out_lock:
                    sys.stdout.buffer.write(refusal)
                    sys.stdout.buffer.flush()
                continue
            child.stdin.write(line)
            child.stdin.flush()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
    finally:
        try:
            child.stdin.close()
        except Exception:
            pass
    return child.wait()
