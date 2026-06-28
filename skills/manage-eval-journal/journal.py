#!/usr/bin/env python3
"""Append-only journal for an eval engagement.

Single source of truth: evals/journal.jsonl (one JSON object per line).
All writes go through `append` so that:
  - the timestamp comes from the system clock, never a model's guess;
  - every entry is exactly one line (newlines in the summary are collapsed);
  - concurrent writers cannot interleave (atomic O_APPEND + flock, entries
    kept well under PIPE_BUF).

Stdlib only, zero configuration: the journal lives next to this script
(evals/journal.jsonl) regardless of project or working directory, so no
per-project customization is ever needed. Cross-platform: on POSIX
(macOS/Linux) it adds flock for cross-process safety; on platforms without
fcntl (e.g. Windows) it falls back to atomic O_APPEND writes.

  python3 evals/journal.py append --type learning --actor vibe-eval-fast-loop \
      --stage stage-1-vibe --summary "3/10 failed: SQL drops user filters" \
      --refs runs/vibe_142/

  python3 evals/journal.py tail -n 20
  python3 evals/journal.py tail -n 50 --stage stage-2-rigor --type learning
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl  # POSIX advisory locking; absent on Windows
except ImportError:  # pragma: no cover
    fcntl = None

JOURNAL = Path(__file__).resolve().parent / "journal.jsonl"
MAX_SUMMARY = 500
VALID_TYPES = ("action", "learning")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append(args):
    if args.type not in VALID_TYPES:
        sys.exit(f"--type must be one of {VALID_TYPES}")
    summary = " ".join(args.summary.split())  # collapse all whitespace -> single line
    if len(summary) > MAX_SUMMARY:
        summary = summary[: MAX_SUMMARY - 1] + "…"
    entry = {
        "ts": _now(),
        "stage": args.stage,
        "actor": args.actor,
        "type": args.type,
        "summary": summary,
    }
    if args.refs:
        entry["refs"] = [r.strip() for r in args.refs.split(",") if r.strip()]
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    # O_APPEND makes the kernel position each write at EOF; flock serializes
    # writers so two parallel appends can never interleave.
    fd = os.open(JOURNAL, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, line.encode("utf-8"))
    finally:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    print(entry["ts"])


def tail(args):
    if not JOURNAL.exists():
        return
    out = []
    for raw in JOURNAL.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            e = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if args.stage and e.get("stage") != args.stage:
            continue
        if args.type and e.get("type") != args.type:
            continue
        if args.since and e.get("ts", "") < args.since:
            continue
        if args.grep and args.grep.lower() not in e.get("summary", "").lower():
            continue
        out.append(e)
    for e in out[-args.n :]:
        refs = (" " + " ".join(e["refs"])) if e.get("refs") else ""
        print(
            f'{e["ts"]} [{e.get("stage", "?")}] {e.get("actor", "?")} '
            f'{e.get("type", "?")}: {e.get("summary", "")}{refs}'
        )


def main():
    p = argparse.ArgumentParser(description="Append-only eval journal.")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("append", help="append one entry")
    a.add_argument("--type", required=True, help="action | learning")
    a.add_argument("--actor", required=True, help="skill/agent name writing the entry")
    a.add_argument("--stage", default="", help="stage-1-vibe | stage-2-rigor | stage-3-production")
    a.add_argument("--summary", required=True, help="one-line summary (auto-collapsed & truncated)")
    a.add_argument("--refs", default="", help="comma-separated artifact paths (pointers, not bodies)")
    a.set_defaults(func=append)

    t = sub.add_parser("tail", help="read most recent entries (oldest first, newest last)")
    t.add_argument("-n", type=int, default=20, help="how many entries to show (default 20)")
    t.add_argument("--stage", default="", help="filter by stage")
    t.add_argument("--type", default="", help="filter by type (action | learning)")
    t.add_argument("--since", default="", help="ISO timestamp lower bound, e.g. 2026-06-01T00:00:00Z")
    t.add_argument("--grep", default="", help="case-insensitive substring filter on summary")
    t.set_defaults(func=tail)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
