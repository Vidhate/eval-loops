---
name: audit-eval-pipeline
description: >
  Stage-aware audit of an existing eval pipeline. Wraps the eval-audit skill
  with lifecycle-aware findings, cross-checks against the artifacts produced
  by other skills in this plugin (context.md, datasets, judges, runs), and
  prioritizes findings by impact at the user's current stage. Use to diagnose
  an inherited or maturing eval system. Do NOT use as a substitute for actually
  running error-analysis on fresh traces.
---

# Audit Eval Pipeline

Run a stage-aware audit and produce a prioritized findings report.

## Prerequisites

- Read `evals/context.md` if it exists. The Stage field determines which findings matter most.
- If `context.md` does not exist, run `gather-product-context` first.

## Procedure

### Step 1: Delegate to the base audit

Run the `evals-skills:eval-audit` skill (Hamel's). It walks the six diagnostic areas: error analysis, evaluator design, judge validation, human review process, labeled data, pipeline hygiene. Capture its findings.

### Step 2: Layer plugin-specific checks

Beyond the base audit, inspect the artifacts this plugin produces:

#### `evals/context.md`
- Missing or stale → flag. Other skills depend on it.
- Feature catalog has untagged features → flag. Profile skills (rag-eval, guardrails-eval) won't engage.
- Stage field absent → flag. Orchestrators can't route.

#### `evals/runs/`
- Latest run more than one BE change ago → flag stale. Re-run before drawing conclusions.
- Runs reference an `input_version` that no longer exists in `harness/inputs/` → broken provenance, flag.

#### `evals/datasets/`
- No frozen versioned datasets → flag. Ablation comparisons impossible.
- Dataset labels have mixed annotators in one block without per-label `annotator` field → flag.
- A dataset referenced by a judge's `metadata.json` `training_dataset_id` is also used as the calibration test set → data leakage, flag as critical.

#### `evals/judges/`
- Judges with `calibration_status: "untested"` referenced in any run → flag as critical.
- Judges with `judge_kind: "llm"` and `model_pinned: null` → flag as critical (silent drift risk).
- LLM judges where a code-based version was never attempted → flag and recommend revisiting.

#### Tracing
- `agent.llm.call` spans with truncated `llm.prompt` or `llm.response` attributes → flag as critical (WYSIWYG violation).
- Code paths in surface-area features that have no corresponding span → flag.

### Step 3: Stage-weighted prioritization

Re-rank findings by stage:

| Finding type | Stage 1 weight | Stage 2 weight | Stage 3 weight |
|---|---|---|---|
| Missing tracing | High | Critical | Critical |
| Unvalidated LLM judges | Low | Critical | Critical |
| Mixed annotators | Low | High | Critical |
| Data leakage in splits | Low | Critical | Critical |
| Truncated trace payloads | Critical | Critical | Critical |
| Stale runs vs latest BE | Low | High | Critical |
| No CI gate | Skip | Low | Critical |
| No drift monitoring | Skip | Skip | Critical |
| LLM judge with unpinned model | Low | Critical | Critical |

"Skip" means do not include in the report at all for that stage.

### Step 4: Report

Use the same format as Hamel's eval-audit but prefix the report with:

```
## Stage: <stage-1-vibe | stage-2-rigor | stage-3-production>
## Audit timestamp: <ISO-8601>
## Latest run audited: <run_id or "none">
```

Order findings by stage-weighted severity. For each finding, include:
- Severity tag: Critical / High / Low
- The specific artifact that triggered the finding (file path or null state)
- The remediation skill to invoke

### Step 5: Recommend next action

End the report with a single sentence: "The highest-impact next step is to run `<skill-name>` because `<reason>`." Make this concrete — don't list five options.

## Anti-Patterns

- Running the base audit and stopping there. The plugin-specific checks are the differentiator.
- Reporting Stage-3 concerns to a Stage-1 user. They're irrelevant noise.
- Treating the audit as a compliance checklist. Findings must point to a concrete remediation skill.
- Auditing without inspecting the latest run. Findings about stale state require knowing what "current" is.
- Recommending `error-analysis-and-triage` as the answer for every audit. Sometimes the answer is `instrument-tracing` or `calibrate-judge-loop`.
