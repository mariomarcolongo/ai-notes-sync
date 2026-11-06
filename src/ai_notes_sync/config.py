"""Settings, read from ~/.config/ai-notes-sync/config.json (all keys optional)."""

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

CONFIG_PATH = Path(os.environ.get("AI_NOTES_SYNC_CONFIG", "~/.config/ai-notes-sync/config.json")).expanduser()

DEFAULT_APP_NAMES = {
    "claude-desktop": "Claude Desktop",
    "claude-code": "Claude Code",
    "antigravity": "Antigravity",
    "antigravity-ide": "Antigravity IDE",
    "cursor": "Cursor",
    "vscode": "VS Code",
    "codex": "Codex",
    "gemini": "Gemini",
    "gemini-cli": "Gemini CLI",
    "project-instructions": "Project instruction files",
}


@dataclass
class Config:
    home: Path = field(default_factory=Path.home)
    vault: Path = field(default_factory=lambda: Path("~/basic-memory").expanduser())
    state_dir: Path = field(default_factory=lambda: Path("~/.local/state/ai-notes-sync").expanduser())
    project_roots: List[Path] = field(default_factory=lambda: [Path("~/Code").expanduser()])
    sources: Dict[str, bool] = field(default_factory=lambda: {
        "claude_code": True, "codex": True, "antigravity": True, "instructions": True})
    server_command: List[str] = field(default_factory=list)
    app_names: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_APP_NAMES))
    git_push: bool = True
    # prompt-injection guard
    guard: bool = True
    protected: List[str] = field(default_factory=lambda: ["notes/Filing guide.md", "README.md"])
    read_only_apps: List[str] = field(default_factory=list)
    shrink_ratio: float = 0.4   # an AI edit keeping less than this share of a note is held back
    shrink_min_chars: int = 400
    notify: bool = True

    # derived paths
    @property
    def imported(self) -> Path:
        return self.vault / "imported"

    @property
    def edit_log(self) -> Path:
        return self.state_dir / "edits.jsonl"

    @property
    def ledger(self) -> Path:
        return self.vault / ".ai-notes" / "edits.jsonl"

    def name(self, app: str) -> str:
        return self.app_names.get(app, app)

    def server(self) -> List[str]:
        if self.server_command:
            return self.server_command
        exe = shutil.which("basic-memory") or str(self.home / ".local/bin/basic-memory")
        return [exe, "mcp"]


def load(path: Optional[Path] = None) -> Config:
    path = path or CONFIG_PATH
    cfg = Config()
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return cfg
    for key in ("vault", "state_dir"):
        if key in data:
            setattr(cfg, key, Path(data[key]).expanduser())
    if "project_roots" in data:
        cfg.project_roots = [Path(p).expanduser() for p in data["project_roots"]]
    if "sources" in data:
        cfg.sources.update(data["sources"])
    if "server_command" in data:
        cfg.server_command = list(data["server_command"])
    if "app_names" in data:
        cfg.app_names.update(data["app_names"])
    for key in ("git_push", "guard", "notify"):
        if key in data:
            setattr(cfg, key, bool(data[key]))
    for key in ("protected", "read_only_apps"):
        if key in data:
            setattr(cfg, key, list(data[key]))
    if "shrink_ratio" in data:
        cfg.shrink_ratio = float(data["shrink_ratio"])
    if "shrink_min_chars" in data:
        cfg.shrink_min_chars = int(data["shrink_min_chars"])
    return cfg
