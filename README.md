# ai-notes-sync

**One Git-backed home for everything your AI assistants write down, and a record of which app, model and setting made each change.**

Claude Code, Codex, Antigravity and other assistants each keep useful notes (memories, plans, session summaries, project instructions) in their own hidden folders. None of them can see the others' notes, and none records who changed what.

`ai-notes-sync` works with [Basic Memory](https://github.com/basicmachines-co/basic-memory), a local, open-source Markdown knowledge base with an MCP server, and adds three things:

1. **Collect:** copies each AI app's own notes into your vault, sorted into readable folders, and keeps the copies up to date.
2. **Attribute:** a small MCP relay sits between each app and Basic Memory and records which app changed which note, plus the model and settings.
3. **Version:** commits every change to Git, **one commit per app and model setup**, so `git log` and GitHub show who changed what. Every AI edit is also logged to a JSONL file for later evaluation.

Everything runs on your machine. The only network traffic is `git push` to a remote you choose (or none).

## What a commit looks like

```
Author: Claude Code (claude-opus-5-5, effort high) <claude-code@ai-notes.local>

    Claude Code (claude-opus-5-5, effort high): changed 1 note(s)

    - notes/projects/site/Deploy checklist.md

    AI-App: Claude Code
    AI-Model: claude-opus-5-5
    AI-Reasoning-Effort: high
    AI-Evidence: verified
    AI-App-Version: 2.1.317
    AI-Session: a064c882-…
```

`AI-Evidence` says how much to trust the model details:

| Evidence | Meaning | Apps |
|---|---|---|
| `verified` | Read from the app's own log of that exact tool call | Claude Code, Codex |
| `self-reported` | What the AI said about itself in the tool call's `metadata` | any app |
| `unknown` | The AI didn't say; the app is still recorded | any app |

MCP tells a server which *app* is connected, but not which model, so the relay can always name the app. The model comes from the app's log or from the AI itself.

## Vault layout

```
~/basic-memory/
  notes/                 notes the AIs and you write, by topic
  imported/              copies, refreshed automatically; don't edit
    claude-code/<project>/          Claude Code memory per project
    codex/{memory,sessions/<month>,skills,notes}/
    antigravity/<month>/<date title>/   one folder per conversation
    instructions/<project>/         CLAUDE.md, AGENTS.md, GEMINI.md
  .ai-notes/edits.jsonl  one line per AI edit: time, app, model, effort, evidence, files
```

Antigravity's scratch files and saved web pages (`.system_generated/`) are skipped: they're noise and can contain tokens.

## Install

Requires Python 3.9+, Git and [uv](https://docs.astral.sh/uv/). Tested on macOS; the core works on Linux.

```bash
uv tool install basic-memory --prerelease=allow
uv tool install git+https://github.com/mariomarcolongo/ai-notes-sync
```

Make the vault a Git repository (optionally with a private remote):

```bash
basic-memory project list          # creates ~/basic-memory on first run
git -C ~/basic-memory init -b main
gh repo create ai-notes --private --source ~/basic-memory --remote origin   # optional
```

Connect your AI apps to the relay. Each command shows what it would change and changes nothing until you add `--apply`. Every file is backed up first.

```bash
ai-notes-sync apps            # preview
ai-notes-sync apps --apply    # Claude Desktop, Claude Code, Codex, Cursor, VS Code, Antigravity…
ai-notes-sync rules --apply   # tell the AIs to search first, file notes properly and report their model
ai-notes-sync schedule --every 2
```

Restart the apps. Copy [`docs/filing-guide.md`](docs/filing-guide.md) to `~/basic-memory/notes/Filing guide.md` (or write your own) so the AIs know where to put notes.

## Commands

| Command | What it does |
|---|---|
| `sync` | import, commit per author, pull, push (what the timer runs) |
| `import` / `commit` | just one of the steps |
| `relay <label>` | the MCP relay an app runs instead of Basic Memory |
| `apps [--apply] [--only LABEL…]` | connect apps to the relay |
| `rules [--apply]` | add the shared-notes rule to global AI instructions |
| `schedule --every N` / `--remove` | timer (launchd on macOS, a cron line elsewhere) |
| `stats` | edits per app, model, reasoning effort and evidence |
| `config` | settings in use |

## Settings

Optional, in `~/.config/ai-notes-sync/config.json`:

```json
{
  "vault": "~/basic-memory",
  "project_roots": ["~/Code", "~/Projects"],
  "sources": {"claude_code": true, "codex": true, "antigravity": true, "instructions": true},
  "git_push": true
}
```

`project_roots` are the folders searched (one level deep) for `CLAUDE.md`, `AGENTS.md` and `GEMINI.md`.

## Limits

- **Model details depend on the app.** Only Claude Code and Codex keep logs that can be checked. Elsewhere it's the AI's word.
- **Edits made without the relay** (by hand, in Obsidian, or by an app not connected) are committed under your Git name.
- **Apps that keep notes only in the cloud** (ChatGPT, the Gemini app, Claude Desktop chats) can't be collected, and can only use local MCP servers if the app supports them.
- **Copies are one-way.** Editing a file in `imported/` doesn't change the original, and the next change to the original overwrites it.
- **Sensitive content.** Notes can contain personal data. Use a private remote, or none.

## Related projects

- [Basic Memory](https://github.com/basicmachines-co/basic-memory): the knowledge base this builds on. Its maintainers plan native revision history (see their issue #1156); if it lands with authorship, part of this tool becomes unnecessary.
- [GitMemo](https://github.com/sahadev/GitMemo): captures AI conversations, clipboard and notes into a Git repo. Broader capture; no per-edit model attribution.

## License

MIT
