import os
import time

from ai_notes_sync import importers
from conftest import write


def claude_project_dir(cfg, name):
    return cfg.home / ".claude/projects" / (str(cfg.home).replace("/", "-") + f"-Code-{name}") / "memory"


def test_claude_code_memory_is_filed_per_project(cfg):
    mem = claude_project_dir(cfg, "my-site")
    write(mem / "MEMORY.md", "- [Prefs](prefs.md)\n")
    write(mem / "prefs.md", "---\nname: user-prefs\ndescription: x\n---\n\nLikes short answers.\n")

    importers.run(cfg)

    out = cfg.imported / "claude-code/my-site"
    text = (out / "prefs.md").read_text()
    assert 'title: "User prefs"' in text
    assert "source_app: claude-code" in text
    assert "description: x" in text  # original frontmatter kept
    assert "name: user-prefs" in text
    assert text.endswith("Likes short answers.\n")
    assert (out / "MEMORY.md").exists()


def test_codex_sessions_are_sorted_by_month(cfg):
    base = cfg.home / ".codex/memories"
    write(base / "rollout_summaries/2026-10-23T20-23-48-xUMX-some_slug.md",
          "thread_id: 1\n\n# Fix the login bug\n\nDetails.\n")
    write(base / "MEMORY.md", "memory\n")
    write(base / "skills/release/SKILL.md", "# Release\n")
    write(base / ".git/HEAD", "ref\n")

    importers.run(cfg)

    out = cfg.imported / "codex"
    assert (out / "sessions/2026-10/2026-10-23 Fix the login bug.md").exists()
    assert (out / "memory/MEMORY.md").exists()
    assert (out / "skills/release.md").exists()


def test_antigravity_conversations_get_titled_folders_and_skip_noise(cfg):
    conv = cfg.home / ".gemini/antigravity/brain/abc123"
    write(conv / "task.md", "# Task: Build the dashboard\n")
    write(conv / "walkthrough.md", "# Walkthrough\n")
    write(conv / "scratchpad_x1.md", "noise")
    write(conv / ".system_generated/steps/1/content.md", "token: secret")
    # same conversation, older copy in the IDE app
    old = write(cfg.home / ".gemini/antigravity-ide/brain/abc123/task.md", "# Task: Old title\n")
    os.utime(old, (time.time() - 86400, time.time() - 86400))

    importers.run(cfg)

    folders = list((cfg.imported / "antigravity").glob("*/*"))
    assert len(folders) == 1
    assert folders[0].name.endswith("Build the dashboard")
    names = sorted(p.name for p in folders[0].rglob("*.md"))
    assert names == ["task.md", "walkthrough.md"]
    assert "source_app: antigravity\n" in (folders[0] / "task.md").read_text()


def test_project_instruction_files(cfg):
    write(cfg.home / "Code/proj/CLAUDE.md", "Use tabs.\n")
    write(cfg.home / "Code/proj/AGENTS.md", "")  # empty files are skipped
    importers.run(cfg)
    assert (cfg.imported / "instructions/proj/CLAUDE.md").exists()
    assert not (cfg.imported / "instructions/proj/AGENTS.md").exists()


def test_rerun_writes_only_changed_sources(cfg):
    mem = claude_project_dir(cfg, "site")
    src = write(mem / "a.md", "one\n")
    assert importers.run(cfg).written == 1
    dest = cfg.imported / "claude-code/site/a.md"
    dest.write_text(dest.read_text() + "permalink: added-by-basic-memory\n")
    assert importers.run(cfg).written == 0
    assert "added-by-basic-memory" in dest.read_text()
    src.write_text("two\n")
    assert importers.run(cfg).written == 1
    assert dest.read_text().endswith("two\n")


def test_disabled_source_is_skipped(cfg):
    write(cfg.home / ".codex/memories/MEMORY.md", "x\n")
    cfg.sources["codex"] = False
    assert importers.run(cfg).planned == {}


def test_clean_names():
    assert importers.clean('a/b: "c"?') == "a b c"
    assert importers.clean("") == "untitled"
    assert importers.strip_prefix("Implementation Plan - New UI") == "New UI"
