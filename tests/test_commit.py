import json
import subprocess

from ai_notes_sync import commit, stats
from conftest import write


def log(cfg):
    out = subprocess.run(["git", "log", "--format=%an|%s|%(trailers:key=AI-Evidence,valueonly)"],
                         cwd=cfg.vault, capture_output=True, text=True, check=True).stdout
    return [l for l in out.splitlines() if l.strip()]


def record(cfg, **e):
    cfg.edit_log.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg.edit_log, "a") as f:
        f.write(json.dumps({"time": "2026-11-06T10:00:00+0000", "ok": True, "tool": "bm_write", **e}) + "\n")


def test_one_commit_per_author_and_model(cfg):
    write(cfg.vault / "notes/ai.md", "by ai\n")
    write(cfg.vault / "notes/mine.md", "by me\n")
    write(cfg.vault / "imported/codex/memory/MEMORY.md", "---\nsource_app: codex\n---\nx\n")
    record(cfg, app="cursor", client="Cursor", client_version="3", paths=["notes/ai.md"],
           model="gpt-x", self_reported={"model": "gpt-x", "reasoning_effort": "high"})

    subjects = commit.run(cfg)

    assert "Cursor (gpt-x, effort high): changed 1 note(s)" in subjects
    assert "Codex: imported/updated 1 note(s)" in subjects
    assert "Test User: edited 1 note(s)" in subjects
    assert "Record AI edit details" in subjects
    authors = {l.split("|")[0] for l in log(cfg)}
    assert {"Cursor (gpt-x, effort high)", "Codex", "Test User", "ai-notes-sync"} <= authors
    assert any(l.endswith("|self-reported") for l in log(cfg))

    led = json.loads(cfg.ledger.read_text().splitlines()[0])
    assert led["model"] == "gpt-x" and led["evidence"] == "self-reported" and led["client"] == "Cursor 3"
    assert "gpt-x" in stats.run(cfg)


def test_nothing_to_commit_and_log_read_once(cfg):
    assert commit.run(cfg) == []
    assert stats.run(cfg) == "No AI edits recorded yet."
    cfg.ledger.parent.mkdir(parents=True)
    cfg.ledger.write_text("")
    assert stats.run(cfg) == "No AI edits recorded yet."
    write(cfg.vault / "notes/a.md", "a\n")
    record(cfg, app="vscode", paths=["notes/a.md"])
    commit.run(cfg)
    write(cfg.vault / "notes/a.md", "changed by hand\n")
    assert commit.run(cfg) == ["Test User: edited 1 note(s)"]


def test_unicode_paths(cfg):
    write(cfg.vault / "imported/antigravity/2026-10/2026-10-05 Plan — Draft 🦟/task.md",
          "---\nsource_app: antigravity\n---\n")
    assert commit.run(cfg) == ["Antigravity: imported/updated 1 note(s)"]
