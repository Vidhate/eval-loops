---
name: build-auto-judge
description: >
  Build an auto-judge for one specific failure mode. Algorithmic-first: exhaust
  code-based checks before reaching for an LLM judge. When an LLM judge is
  required, delegates to the write-judge-prompt skill for prompt design. Use
  after error-analysis-and-triage has identified a generalization failure that
  needs an automated detector. Do NOT use for specification failures — those
  are fixed by editing the agent prompt, not by adding a judge.
---

# Build Auto-Judge

Produce a callable judge that takes a trace and returns a binary Pass/Fail verdict for one specific failure mode. Algorithmic if at all possible; LLM-as-judge only when forced.

## Prerequisites

- The failure mode is well-defined and tagged as a **generalization failure** by `error-analysis-and-triage`.
- A labeled dataset exists with at least 20 Pass and 20 Fail examples for this failure mode.
- `evals/context.md` is current.

## The Algorithmic-First Decision

Walk through this triage in order. Do NOT skip to LLM judges.

### Tier 1: Pure code (preferred)

Use code if the failure mode reduces to:
- **Schema/format validation** — JSON schema, regex, parser. Example: "agent must return valid SQL" → run through the SQL parser.
- **Keyword presence/absence** — Example: "must include disclaimer" → string search.
- **Numeric/structural constraint** — Example: "response under 500 tokens" → token count.
- **Tool-call signature** — Example: "must call `verify_payment` before `place_order`" → trace span ordering check.
- **Comparison against a known reference** — Example: deterministic SQL → execute against fixture DB, compare result rows.

Many failures that *feel* subjective reduce to keyword checks once the domain is well-understood. From `write-judge-prompt`'s prerequisites: detecting "general" interview questions vs. specific ones can often be a keyword check for "usually," "typically," "normally" — no LLM needed.

Spend 15 minutes brainstorming a code-based heuristic with the user before declaring it impossible.

### Tier 2: Hybrid (code + small LLM call)

Use when one component requires interpretation but most of the check is structural. Example: "agent must ground answer in retrieved context" → extract claims with code, judge each claim's groundedness with a focused LLM call. The LLM call is narrow and judged separately for calibration.

### Tier 3: Pure LLM judge

Use only when the failure mode genuinely requires interpretation across the full output. Examples: tone-mismatch, helpfulness, faithfulness across loose paraphrasing.

When you reach this tier, delegate to `write-judge-prompt` for prompt design. After the prompt is written, validate with `calibrate-judge-loop` — that loop won't certify the judge as trusted until TPR/TNR thresholds are met.

## Output Layout

```
evals/judges/
  <failure_mode_slug>/
    judge.py             # callable: judge(trace) -> {"verdict": "Pass"|"Fail", "evidence": str, "judge_kind": "code"|"hybrid"|"llm"}
    metadata.json        # see schema below
    prompt.md            # if LLM-based; written by write-judge-prompt
    test_fixtures.json   # tiny set of Pass/Fail examples for unit testing the judge code itself
```

### `metadata.json` schema

```json
{
  "failure_mode": "missing_query_constraints",
  "failure_mode_description": "SQL generation drops a constraint stated in the user query",
  "judge_kind": "code" | "hybrid" | "llm",
  "axis_b_type": "objective" | "subjective" | "rag" | "guardrail",
  "trace_input_fields": ["agent.user_input", "agent.tool.call[name=run_sql].input"],
  "model_pinned": "gpt-4o-2024-05-13" | null,
  "training_dataset_id": "<id>" | null,
  "calibration_status": "untested" | "in_calibration" | "certified",
  "tpr_test": null | <float>,
  "tnr_test": null | <float>,
  "created_at": "ISO-8601",
  "version": 1
}
```

`calibration_status` starts as `untested`. Only `calibrate-judge-loop` may flip it to `certified`.

## Judge Interface Contract

Every judge — code, hybrid, or LLM — exposes a single function with this signature:

```python
def judge(trace: dict) -> dict:
    """
    trace: dict matching the OTEL span tree shape captured by instrument-tracing.
           Required keys: 'agent.user_input', 'agent.final_output', 'spans' (list).
    returns: {
      "verdict": "Pass" | "Fail",
      "evidence": str,        # specific text/spans cited from the trace
      "judge_kind": "code" | "hybrid" | "llm"
    }
    """
```

`evidence` is mandatory. A judge that says Fail without citing evidence is uncalibratable.

## Trace Slicing

Pass only what the judge needs. From the failure mode definition:
- For SQL constraint checks → user input + the SQL tool-call input
- For tone matches → final output + persona attribute
- For groundedness → final output + retrieval span results

Write the slice mapping into `metadata.json` under `trace_input_fields` so calibration runs read the same slice.

## Pin LLM Models

If `judge_kind` is `llm` or `hybrid`, set `model_pinned` to a fully versioned model identifier. Never `gpt-4o`, always `gpt-4o-2024-05-13`. The judge's calibration is invalid the moment the underlying model rotates.

## What This Skill Does Not Do

- It does not validate the judge against human labels. That's `calibrate-judge-loop`.
- It does not write the LLM judge prompt. That's `write-judge-prompt`.
- It does not pick which failure modes need judges. That's `error-analysis-and-triage`.

This skill produces a judge artifact in `untested` state. The user must run `calibrate-judge-loop` before trusting it.

## Anti-Patterns

- Reaching for an LLM judge without spending 15 minutes on the code-based version.
- Building a judge for a specification failure ("agent never includes disclaimer because the prompt didn't say to") — fix the prompt instead.
- Building a holistic "is this output good?" judge. One failure mode per judge.
- LLM judge with unpinned model identifier.
- Marking a judge `certified` before calibration runs.
- Passing the entire trace tree when the judge only needs two fields. Slice carefully.
