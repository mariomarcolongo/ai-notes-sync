"""Summarize recorded AI edits by app, model, reasoning effort and evidence."""

import json
from collections import Counter
from typing import List

from .config import Config


def table(rows: List[List[str]]) -> str:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    out = []
    for n, r in enumerate(rows):
        out.append("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())
        if n == 0:
            out.append("  ".join("-" * w for w in widths))
    return "\n".join(out)


def run(cfg: Config) -> str:
    if not cfg.ledger.exists():
        return "No AI edits recorded yet."
    counts: Counter = Counter()
    files: Counter = Counter()
    for line in cfg.ledger.read_text().splitlines():
        try:
            e = json.loads(line)
        except Exception:
            continue
        key = (cfg.name(e.get("app") or "?"), e.get("model") or "unknown",
               e.get("reasoning_effort") or "unknown", e.get("evidence") or "unknown")
        counts[key] += 1
        files[key] += len(e.get("paths") or [])
    if not counts:
        return "No AI edits recorded yet."
    rows = [["App", "Model", "Effort", "Evidence", "Edits", "Files"]]
    for key, n in counts.most_common():
        rows.append([*key, str(n), str(files[key])])
    return table(rows)
