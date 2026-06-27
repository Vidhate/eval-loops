# eval-loops

Skills and subagents that guide AI coding agents through the **full LLM eval lifecycle** — from gathering product context to running self-improving fix-and-ablate loops.

`eval-loops` is a superset of [Hamel Husain's evals-skills](https://github.com/hamelsmu/evals-skills). It keeps Hamel's original skills and adds agnostic-core lifecycle skills, stage-aware orchestrators, and supervisor subagents that turn evals into repeatable loops. The original skills guard against common mistakes seen across 50+ companies and students in the [AI Evals course](https://maven.com/parlance-labs/evals?promoCode=evals-info-url); the additions wire them into an end-to-end process. If you're new to evals, see [questions.md](questions.md) for free fundamentals.

> [!IMPORTANT]
> **The best evals are hyper-customized to the problem at hand. No general framework — including this one — will ever beat them.** These skills exist to get you off the ground and to teach you evals in the process, so you come away with the right starting point and the knowledge to iterate. Treat them as scaffolding to outgrow, not a destination. The moment you understand your own failure modes well enough to write evals grounded in your stack, your domain, and your data, do that — they will outperform anything generic here.

## What makes this different

Hamel's skills give you sharp individual tools (error analysis, judge design, calibration). `eval-loops` adds the connective tissue:

- **A full 9-step lifecycle** — context → tracing → simulation → datasets → annotation → error analysis & triage → judge building → judge calibration → fix & ablate.
- **Two entry-point orchestrators** — a lightweight *vibe* loop for solo devs with no tooling, and a rigorous *expert* loop with human checkpoints.
- **Supervisor subagents** — self-improving loops that calibrate judges and run fix-and-ablate experiments until thresholds are met or progress stalls.
- **Profile lenses** — guardrails and RAG profiles that inject domain-specific failure catalogs and judge templates into the standard flow.
- **Shared artifacts** — skills read and write `context.md`, dataset manifests, judge metadata, and run logs so each stage builds on the last.

## Where to Start

**You don't invoke the 17 skills one by one. Pick one of three entry points based on your situation — each one drives the individual skills and sub-agents for you, end to end.**

| Your situation | Start with | Type | What it does |
|----------------|-----------|------|--------------|
| I already have an eval pipeline and want to know if it's any good | `audit-eval-pipeline` | skill | Diagnoses an existing pipeline, prioritizes findings by severity, and recommends which skills to run next |
| Building from scratch — solo, no domain experts, no observability tooling | `orchestrator-stage1-vibe` | sub-agent | Gets you from zero to a running vibe-eval loop in under an hour, then watches for the signals that mean you're ready for rigor |
| Building or maturing evals — domain experts available and/or you want full rigor | `orchestrator-stage2-rigor` | sub-agent | Drives the full 9-step pipeline with human checkpoints, and resumes from wherever you left off |

**Not sure which?** Start with `orchestrator-stage1-vibe`. It's the cheapest path to signal, and it graduates you into the stage-2 orchestrator automatically once manual review starts costing more than rigor would.

Once the plugin is installed (see below), just tell Claude what you want. For example, to be driven end to end:

> Use the eval-loops stage-2 rigor orchestrator to set up evals for my agent. Start by gathering product context and stop at each human checkpoint for my sign-off.

Or to diagnose an existing setup:

> Run the eval-loops audit-eval-pipeline skill on my eval setup. Investigate each diagnostic area with a separate subagent in parallel, synthesize one report, and recommend which skills to run next.

> [!NOTE]
> **Skills vs. sub-agents.** Skills are invocable directly as `/eval-loops:<skill-name>`. Sub-agents (including the two orchestrators) are *dispatched by Claude* when you ask for them by name — they aren't slash commands. The tables below mark which is which. Everything other than the three entry points is a building block these orchestrators sequence; invoke them directly only when you want à la carte control.

New to evals entirely? See [questions.md](questions.md) for free fundamentals before you start.

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

## Skills

The skills map onto a 9-step lifecycle. It's a loop, not a one-way pipeline — error analysis feeds judge building, and fix-and-ablate feeds back into error analysis. The **Stage** column tells you when each skill applies: **1** = vibe (fast, solo), **2** = rigor (experts + tooling), **Any** = useful at either stage. The orchestrators invoke these for you; the table is here so you understand what's happening and can run any skill on its own.

| Step | Skill | Stage | What it does |
|------|-------|:-----:|-------------|
| 1. Context | `gather-product-context` | 1 & 2 | Gather product, vision, and architecture context into a wiki-style `context.md` that downstream skills consume |
| 2. Tracing | `instrument-tracing` | 2 | Instrument the codebase with WYSIWYG OpenTelemetry tracing across endpoints, tools, retrieval, and pre/post-processing (stage 1 uses lightweight file logging instead) |
| 3. Simulation | `build-simulation-harness` | 1 & 2 | Build a Python harness that generates inputs, runs them through the agent, and produces traced outputs (static or dynamic, single- or multi-turn) |
| 3a. Inputs | `generate-synthetic-data` | 1 & 2 | Create diverse synthetic test inputs via dimension-based tuple generation |
| 4. Datasets | `manage-eval-datasets` | 2 | Create, version, and manage datasets as manifests of `trace_id`s — the source of truth for ablation and annotation |
| 5. Annotation | `run-annotation-session` | 2 | Drive a labeling session in human-local, third-party-GUI, or llm-council mode |
| 5a. Interface | `build-review-interface` | 2 | Build a custom browser-based annotation interface tailored to your data |
| 6. Error analysis | `error-analysis` | 2 | Systematically identify and categorize failure modes by reading traces |
| 7. Judge building | `build-auto-judge` | 2 | Build an auto-judge for one failure mode — algorithmic-first, LLM judge only when needed |
| 7a. Judge prompts | `write-judge-prompt` | 2 | Design LLM-as-Judge evaluators for subjective criteria code can't check |
| 8. Calibration | `validate-evaluator` | 2 | Calibrate an LLM judge against human labels using data splits, TPR/TNR, and bias correction |
| 9. RAG eval | `evaluate-rag` | 2 | Evaluate retrieval and generation quality in RAG pipelines |
| Fast loop | `vibe-eval-fast-loop` | 1 | Run a small input set and render traces as markdown tables in chat for quick pass/fail signal |
| Audit ⭐ | `audit-eval-pipeline` | Any | **Entry point.** Stage-aware audit of an existing pipeline, cross-checked against artifacts from the other skills |
| Audit (core) | `eval-audit` | Any | The underlying audit: surface problems — missing error analysis, unvalidated judges, vanity metrics |

⭐ = an [entry point](#where-to-start).

## Sub-agents

Dispatched by Claude (ask for them by name — they aren't slash commands). Each runs in its own context window so heavy trace-reading and iterative loops don't pollute the parent conversation. The two **orchestrators** are the end-to-end drivers; the rest are building blocks the orchestrators spawn.

| Sub-agent | Stage | Role | What it does |
|-----------|:-----:|------|-------------|
| `orchestrator-stage1-vibe` ⭐ | 1 | Entry point | Drives stage-1 setup zero → running vibe loop: context (lightweight) → file logging → ~10 inputs → vibe loop. Watches for graduation signals and hands off to stage-2 |
| `orchestrator-stage2-rigor` ⭐ | 2 | Entry point | Drives the full 9-step flow with all 6 human checkpoints, detecting existing artifacts and resuming from the right step |
| `error-analysis-and-triage` | 2 | Building block | Reads a labeled dataset, buckets failure modes, and triages into spec-failure (fix-the-prompt) vs gen-failure (build-a-judge) queues |
| `llm-council-annotator` | 2 | Building block | Karpathy-style 3-stage LLM council producing baseline Pass/Fail labels when no domain experts are available |
| `calibrate-judge-loop` | 2 | Building block | Self-improving loop that calibrates an auto-judge against human labels until TPR/TNR thresholds are met or stalled |
| `fix-and-ablate-loop` | 2 | Building block | Self-improving supervisor that applies one fix per branch, re-runs the dataset, runs certified judges, and compares pass rates |

⭐ = an [entry point](#where-to-start).

## The Two Stages, Explained

`eval-loops` recognizes that not everyone has domain experts and observability tooling on day one. The entry-point orchestrators correspond to these stages.

- **Stage 1 (vibe)** — Solo dev, no experts, no tooling. Get fast pass/fail signal from a small simulated input set rendered directly in chat. Skips dataset versioning, judge calibration, and rigorous error analysis. Driven by `orchestrator-stage1-vibe`.
- **Stage 2 (rigor)** — Domain experts available, agent maturing or in production. The full 9-step process with human checkpoints at context sign-off, tracing smoke-test, tool-integration validation, harness smoke-test, failure-mode confirmation, and judge certification. Driven by `orchestrator-stage2-rigor`.

You don't have to choose manually: stage 1 graduates into stage 2 on its own when manual review starts costing more than rigor would. The orchestrators also read the Stage field from `context.md` if it already exists.

## Profile Lenses

Applied automatically by the stage-2 orchestrator when `context.md` tags a feature. They augment the standard flow — injecting failure catalogs, attack templates, and judge templates — rather than replacing it.

| Profile | Stage | When |
|---------|:-----:|------|
| `guardrails-eval-profile` | 2 | Agent has guardrail features (jailbreak resistance, prompt-injection defense, harmful-content blocking, regulated topics) |
| `rag-eval-profile` | 2 | Agent has RAG features — separates retrieval vs generation evaluation |

## Write Your Own Skills

As the note at the top says, generic skills are scaffolding to outgrow. These encode mistakes that generalize across projects; skills grounded in your stack, your domain, and your data will outperform them. Start here, then write your own — the [meta-skill](meta-skill.md) can help you ground custom skills.

## Beyond These Skills

These skills handle the parts of eval work that generalize. Much doesn't: production monitoring, CI/CD integration, data analysis, and more. The [course](https://maven.com/parlance-labs/evals?promoCode=evals-info-url) covers all of it.

## Credits & License

Built on top of [Hamel Husain's evals-skills](https://github.com/hamelsmu/evals-skills) (MIT). The original skills and course material are Hamel's; the lifecycle skills, orchestrators, and supervisor subagents are extensions by Aditya Vidhate. Licensed under [MIT](LICENSE).
