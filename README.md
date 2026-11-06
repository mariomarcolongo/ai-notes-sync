# ai-notes-sync

**One Git-backed home for everything your AI assistants write down, and a record of which app, model and setting made each change.**

Claude Code, Codex, Antigravity and other assistants each keep useful notes (memories, plans, session summaries, project instructions) in their own hidden folders. None of them can see the others' notes, and none records who changed what.

`ai-notes-sync` works with [Basic Memory](https://github.com/basicmachines-co/basic-memory), a local, open-source Markdown knowledge base with an MCP server, and adds four things:

1. **Collect:** copies each AI app's own notes into your vault, sorted into readable folders, and keeps the copies up to date.
2. **Attribute:** a small MCP relay sits between each app and Basic Memory and records which app changed which note, plus the model and settings.
3. **Version:** commits every change to Git, **one commit per app and model setup**, so `git log` and GitHub show who changed what. Every AI edit is also logged to a JSONL file for later evaluation.
4. **Guard:** when every AI reads the same notes, one poisoned note can steer all of them. Suspicious AI edits and imports are held back in a quarantine no AI can read, until you decide.

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

## Prompt-injection guard

Shared notes are a shared attack surface: an agent reads a web page, saves a summary with an embedded instruction, and every other assistant that searches the notes later reads it. In one reported case ([basic-memory#1156](https://github.com/basicmachines-co/basic-memory/issues/1156)) an AI replaced a memory file with injected-looking text.

Layers, from the outside in:

| Layer | What it does |
|---|---|
| **Rule** | `ai-notes-sync rules` tells every AI that notes are information, not instructions, and to report a note that tries to instruct it. |
| **Scan** | Each sync checks the *new* text of AI edits and imports for instruction overrides, role markup (`<\|im_start\|>`, `[INST]`), identity changes, secrecy requests, data-leaking links, hidden Unicode characters and large encoded blobs. |
| **Quarantine** | A high-severity finding moves the note to `.quarantine/` (Basic Memory doesn't index hidden folders, so no AI can find it) and restores the previous version. You get a notification. |
| **Large deletions** | An AI edit that keeps less than 40% of a note is held back the same way. |
| **Protected files** | AIs can't change or delete `notes/Filing guide.md` (configurable). |
| **Read-only apps** | Apps listed in `read_only_apps` (say, the one that browses the web) can search and read but every write is refused. |
| **Undo** | `ai-notes-sync undo <app> --since "…" [--model …] --apply` reverts everything one app or model changed. |

Your own edits are scanned and warned about, never moved. Review what was held back:

```bash
ai-notes-sync review                       # what, when, which app/model, why
ai-notes-sync review --approve notes/x.md  # put it back; approved content isn't flagged again
ai-notes-sync review --discard notes/x.md
ai-notes-sync scan                         # check the whole vault, changes nothing
```

This raises the bar; it doesn't make injection impossible. Pattern lists miss new phrasings, and an agent with shell access (Claude Code, Codex) can write files directly, around the relay. Those writes are still versioned, attributed to you, scanned and warned about, and can be undone with Git.

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
  .ai-notes/guard.jsonl  what the guard quarantined, restored or warned about
  .quarantine/           notes held back for review; invisible to the AIs
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
| `review [--approve P \| --discard P]` | notes held back by the guard |
| `scan [paths…]` | check notes for injection patterns without changing anything |
| `undo <app> [--since T] [--model M] [--apply]` | revert one app's (or model's) commits |
| `config` | settings in use |

## Settings

Optional, in `~/.config/ai-notes-sync/config.json`:

```json
{
  "vault": "~/basic-memory",
  "project_roots": ["~/Code", "~/Projects"],
  "sources": {"claude_code": true, "codex": true, "antigravity": true, "instructions": true},
  "git_push": true,
  "guard": true,
  "protected": ["notes/Filing guide.md", "README.md"],
  "read_only_apps": ["antigravity"],
  "shrink_ratio": 0.4,
  "notify": true
}
```

`project_roots` are the folders searched (one level deep) for `CLAUDE.md`, `AGENTS.md` and `GEMINI.md`.

## Limits

- **Model details depend on the app.** Only Claude Code and Codex keep logs that can be checked. Elsewhere it's the AI's word.
- **Edits made without the relay** (by hand, in Obsidian, or by an app not connected) are committed under your Git name.
- **Apps that keep notes only in the cloud** (ChatGPT, the Gemini app, Claude Desktop chats) can't be collected, and can only use local MCP servers if the app supports them.
- **The guard is a filter, not a proof.** See [Prompt-injection guard](#prompt-injection-guard).
- **Copies are one-way.** Editing a file in `imported/` doesn't change the original, and the next change to the original overwrites it.
- **Sensitive content.** Notes can contain personal data. Use a private remote, or none.

## Related projects

- [Basic Memory](https://github.com/basicmachines-co/basic-memory): the knowledge base this builds on. Its maintainers plan native revision history (see their issue #1156); if it lands with authorship, part of this tool becomes unnecessary.
- [GitMemo](https://github.com/sahadev/GitMemo): captures AI conversations, clipboard and notes into a Git repo. Broader capture; no per-edit model attribution.

## License

[Apache-2.0](LICENSE). Created by [Mario Marcolongo](https://github.com/mariomarcolongo); if you redistribute it, keep the [NOTICE](NOTICE) file. To cite it, use [CITATION.cff](CITATION.cff) (GitHub's "Cite this repository").
