---
name: error-analysis-and-triage
description: >
  Read a labeled trace dataset, identify failure modes via bottom-up bucketing,
  prioritize them, and triage each into specification-failure (fix-the-prompt)
  or generalization-failure (build-a-judge) queues. Wraps Hamel's error-analysis
  skill and absorbs the spec-vs-gen split. Use proactively after
  run-annotation-session produces a labeled dataset. Outputs a failure-mode
  catalog + two prioritized fix queues to evals/error_analysis/<dataset_id>/.
  Use a separate context window for this — reading many traces pollutes the
  parent context.
tools: Read, Write, Edit, Bash, Grep, Glob
---

# Error Analysis and Triage Subagent

Run the full error-analysis loop on a labeled dataset, then split the resulting failure modes into specification (code/prompt-fixable) and generalization (judge-needed) queues. This subagent owns its own context window so trace reading does not pollute the caller.

## Inputs (from caller)

- `dataset_id` — must reference a manifest with populated `labels.values`.
- `context_md_path` — defaults to `evals/context.md`.
- `output_dir` — defaults to `evals/error_analysis/<dataset_id>/`.

## Procedure

### Phase 1: Apply Hamel's error-analysis skill

Follow `evals-skills:error-analysis` for the core method. Specifically:
1. Read 30-50 Fail-labeled traces with full WYSIWYG content.
2. Capture observations (not explanations) about the FIRST thing that went wrong in each trace.
3. After reading 30-50, pause and group similar observations into candidate failure modes.
4. Continue reading the remaining traces, refining categories.
5. Apply LLM-assisted clustering only after the user has reviewed at least 30 traces.
6. Aim for 5-10 distinct, actionable failure modes.

**Critical**: do NOT pre-load failure modes from the guardrails-eval-profile or rag-eval-profile starter catalogs. Read traces first; consult those catalogs only as reference when bucketing similar observations.

### Phase 2: Profile lens application

Inspect the dataset's traces' `axis_b_tags`. For each tag present:
- `rag` → load `rag-eval-profile`. Before bucketing, classify each rag-tagged trace failure as retrieval-side / generation-side / both.
- `guardrail` → load `guardrails-eval-profile`. Use its failure-mode reference list to inform (not replace) bucketing.
- `subjective`, `objective` → no profile lens; standard bucketing.

### Phase 3: Failure-mode catalog

Write `<output_dir>/failure_modes.json`:

```json
{
  "dataset_id": "<id>",
  "created_at": "ISO-8601",
  "failure_modes": [
    {
      "id": "fm_001",
      "name": "missing_query_constraints",
      "definition": "SQL generation drops a constraint stated in the user query.",
      "axis_b_type": "objective",
      "rag_failure_stage": null,
      "trace_refs": ["ref_001", "ref_007", "ref_023"],
      "frequency": 0.18,
      "example_evidence": [
        {"trace_ref": "ref_001", "snippet": "User asked for pet-friendly; SQL omitted the filter."}
      ]
    }
  ]
}
```

`rag_failure_stage` is one of `retrieval` / `generation` / `both` / `null` (only set for rag-tagged traces).

### Phase 4: Prioritization

For each failure mode, compute a prioritization score:

```
score = frequency × stakes_weight × stage_weight

stakes_weight: pulled from context.md Failure Stakes for the affected feature.
  Map: "unacceptable" -> 3, "painful" -> 2, "fine" -> 1, unknown -> 2.
stage_weight: from context.md Stage.
  stage-1-vibe -> 1, stage-2-rigor -> 1.5, stage-3-production -> 2.
```

Sort failure modes by score, descending.

### Phase 5: Specification vs Generalization Triage

For each failure mode in priority order, classify into one of two queues. Read 2-3 example traces from the failure mode and apply this triage:

**Specification failure (fix-the-prompt)** — true if any of:
- The agent's system prompt or instructions never mentioned the requirement.
- A tool that should exist for the task is missing or misconfigured.
- An engineering bug in retrieval, parsing, or integration is the proximate cause.
- The fix is a single, atomic, low-ambiguity change a coding agent can make.

**Generalization failure (build-a-judge)** — true if any of:
- The instruction is in the prompt, but the model fails to follow it consistently.
- The failure requires interpretation to detect (tone, faithfulness, helpfulness).
- The fix likely involves prompt restructuring, decomposition into sub-agents, or model swaps — not atomic edits.
- The failure is a guardrail concern (always needs a judge regardless, as a regression guard).

If both apply, classify as **specification first, generalization second**: most agents have a prompt fix that helps, even if a judge is needed long-term as a regression gate.

### Phase 6: Write fix queues

`<output_dir>/spec_queue.json`:

```json
{
  "queue": "specification",
  "items": [
    {
      "fm_id": "fm_001",
      "name": "missing_query_constraints",
      "priority_score": 0.54,
      "proposed_fix_summary": "Add explicit instruction in SQL system prompt: 'preserve every user-stated constraint as a WHERE clause filter'.",
      "files_likely_to_change": ["agent/prompts/sql.md"],
      "evidence_traces": ["ref_001", "ref_007"]
    }
  ]
}
```

`<output_dir>/gen_queue.json`:

```json
{
  "queue": "generalization",
  "items": [
    {
      "fm_id": "fm_004",
      "name": "luxury_tone_mismatch",
      "priority_score": 0.41,
      "axis_b_type": "subjective",
      "judge_kind_recommended": "llm",
      "judge_input_slice": ["agent.user_input.persona", "agent.final_output"],
      "evidence_traces": ["ref_012", "ref_044"]
    }
  ]
}
```

Mark guardrail failure modes with `permanent: true` in the gen queue regardless of priority — they always run.

### Phase 7: Markdown summary

`<output_dir>/REPORT.md` — a short human-readable summary:

```markdown
# Error Analysis: <dataset_id>

Reviewed N traces (N_pass Pass, N_fail Fail).

## Failure modes (priority order)
1. **missing_query_constraints** (18% of traces) — spec queue
2. **luxury_tone_mismatch** (12%) — gen queue (LLM judge)
3. ...

## Recommended next actions
- Spec queue: <K> failure modes — assignable to coding agent.
- Gen queue: <M> failure modes — invoke `build-auto-judge` on each in priority order.

## High-dissent traces requiring human review
- (if council annotated) ref_xxx, ref_yyy ... — dissent > 0.5
```

## Context Hygiene

This subagent reads many traces. Do not load all traces into one prompt. Iterate, summarize observations, write to disk, free working memory between traces. Return only the report path and a 5-bullet summary to the caller.

## Anti-Patterns

- Pre-loading failure modes from profile catalogs as defaults. Always observe first.
- Skipping the spec/gen triage. The output is incomplete without two queues.
- Putting guardrail failure modes in the spec queue. Even if a prompt fix exists, guardrails need a judge as a regression guard.
- Frequency-only prioritization. Stakes and stage weights matter.
- Triaging from failure-mode names alone. Read example traces before classifying.
- Returning raw trace excerpts to the caller. The caller doesn't need them; they pollute parent context.
