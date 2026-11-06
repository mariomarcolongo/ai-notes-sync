"""One sync round: import AI notes, commit per author, pull and push."""

import os
import subprocess
import time
from contextlib import contextmanager

from . import commit, importers
from .config import Config


@contextmanager
def single_run(cfg: Config):
    """Skip this round if another one is running; clear a lock left by a crash."""
    lock = cfg.state_dir / "sync.lock"
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    try:
        if lock.exists() and time.time() - lock.stat().st_mtime > 600:
            os.rmdir(lock)
        os.mkdir(lock)
    except FileExistsError:
        yield False
        return
    try:
        yield True
    finally:
        try:
            os.rmdir(lock)
        except OSError:
            pass


def _git(cfg: Config, *args: str) -> bool:
    r = subprocess.run(["git", *args], cwd=cfg.vault, capture_output=True, text=True)
    if r.returncode:
        print(f"git {args[0]} failed: {(r.stderr or r.stdout).strip()[:300]}")
    return r.returncode == 0


def has_remote(cfg: Config) -> bool:
    r = subprocess.run(["git", "remote"], cwd=cfg.vault, capture_output=True, text=True)
    return bool(r.stdout.strip())


def run(cfg: Config, push: bool = True) -> int:
    if not (cfg.vault / ".git").exists():
        print(f"{cfg.vault} is not a git repository. Run: git -C {cfg.vault} init")
        return 1
    with single_run(cfg) as ok:
        if not ok:
            return 0
        print(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')}")
        imp = importers.run(cfg)
        if imp.written:
            print(f"import: {len(imp.planned)} files tracked, {imp.written} written")
        for subject in commit.run(cfg):
            print(subject)
        if push and cfg.git_push and has_remote(cfg):
            _git(cfg, "pull", "-q", "--rebase", "--autostash")
            _git(cfg, "push", "-q")
    return 0
