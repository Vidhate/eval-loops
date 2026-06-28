---
name: manage-eval-journal
description: >
  Maintain an append-only journal of an eval engagement so any skill, subagent,
  or fresh session can recover what has already happened. Ships a helper
  (journal.py) that records actions and learnings to evals/journal.jsonl with
  system-clock timestamps and atomic, concurrency-safe appends. Use to bootstrap
  the journal at the start of an engagement, and read its contracts before any
  skill writes to or reads from the journal. Do NOT duplicate artifact bodies
  into the journal — log one-line pointers to the files instead.
---

# Manage Eval Journal

A single append-only log, `evals/journal.jsonl`, is the memory of the eval engagement. Every other skill writes a one-line entry when it does something or learns something, and reads recent entries on startup to recover context. This is how a re-run — or a fresh agent — picks up where the last one left off without re-interrogating the user.

## Overview

1. Bootstrap: ensure `evals/journal.py` exists (copy the helper shipped with this skill).
2. Write: record actions and learnings through the helper — never by hand-editing the file.
3. Read: tail the most recent entries first; page further back only when needed.

## Bootstrap

The helper script ships alongside this skill as `journal.py`. Copy it into the project — **never rewrite it by hand**; a reconstructed copy loses the atomic-append (`flock` + single-line) and `</`-escape guarantees that are the entire point of the helper.

```bash
mkdir -p evals
test -f evals/journal.py || cp "${CLAUDE_SKILL_DIR}/journal.py" evals/journal.py
```

`${CLAUDE_SKILL_DIR}` resolves to this skill's own directory at runtime — it is the only reliable way to locate a bundled file. If the copy fails (e.g., the variable is unset in some runtime), surface the error and stop; do NOT author a replacement `journal.py` from the CLI signature. It is stdlib-only (POSIX, macOS/Linux) and has no dependencies.

**Who can install it:** only a *skill* can resolve `${CLAUDE_SKILL_DIR}`. Subagents (the orchestrators, `error-analysis-and-triage`, `calibrate-judge-loop`, `fix-and-ablate-loop`) have no path to bundled plugin files, so they must **never** create `journal.py` — they only call an `evals/journal.py` that a skill already installed. The install happens in the first skill of any engagement: `gather-product-context` (stage 2) or `vibe-eval-fast-loop` (stage 1), each copying from a sibling path `${CLAUDE_SKILL_DIR}/../manage-eval-journal/journal.py`. If a subagent finds `evals/journal.py` missing, it skips journaling rather than reconstructing it.

## Schema

One JSON object per line. The helper writes exactly these fields:

```json
{"ts":"2026-06-27T14:02:11Z","stage":"stage-1-vibe","actor":"vibe-eval-fast-loop","type":"learning","summary":"3/10 failed: SQL drops user filters","refs":["runs/vibe_142/"]}
```

- `ts` — UTC, set by the helper from the system clock. Never pass a timestamp in; models guess clock time wrong.
- `stage` — `stage-1-vibe` / `stage-2-rigor` / `stage-3-production`.
- `actor` — the skill or subagent name writing the entry.
- `type` — `action` (something was done) or `learning` (something was discovered).
- `summary` — one line. The helper collapses newlines and truncates past 500 chars.
- `refs` — optional list of artifact paths. Pointers, not bodies.

## Write Contract

Append through the helper:

```bash
python evals/journal.py append --type learning --actor <skill-name> \
  --stage <stage> --summary "one line" --refs path/a,path/b
```

What to log — the grain is "things a future agent would want to know happened":

- A step or human checkpoint completed (`action`).
- A run, dataset version, judge, or experiment produced — with its path in `refs` (`action`).
- A failure mode discovered, a judge certified or stalled, a fix's measured effect (`learning`).
- A stage graduation (`action`).

Do NOT log: every tool call, every file write, intermediate scratch work, or the contents of an artifact that already lives on disk. Log the pointer (`refs`), not the body.

## Read Contract

On startup, recover context tail-first — keep it small, page back only if the recent window is insufficient:

```bash
python evals/journal.py tail -n 20                 # most recent 20, newest last
python evals/journal.py tail -n 50 --stage stage-2-rigor
python evals/journal.py tail --type learning --grep judge
python evals/journal.py tail --since 2026-06-01T00:00:00Z
```

Start with the default `-n 20`. Go further back (larger `-n`, or `--since`) only when the recent window doesn't explain the current state. Filter with `--stage`, `--type`, or `--grep` to avoid pulling irrelevant history into context.

## Who Writes

- **Orchestrators** write after each step and each human checkpoint.
- **Leaf skills and same-worktree subagents** write their own actions and learnings directly — that is where most discoveries happen.
- **Worktree-isolated subagents do NOT write.** A subagent running in its own git worktree (e.g., `fix-and-ablate-loop` applying one fix per branch) has a *separate copy* of `evals/journal.jsonl`; its appends would be lost or diverge on cleanup. Instead it returns a one-line summary to its supervisor, and the supervisor writes the entry on the main worktree.

## Concurrency

Parallel writers in the same worktree are safe: the helper appends with `O_APPEND` + `flock` and keeps each entry to a single line well under `PIPE_BUF`, so writes cannot interleave. This safety holds only when every write goes through the helper — never hand-append or echo into the file.

## Anti-Patterns

- Writing timestamps from the model instead of letting the helper read the system clock.
- Logging artifact bodies (catalogs, traces, full outputs) instead of `refs` pointers.
- Worktree-isolated subagents appending directly instead of returning to the supervisor.
- Logging every tool call — the journal becomes write-only noise no one reads.
- Reading the whole journal into context when `tail -n 20` would do.
