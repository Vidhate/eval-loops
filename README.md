# eval-loops

Skills and subagents that guide AI coding agents through the **full LLM eval lifecycle** — from gathering product context to running self-improving fix-and-ablate loops.

`eval-loops` is a superset of [Hamel Husain's evals-skills](https://github.com/hamelsmu/evals-skills). It keeps Hamel's original skills and adds agnostic-core lifecycle skills, stage-aware orchestrators, and supervisor subagents that turn evals into repeatable loops. The original skills guard against common mistakes seen across 50+ companies and students in the [AI Evals course](https://maven.com/parlance-labs/evals?promoCode=evals-info-url); the additions wire them into an end-to-end process. If you're new to evals, see [questions.md](questions.md) for free fundamentals.

## What makes this different

Hamel's skills give you sharp individual tools (error analysis, judge design, calibration). `eval-loops` adds the connective tissue:

- **A full 9-step lifecycle** — context → tracing → simulation → datasets → annotation → error analysis & triage → judge building → judge calibration → fix & ablate.
- **Two entry-point orchestrators** — a lightweight *vibe* loop for solo devs with no tooling, and a rigorous *expert* loop with human checkpoints.
- **Supervisor subagents** — self-improving loops that calibrate judges and run fix-and-ablate experiments until thresholds are met or progress stalls.
- **Profile lenses** — guardrails and RAG profiles that inject domain-specific failure catalogs and judge templates into the standard flow.
- **Shared artifacts** — skills read and write `context.md`, dataset manifests, judge metadata, and run logs so each stage builds on the last.

## New to Evals? Start Here

Give your coding agent these instructions:

> Install the eval-loops plugin from https://github.com/Vidhate/eval-loops, then run /eval-loops:audit-eval-pipeline on my eval pipeline. Investigate each diagnostic area using a separate subagent in parallel, then synthesize the findings into a single report. Use other skills in the plugin as recommended by the audit.

The audit isn't a complete solution, but it catches common problems and recommends which other skills to use to fix them.

Want the guided, end-to-end experience instead? Start with `gather-product-context`, then let an orchestrator drive the rest:

- **Solo, no tooling, fast signal** → `orchestrator-stage1-vibe`
- **Full rigor with domain experts** → `orchestrator-stage2-rigor`

## Installation

In Claude Code, run these two commands:

```bash
# Step 1: Register the plugin repository
/plugin marketplace add Vidhate/eval-loops

# Step 2: Install the plugin
/plugin install eval-loops@eval-loops
```

To upgrade:

```bash
/plugin update eval-loops@eval-loops
```

After installation, restart Claude Code. The skills will appear as `/eval-loops:<skill-name>`.

## Installation (npx skills)

If you use the open Skills CLI, install from this repo with:

```bash
npx skills add https://github.com/Vidhate/eval-loops
```

Install one skill only:

```bash
npx skills add https://github.com/Vidhate/eval-loops --skill audit-eval-pipeline
```

Check for updates:

```bash
npx skills check
npx skills update
```

## The Lifecycle

The skills map onto a 9-step process. Steps are loops, not a one-way pipeline — error analysis feeds judge building, fix-and-ablate feeds back into error analysis.

| Step | Skill | What it does |
|------|-------|-------------|
| 1. Context | `gather-product-context` | Gather product, vision, and architecture context into a wiki-style `context.md` that downstream skills consume |
| 2. Tracing | `instrument-tracing` | Instrument the codebase with WYSIWYG OpenTelemetry tracing across endpoints, tools, retrieval, and pre/post-processing |
| 3. Simulation | `build-simulation-harness` | Build a Python harness that generates inputs, runs them through the agent, and produces traced outputs (static or dynamic, single- or multi-turn) |
| 3a. Inputs | `generate-synthetic-data` | Create diverse synthetic test inputs via dimension-based tuple generation |
| 4. Datasets | `manage-eval-datasets` | Create, version, and manage datasets as manifests of `trace_id`s — the source of truth for ablation and annotation |
| 5. Annotation | `run-annotation-session` | Drive a labeling session in human-local, third-party-GUI, or llm-council mode |
| 5a. Interface | `build-review-interface` | Build a custom browser-based annotation interface tailored to your data |
| 6. Error analysis | `error-analysis` | Systematically identify and categorize failure modes by reading traces |
| 7. Judge building | `build-auto-judge` | Build an auto-judge for one failure mode — algorithmic-first, LLM judge only when needed |
| 7a. Judge prompts | `write-judge-prompt` | Design LLM-as-Judge evaluators for subjective criteria code can't check |
| 8. Calibration | `validate-evaluator` | Calibrate an LLM judge against human labels using data splits, TPR/TNR, and bias correction |
| 9. RAG eval | `evaluate-rag` | Evaluate retrieval and generation quality in RAG pipelines |
| Audit | `audit-eval-pipeline` | Stage-aware audit of an existing pipeline, cross-checked against artifacts from the other skills |
| Audit (core) | `eval-audit` | Surface problems — missing error analysis, unvalidated judges, vanity metrics |
| Fast loop | `vibe-eval-fast-loop` | Stage-1 vibe loop: run a small input set and render traces as markdown tables in chat |

## Profiles (Lenses)

Profiles augment the standard flow when the agent has specific features. They don't replace the main loop — they inject failure catalogs, attack templates, and judge templates.

| Profile | When |
|---------|------|
| `guardrails-eval-profile` | Agent has guardrail features (jailbreak resistance, prompt-injection defense, harmful-content blocking, regulated topics) |
| `rag-eval-profile` | Agent has RAG features — separates retrieval vs generation evaluation |

## Subagents

Run in their own context windows so heavy trace-reading and iterative loops don't pollute the parent conversation.

| Subagent | What it does |
|----------|-------------|
| `orchestrator-stage1-vibe` | Top-level driver for stage-1 (pre-conviction) setup: context → minimal tracing → ~10 inputs → vibe loop |
| `orchestrator-stage2-rigor` | Top-level driver for the full 9-step flow with all 6 human checkpoints |
| `error-analysis-and-triage` | Read a labeled dataset, bucket failure modes, and triage into spec-failure (fix-the-prompt) vs gen-failure (build-a-judge) queues |
| `llm-council-annotator` | Karpathy-style 3-stage LLM council producing baseline Pass/Fail labels when no domain experts are available |
| `calibrate-judge-loop` | Self-improving loop that calibrates an auto-judge against human labels until TPR/TNR thresholds are met or stalled |
| `fix-and-ablate-loop` | Self-improving supervisor that applies one fix per branch, re-runs the dataset, runs certified judges, and compares pass rates |

## Two Stages

`eval-loops` recognizes that not everyone has domain experts and observability tooling on day one.

- **Stage 1 (vibe)** — Solo dev, no experts, no tooling. Get fast pass/fail signal from a small simulated input set rendered directly in chat. Skips dataset versioning, judge calibration, and rigorous error analysis.
- **Stage 2 (rigor)** — Domain experts available, agent maturing or in production. The full 9-step process with human checkpoints at context sign-off, tracing smoke-test, tool-integration validation, harness smoke-test, failure-mode confirmation, and judge certification.

The orchestrators pick the stage from `context.md`, or you can request one explicitly.

## Write Your Own Skills

These skills encode mistakes that generalize across projects. Skills grounded in your stack, your domain, and your data will outperform them. Start here, then write your own — the [meta-skill](meta-skill.md) can help you ground custom skills.

## Beyond These Skills

These skills handle the parts of eval work that generalize. Much doesn't: production monitoring, CI/CD integration, data analysis, and more. The [course](https://maven.com/parlance-labs/evals?promoCode=evals-info-url) covers all of it.

## Credits & License

Built on top of [Hamel Husain's evals-skills](https://github.com/hamelsmu/evals-skills) (MIT). The original skills and course material are Hamel's; the lifecycle skills, orchestrators, and supervisor subagents are extensions by Aditya Vidhate. Licensed under [MIT](LICENSE).
