---
name: calibrate-judge-loop
description: >
  Self-improving supervisor loop that calibrates an auto-judge against human
  labels until TPR/TNR thresholds are met or stalled. Wraps Hamel's
  validate-evaluator skill, manages train/dev/test splits, runs iterative
  refinement subagents, and certifies the judge or surfaces a stall reason.
  Use proactively after build-auto-judge produces an untested judge artifact.
  Outputs updated judge metadata with calibration_status set to certified or
  stalled, plus a calibration log.
tools: Read, Write, Edit, Bash, Grep, Glob
---

# Calibrate Judge Loop Subagent

Supervise the calibrate → measure → refine → re-measure cycle until the judge passes thresholds, then certify it. Owns its own context so per-iteration trace reading does not pollute the caller.

## Inputs (from caller)

- `judge_path` — `evals/judges/<failure_mode_slug>/`
- `labeled_dataset_id` — dataset with human labels for this failure mode
- `target_tpr` (default 0.90), `target_tnr` (default 0.90)
- `min_tpr` (default 0.80), `min_tnr` (default 0.80) — minimum acceptable
- `max_iterations` (default 5)

## Prerequisites

- The judge artifact exists (created by `build-auto-judge`) with `calibration_status: "untested"`.
- `labeled_dataset_id` has at least 50 Pass and 50 Fail labels for this failure mode.

## Procedure

### Step 1: Create train/dev/test splits

Per Hamel's `validate-evaluator`:
- Train: 10-20% (~10-20 examples) — only if the judge is LLM-based and uses few-shot examples
- Dev: 40-45% — iterative refinement
- Test: 40-45% — final, ONE measurement only

Implement as three derived datasets via `manage-eval-datasets`:
- `<dataset>_train_v1`
- `<dataset>_dev_v1`
- `<dataset>_test_v1`

All three have the parent dataset as their `parent_dataset_id`. Use stratified split by label balance.

If splits already exist (re-running calibration on same judge), reuse them.

### Step 2: Iteration loop

For iteration `i` from 1 to `max_iterations`:

1. Run the judge on every dev-set trace.
2. Compare predictions to human labels using `confusion_matrix` (per `validate-evaluator`).
3. Compute TPR and TNR.
4. Append to `<judge_path>/calibration_log.json`:

```json
{
  "iteration": 1,
  "timestamp": "ISO-8601",
  "split": "dev",
  "tpr": 0.78,
  "tnr": 0.92,
  "false_passes": 4,
  "false_fails": 2,
  "judge_kind": "llm",
  "model_pinned": "gpt-4o-2024-05-13",
  "prompt_hash": "<sha256 of prompt.md if LLM>",
  "code_hash": "<sha256 of judge.py>",
  "notes": "..."
}
```

5. If `tpr >= target_tpr AND tnr >= target_tnr` → break loop, proceed to Step 3.

6. Else, decide whether to refine and how:
   - **Both metrics low (< 0.7)** → recommend more capable model (LLM judge) or add code structure (code judge). Surface to user; do not auto-swap models.
   - **TPR low, TNR ok** → judge is too strict. Inspect false fails. Refinement directives: clarify Pass definitions in prompt; add Pass examples from training set; loosen overly strict code rules.
   - **TPR ok, TNR low** → judge is too lenient. Inspect false passes. Refinement directives: strengthen Fail definitions; add Fail few-shot examples; tighten code rules.
   - **Both metrics plateau across 2+ iterations** → recommend decomposing the failure mode into atomic sub-checks. Halt.

7. Spawn a refinement subagent (use Agent tool with subagent_type=general-purpose):
   - Pass it: judge artifact path, the misclassified examples (just the relevant slices, not full traces), the directive from above.
   - It returns: a proposed prompt or code edit.
   - Apply the edit, write the new prompt_hash/code_hash to the next iteration log.

8. Repeat.

If `max_iterations` reached without hitting target:
- If `tpr >= min_tpr AND tnr >= min_tnr` → continue to Step 3 with `calibration_status: "certified_minimum"`.
- Else → set `calibration_status: "stalled"`, write stall reason to log, return failure to caller.

### Step 3: Final test-set measurement

Run the judge ONCE on the test set. Record TPR_test and TNR_test. Append to log with `"split": "test"`.

If the test-set numbers are dramatically worse than dev (>5 percentage point drop in either), warn the user — likely overfitting to dev. Consider this a soft stall.

### Step 4: Bias correction estimation

If the user has unlabeled production traces, run the Rogan-Gladen formula per `validate-evaluator` Step 7. Add `bias_correction` block to judge metadata:

```json
"bias_correction": {
  "tpr_test": 0.92,
  "tnr_test": 0.88,
  "p_obs_sample": 0.80,
  "theta_hat": 0.85,
  "ci_95_lower": 0.78,
  "ci_95_upper": 0.91,
  "n_unlabeled": 500
}
```

Use bootstrap CI per `validate-evaluator`'s code.

### Step 5: Certify

Update `<judge_path>/metadata.json`:

```json
{
  ...,
  "calibration_status": "certified" | "certified_minimum" | "stalled",
  "tpr_test": 0.92,
  "tnr_test": 0.88,
  "calibrated_at": "ISO-8601",
  "calibration_dataset_id": "<labeled_dataset_id>",
  "split_ids": {
    "train": "<id>",
    "dev": "<id>",
    "test": "<id>"
  },
  "bias_correction": {...}
}
```

### Step 6: Journal

This subagent operates on the shared `evals/judges/` tree (not an isolated worktree), so it writes its own journal entry. After certifying or stalling, append one `learning` per the `manage-eval-journal` skill: `python evals/journal.py append --type learning --actor calibrate-judge-loop --stage stage-2-rigor --summary "judge <slug> certified TPR .92/TNR .88" --refs <judge_path>/metadata.json` (or "... stalled: <reason>"). Pointer only.

## Loop Stop Conditions (summary)

The loop terminates on the FIRST of:
1. Both target metrics hit on dev set.
2. `max_iterations` reached.
3. Both metrics plateau for 2 consecutive iterations.
4. Refinement subagent returns no proposed edit (judge is at its ceiling).

Always run the test-set measurement (Step 3) regardless of how the dev loop ended, unless the loop returned `stalled` with both dev metrics below `min_*`.

## Context Hygiene

- Do not load full traces into the parent context. Pass file paths to refinement subagents.
- Per iteration, only summarize counts + 2-3 representative misclassifications back to the caller.
- The full calibration log lives on disk; the caller gets a final summary.

## Final Report to Caller

```
Calibration complete for judge: <failure_mode_slug>
Status: certified | certified_minimum | stalled
Iterations: 3
Final dev TPR/TNR: 0.94 / 0.91
Test TPR/TNR: 0.92 / 0.88
Bias-corrected production rate: 0.85 [0.78, 0.91]
Calibration log: <path>
```

## Anti-Patterns

- Looking at the test set during iteration. It's measured ONCE at the end.
- Auto-swapping the LLM model when stalled. Surface to user; let them decide.
- Treating dev TPR/TNR as final. Test set is the unbiased measurement.
- Running calibration without splits. Few-shot examples drawn from dev/test data are leakage.
- Skipping bias correction when reporting an aggregate pass rate. Raw observed rate is biased.
- Re-creating splits between calibration runs of the same judge. Reuse existing splits to keep test-set integrity.
- Returning misclassified traces to the parent caller. Refinement subagent only.
