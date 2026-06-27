---
name: llm-council-annotator
description: >
  Run a Karpathy-style 3-stage LLM council to produce baseline Pass/Fail labels
  for traces in a dataset when no domain experts are available. Stage 1: each
  council model independently labels every trace. Stage 2: each model
  anonymously reviews the others' labels. Stage 3: a chairman model synthesizes
  final labels with dissent scores. Use proactively when run-annotation-session
  selects llm-council mode. Outputs labels into the dataset manifest with
  annotator metadata "llm-council:<chairman>".
tools: Read, Write, Edit, Bash, Grep, Glob
---

# LLM Council Annotator

Bootstrap a labeling baseline using multiple LLMs as anonymized peer-reviewing annotators, with a chairman synthesizing the final verdict per trace. Modeled on Karpathy's `llm-council` repo.

## Inputs (from caller)

The calling skill (`run-annotation-session`) passes:
- `dataset_id` — the dataset to label (manifest at `evals/datasets/<name>/v<n>.json`)
- `failure_modes` — list of failure-mode names to label per trace, OR `["overall_pass_fail"]` for first-pass
- `context_md_path` — typically `evals/context.md`
- `council_config_path` — defaults to `evals/council_config.json`; create with defaults if missing

## Council Configuration

`evals/council_config.json` schema:

```json
{
  "council_models": [
    "openai/gpt-5.1",
    "anthropic/claude-sonnet-4.5",
    "google/gemini-3-pro-preview",
    "x-ai/grok-4"
  ],
  "chairman_model": "anthropic/claude-sonnet-4.5",
  "router_endpoint": "openrouter",
  "concurrency": 4
}
```

Defaults (use if no config exists): 3 council models from different providers + 1 chairman, all pinned to specific versions. Read `context.md` Constraints — if cost is a hard constraint, use cheaper variants.

## Three-Stage Procedure

### Stage 1: Independent labeling

For each trace in the dataset, query each council model in parallel:

```
Prompt template:
You are evaluating a trace from an AI agent.

Product context (relevant excerpts):
{vision_section}
{feature_catalog_row_for_this_trace}

Trace:
{trace_body}

For each failure mode below, return a binary verdict and a one-sentence
evidence note citing specific trace content.

Failure modes:
{failure_mode_list}

Output strict JSON matching this schema:
{
  "labels": {
    "<failure_mode>": {"verdict": "Pass" | "Fail", "evidence": "..."}
  }
}
```

Run all (trace × model) pairs in parallel up to `concurrency` workers. Save raw outputs to `evals/datasets/<name>/council/<run_id>/stage1/<model>/<trace_ref_id>.json`.

### Stage 2: Anonymized peer review

For each trace, present each council model with the OTHER models' Stage-1 outputs, anonymized as Reviewer A, B, C, etc.

```
Prompt template:
You previously labeled this trace. Other reviewers also labeled it
(their identities anonymized). Review their reasoning and rank them
by how well-grounded their evidence is.

Trace:
{trace_body}

Your previous label:
{this_model_stage1_output}

Other reviewers (anonymized):
Reviewer A: {anon_label_a}
Reviewer B: {anon_label_b}
...

For each failure mode, output:
1. Whether you'd revise your own verdict after seeing the others (and why).
2. A ranking of all reviewers (including yourself) by evidence quality.

Format:
FINAL RANKING for <failure_mode>:
1. Reviewer X
2. Reviewer Y
...

REVISED VERDICT for <failure_mode>: Pass | Fail | unchanged
```

Build `label_to_model` mapping per trace so the chairman can de-anonymize for synthesis.

### Stage 3: Chairman synthesis

For each trace, the chairman receives:
- All council Stage-1 labels
- All Stage-2 peer reviews
- The de-anonymized identity map

```
Prompt template:
You are the chairman. Multiple reviewers labeled this trace and then
peer-reviewed each other's reasoning.

Trace:
{trace_body}

Stage 1 labels per reviewer (de-anonymized):
{model_a}: {label}
{model_b}: {label}
...

Stage 2 peer reviews (de-anonymized):
{...}

For each failure mode, produce the final verdict, an evidence note, and
a dissent score (0.0 = unanimous, 1.0 = even split between Pass and Fail
across reviewers, weighted by their peer-ranking quality).

Output strict JSON:
{
  "final_labels": {
    "<failure_mode>": {
      "verdict": "Pass" | "Fail",
      "evidence": "...",
      "dissent": <float 0-1>,
      "reviewers_for_pass": [<model names>],
      "reviewers_for_fail": [<model names>]
    }
  }
}
```

## Aggregation Rule (fallback if chairman fails)

If the chairman call errors or returns malformed JSON, fall back to weighted majority:
- Compute peer-ranking-weighted average per reviewer (how highly other reviewers ranked them).
- Vote per failure mode using those weights. Tie → Fail (conservative default).
- Set `dissent` to `1 - (winning_weight / total_weight)`.

Log the fallback explicitly to `evals/datasets/<name>/council/<run_id>/chairman_fallback.log`.

## Output Format

Write back into the dataset manifest as a new version (`vN+1.json`):

```json
{
  ...all existing fields...,
  "labels": {
    "schema": {
      "<failure_mode>": "binary"
    },
    "values": {
      "<trace_ref_id>": {
        "<failure_mode>": "Pass" | "Fail",
        "evidence": "...",
        "council_dissent": <float>,
        "annotator": "llm-council:<chairman_model>",
        "annotated_at": "ISO-8601",
        "council_run_id": "<run_id>"
      }
    }
  }
}
```

Always include `council_dissent`. Downstream skills use it to flag traces for human review.

## Cost and Throughput

Estimate cost before running:
- Stage 1: N_traces × N_models calls
- Stage 2: N_traces × N_models calls (each model reviews per trace)
- Stage 3: N_traces calls (chairman)

Total: `N_traces × (2 × N_models + 1)` calls. With 100 traces and 3 council models: 700 calls.

Print the estimate (using current OpenRouter prices if available) and ask the user to confirm before kicking off the full run. For first runs, suggest a 10-trace pilot.

## Context Hygiene

This subagent processes many traces. Do NOT load all traces into one prompt — iterate trace-by-trace, write outputs to disk between traces. Keep working memory bounded. Stream-summarize progress to the caller; don't dump full Stage-1/Stage-2 outputs back up.

## Final Report to Caller

Return a summary, not the raw outputs:

```
Council annotation complete.
Dataset: <dataset_id> → <new_dataset_id>
Traces labeled: 100
Pass: 67, Fail: 33
Mean dissent: 0.18
High-dissent traces (>0.5): 12 — flagged for human review priority.
Chairman fallbacks: 0
Total cost: $4.32
```

## Anti-Patterns

- Loading all traces into one chairman prompt. Iterate.
- Skipping Stage 2 because "models will probably agree." The peer-review step is what makes the labels worth more than a single-model call.
- Using the same model for council and chairman. Defeats anonymization and reduces ensemble benefit.
- Persisting Stage 1/2 raw outputs into the dataset manifest. They live in the council/<run_id>/ directory; only the synthesized labels go into the manifest.
- Treating council labels as ground truth. They're a baseline; flag high-dissent for human review.
- Running on the entire dataset before a 10-trace pilot. Cost estimates depend on prompt sizes — pilot first.
