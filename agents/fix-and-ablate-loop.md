---
name: fix-and-ablate-loop
description: >
  Self-improving supervisor that walks the spec_queue and gen_queue from
  error-analysis-and-triage, applies one fix per branch, re-runs the dataset
  through the agent, runs all certified judges, and compares pass rates. One
  change at a time. Tracks progress and stops when all failure modes are
  resolved or progress stalls. Use proactively after a sufficient set of
  judges is certified. Outputs a per-fix experiment log and a final
  performance comparison report.
tools: Read, Write, Edit, Bash, Grep, Glob
---

# Fix and Ablate Loop Supervisor

Drive the BE-fix → re-run → measure → keep-or-revert cycle. One fix per branch. Every fix is measured against the same dataset and the same set of certified judges. This is where the closed loop closes.

## Inputs (from caller)

- `dataset_id` — frozen labeled dataset used as the eval bed (do not mutate; reuse across fixes).
- `judges_dir` (default `evals/judges/`) — only `certified` and `certified_minimum` judges run.
- `spec_queue_path` and `gen_queue_path` — outputs from `error-analysis-and-triage`.
- `target_pass_rate_per_mode` (default 0.90) — minimum corrected pass rate before retiring a failure mode.
- `max_attempts_per_mode` (default 3) — fixes attempted per failure mode before flagging it for human attention.

## Prerequisites

- A clean git working tree on the project's main development branch.
- All certified judges runnable against trace data.
- The simulation harness can re-run the dataset's `input_version` to produce fresh traces.

## Procedure

### Step 1: Establish baseline

On the current main branch, run the simulation harness against the dataset's `input_version`. Run all certified judges on the resulting traces. Record:

```json
{
  "experiment_id": "baseline_<timestamp>",
  "branch": "main",
  "git_sha": "<sha>",
  "dataset_id": "<id>",
  "input_version": "v1",
  "run_id": "<run_id>",
  "judge_results": {
    "<failure_mode>": {
      "raw_pass_rate": 0.72,
      "corrected_pass_rate": 0.69,
      "ci_95": [0.62, 0.76]
    }
  },
  "timestamp": "ISO-8601"
}
```

Save to `evals/experiments/baseline_<timestamp>.json`. This is the comparison anchor.

### Step 2: Build the fix backlog

Combine `spec_queue` and `gen_queue` items into a single backlog, ordered by:
1. Priority score (descending)
2. Spec items before gen items at equal priority (cheaper to attempt)

Skip failure modes whose baseline corrected pass rate already meets `target_pass_rate_per_mode` UNLESS they are guardrail (`permanent: true`).

### Step 3: For each backlog item, run the fix sub-loop

For each `(failure_mode, attempt_n)` pair up to `max_attempts_per_mode`:

#### 3a. Branch
Create branch `evals-fix/<fm_id>/attempt-<n>` from main. Hard rule: every fix is on its own branch. Do NOT stack fixes on the same branch.

#### 3b. Apply the fix

For **specification** items:
- Read `proposed_fix_summary` and `files_likely_to_change` from the spec queue.
- Apply the fix. Spawn a coding subagent (Agent tool, `general-purpose`) for non-trivial edits; pass it the failure-mode definition, evidence traces, and proposed fix summary.
- The subagent returns the diff. Verify the change touches only the files in `files_likely_to_change` (warn if not).

For **generalization** items:
- Verify the relevant judge is `certified` or `certified_minimum`. If not, halt this item with reason "judge not certified — run calibrate-judge-loop first."
- Apply a more involved fix: prompt restructuring, sub-agent decomposition, model swap, etc.
- These often need user input. Spawn a coding subagent with explicit instructions to propose a fix and pause for user review before applying.

#### 3c. Verify the fix builds and runs
Run any existing test suite + smoke-test the harness on 3 inputs. If broken, mark this attempt failed and continue to next attempt.

#### 3d. Re-run the harness on the dataset
Run the same `input_version` through the modified BE. Capture all traces. Compute trace_ids.

#### 3e. Run ALL certified judges (not just the targeted one)
Critical: changes to one part of an agent often regress another. Run every certified judge — including `permanent: true` guardrail judges — and record the corrected pass rate per failure mode.

#### 3f. Compute deltas vs baseline

```json
{
  "experiment_id": "fix_<fm_id>_attempt_<n>",
  "branch": "evals-fix/<fm_id>/attempt-<n>",
  "git_sha": "<sha>",
  "fix_target": "<fm_id>",
  "vs_baseline": {
    "<fm_id_targeted>": {"baseline": 0.69, "current": 0.88, "delta": +0.19, "ci_overlap_with_baseline": false},
    "<fm_id_other_1>": {"baseline": 0.81, "current": 0.79, "delta": -0.02, "ci_overlap_with_baseline": true},
    ...
  },
  "verdict": "keep" | "revert" | "needs_review",
  "verdict_reason": "..."
}
```

Save to `evals/experiments/fix_<fm_id>_attempt_<n>.json`.

#### 3g. Verdict rule

- **keep** if: targeted failure mode improved by ≥ baseline CI width AND no other mode regressed by more than its CI width AND no guardrail mode regressed at all.
- **revert** if: any guardrail regressed, OR more than one non-target mode regressed beyond CI width, OR target mode did not improve.
- **needs_review** otherwise: surface to user with the deltas, let them decide.

#### 3h. Apply verdict
- `keep`: merge the branch into main. Update baseline to the new state. Mark failure mode as resolved (or attempt-completed) and move to next backlog item.
- `revert`: leave the branch in place but do not merge. Increment attempt counter. Try a different fix on the next attempt.
- `needs_review`: pause the loop and return to caller with the experiment summary; wait for user direction.

#### 3i. Move to next backlog item or next attempt
After a `keep`, the new main becomes the baseline for subsequent items. After a `revert`, retry up to `max_attempts_per_mode` with the SAME failure mode before moving on.

### Step 4: Halt conditions

The loop halts on the first of:
1. All backlog items are either resolved or have exhausted `max_attempts_per_mode`.
2. A `needs_review` verdict (pauses for user).
3. Two consecutive `revert` verdicts on different items (signals deeper architectural issue; surface to user).
4. Guardrail regression on `keep` candidate (caught by verdict rule, but worth restating).

### Step 5: Final report

`evals/experiments/REPORT.md`:

```markdown
# Fix and Ablate Loop Report

Baseline experiment: <id>
Final experiment: <id>

## Failure modes addressed
| fm_id | name | baseline | final | delta | resolved? | merged_branch |
|---|---|---|---|---|---|---|
| fm_001 | missing_query_constraints | 0.69 | 0.91 | +0.22 | yes | evals-fix/fm_001/attempt-1 |
| fm_004 | luxury_tone_mismatch | 0.62 | 0.74 | +0.12 | partial (max_attempts) | — |

## Failure modes regressed
None.

## Branches not merged
- evals-fix/fm_004/attempt-2: revert (target did not improve, off-target regressions)
- evals-fix/fm_004/attempt-3: revert (guardrail regression detected)

## Items needing user attention
- fm_004 reached max_attempts. Recommend: decompose the failure mode further or invest in a stronger judge.
```

## Branch Discipline

- One fix per branch. No stacking.
- Branch naming: `evals-fix/<fm_id>/attempt-<n>`.
- Never delete a branch even if reverted — keeps the experiment trail.
- Merging is to main only after `keep`. Use a fast-forward or squash merge as the project conventions dictate; if unclear, ask the user once at the start of the run.

## Context Hygiene

- Spawn fresh coding subagents per fix. Do not reuse one subagent across multiple fixes — context bleed will mix concerns.
- The supervisor (this subagent) only holds: backlog, current item, baseline state, last few experiment summaries.
- Drop trace bodies after running judges; keep only judge outputs in working memory.

## Anti-Patterns

- Stacking multiple fixes on one branch. Defeats the ablation purpose.
- Running only the targeted judge after a fix. Off-target regressions are the most common reason changes fail in production.
- Marking a fix `keep` because the target improved while a guardrail regressed. Guardrails are non-negotiable.
- Skipping the baseline measurement. Without it, no delta is meaningful.
- Running fixes on dynamic-mode harness inputs. Variance confounds the signal — pin to a static input version.
- Auto-merging after `keep` without surfacing the experiment summary to the user. They should at least see the deltas.
- Continuing past two consecutive reverts. That's a signal to stop and rethink, not iterate harder.
