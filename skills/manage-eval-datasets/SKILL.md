---
name: manage-eval-datasets
description: >
  Create, version, and manage eval datasets — curated subsets of traces that
  serve as the source of truth for ablation experiments and human annotation.
  A dataset is a manifest pointing at trace_ids; trace bodies live in the
  observability backend, not duplicated locally. Use after a simulation run
  produces traces. Do NOT use when a tool-specific dataset skill (e.g.,
  manage-eval-datasets-braintrust) is available — those override this one.
---

# Manage Eval Datasets

A dataset is a frozen, named, versioned set of trace pointers. It is the unit of "what we ran evals on" so the user can compare BE iterations apples-to-apples.

## Why pointers, not bodies

Trace bodies are large and live in the observability backend (Braintrust, LangSmith, Phoenix, OTLP backend, etc.). Local manifests reference traces by ID. If the backend purges old traces, datasets break — that's the right failure mode, since evals on stale traces are meaningless.

If the user has no observability backend yet, fall back to local trace storage in `evals/runs/<run_id>/traces/<trace_id>.json` and reference those file paths in the manifest.

## Manifest Schema

`evals/datasets/<dataset_name>/v<n>.json`:

```json
{
  "dataset_id": "<name>_v<n>",
  "name": "<name>",
  "version": <n>,
  "created_at": "ISO-8601",
  "description": "human-readable purpose of this dataset",
  "parent_dataset_id": "<id>" | null,
  "input_version": "v1",
  "feature_filter": ["search", "scheduling"] | null,
  "axis_b_filter": ["rag", "subjective"] | null,
  "trace_refs": [
    {
      "trace_ref_id": "ref_0001",
      "trace_id": "<observability backend trace_id>",
      "session_id": "<session_id if multi-turn>",
      "input_id": "in_0042",
      "source_run_id": "20260508T143022Z_v1abc12",
      "feature": "search",
      "axis_b_tags": ["rag"]
    }
  ],
  "labels": {
    "schema": {
      "<failure_mode_name>": "binary"
    },
    "values": {
      "ref_0001": {
        "overall_pass_fail": "Fail",
        "<failure_mode_name>": "Fail",
        "annotator": "user@example.com",
        "notes": "Missing budget filter in SQL"
      }
    }
  } | null
}
```

### Field rules

- `dataset_id` is `<name>_v<n>` — uniqueness is name + version.
- `parent_dataset_id` is set when this dataset derives from another (e.g., a filtered subset, a re-labeled version). Lets you trace lineage.
- `input_version` ties the dataset to the input file used to produce its traces. Required for ablation reproducibility.
- `trace_refs` does NOT embed trace bodies. Just IDs and minimal routing metadata.
- `labels` is null for unlabeled datasets, populated after annotation. Each entry keyed by `trace_ref_id`.
- `labels.schema` declares the failure modes labeled in this dataset. `binary` is the only supported type — labels are Pass or Fail.

## Lifecycle

### Step 1: Create dataset from a run

After `build-simulation-harness` produces a run, create a dataset:

```python
def create_dataset(name: str, run_id: str, *, feature_filter=None, axis_b_filter=None, sample_n=None, parent=None) -> str:
    """
    Read evals/runs/<run_id>/trace_ids.json and produce a manifest at
    evals/datasets/<name>/v<n>.json. Return the new dataset_id.
    """
```

Filtering rules:
- `feature_filter`: only include traces whose `agent.feature` matches.
- `axis_b_filter`: only include traces tagged with at least one matching Axis B type (read from context.md feature catalog).
- `sample_n`: random sample with seed for reproducibility.

### Step 2: Freeze

Datasets are immutable once written. Bumping a version (`v1` → `v2`) is the only way to change membership or labels. Never overwrite `vN.json`.

### Step 3: Reference in experiments

Every eval experiment, judge calibration run, and ablation comparison MUST reference exactly one `dataset_id`. Record it in run logs.

### Step 4: Version on change

Bump the version when:
- Trace membership changes (added/removed)
- Labels are added or revised
- Input version changes upstream

Do NOT bump for:
- Description edits
- Annotator metadata corrections (treat as in-place metadata, not data)

### Step 5: Lineage

When deriving a dataset from another (e.g., taking the failures-only subset for judge training), set `parent_dataset_id` to the source. The lineage chain lets later skills validate non-leakage between train/dev/test splits.

## Local Trace Storage Fallback

If no observability backend is configured:

1. The harness writes `evals/runs/<run_id>/traces/<trace_id>.json` per trace.
2. The manifest's `trace_id` field points at that file path (relative to repo root).
3. Loading a dataset reads trace bodies from those files.

This mode is acceptable for stage 1. Switch to a real backend before stage 2.

## CLI Helpers

Provide `evals/datasets_cli.py` with these commands:

```
datasets create <name> --run <run_id> [--feature ...] [--axis-b ...] [--sample N] [--parent <id>]
datasets list
datasets show <dataset_id>
datasets bump <dataset_id>           # creates next version copy for editing
datasets diff <dataset_id_a> <dataset_id_b>
```

`bump` is the ONLY way to mutate a dataset — it copies vN to vN+1 in writable form.

## Anti-Patterns

- Embedding trace bodies in the manifest. Pointers only — bodies live in the backend.
- Mutating a frozen `vN.json`. Bump to `vN+1`.
- Running an eval experiment without recording the `dataset_id`. The result is unreproducible.
- Creating a labeled dataset from one run and a different one's traces — `source_run_id` per ref pins provenance.
- Mixing train/dev/test split membership across versions. Splits live as separate datasets with `parent_dataset_id` pointing at the parent.
- Storing labels in a separate file from the manifest. They live in the same JSON to keep dataset state atomic.
