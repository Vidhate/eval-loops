---
name: orchestrator-stage1-vibe
description: >
  Top-level orchestrator for stage-1 (pre-conviction) eval setup. Walks a solo
  developer with no domain experts and no observability tooling from zero to a
  running vibe-eval loop. Invokes a minimal subset of skills:
  gather-product-context (lightweight), instrument-tracing (minimal logging
  fallback), build-simulation-harness (~10 inputs), and vibe-eval-fast-loop.
  Skips dataset versioning, judge calibration, and rigorous error analysis. Use
  when the user explicitly requests stage-1 evals or when context.md Stage =
  stage-1-vibe.
tools: Read, Write, Edit, Bash, Grep, Glob
---

# Stage-1 Vibe Orchestrator

Get a solo developer from zero to actionable signal in under an hour. Optimize for speed, not rigor.

## Inputs (from caller)

None required. The orchestrator interviews from scratch if `evals/context.md` does not exist.

## Procedure

### Step 0: Journal

Read the engagement journal before doing anything else: `python3 evals/journal.py tail -n 20` to recover what prior runs did and discovered, so you can skip re-asking the user things the journal already answers. After each step below, append a one-line entry (`--actor orchestrator-stage1-vibe`, `--stage stage-1-vibe`).

`evals/journal.py` is installed by the `vibe-eval-fast-loop` skill (Step 1), which you invoke next — as a subagent you cannot resolve bundled plugin paths, so **never author `journal.py` yourself**. If it is still missing when you need it, skip journaling for that step rather than reconstructing it.

### Step 1: Detect or set stage

If `evals/context.md` exists and its Stage field is `stage-1-vibe`, proceed.
If it exists with a different stage, ask the user: "Your context.md says <stage>. Did you want stage-2-rigor or stage-3-production instead?" Hand off to the right orchestrator if so.
If it doesn't exist, run `gather-product-context` in **lightweight mode**: only Vision, Agent Surface Area, and Stage = stage-1-vibe. The other sections can be filled later.

### Step 2: Tracing (lightweight)

Skip OTEL setup at this stage. Instead, instruct the user to wrap their agent entry point with simple file-based logging that captures the WYSIWYG envelope: input, full output, every tool call's full input/output. Output one JSON line per request to `evals/runs/vibe_logs/<timestamp>.jsonl`.

If the user wants real OTEL tracing, route them to `instrument-tracing` and graduate them to stage 2 — vibe-eval doesn't need OTEL.

### Step 3: Run the vibe loop

Invoke `vibe-eval-fast-loop`. It owns the rest: input generation, run execution, in-chat rendering, vibe annotation, recommend-fix, re-run.

### Step 4: Watch for graduation signals

After each vibe-loop iteration, check for graduation signals. Tell the user to graduate if any are true:
- They've completed 3+ vibe-loop iterations this week — manual review cost is exceeding rigor setup cost.
- Domain experts have become available.
- The agent has gone live with real users.
- The user is asking for failure-mode buckets, judges, or CI integration — they've left vibe territory.

When graduating:
1. Update `context.md` Stage to `stage-2-rigor`.
2. Promote the latest vibe run into a real dataset via `manage-eval-datasets`.
3. Hand off to `orchestrator-stage2-rigor`.

## What This Orchestrator Does Not Do

- Does not invoke `manage-eval-datasets`, `run-annotation-session`, `error-analysis-and-triage`, `build-auto-judge`, `calibrate-judge-loop`, `fix-and-ablate-loop`. Those are stage-2 tools.
- Does not invoke profile lenses (`guardrails-eval-profile`, `rag-eval-profile`). Lightweight rendering of guardrail/RAG features is fine in vibe mode; rigorous separation comes at stage 2.
- Does not enforce input versioning. Inputs can be regenerated each run.

## Anti-Patterns

- Setting up OTEL at stage 1. The user will graduate before reaping the benefit.
- Spawning an LLM council at stage 1. Council annotation is for when you have a frozen labeled dataset — vibe stage doesn't have one.
- Letting the user run this orchestrator while in stage 2 or 3 just because it's faster. Skipping rigor at those stages is more expensive than running it.
- Forgetting to check for graduation signals after each iteration.
