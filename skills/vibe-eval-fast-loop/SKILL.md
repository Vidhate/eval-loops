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

Cheap, fast pass/fail signal for a solo developer. The user is the alias domain expert, a throwaway HTML dashboard is the review UI, the loop is iteration → eyeball → adjust.

## When This Skill Is Right

All of:
- No domain experts available; the user is reviewing alone.
- No observability vendor wired up.
- The agent is early enough that catching obvious breakage matters more than measuring TPR/TNR.

If any of those flip, graduate to stage 2: run `gather-product-context` (set Stage to `stage-2-rigor`) and switch to the full pipeline.

## Procedure

### Step 1: Quick context (5 minutes, in chat)

First, recover prior context from the journal. Install the shipped helper if missing — copy it, do not rewrite it: `mkdir -p evals && test -f evals/journal.py || cp "${CLAUDE_SKILL_DIR}/../manage-eval-journal/journal.py" evals/journal.py`. Then `python evals/journal.py tail -n 20 --stage stage-1-vibe`. If earlier runs already discovered failures, surface them instead of asking Q2 cold — "Last time we found X and Y breaking; want to re-test those plus broader coverage?" The journal is what lets discovered failures, not the user's fresh guess, seed the loop.

If `evals/context.md` doesn't exist, ask the user three questions only:
1. What does the agent do, in one sentence?
2. What are the most pressing ways you suspect your agent could fail? Note: your answer will focus the eval loop on the failures you name. If you don't have strong opinions, say so — we'll instead discover failures by exercising the agent across realistic usage.
3. What's the entry point — file path or endpoint?

Treat any failure the user names in Q2 as a *hypothesis to investigate*, never as the whole test surface. The user's answer sets the balance of the input set in Step 2, not its entirety.

Write a minimal `evals/context.md` with just Vision, Agent Surface Area, and Stage = `stage-1-vibe`. Skip the other sections — they can be filled in later if the user graduates.

### Step 2: Generate inputs in chat

Default to ~10 inputs. Use the dimension/tuple method from `generate-synthetic-data` but keep it lightweight: 3 dimensions × ~3 values each, then sample tuples.

Split the input budget by what the user said in Q2 — never let one stated failure consume the whole set, or the loop clamps to it and discovers nothing else:

- **User named failures:** ~60% targeted at the stated failure(s), ~30% general coverage of realistic usage, ~10% adversarial. The non-targeted slots are what let *other* failures surface.
- **User had no strong opinion (discovery):** ~80% coverage, ~20% adversarial. Generate coverage by spanning the realistic usage space (persona × task × query-clarity), then let failures emerge from reading traces in Steps 5–6. Do NOT pre-guess failures and generate inputs for them — that just moves the bias from the user to you.

For the discovery path, if Q1 didn't give enough to span usage, ask one or two follow-ups aimed *past* Q1 — typical inputs, who uses it, the 2–3 most common tasks — not "what does it do" again.

Adversarial inputs should be subtle and context-appropriate to what the agent actually does — an indirect constraint the agent might quietly drop, an out-of-scope ask phrased plausibly, a real-world edge case — not a generic "ignore your instructions" jailbreak.

**Sizing:** ~10 is the default and the preference. If the user named many distinct failures, or the agent's usage surface is genuinely large, a fair sample needs more — call this out explicitly ("Covering these fairly needs ~25 inputs; I'll generate that and we'll review in batches of ~10") and scale up. Decouple generation from review: generating more than ~10 is fine, but eyeballing more than ~10 in one sitting is not — review in batches (see Rendering Rules).

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

### Step 4: Generate the HTML review dashboard

Trace review and annotation happen in a standalone HTML file, not the chat. This keeps the developer's terminal from drowning in large traces while still showing every input and output in full.

1. Copy the template `review_template.html` shipped with this skill to `evals/runs/vibe_<timestamp>/review.html` (a throwaway artifact — it lives under `evals/` and is regenerable from `results.json`).
2. Replace the placeholder `__RESULTS_JSON__` with the **verbatim contents of `results.json`** — copy the file's bytes; do not retype, summarize, or abbreviate them. Before inserting, escape the substring `</` to `<\/` (a JSON-safe escape that renders identically) so code or HTML inside a trace can't break the page.
3. Tell the user the path and to open it in a browser (e.g., `open evals/runs/vibe_<timestamp>/review.html` on macOS).

The dashboard renders one collapsible card per trace with the **exact** input, output, and tool calls — read from the embedded JSON via `textContent`, never reconstructed — plus P/F/? controls and a note field. Do not paste full trace contents into the chat; the HTML is the review surface.

### Step 5: Collect annotations via paste-back

The user labels each trace in the dashboard (P/F/?, note for fails), clicks **Copy Results as JSON**, and pastes the result into the chat.

The pasted blob is labels only — `{"vibe_labels": [{"input_id", "vibe", "note"}, ...]}`, keyed by `input_id`. Write it to `evals/runs/vibe_<timestamp>/vibe_labels.json`, matching each label to its trace by `input_id`.

If the user pasted nothing or only partial labels, ask them to finish in the dashboard and re-copy — do not infer labels yourself.

### Step 6: Quick pattern recognition (no formal failure mode bucketing)

Read the Fail notes back to the user as a list. Ask: "Do any of these look like the same root cause? If yes, group them in one sentence."

Do NOT formalize this into a failure-mode catalog. That's stage-2 work. The output here is at most: "3 of 10 fails look like missing filter handling in the SQL tool."

Append the pattern to the journal as a `learning` so the next run starts from it instead of re-asking the user: `python evals/journal.py append --type learning --actor vibe-eval-fast-loop --stage stage-1-vibe --summary "3/10 fails: SQL drops user filters" --refs runs/vibe_<ts>/`.

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

Record the change and its effect as an `action`: `python evals/journal.py append --type action --actor vibe-eval-fast-loop --stage stage-1-vibe --summary "added 'preserve constraints' to SQL prompt; pass 7/10 -> 9/10" --refs runs/vibe_<ts>/`.

## Rendering Rules

- **Trace review and annotation live in the `review.html` dashboard, not the chat.** Never render full inputs/outputs as a chat markdown table.
- **Verbatim, copied from source.** Whenever a trace's input or output is shown anywhere, reproduce it exactly from `results.json` — copied from the file, not retyped from memory, and never shortened with `...`. Large values are what the collapsible HTML cards are for.
- **The chat is for orientation and compact summaries only** — counts, the fix recommendation, and the re-run diff (P/F status, not trace bodies) may use small markdown tables.
- **Review ~10 traces per sitting** for reliable human attention; the dashboard scrolls fine beyond that, but split larger batches across sittings.

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
- Truncating storage on disk to make rendering cleaner. `results.json` is full WYSIWYG; the dashboard collapses, it does not shorten.
- Pasting full trace contents into the chat instead of opening the HTML dashboard. The chat drowns and the user can't read exact outputs.
- Populating the dashboard by retyping or summarizing outputs instead of copying `results.json` verbatim into the data placeholder.
- Building a judge inside this skill. If the user wants a judge, they've left vibe-eval territory — graduate.
- Generating a large input set for vanity ("more is better"). Scale past ~10 only when genuine coverage demands it, and review in batches of ~10 — vibe review of more than ~10 traces in one sitting is unreliable.
