---
name: run-annotation-session
description: >
  Drive a trace annotation session that produces labeled data for error analysis
  and judge calibration. Three modes: human-local (uses build-review-interface),
  third-party-GUI (handoff to a vendor's annotation UI), and llm-council (invokes
  the llm-council-annotator subagent for solo devs without domain experts). Use
  after a dataset exists. Do NOT use to design failure categories — that's
  error-analysis-and-triage.
---

# Run Annotation Session

Coordinate the act of attaching Pass/Fail labels and notes to every trace in a dataset. The output is the dataset's `labels` block populated.

## Prerequisites

- `evals/context.md` exists.
- A dataset exists (see `manage-eval-datasets`).
- The user has decided on a failure-mode schema (initial round can be `overall_pass_fail` only — that's fine for the first pass).

## Mode Selection

Ask the user:

> "Who is annotating these traces?
> 1. **You alone, in a local UI.** (human-local)
> 2. **Domain experts using your observability vendor's GUI** — Braintrust, LangSmith, Phoenix annotation queues, etc. (third-party-GUI)
> 3. **No domain experts available right now** — use an LLM council to bootstrap a labeling baseline, with the understanding that this is a stand-in until experts are available. (llm-council)"

Default by stage:
- Stage 1 → llm-council (with explicit "this is a baseline, not ground truth" framing)
- Stage 2 → third-party-GUI if a vendor is wired, else human-local
- Stage 3 → third-party-GUI

## Mode A: human-local

Delegate to the `build-review-interface` skill to scaffold the UI. Then:

1. Load traces from the dataset into the UI.
2. User labels each trace with Pass/Fail + free-text note + (optional) failure-mode tags if a schema exists.
3. On every save, write back into the dataset manifest's `labels.values` block.
4. After the session ends, bump the dataset version to capture the new labels.

The annotation UI is build-review-interface's responsibility. This skill only handles dataset wiring.

## Mode B: third-party-GUI

This mode is mostly a handoff. The vendor owns the UI; this skill prepares inputs and ingests outputs.

1. Use the appropriate tool-specific skill (e.g., `superset-evals-braintrust:run-annotation-session-braintrust`) if installed. It handles the vendor-specific dataset push and queue creation.
2. If no vendor skill is installed, walk the user through:
   - Exporting the dataset's `trace_refs` to a CSV with columns `trace_id, input_id, link_to_trace_in_vendor_ui`.
   - Telling them to label in the vendor UI, then export labels back.
   - Ingesting the export and writing into the dataset manifest.
3. Bump the dataset version on ingest.

### Vendor-integration validation checkpoint

Before declaring this mode set up, verify with the user:
1. The dataset and its traces are visible in the vendor UI.
2. At least one annotation can be saved and retrieved end-to-end.
3. The label-export pipeline round-trips correctly.

## Mode C: llm-council

Invoke the `llm-council-annotator` subagent. Pass it:
- The `dataset_id`
- The path to `evals/context.md`
- The failure-mode schema (or `["overall_pass_fail"]` for the first pass)

The subagent runs Karpathy's 3-stage council pattern (first opinions → anonymized peer review → chairman synthesis) and returns labels + dissent notes per trace.

Critical framing for the user:
> "These labels are an LLM-generated baseline. They surface obvious failures and serve as a stand-in until domain experts can annotate. Treat dissent notes as flags for traces that need human review when experts become available."

Write the labels into the dataset manifest with annotator metadata `"annotator": "llm-council:<chairman-model>"` and a per-trace `"council_dissent": <0..1>` score.

When experts later annotate the same dataset, treat their labels as overrides and bump the version.

## What gets labeled

For each trace in the dataset:
- `overall_pass_fail`: Pass / Fail (always required)
- `notes`: free-text — what went wrong, or what was right (always required for Fail; optional for Pass)
- Per-failure-mode binary tags: only if the schema includes them

If the user is in their first annotation round (no failure modes defined yet), only `overall_pass_fail` and `notes` are needed. The error-analysis-and-triage skill will derive failure modes from the notes.

## Annotator Hygiene

- One annotation session = one annotator (or one council). Mixing annotators in one session muddles inter-rater calibration.
- Capture the annotator identifier per label.
- Record session start/end timestamps for later analysis of fatigue effects.

## Output

When the session ends:
1. Write all labels into `evals/datasets/<name>/v<n+1>.json` (bumped version).
2. Update `parent_dataset_id` to the previous version.
3. Print a summary: total traces labeled, Pass count, Fail count, traces deferred.
4. Hand off to `error-analysis-and-triage` if the user wants failure-mode categorization next.

## Anti-Patterns

- Treating LLM-council labels as ground truth. They're a baseline.
- Labeling without a `dataset_id`. Labels must be attached to a versioned dataset.
- Mixing annotators in a single labels block without per-label `annotator` field.
- Asking the user to label dimensions they haven't defined yet. First-pass annotation is overall_pass_fail + notes only.
- Mutating an existing dataset version's labels in place. Bump.
