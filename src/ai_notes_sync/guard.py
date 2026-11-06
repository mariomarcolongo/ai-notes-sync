"""Keep prompt injection and destructive edits out of the shared notes.

Every AI reads these notes, so one poisoned note could steer all of them. The guard
runs on every sync:

- scan: new text from AI edits and imports is checked for injection patterns
  (instruction overrides, role markup, hidden characters, secrecy requests,
  data-leaking links, large encoded blobs);
- quarantine: a note with a high-severity finding is moved to <vault>/.quarantine/,
  which Basic Memory does not index, so no AI can find it. The previous version is
  restored. You decide with `ai-notes-sync review`;
- large deletions: an AI edit that removes most of a note is quarantined the same way;
- protected files (the Filing guide by default) can't be changed by an AI at all.

Edits you make yourself are scanned and warned about, never moved. No pattern list
catches everything; the guard makes poisoning harder and easy to spot and undo.
"""

import hashlib
import json
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .config import Config

HIGH, MEDIUM = "high", "medium"
QUARANTINE = ".quarantine"

_I = re.I
_IM = re.I | re.M
PATTERNS = [
    # (kind, severity, regex)
    ("instruction override", HIGH, re.compile(
        r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b(previous|prior|above|earlier|preceding|all|any|your|system)\b"
        r"[^.\n]{0,25}\b(instructions?|prompts?|rules|directions|guidelines|guardrails)\b", _I)),
    ("identity change", HIGH, re.compile(
        r"\byou are now\b(?! (logged|signed|connected|able|ready|done|in |on |at ))|\bfrom now on,? you (are|will|must|should)\b"
        r"|\b(developer|jailbreak|DAN) mode\b|\bact as an? (unrestricted|unfiltered|jailbroken)\b", _I)),
    ("role markup", HIGH, re.compile(
        r"<\|(im_start|im_end|system|endoftext)\|>|\[/?INST\]|<<SYS>>"
        r"|^\s*</?(system|assistant|developer)>\s*$|^#{1,3}\s*(system|developer)\s+(prompt|message|instructions)\s*:?\s*$", _IM)),
    ("secrecy request", HIGH, re.compile(
        r"\b(do not|don't|never|without)\b[^.\n]{0,15}\b(tell|telling|inform|informing|mention|mentioning|reveal|revealing|alert|alerting|notify|notifying)\b"
        r"[^.\n]{0,15}\b(the )?(user|human|owner|operator)\b", _I)),
    ("data-leaking link", HIGH, re.compile(
        r"!\[[^\]]*\]\(\s*https?://[^)\s]+\?[^)\s]*=[^)\s]{24,}\)"
        r"|\b(send|post|upload|forward|exfiltrate)\b[^\n]{0,60}?\b(to|at)\s+https?://", _I)),
    ("instructions to AI", MEDIUM, re.compile(
        r"\b(AI|assistant|agent|LLM|language model|Claude|ChatGPT|GPT|Gemini|Codex|Copilot)s?\b[,:]?\s+(you must|you should|must now|should now|are instructed)\b", _I)),
    ("hidden comment instructions", MEDIUM, re.compile(
        r"<!--(?:(?!-->).){0,600}?\b(ignore|instruction|assistant|you must|system prompt|do not tell)\b", _I | re.S)),
    ("tool instructions", MEDIUM, re.compile(
        r"\b(call|use|run|invoke|execute)\b[^.\n]{0,25}\b(bm_delete|bm_move|bm_write|bm_edit)\b"
        r"|\bcurl\b[^\n|]{0,200}\|\s*(ba|z)?sh\b", _I)),
    ("encoded blob", MEDIUM, re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{300,}={0,2}")),
]

# invisible characters used to hide text from people but not from models
HIDDEN = re.compile("[​‌‎‏‪-‮⁠-⁤⁦-⁩﻿\U000e0000-\U000e007f]")


@dataclass
class Finding:
    kind: str
    severity: str
    line: int
    excerpt: str


def scan(text: str) -> List[Finding]:
    findings: List[Finding] = []
    for kind, sev, rx in PATTERNS:
        for m in rx.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            findings.append(Finding(kind, sev, line, _excerpt(m.group(0))))
            break  # one finding per kind is enough
    hidden = HIDDEN.findall(text)
    if hidden:
        tag_chars = sum(1 for c in hidden if "\U000e0000" <= c <= "\U000e007f")
        # a few tag characters are legitimate inside flag emoji; many hide text
        if len(hidden) - tag_chars > 0 or tag_chars > 12:
            m = HIDDEN.search(text)
            names = sorted({unicodedata.name(c, hex(ord(c))) for c in hidden})[:3]
            findings.append(Finding("hidden characters", HIGH, text.count("\n", 0, m.start()) + 1,
                                    f"{len(hidden)} invisible character(s): {', '.join(names)}"))
    return findings


def _excerpt(s: str, limit: int = 120) -> str:
    s = HIDDEN.sub("·", s.replace("\n", " ⏎ "))
    return s if len(s) <= limit else s[:limit] + "…"


def is_high(findings: List[Finding]) -> bool:
    return any(f.severity == HIGH for f in findings)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class Approvals:
    """Content you approved, by hash, so it isn't flagged again (kept on this machine)."""

    def __init__(self, cfg: Config):
        self.path = cfg.state_dir / "approved.json"
        try:
            self.hashes = set(json.loads(self.path.read_text()))
        except Exception:
            self.hashes = set()

    def __contains__(self, text_hash: str) -> bool:
        return text_hash in self.hashes

    def add(self, text_hash: str) -> None:
        self.hashes.add(text_hash)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(sorted(self.hashes)))


def log_event(cfg: Config, event: Dict) -> None:
    path = cfg.vault / ".ai-notes" / "guard.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def notify(cfg: Config, message: str) -> None:
    if not cfg.notify or sys.platform != "darwin":
        return
    script = f'display notification {json.dumps(message)} with title "ai-notes-sync"'
    subprocess.run(["osascript", "-e", script], capture_output=True)


def quarantine(cfg: Config, rel: str, content: str, reasons: List[str], findings: List[Finding],
               who: Optional[Dict] = None) -> Path:
    """Store flagged content under .quarantine/<rel> with a .json describing why."""
    dest = cfg.vault / QUARANTINE / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    meta = {"path": rel, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "reasons": reasons,
            "findings": [asdict(f) for f in findings], "by": who or {}, "sha256": digest(content)}
    dest.with_name(dest.name + ".json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    log_event(cfg, {"event": "quarantined", **meta})
    notify(cfg, f"Quarantined {rel}: {', '.join(reasons)}")
    return dest


def quarantined(cfg: Config) -> List[Dict]:
    root = cfg.vault / QUARANTINE
    items = []
    for meta in sorted(root.rglob("*.json")) if root.exists() else []:
        try:
            m = json.loads(meta.read_text())
        except Exception:
            continue
        m["file"] = str(meta.parent / meta.name[:-len(".json")])
        items.append(m)
    return items


def _find(cfg: Config, which: str) -> Optional[Dict]:
    for item in quarantined(cfg):
        if which in (item["path"], item["file"], str(Path(item["file"]).relative_to(cfg.vault))):
            return item
    return None


def approve(cfg: Config, which: str) -> str:
    item = _find(cfg, which)
    if not item:
        return f"Not in quarantine: {which}"
    src = Path(item["file"])
    content = src.read_text()
    Approvals(cfg).add(digest(content))
    if item.get("by", {}).get("source"):  # an import: remember the source, too
        Approvals(cfg).add(item["by"]["source"])
    dest = cfg.vault / item["path"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    src.unlink()
    Path(item["file"] + ".json").unlink()
    log_event(cfg, {"event": "approved", "path": item["path"], "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    return f"Approved: {item['path']} is back in place."


def discard(cfg: Config, which: str) -> str:
    item = _find(cfg, which)
    if not item:
        return f"Not in quarantine: {which}"
    Path(item["file"]).unlink()
    Path(item["file"] + ".json").unlink()
    log_event(cfg, {"event": "discarded", "path": item["path"], "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    return f"Discarded the quarantined version of {item['path']}."


def review_text(cfg: Config) -> str:
    items = quarantined(cfg)
    if not items:
        return "Nothing in quarantine."
    out = []
    for it in items:
        by = it.get("by") or {}
        who = " · ".join(str(by[k]) for k in ("app", "model") if by.get(k)) or "unknown"
        out.append(f"{it['path']}\n  when: {it['time']}  by: {who}\n  why: {', '.join(it['reasons'])}")
        for f in it.get("findings", [])[:5]:
            out.append(f"    [{f['severity']}] {f['kind']} (line {f['line']}): {f['excerpt']}")
    out.append("\nApprove:  ai-notes-sync review --approve <path>\nDiscard:  ai-notes-sync review --discard <path>")
    return "\n".join(out)
