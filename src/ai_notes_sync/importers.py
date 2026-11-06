"""Copy the notes each AI app keeps in its own folder into <vault>/imported/.

One-way and safe to re-run: a file is (re)written only when its source changed,
so frontmatter that Basic Memory adds is not undone on every run. Copies whose
source disappeared are kept as an archive. Edits made inside imported/ are
overwritten the next time the original changes.
"""

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from .config import Config

SKIP_DIRS = {".git", ".codex-baseline", ".system_generated", "node_modules"}
OWN_FM_KEYS = {"title", "type", "source_app", "source_path", "source_date"}
INSTRUCTION_FILES = ("CLAUDE.md", "AGENTS.md", "GEMINI.md", "CLAUDE.local.md")


def clean(name: str, limit: int = 80) -> str:
    """Turn a heading into a safe, readable file or folder name."""
    name = re.sub(r"[`*_#\[\]]", "", name)
    name = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .-")
    return name[:limit].rstrip(" .-") or "untitled"


def split_frontmatter(text: str) -> Tuple[List[str], str]:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            return text[4:end].splitlines(), text[end + 4:].lstrip("\n")
    return [], text


def first_heading(text: str) -> Optional[str]:
    for line in split_frontmatter(text)[1].splitlines():
        m = re.match(r"^#{1,2}\s+(.+)", line.strip())
        if m:
            return m.group(1).strip()
    return None


def strip_prefix(title: str) -> str:
    return re.sub(r"^(tasks?|task outline|implementation plan|walkthrough|plan)\s*[:\-–—]\s*",
                  "", title, flags=re.I).strip(" \"'")


def mdate(path: Path) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(path.stat().st_mtime))


def md_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if f.endswith(".md") and not f.startswith("scratchpad_"):
                yield Path(dirpath) / f


class Importer:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.state_file = cfg.state_dir / "import-state.json"
        try:
            self.state: Dict[str, str] = json.loads(self.state_file.read_text())
        except Exception:
            self.state = {}
        self.planned: Dict[Path, Tuple[str, str, str, Path]] = {}
        self.written = 0

    def plan(self, dest: Path, title: str, app: str, date: str, src: Path) -> None:
        prev = self.planned.get(dest)
        if prev and prev[3].stat().st_mtime >= src.stat().st_mtime:
            return  # keep the newer copy of a duplicate
        self.planned[dest] = (title, app, date, src)

    def _shown_path(self, src: Path) -> str:
        try:
            return "~/" + str(src.relative_to(self.cfg.home))
        except ValueError:
            return str(src)

    def write_all(self) -> None:
        vault = self.cfg.vault
        for dest, (title, app, date, src) in sorted(self.planned.items()):
            raw = src.read_text(errors="replace")
            digest = hashlib.sha256(raw.encode()).hexdigest()
            key = str(dest.relative_to(vault))
            if self.state.get(key) == digest and dest.exists():
                continue
            fm, body = split_frontmatter(raw)
            kept = [l for l in fm if l.split(":", 1)[0].strip() not in OWN_FM_KEYS]
            head = ["---",
                    f"title: {json.dumps(title, ensure_ascii=False)}",
                    "type: imported",
                    f"source_app: {app}",
                    f"source_path: {json.dumps(self._shown_path(src))}",
                    f"source_date: {date}",
                    *kept, "---", ""]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("\n".join(head) + body)
            self.state[key] = digest
            self.written += 1
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.state, indent=1, sort_keys=True))


def project_name(dirname: str, cfg: Config) -> str:
    """Claude Code names project folders after their path: '-Users-me-Code-site' -> 'site'."""
    n = dirname
    home_prefix = str(cfg.home).replace("/", "-") + "-"
    if n.startswith(home_prefix):
        n = n[len(home_prefix):]
    m = re.search(r"scratch-(\d{4}-\d{2}-\d{2})-([a-z0-9]+)$", n)
    if m:
        return f"scratch sessions/{m.group(1)} {m.group(2)}"
    roots = {r.name for r in cfg.project_roots} | {"Code", "Applications", "Documents", "Desktop", "Projects"}
    for r in sorted(roots, key=len, reverse=True):
        if n.startswith(r + "-"):
            n = n[len(r) + 1:]
            break
    return clean(n)


def claude_code(imp: Importer) -> None:
    root = imp.cfg.home / ".claude" / "projects"
    for mem in sorted(root.glob("*/memory")):
        proj = project_name(mem.parent.name, imp.cfg)
        for f in md_files(mem):
            if f.name == "MEMORY.md":
                title = f"{proj.split('/')[-1]} memory index"
            else:
                fm, _ = split_frontmatter(f.read_text(errors="replace"))
                name = next((l.split(":", 1)[1].strip() for l in fm if l.startswith("name:")), f.stem)
                title = name.replace("-", " ").capitalize()
            imp.plan(imp.cfg.imported / "claude-code" / proj / f.relative_to(mem),
                     title, "claude-code", mdate(f), f)


def codex(imp: Importer) -> None:
    out = imp.cfg.imported / "codex"
    for base in (imp.cfg.home / ".codex" / "memories", imp.cfg.home / ".codex" / "memories_v2"):
        if not base.exists():
            continue
        v2 = base.name.endswith("_v2")
        for f in md_files(base):
            rel = f.relative_to(base)
            text = f.read_text(errors="replace")
            if rel.parts[0] == "rollout_summaries":
                m = re.match(r"(\d{4}-\d{2}-\d{2})", f.name)
                day = m.group(1) if m else mdate(f)
                title = clean(first_heading(text) or f.stem)
                dest = out / "sessions" / day[:7] / f"{day} {title}.md"
            elif rel.parts[0] == "skills" and len(rel.parts) > 1:
                title = f"Codex skill: {rel.parts[1]}"
                dest = out / "skills" / f"{rel.parts[1]}.md"
            elif rel.parts[0] == "extensions":
                title = clean(first_heading(text) or f.stem)
                dest = out / "notes" / f.name
            else:
                stem = f.stem + (" (v2)" if v2 else "")
                title = f"Codex {stem.replace('_', ' ')}"
                dest = out / "memory" / f"{stem}.md"
            imp.plan(dest, title, "codex", mdate(f), f)


def antigravity(imp: Importer) -> None:
    """One folder per conversation, named '<date> <title>', grouped by month."""
    convs = {}
    for app in ("antigravity", "antigravity-ide"):
        root = imp.cfg.home / ".gemini" / app / "brain"
        if not root.exists():
            continue
        for d in root.iterdir():
            files = list(md_files(d)) if d.is_dir() else []
            if not files:
                continue
            newest = max(f.stat().st_mtime for f in files)
            if d.name not in convs or newest > convs[d.name][2]:
                convs[d.name] = (d, app, newest, files)
    used = set()
    for cid, (d, app, _, files) in sorted(convs.items()):
        by_name = {f.name: f for f in files}
        title = None
        for n in ("task.md", "implementation_plan.md", "walkthrough.md", *sorted(by_name)):
            if n in by_name:
                h = first_heading(by_name[n].read_text(errors="replace"))
                if h and strip_prefix(h).lower() not in ("", "proposed changes", "goal", "overview"):
                    title = strip_prefix(h)
                    break
        day = time.strftime("%Y-%m-%d", time.localtime(min(f.stat().st_mtime for f in files)))
        folder = f"{day} {clean(title or 'Untitled conversation', 70)}"
        if folder in used:
            folder += f" ({cid[:6]})"
        used.add(folder)
        for f in files:
            kind = f.stem.replace("_", " ").capitalize()
            imp.plan(imp.cfg.imported / "antigravity" / day[:7] / folder / f.relative_to(d),
                     f"{clean(title or 'Untitled', 70)} — {kind}", app, day, f)


def instructions(imp: Importer) -> None:
    out = imp.cfg.imported / "instructions"
    g = imp.cfg.home / ".gemini" / "GEMINI.md"
    if g.exists() and g.stat().st_size:
        imp.plan(out / "global" / "GEMINI.md", "Global Gemini instructions", "gemini", mdate(g), g)
    for base in imp.cfg.project_roots:
        if not base.exists():
            continue
        for proj in sorted(p for p in base.iterdir() if p.is_dir()):
            for n in INSTRUCTION_FILES:
                f = proj / n
                if f.exists() and f.stat().st_size:
                    imp.plan(out / clean(proj.name) / n, f"{proj.name} {n}",
                             "project-instructions", mdate(f), f)


SOURCES = {"claude_code": claude_code, "codex": codex, "antigravity": antigravity,
           "instructions": instructions}


def run(cfg: Config) -> Importer:
    imp = Importer(cfg)
    for key, step in SOURCES.items():
        if not cfg.sources.get(key, True):
            continue
        try:
            step(imp)
        except Exception as e:  # one broken source must not stop the others
            print(f"import: {key} failed: {e}")
    imp.write_all()
    return imp
