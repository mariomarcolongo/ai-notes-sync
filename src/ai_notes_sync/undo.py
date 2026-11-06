"""Undo everything one AI app (optionally one model) changed since a given time.

Each AI commit is authored "<App> (<model>, effort <x>) <label@ai-notes.local>", so
the commits to undo can be picked by author. They are reverted newest first with
`git revert`, which keeps the history: the bad edits stay visible, followed by
commits that cancel them.
"""

import subprocess
from typing import List, Optional, Tuple

from .config import Config


def _git(cfg: Config, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cfg.vault, capture_output=True, text=True)


def find(cfg: Config, app: str, since: Optional[str], model: Optional[str]) -> List[Tuple[str, str, str]]:
    args = ["log", "--format=%H%x1f%an%x1f%s", f"--author=<{app}@ai-notes.local>"]
    if since:
        args.append(f"--since={since}")
    commits = []
    for line in _git(cfg, *args).stdout.splitlines():
        sha, author, subject = line.split("\x1f", 2)
        if model and f"({model}" not in author:
            continue
        commits.append((sha, author, subject))
    return commits  # newest first


def run(cfg: Config, app: str, since: Optional[str], model: Optional[str], apply: bool) -> str:
    commits = find(cfg, app, since, model)
    if not commits:
        return "No matching commits."
    lines = [f"{sha[:8]}  {subject}" for sha, _, subject in commits]
    if not apply:
        return "\n".join(["Would undo:", *lines, "", "Run again with --apply to undo them."])
    if _git(cfg, "status", "--porcelain").stdout.strip():
        return "There are uncommitted changes. Run `ai-notes-sync sync` first, then undo."
    for sha, _, subject in commits:
        r = _git(cfg, "revert", "--no-edit", sha)
        if r.returncode:
            _git(cfg, "revert", "--abort")
            return (f"Stopped: {sha[:8]} ({subject}) can't be undone automatically because later "
                    f"edits changed the same lines. Nothing from this step was applied.\n{r.stderr.strip()[:300]}")
    return "\n".join([f"Undid {len(commits)} commit(s):", *lines, "", "They reach GitHub with the next sync."])
