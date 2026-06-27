---
name: build-simulation-harness
description: >
  Build a Python simulation harness that generates inputs, runs them through the
  agent backend, and produces traced outputs for downstream eval work. Supports
  static (pre-generated, versioned) and dynamic (LLM-generated at runtime) input
  modes, single-turn and multi-turn conversations. Use after instrument-tracing.
  Extends the generate-synthetic-data skill — invoke that for input generation
  best practices.
---

# Build Simulation Harness

Build the scaffolding that lets the user run synthetic or real-shaped inputs through their agent and capture the resulting traces. Every later eval step operates on these traces.

## Prerequisites

- `evals/context.md` exists.
- Tracing is implemented and verified per `instrument-tracing`.
- The agent backend is runnable locally or has a hittable endpoint.

## Decision: Static vs. Dynamic Inputs

Ask the user one question:

> "Do you want simulation inputs to be regenerated each run, or stored as a versioned file so you can compare run-to-run on the same inputs?"

| Mode | When to use |
|---|---|
| **Static** (default for stage 2+) | Apples-to-apples comparison across BE iterations. Inputs versioned in git. |
| **Dynamic** | Stage 1 vibe-evals. Maximizing coverage diversity. Stress-testing for regressions where input variety matters more than reproducibility. |

If unclear, default to **static**. Dynamic adds variance that confounds ablation experiments.

## Output Layout

```
evals/
  harness/
    inputs/
      v1.json          # versioned static inputs (if static mode)
      generator.py     # dynamic generator (if dynamic mode)
    runner.py          # the runner that hits the BE
    multi_turn.py      # multi-turn driver (if needed)
    requirements.txt
  runs/
    <run_id>/
      manifest.json    # see manage-eval-datasets for schema
      trace_ids.json   # list of trace_ids/session_ids produced this run
```

## Input Generation

For both static and dynamic modes, follow the dimension/tuple/query method from the `generate-synthetic-data` skill. Read `evals/context.md` Feature Catalog and Known Failure Hypotheses to pick dimensions targeted at suspected failure regions.

### Static mode: `inputs/v1.json`

```json
{
  "version": "v1",
  "created_at": "ISO-8601",
  "dimensions": {
    "feature": ["search", "scheduling", "email"],
    "persona": ["first-time-buyer", "investor", "luxury"],
    "scenario": ["well-specified", "ambiguous", "out-of-scope"]
  },
  "inputs": [
    {
      "input_id": "in_0001",
      "tuple": {"feature": "search", "persona": "investor", "scenario": "ambiguous"},
      "query": "Show me units under $500K with good cap rates near downtown",
      "turns": null
    },
    {
      "input_id": "in_0042",
      "tuple": {...},
      "query": null,
      "turns": [
        {"role": "user", "content": "I'm looking for a 2br"},
        {"role": "user", "content": "Actually under $400k"}
      ]
    }
  ]
}
```

`turns` is non-null for multi-turn cases. `query` and `turns` are mutually exclusive.

Bump the version (`v1` → `v2`) only when inputs change. Pin all eval runs to a specific version. Never edit a frozen version in-place.

### Dynamic mode: `generator.py`

A function `generate_inputs(n: int, seed: int | None) -> list[Input]` that produces `n` inputs at runtime using the same dimension/tuple/query process. Set the seed for partial reproducibility.

## The Runner

`runner.py` is the core integration point. It must:

1. Load inputs (from `v1.json` or generator).
2. For each input, call the agent backend.
3. Capture the resulting trace_id / session_id from the OTEL context (set as attribute on `agent.request`).
4. Write `runs/<run_id>/trace_ids.json` mapping `input_id → trace_id`.
5. Tolerate failures: if one input crashes, log it and continue.

### Calling the backend — how

Pick **one** integration mode based on what the agent exposes:

| BE shape | Integration |
|---|---|
| FastAPI/Flask HTTP endpoint | `httpx.post(...)` against the local server |
| Python function | Direct import + call |
| CLI | `subprocess.run(...)` |
| Multi-turn dialog | See multi-turn section below |

Read `context.md` Agent Surface Area to find the entry point. Confirm with the user before wiring.

### Multi-turn driver

For inputs with `turns` set:

```python
session_id = new_session()
for turn in input["turns"]:
    response = call_backend(turn["content"], session_id=session_id)
    # next turn waits for response — do not parallelize within a session
```

Pass a session ID to the backend so turns share trace context. Verify in the captured trace that all turns of a session share the same `agent.session_id` attribute.

### Concurrency

Default: 4 concurrent workers across **inputs** (not within a session). Configurable via `--workers`. Do not parallelize turns within a multi-turn input.

### Run identifier

`run_id` format: `<UTC-iso8601>_<short-hash-of-input-version>`. Example: `20260508T143022Z_v1abc12`. Stable, sortable, links a run to its input version.

## Smoke-Test Checkpoint (required)

Before signaling completion, run the harness end-to-end with at least 3 inputs:
1. Confirm all 3 produced trace_ids.
2. Pull the traces from the backend and show the user — full input, full output, full tool calls.
3. For one input, diff the harness's recorded output against the trace's `agent.final_output` attribute. They must match.
4. If any input crashed, surface the error to the user before claiming the harness works.

Do NOT mark complete until the user confirms the smoke-test traces look correct.

## Anti-Patterns

- Generating inputs in `runner.py` rather than separating into `inputs/` artifacts. Inputs must be reviewable/version-controllable.
- Picking dynamic mode by default. Dynamic inputs make ablation experiments noisy.
- Editing frozen input files in place. Bump the version.
- Mocking the backend. Hit the real BE so traces are real.
- Sequential single-input runs that take hours. Default to parallel workers across inputs.
- Skipping the smoke-test checkpoint.
- Setting `agent.feature` from the harness instead of letting the BE set it. The harness doesn't know which feature a request will route to.
