"""Commit vault changes, one commit per author and model setup.

Who authored a changed file:
1. the AI app that last changed it through the relay. Its model and settings come
   from the app's own log when there is one ("verified"), else from what the AI
   said about itself ("self-reported"), else "unknown";
2. for files under imported/, the app the file was copied from;
3. otherwise you: a change made by hand, e.g. in Obsidian.

Every AI edit is also appended to <vault>/.ai-notes/edits.jsonl, one JSON line per
edit, so edits can be evaluated later by app, model and setting.
"""

import difflib
import json
import re
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import guard
from .config import Config
from .verify import verify

TRAILER_KEYS = ("app_version", "surface", "client", "approval_policy", "mode",
                "temperature", "thinking", "session")


class Git:
    def __init__(self, repo: Path):
        self.repo = repo

    def __call__(self, *args: str, check: bool = True) -> str:
        return subprocess.run(["git", *args], cwd=self.repo, check=check,
                              capture_output=True, text=True).stdout


def describe(entry: Dict, cfg: Config) -> Dict:
    """Model setup for one edit: verified from logs, else self-reported, else unknown."""
    v = verify(entry, cfg.home)
    if v and v.get("model"):
        setup = {k: val for k, val in v.items() if val}
        setup["evidence"] = "verified"
    elif entry.get("model") or entry.get("self_reported"):
        setup = {k: val for k, val in (entry.get("self_reported") or {}).items() if val}
        if entry.get("model"):
            setup.setdefault("model", entry["model"])
        if "effort" in setup and "reasoning_effort" not in setup:
            setup["reasoning_effort"] = setup.pop("effort")
        setup["evidence"] = "self-reported"
    else:
        setup = {"evidence": "unknown"}
    if entry.get("client"):
        setup["client"] = f"{entry['client']} {entry.get('client_version') or ''}".strip()
    return setup


def _state(cfg: Config) -> Tuple[Path, Dict]:
    path = cfg.state_dir / "commit-state.json"
    try:
        return path, json.loads(path.read_text())
    except Exception:
        return path, {"offset": 0}


def _new_edits(cfg: Config, offset: int) -> Tuple[List[Dict], int]:
    if not cfg.edit_log.exists():
        return [], 0
    with open(cfg.edit_log, "rb") as f:
        size = f.seek(0, 2)
        f.seek(offset if offset <= size else 0)  # log was rotated or replaced
        data = f.read()
        end = f.tell()
    out = []
    for line in data.decode(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("ok"):
            out.append(e)
    return out, end


def _source_app(cfg: Config, path: str) -> str:
    try:
        head = (cfg.vault / path).read_text(errors="replace")[:1500]
    except Exception:
        head = ""
    m = re.search(r"^source_app:\s*(\S+)", head, re.M)
    if m:
        return m.group(1)
    parts = path.split("/")
    return parts[1] if len(parts) > 1 else "import"


def _changed_paths(git: Git) -> List[Tuple[str, bool]]:
    """(path, exists) for every changed or new file in the working tree."""
    out, tokens = [], git("status", "--porcelain=v1", "-z", "-uall").split("\0")
    i = 0
    while i < len(tokens):
        t = tokens[i]
        i += 1
        if len(t) < 4:
            continue
        code, path = t[:2], t[3:]
        if "R" in code or "C" in code:
            i += 1  # skip the old name of a rename
        out.append((path, "D" not in code))
    return out


def _added_text(old: Optional[str], new: str) -> str:
    if old is None:
        return new
    return "\n".join(l[1:] for l in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0)
                     if l.startswith("+") and not l.startswith("+++"))


def run_guard(cfg: Config, git: Git, last_by_path: Dict[str, Tuple[Dict, Dict]]) -> Tuple[List[str], Dict[str, List[str]]]:
    """Quarantine risky AI changes before they are committed. Returns (messages, warnings by path)."""
    messages: List[str] = []
    warnings: Dict[str, List[str]] = {}
    if not cfg.guard:
        return messages, warnings
    approvals = guard.Approvals(cfg)
    for path, exists in _changed_paths(git):
        if path.startswith((".ai-notes/", guard.QUARANTINE + "/", "imported/")) or not path.endswith(".md"):
            continue
        full = cfg.vault / path
        old = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=cfg.vault, capture_output=True, text=True)
        old_text = old.stdout if old.returncode == 0 else None
        e, s = last_by_path.get(path, (None, None))
        who = {k: v for k, v in {"app": e and e.get("app"), "model": s and s.get("model"),
                                 "reasoning_effort": s and s.get("reasoning_effort"),
                                 "evidence": s and s.get("evidence")}.items() if v}
        if not exists:
            if e and path in cfg.protected and old_text is not None:
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(old_text)
                guard.log_event(cfg, {"event": "restored", "path": path, "reason": "protected file deleted by an AI",
                                      "by": who, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
                messages.append(f"Guard: restored protected {path} (deleted by {cfg.name(e.get('app'))})")
            continue
        try:
            new_text = full.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        if guard.digest(new_text) in approvals:
            continue
        findings = guard.scan(_added_text(old_text, new_text))
        if e:  # changed by an AI through the relay
            reasons = []
            if path in cfg.protected:
                reasons.append("protected file changed by an AI")
            if guard.is_high(findings):
                reasons.append("possible prompt injection")
            if (old_text and len(old_text) >= cfg.shrink_min_chars
                    and len(new_text) < cfg.shrink_ratio * len(old_text)):
                reasons.append(f"large deletion (kept {round(100 * len(new_text) / len(old_text))}% of the note)")
            if reasons:
                guard.quarantine(cfg, path, new_text, reasons, findings, who)
                if old_text is None:
                    full.unlink()
                else:
                    full.write_text(old_text)
                messages.append(f"Guard: quarantined {path} ({'; '.join(reasons)})")
                continue
        if findings:
            kinds = sorted({f.kind for f in findings})
            warnings[path] = kinds
            guard.log_event(cfg, {"event": "warning", "path": path, "by": who or {"app": "you"},
                                  "findings": [vars(f) for f in findings],
                                  "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
            messages.append(f"Guard: warning for {path}: {', '.join(kinds)}")
    return messages, warnings


def run(cfg: Config) -> List[str]:
    """Commit everything that changed. Returns the commit subjects."""
    git = Git(cfg.vault)
    state_path, state = _state(cfg)
    edits, end = _new_edits(cfg, state.get("offset", 0))

    last_by_path: Dict[str, Tuple[Dict, Dict]] = {}
    ledger = []
    for e in edits:
        setup = describe(e, cfg)
        ledger.append(json.dumps({"time": e.get("time"), "app": e.get("app"), "tool": e.get("tool"),
                                  "paths": e.get("paths"), **setup}, ensure_ascii=False))
        for p in e.get("paths") or []:
            last_by_path[p] = (e, setup)
    if ledger:
        cfg.ledger.parent.mkdir(parents=True, exist_ok=True)
        with open(cfg.ledger, "a") as f:
            f.write("\n".join(ledger) + "\n")

    subjects, warnings = run_guard(cfg, git, last_by_path)

    git("add", "-A")
    changed = [p for p in git("diff", "--cached", "--name-only", "-z").split("\0") if p]
    if changed:
        me = git("config", "user.name", check=False).strip() or "Me"
        my_email = git("config", "user.email", check=False).strip() or "me@ai-notes.local"
        groups = defaultdict(list)
        for path in changed:
            if path.startswith(".ai-notes/"):
                groups[("~ledger", "", "", "", "")].append(path)
            elif path.startswith(guard.QUARANTINE + "/"):
                groups[("~guard", "", "", "", "")].append(path)
            elif path in last_by_path:
                e, s = last_by_path[path]
                groups[("ai", e.get("app") or "unknown-ai", s.get("model") or "",
                        s.get("reasoning_effort") or "", s.get("evidence"))].append(path)
            elif path.startswith("imported/"):
                groups[("import", _source_app(cfg, path), "", "", "")].append(path)
            else:
                groups[("me", me, "", "", "")].append(path)

        git("reset", "-q")
        for (kind, who, model, effort, evidence), files in sorted(groups.items()):
            trailers: List[str] = []
            if kind == "me":
                name, email = me, my_email
                subject = f"{me}: edited {len(files)} note(s)"
            elif kind == "~ledger":
                name, email = "ai-notes-sync", "sync@ai-notes.local"
                subject = "Record AI edit details"
            elif kind == "~guard":
                name, email = "ai-notes-sync guard", "guard@ai-notes.local"
                n = sum(1 for f in files if not f.endswith(".json"))
                subject = f"Guard: quarantine updated ({n} note(s))"
            elif kind == "import":
                name, email = cfg.name(who), f"{who}@ai-notes.local"
                subject = f"{name}: imported/updated {len(files)} note(s)"
            else:
                app = cfg.name(who)
                bits = [b for b in (model, f"effort {effort}" if effort else "") if b]
                name = f"{app} ({', '.join(bits)})" if bits else app
                email = f"{who}@ai-notes.local"
                subject = f"{name}: changed {len(files)} note(s)"
                _, s = last_by_path[files[-1]]
                trailers = [f"AI-App: {app}", f"AI-Model: {model or 'unknown'}",
                            f"AI-Reasoning-Effort: {effort or 'unknown'}", f"AI-Evidence: {evidence}"]
                trailers += [f"AI-{k.replace('_', '-').title()}: {s[k]}" for k in TRAILER_KEYS if s.get(k)]
                warned = sorted({k for f in files for k in warnings.get(f, [])})
                if warned:
                    trailers.append(f"AI-Guard-Warning: {', '.join(warned)}")
            args = ["commit", "-q", "--author", f"{name} <{email}>", "-m", subject,
                    "-m", "\n".join(f"- {p}" for p in sorted(files)[:200])]
            if trailers:
                args += ["-m", "\n".join(trailers)]
            git("add", "-A", "--", *files)
            git(*args)
            subjects.append(subject)

    state["offset"] = end
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state))
    return subjects
