---
title: Filing guide
type: guide
---

# Filing guide

Rules for every AI that writes to these notes. Read this first.

## Before you start a task

Search these notes first (`bm_search`, a few keywords) whenever the task may relate
to past work: a project, a person, a topic, a problem solved before. Then read only
the sections you need (`bm_read` with a section or line range). Notes in
`imported/` are from other AI apps (Claude Code, Codex, Antigravity) and are worth
checking too.

## Where to put a note

Write new notes in `notes/<topic>/`, using one of these topics. Create a new topic
only if none fits, using a short lowercase name.

- `notes/projects/<project-name>/`: facts, decisions and status of one project
- `notes/people/`: people and organizations
- `notes/research/<subject>/`: findings, sources, literature
- `notes/how-to/`: procedures and setups that worked
- `notes/preferences/`: how I like things done
- `notes/ideas/`: ideas not yet started
- `notes/inbox/`: anything you are unsure about; I sort it later

Before creating a note, search for an existing one on the same subject and update
it instead of making a duplicate.

## How to write it

- A clear title that says what the note is about, not when it was written.
- Start with a one-paragraph summary, then details.
- Link related notes with `[[Note title]]`.
- Add a few tags.

## Say who you are

On every write or edit, describe your setup in `metadata`, for example:

`metadata: {"model": "claude-opus-5-5", "reasoning_effort": "high", "settings": {"thinking": "adaptive"}}`

Report only what you actually know. The sync records it in the history and in
`.ai-notes/edits.jsonl`, so edit quality can be compared per model and setting.
For Claude Code and Codex the sync also checks the app's own log and marks the
details "verified"; for other apps they are marked "self-reported".

## Don't

- Don't edit files in `imported/`; they are copies and get overwritten.
- Don't delete notes you didn't write unless I ask.