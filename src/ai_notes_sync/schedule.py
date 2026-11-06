"""Run `ai-notes-sync sync` on a timer: launchd on macOS, a cron line elsewhere."""

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from .apps import relay_command
from .config import Config

LABEL = "io.github.ai-notes-sync"


def plist_path(cfg: Config) -> Path:
    return cfg.home / "Library/LaunchAgents" / f"{LABEL}.plist"


def _domain() -> str:
    return f"gui/{os.getuid()}"


def install(cfg: Config, minutes: int) -> str:
    cmd = relay_command() + ["sync"]
    if sys.platform != "darwin":
        return ("Add this line with `crontab -e`:\n\n"
                f"*/{minutes} * * * * {' '.join(cmd)} >> {cfg.state_dir}/sync.log 2>&1")
    path = plist_path(cfg)
    log = cfg.home / "Library/Logs/ai-notes-sync.log"
    plist = {
        "Label": LABEL,
        "ProgramArguments": cmd,
        "StartInterval": minutes * 60,
        "RunAtLoad": True,
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
        # git credential helpers such as `gh` usually live in Homebrew's bin
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["launchctl", "bootout", f"{_domain()}/{LABEL}"], capture_output=True)
    with open(path, "wb") as f:
        plistlib.dump(plist, f)
    r = subprocess.run(["launchctl", "bootstrap", _domain(), str(path)], capture_output=True, text=True)
    if r.returncode:
        return f"Wrote {path}, but launchctl failed: {r.stderr.strip()}"
    return f"Sync runs every {minutes} min (and at login). Log: {log}"


def remove(cfg: Config) -> str:
    if sys.platform != "darwin":
        return "Remove the ai-notes-sync line with `crontab -e`."
    subprocess.run(["launchctl", "bootout", f"{_domain()}/{LABEL}"], capture_output=True)
    path = plist_path(cfg)
    if path.exists():
        path.unlink()
    return "Scheduled sync removed."
