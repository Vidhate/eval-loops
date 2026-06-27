---
name: rag-eval-profile
description: >
  Profile/lens skill applied during error-analysis and judge-building when the
  agent has RAG features. Wraps the evaluate-rag skill's metrics and chunking
  optimization guidance and plugs them into the standard 9-step flow (datasets,
  judges, ablation). Use when context.md feature catalog tags any feature as
  axis B = rag. Does not replace the main eval flow — augments it with retrieval
  vs generation separation.
---

# RAG Eval Profile

A lens loaded when the agent has RAG features. Provides retrieval-vs-generation separation, RAG-specific failure modes, and the metric playbook from `evaluate-rag`.

## Activation

Invoked by:
- `error-analysis-and-triage` — apply the retrieval-vs-generation lens when reading traces. Tag failures by stage.
- `build-auto-judge` — pull RAG judge templates.
- `build-simulation-harness` — generate RAG-shaped inputs (factual lookup, multi-hop, synthesis).
- `manage-eval-datasets` — supports the retrieval evaluation dataset shape (queries paired with ground-truth chunks).

## Read First

Read `eval-loops:evaluate-rag` skill for the metric definitions (Recall@k, Precision@k, MRR, NDCG@k, Two-hop Recall@k) and chunking grid-search procedure. This profile does not duplicate that content; it slots it into the wider eval flow.

## Retrieval-vs-Generation Separation

In `error-analysis-and-triage`, every RAG-feature failure must be classified into one of three buckets BEFORE failure modes are derived:

1. **Retrieval-side**: relevant chunk(s) not in top-k, or relevant chunk ranked too low to be effectively used.
2. **Generation-side**: retrieval was correct, generator failed to use it (hallucinated, ignored context, misinterpreted).
3. **Both**: retrieval missed and generator confabulated.

This classification happens before failure-mode bucketing. Reading the trace, ask:
- What did the retriever return? (read `agent.retrieval` span's `retrieval.results`)
- What was the ground-truth relevant chunk? (from the user, or from a labeled retrieval-eval dataset)
- Was it in the top-k? At what rank?
- If yes, did the generator's output reflect it?

Tag traces with `rag_failure_stage: retrieval | generation | both` before bucketing into failure modes.

## Retrieval Eval Datasets

A retrieval eval dataset differs from a trace dataset. It's queries paired with ground-truth relevant chunk IDs.

```json
{
  "dataset_id": "rag_retrieval_v1",
  "kind": "retrieval_eval",
  "queries": [
    {
      "query_id": "rq_001",
      "query": "...",
      "relevant_chunk_ids": ["chunk_abc", "chunk_xyz"],
      "query_type": "factual_lookup" | "synthesis" | "multi_hop"
    }
  ]
}
```

Build via:
- **Manual curation**: highest quality, smallest scale. User writes queries and identifies chunks.
- **Synthetic QA**: per `evaluate-rag`'s chunk → fact → question template.
- **Adversarial**: per `evaluate-rag`'s distractor-chunk method for harder queries.

Store at `evals/datasets/rag_retrieval/v<n>.json`. Track separately from trace datasets.

## RAG-Specific Failure Modes (starter catalog)

Use as reference, not default. Let actual failures emerge from trace reading.

```
[retrieval-side]
- relevant_chunk_not_in_top_k
- relevant_chunk_buried_below_distractors      # in top-k but ranked too low to influence generator
- query_rewrite_dropped_constraint              # if there's a query-rewrite step
- chunking_split_relevant_information           # the answer is split across chunks, none individually has it
- embedding_mismatch_terminology                # query and relevant chunk use different vocab

[generation-side]
- hallucinated_information_absent_from_context
- ignored_relevant_information_from_context
- misinterpreted_context                        # context says X, generator says Y
- attributed_to_wrong_source                    # if citations are part of the output
- combined_unrelated_chunks_into_false_synthesis

[both]
- retrieved_irrelevant_AND_hallucinated
```

## Judge Templates

### Retrieval-side judges (mostly code-based)

- **Recall@k judge**: span attribute `retrieval.results` ∩ `relevant_chunk_ids`. Pure code.
- **MRR / NDCG@k judges**: pure code over span attributes.
- **Chunk-coverage judge**: did the retrieved chunks contain the answer fact? Hybrid: code retrieves chunks, LLM checks if the fact is present in the union.

### Generation-side judges

- **Faithfulness judge** (LLM): given the retrieved context and the generated output, every claim in the output must be supported by the context. Decompose: extract claims with code or LLM, check each.
- **Context-utilization judge** (hybrid): did the output reference the highest-relevance retrieved chunk? Code finds the chunk; LLM judges reference.
- **Answer-relevance judge** (LLM): does the output address the original query, regardless of context? Per `evaluate-rag` definition.

For all LLM judges, follow `write-judge-prompt` and validate via `calibrate-judge-loop`. Pin model versions.

## Chunking Optimization Slot

If retrieval-side failures dominate, run the chunking grid search per `evaluate-rag`. Treat each chunk-config as a BE iteration in `fix-and-ablate-loop`:

| run | chunk_size | overlap | Recall@5 | NDCG@5 | end_to_end_pass_rate |
|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... |

The end-to-end pass rate (your generation-side judges, on the same dataset) is the tiebreaker when retrieval metrics are close.

## Diagnosing Pipeline Failures

Per `evaluate-rag`'s diagnosis table:

| Context Relevance | Faithfulness | Answer Relevance | Diagnosis |
|---|---|---|---|
| High | High | Low | Generator attended to wrong section of correct context |
| High | Low | -- | Hallucination or misinterpretation |
| Low | -- | -- | Retrieval problem — fix retrieval first |

Plug this matrix into `error-analysis-and-triage` output: every RAG failure mode should reference which row of this table it falls under.

## Stage Behavior

RAG features are unusual: retrieval-side failures often reduce to objective code-based judges (Recall@k), while generation-side failures stay subjective. Treat the two halves separately:
- Retrieval-side judges: can saturate at high accuracy and move to lighter monitoring.
- Generation-side judges (faithfulness, relevance): stay in continuous evaluation; foundation-model swaps change generator behavior.

## Anti-Patterns

- Building one end-to-end RAG judge instead of separating retrieval and generation. Failures become unactionable.
- Optimizing retrieval metrics without checking the end-to-end pass rate. A retriever that maximizes Recall@k can degrade generation by adding noise.
- Skipping the chunking grid search and assuming defaults are fine. Chunking dominates retrieval quality.
- Treating synthetic QA datasets as ground truth. Validate against real user queries periodically.
- Generation-side LLM judges with unpinned models.
