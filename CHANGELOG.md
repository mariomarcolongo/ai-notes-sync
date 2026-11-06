# Changelog

## 0.1.0 — 2026-11-06

First release.

- Import notes from Claude Code memory, Codex memories, Antigravity conversations and project instruction files.
- MCP relay that records which app changed which note, with self-reported model details.
- Model and reasoning effort verified from Claude Code and Codex logs.
- One Git commit per app and model setup, with `AI-*` trailers, and an edit log in `.ai-notes/edits.jsonl`.
- `apps`, `rules`, `schedule` and `stats` commands.
- Prompt-injection guard: scan AI edits and imports, quarantine suspicious notes (`review`, `scan`), hold back large deletions, protect the Filing guide, read-only apps, and `undo` per app or model.
- Safer sync: no autostash; a pull that would conflict is skipped or undone.
- Licensed under Apache-2.0 with a NOTICE file and CITATION.cff.
