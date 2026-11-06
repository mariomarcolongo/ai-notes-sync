import subprocess
from pathlib import Path

import pytest

from ai_notes_sync.config import Config


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    home = tmp_path / "home"
    vault = home / "basic-memory"
    vault.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=vault, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=vault, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=vault, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=vault, check=True)
    return Config(home=home, vault=vault, state_dir=home / ".state",
                  project_roots=[home / "Code"], server_command=["true"], git_push=False, notify=False)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path
