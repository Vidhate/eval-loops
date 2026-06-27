---
name: vibe-eval-fast-loop
description: >
  Stage-1 fast eval loop for solo developers without domain experts or
  observability tooling. Runs the agent against a small simulated input set,
  renders traces directly in the Claude Code chat window as compact markdown
  tables, and produces vibe-based pass/fail signal. Skips dataset versioning,
  judge calibration, and rigorous error analysis. Use when prerequisites for
  stage-2 rigor are not met. Do NOT use when domain experts are available or
  the agent is in production.
---

# Vibe Eval Fast Loop

Cheap, fast pass/fail signal in a single chat thread. The user is the alias domain expert, the chat window is the review UI, the loop is iteration → eyeball → adjust.

## When This Skill Is Right

All of:
- No domain experts available; the user is reviewing alone.
- No observability vendor wired up.
- The agent is early enough that catching obvious breakage matters more than measuring TPR/TNR.

If any of those flip, graduate to stage 2: run `gather-product-context` (set Stage to `stage-2-rigor`) and switch to the full pipeline.

## Procedure

### Step 1: Quick context (5 minutes, in chat)

If `evals/context.md` doesn't exist, ask the user three questions only:
1. What does the agent do, in one sentence?
2. What's one specific failure you're worried about right now?
3. What's the entry point — file path or endpoint?

Write a minimal `evals/context.md` with just Vision, Agent Surface Area, and Stage = `stage-1-vibe`. Skip the other sections — they can be filled in later if the user graduates.

### Step 2: Generate ~10 inputs in chat

In the chat window, propose 10 natural-language inputs that target the worry from Q2. Use the dimension/tuple method from `generate-synthetic-data` but keep it lightweight: 3 dimensions × ~3 values each, then sample 10 tuples.

Show the inputs as a markdown table. Ask the user to thumbs-up the list or edit it inline.

### Step 3: Run inputs (use simplest possible runner)

Either:
- Call the BE directly with `httpx`/`requests` if it's an HTTP service.
- Import and call the agent function if it's a Python module.

Capture: input, output, and any tool calls. If tracing isn't set up, capture by wrapping the call site with simple logging — full WYSIWYG, no truncation.

Save the run as `evals/runs/vibe_<timestamp>/results.json` with the schema:

```json
[
  {"input_id": "v_001", "input": "...", "output": "...", "tool_calls": [...], "error": null}
]
```

### Step 4: Render results in chat

Render results as a chat-window-friendly markdown table. Constraints:

- **Truncate display only, never storage.** The JSON file is full WYSIWYG. The chat table truncates long fields with `...` and a `[full]` link to the relevant line in the JSON.
- **One row per input.** Columns: `#`, `Input (truncated)`, `Output (truncated)`, `Tool Calls`, `Vibe`.
- **Tool Calls column** is a count + collapsed list, e.g., `2: [search_db, send_email]`.
- **Vibe column** is empty — the user fills it as they read.

Example:

```
| # | Input | Output | Tools | Vibe |
|---|-------|--------|-------|------|
| 1 | "Find me a 2br under $400k pet-friendly" | "I found 3 options: ..." | 1: [search_db] | |
| 2 | "Schedule a tour for tomorrow" | "I'd suggest 2pm..." | 0 | |
```

After the table, list each input with its full output as a fenced block, so the user can read details without leaving chat:

```
### #1 — Full output
**Input:** Find me a 2br under $400k pet-friendly
**Output:**
> I found 3 options matching your criteria:
> 1. ...
**Tool calls:**
- search_db({"price_max": 400000, "beds": 2, "pets": true}) → [...]
```

### Step 5: Vibe annotation

Ask the user: "Mark each row as P (pass), F (fail), or ? (unsure). For Fails, one-line note on what went wrong."

Capture inline:

```
| # | Vibe | Note |
|---|------|------|
| 1 | F | Missed pet-friendly filter |
| 2 | P |  |
```

Save annotations into `evals/runs/vibe_<timestamp>/vibe_labels.json`.

### Step 6: Quick pattern recognition (no formal failure mode bucketing)

Read the Fail notes back to the user as a list. Ask: "Do any of these look like the same root cause? If yes, group them in one sentence."

Do NOT formalize this into a failure-mode catalog. That's stage-2 work. The output here is at most: "3 of 10 fails look like missing filter handling in the SQL tool."

### Step 7: Recommend the fix

Pick the single highest-frequency Fail pattern. State it. Suggest one specific code or prompt change. Stop there.

> "3 of 10 inputs failed because the SQL generator drops user-stated filters. Try adding 'preserve all user-stated constraints' to the SQL system prompt and re-run this loop."

### Step 8: Loop

After the user makes a change, re-run steps 3-7 against the *same* inputs. Render the diff:

```
| # | Old Vibe | New Vibe | Output Changed? |
|---|----------|----------|------------------|
| 1 | F | P | yes |
| 2 | P | P | no |
| 3 | F | F | yes (different failure) |
```

If overall Pass count goes up — the fix helped, continue. If it goes down — revert the change, try another.

## Chat Rendering Rules

- **Markdown tables only.** No HTML, no images.
- **Truncate input/output displays to ~80 chars** in the table; full content goes below.
- **Code blocks for tool inputs/outputs.** Use language hints (`json`, `sql`, `python`) for syntax highlighting.
- **No more than 10 traces per chat scroll.** If the user wants more, paginate by running smaller batches.
- **Bold the Fail rows** for visual scanning.

## What This Skill Skips (and why that's OK at stage 1)

- Failure-mode bucketing → user is the expert and can hold patterns in their head at this scale.
- Judge calibration → no judges yet.
- Dataset versioning → ad-hoc `vibe_<timestamp>` runs are enough.
- TPR/TNR → 10 vibe-labeled traces is too small for meaningful statistics.
- Multi-annotator agreement → single annotator (the user).

## Graduation Signal

Tell the user to graduate to stage 2 when any of these is true:
- Domain experts become available.
- The agent leaves prototype and takes real user traffic.
- The user is rerunning this loop more than 3 times a week — the manual labeling cost exceeds setting up rigor.

When graduating, hand off: keep `evals/context.md` (update Stage), promote `vibe_<timestamp>/results.json` into a real dataset via `manage-eval-datasets`, then run the stage-2 orchestrator.

## Anti-Patterns

- Running this skill at stage 2 or 3 just because it's faster. Skipping rigor at those stages costs more downstream than it saves.
- Truncating storage on disk to make rendering cleaner. Display truncation only — full WYSIWYG in JSON.
- Building a judge inside this skill. If the user wants a judge, they've left vibe-eval territory — graduate.
- Generating 100 inputs because "more is better." Vibe review past ~10 traces in one sitting is unreliable.
