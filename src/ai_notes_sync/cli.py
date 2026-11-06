"""Command line: ai-notes-sync <command>."""

import argparse
import sys

from . import __version__, apps, commit, importers, relay, schedule, stats, sync
from .config import CONFIG_PATH, load


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
    elif args.cmd == "config":
        print(f"config file: {CONFIG_PATH}{'' if CONFIG_PATH.exists() else ' (not found, using defaults)'}")
        for k in ("vault", "state_dir", "project_roots", "sources", "git_push"):
            print(f"{k}: {getattr(cfg, k)}")
        print(f"server: {' '.join(cfg.server())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
