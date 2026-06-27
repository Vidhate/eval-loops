---
name: gather-product-context
description: >
  Gather product, vision, and architecture context for an AI agent project before
  any evals work begins. Produces a wiki-style context.md that downstream eval
  skills consume. Use at the start of every eval engagement, or when resuming
  work on a project that has no captured context. Do NOT use when context.md
  already exists and is current — read it instead.
---

# Gather Product Context

Interview the user and inspect the codebase to produce `evals/context.md`, a single source of truth for what the agent does, who it serves, and what failure looks like. Every other eval skill in this plugin reads this file.

## Overview

1. Inspect the codebase to identify agent entry points, tools, and integrations
2. Interview the user across four areas: vision, surface area, failure stakes, constraints
3. Tag each agent feature by Axis B (guardrails / RAG / objective / subjective)
4. Write `evals/context.md`
5. Get user sign-off before any other eval skill runs

## Output Location

`evals/context.md` at the repo root. Create the `evals/` directory if missing.

## Required Sections

The output file MUST contain exactly these sections, in this order. Do not add or rename sections — downstream skills parse them by heading.

```markdown
# Product Context

## Vision
[1-3 sentences. What is this agent for? What outcome does it produce for the user?]

## User Personas
[Bulleted list. Each persona: name, what they want, what they bring to the interaction.]

## Agent Surface Area
[Numbered list of every entry point the agent exposes — endpoints, slash commands, tools-as-clients, etc. For each: input shape, expected output, file path of the handler.]

## Feature Catalog
[Table. One row per agent feature. Columns:
| Feature | Axis B Type | Stage Sensitivity | Failure Stakes | Notes |
Axis B Type: one of guardrails / rag / objective / subjective.
Stage Sensitivity: which lifecycle stages this feature must be evaluated in.
Failure Stakes: what business/user impact a failure has.]

## Tools and Integrations
[Bulleted list. Every tool the agent calls, every external service, every model used. Include model versions where pinned.]

## Pre-Existing Eval Artifacts
[What already exists: traces, datasets, judges, dashboards. Empty bullet if nothing exists.]

## Known Failure Hypotheses
[Bulleted list. What the user expects to fail and why. These are hypotheses to validate during error analysis, not conclusions.]

## Constraints
[Bulleted list. Hard constraints: latency budgets, cost ceilings, compliance requirements, regulated content rules.]

## Stage
[One of: stage-1-vibe / stage-2-rigor / stage-3-production. The user's current lifecycle stage. Used by orchestrators to pick the right flow.]
```

## Interview Procedure

Ask questions in this order. Do not skip ahead — early answers gate later ones.

### Vision (5 minutes)
1. "What does this agent help the user do?"
2. "What does success look like in one sentence?"
3. "Who is this for? Internal users, external customers, both?"

### Surface Area (codebase-driven)
- Inspect the repo for handler files, route definitions, tool registrations.
- Present what you found and ask the user to confirm completeness: "I see endpoints A, B, C and tools X, Y. Anything else exposed?"

### Feature Tagging (the critical step)
For each feature listed, ask:
- "Is this feature **subjective** (requires interpretation, e.g., tone, helpfulness) or **objective** (verifiable, e.g., correct SQL, valid JSON)?"
- "Does this involve **retrieval**?"
- "Does this enforce a **safety guardrail** (jailbreaks, injections, harmful content, regulated topics)?"

A feature can have multiple tags. A RAG-based medical chatbot answer is both `rag` and `subjective`. Capture all applicable tags.

### Failure Stakes
- "What's the worst thing this agent could do? Walk through one example."
- "If this fails 5% of the time, is that fine, painful, or unacceptable?"

### Constraints
- "What's the latency budget per request?"
- "Is there a compliance regime in play (HIPAA, SOC 2, GDPR, etc.)?"
- "Are there any topics the agent must refuse?"

### Stage Detection
Ask directly: "Where are you in the lifecycle?"
- **Stage 1 (vibe):** No domain experts available, fast iteration, just trying to validate the idea.
- **Stage 2 (rigor):** Have domain experts, refining features pre-launch, no real production data yet.
- **Stage 3 (production):** Live product with real users, need continuous evals and CI gates.

If the user is uncertain, ask: "Do you have domain experts you can pull in for annotation work?" → if no → Stage 1. "Is the agent in production with real user traffic?" → if yes → Stage 3. Otherwise → Stage 2.

## Codebase Inspection Heuristics

Before the interview, scan for:
- `requirements.txt` / `pyproject.toml` for framework hints (LangChain, LlamaIndex, raw OpenAI SDK, Anthropic SDK)
- `**/*.py` files matching common agent patterns: classes ending in `Agent`, functions decorated with `@tool`, files named `agent.py`, `tools.py`, `prompts.py`
- API frameworks: FastAPI, Flask routes
- Vector DB clients: Pinecone, Weaviate, Chroma, pgvector
- Trace/eval libs: opentelemetry, braintrust, langsmith, langfuse, phoenix

Report what you found before asking the user — they'll either confirm or correct.

## Sign-off Checkpoint

After writing `evals/context.md`, present the file to the user and ask:
> "Does this match your understanding of the product? Any features missing, mistagged, or stakes wrong?"

Do not proceed to other eval skills until the user explicitly confirms. Other skills will read this file as ground truth.

## Anti-Patterns

- Skipping the interview because the codebase looks self-explanatory. Vision and stakes are not in the code.
- Tagging every subjective-looking feature as `subjective` without asking. The user's tolerance for interpretive failures varies by feature.
- Writing `context.md` without the Stage field. Orchestrators need it.
- Adding sections beyond the required ones. Downstream skills parse by heading.
- Treating this as a one-time activity. Re-run after major product pivots or when surface area expands.
