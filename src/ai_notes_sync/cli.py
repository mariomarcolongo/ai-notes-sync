"""Command line: ai-notes-sync <command>."""

import argparse
import sys

from pathlib import Path

from . import __version__, apps, commit, guard, importers, relay, schedule, stats, sync, undo
from .config import CONFIG_PATH, load


def scan_paths(cfg, paths) -> int:
    roots = [Path(p).expanduser() for p in paths] or [cfg.vault]
    files = []
    for r in roots:
        files += [r] if r.is_file() else [f for f in r.rglob("*.md") if ".git" not in f.parts]
    hits = 0
    for f in sorted(files):
        try:
            findings = guard.scan(f.read_text(errors="replace"))
        except OSError:
            continue
        if findings:
            hits += 1
            print(f)
            for x in findings:
                print(f"  [{x.severity}] {x.kind} (line {x.line}): {x.excerpt}")
    print(f"\n{len(files)} file(s) checked, {hits} with findings.")
    return 1 if hits else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="ai-notes-sync",
        description="Collect your AI assistants' notes into one Git-backed Basic Memory vault "
                    "and record which app, model and setting made each edit.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sync", help="import, commit per author, pull and push (what the timer runs)")
    sub.add_parser("import", help="only copy AI notes into imported/")
    sub.add_parser("commit", help="only commit changes, one commit per author and model")
    r = sub.add_parser("relay", help="MCP relay that apps run instead of Basic Memory")
    r.add_argument("label", help="app label recorded with each edit, e.g. claude-desktop")
    a = sub.add_parser("apps", help="connect AI apps to the relay (dry run unless --apply)")
    a.add_argument("--apply", action="store_true")
    a.add_argument("--only", nargs="*", metavar="LABEL")
    ru = sub.add_parser("rules", help="add the shared-notes rule to AI instructions (dry run unless --apply)")
    ru.add_argument("--apply", action="store_true")
    s = sub.add_parser("schedule", help="run sync on a timer (macOS launchd)")
    s.add_argument("--every", type=int, default=2, metavar="MINUTES")
    s.add_argument("--remove", action="store_true")
    sub.add_parser("stats", help="edits per app, model, reasoning effort and evidence")
    rv = sub.add_parser("review", help="list notes held back by the injection guard")
    rv.add_argument("--approve", metavar="PATH")
    rv.add_argument("--discard", metavar="PATH")
    sc = sub.add_parser("scan", help="check notes for prompt-injection patterns (reads only)")
    sc.add_argument("paths", nargs="*", help="files or folders (default: the whole vault)")
    u = sub.add_parser("undo", help="undo what one AI app changed (dry run unless --apply)")
    u.add_argument("app", help="app label, e.g. antigravity")
    u.add_argument("--since", help='e.g. "2026-11-06 10:00" or "2 hours ago"')
    u.add_argument("--model", help="only edits by this model")
    u.add_argument("--apply", action="store_true")
    sub.add_parser("config", help="show the settings in use")

    args = p.parse_args(argv)
    cfg = load()

    if args.cmd == "relay":
        return relay.run(cfg, args.label)
    if args.cmd == "sync":
        return sync.run(cfg)
    if args.cmd == "import":
        imp = importers.run(cfg)
        print(f"import: {len(imp.planned)} files tracked, {imp.written} written")
    elif args.cmd == "commit":
        for subject in commit.run(cfg):
            print(subject)
    elif args.cmd == "apps":
        print(apps.run(cfg, args.apply, args.only))
        if not args.apply:
            print("\nNothing changed. Run again with --apply to connect.")
    elif args.cmd == "rules":
        print(apps.run_rules(cfg, args.apply))
    elif args.cmd == "schedule":
        print(schedule.remove(cfg) if args.remove else schedule.install(cfg, args.every))
    elif args.cmd == "stats":
        print(stats.run(cfg))
    elif args.cmd == "review":
        if args.approve:
            print(guard.approve(cfg, args.approve))
        elif args.discard:
            print(guard.discard(cfg, args.discard))
        else:
            print(guard.review_text(cfg))
    elif args.cmd == "scan":
        return scan_paths(cfg, args.paths)
    elif args.cmd == "undo":
        print(undo.run(cfg, args.app, args.since, args.model, args.apply))
    elif args.cmd == "config":
        print(f"config file: {CONFIG_PATH}{'' if CONFIG_PATH.exists() else ' (not found, using defaults)'}")
        for k in ("vault", "state_dir", "project_roots", "sources", "git_push"):
            print(f"{k}: {getattr(cfg, k)}")
        print(f"server: {' '.join(cfg.server())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
