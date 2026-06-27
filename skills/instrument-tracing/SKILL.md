---
name: instrument-tracing
description: >
  Instrument an AI agent codebase with WYSIWYG OpenTelemetry tracing across
  every endpoint, tool call, retrieval step, and pre/post-processing stage. Use
  after gather-product-context and before any simulation or eval work. Do NOT
  use when a tool-specific tracing skill (e.g., instrument-tracing-braintrust)
  is available — those override this one.
---

# Instrument Tracing

Add OTEL spans across the agent so every byte of context, every tool call, and every model response is captured exactly as it flowed at runtime. WYSIWYG is the rule: traces must reproduce what happened, not a sanitized summary.

## Prerequisites

- `evals/context.md` exists. Read the **Agent Surface Area** and **Tools and Integrations** sections — they list what must be traced.
- Python project with a known agent framework (raw SDK, LangChain, LlamaIndex, etc.).

## Core Directives

### WYSIWYG: never snip context

- Do **not** truncate prompts, tool inputs, tool outputs, retrieved documents, or model responses. Even if a span attribute is 50,000 tokens long, store it intact.
- Do **not** redact field names or restructure data into "summary" objects. Capture raw payloads.
- The only acceptable redaction is for secrets (API keys, OAuth tokens, PII covered by compliance). Replace with `<redacted:reason>` and document the redaction list in `evals/context.md` under Constraints.
- If span size limits are a concern, configure the OTEL exporter to handle large payloads (raise `max_attribute_value_length` or use the body field). Do not solve size limits by truncating.

### Span coverage requirements

Every one of these must produce a span:

1. **Each agent endpoint entry point** — root span for the request, with the user input as an attribute.
2. **Each LLM call** — model name, full prompt (system + user + assistant turns), full response, token counts, latency.
3. **Each tool call** — tool name, full input args, full output, error if any.
4. **Each retrieval step** — query, top-k results with full chunk text, scores, retrieval params.
5. **Each pre-processing step on user input** — input transformations, classification, routing decisions.
6. **Each post-processing step on agent output** — formatting, filtering, redaction.
7. **Multi-turn boundaries** — session/conversation IDs as span attributes so traces can be grouped.

If a step is in code but not in a span, the eval pipeline cannot see it.

### Stable span and attribute naming

Use these names consistently. Downstream eval skills parse by name.

```
Span names:
  agent.request           — root span for an endpoint hit
  agent.llm.call          — any LLM API call
  agent.tool.call         — any tool invocation
  agent.retrieval         — RAG retrieval step
  agent.preprocess        — user input transformation
  agent.postprocess       — agent output transformation

Required attributes on agent.request:
  agent.session_id        — unique per conversation
  agent.user_input        — raw user input
  agent.final_output      — final response to user
  agent.feature           — feature name from context.md Feature Catalog

Required attributes on agent.llm.call:
  llm.model               — pinned model version (e.g., "gpt-4o-2024-05-13")
  llm.prompt              — full prompt as JSON-serialized message list
  llm.response            — full response text
  llm.input_tokens
  llm.output_tokens

Required attributes on agent.tool.call:
  tool.name
  tool.input              — JSON-serialized args
  tool.output             — JSON-serialized result
  tool.error              — error message if failed

Required attributes on agent.retrieval:
  retrieval.query         — query sent to retriever
  retrieval.top_k
  retrieval.results       — JSON list of {chunk_id, text, score}
```

### Pin model versions

In every `agent.llm.call` span, set `llm.model` to a fully pinned identifier. Never `gpt-4o`, always `gpt-4o-2024-05-13`. Foundation models drift silently.

If the codebase currently uses unpinned model strings, flag this to the user and offer to pin them. Do not pin without confirmation — they may have a reason.

## Implementation Steps

### Step 1: Add OTEL dependencies

```
opentelemetry-api
opentelemetry-sdk
opentelemetry-exporter-otlp
```

If using a known framework with native OTEL support (e.g., `openinference-instrumentation-openai`, `opentelemetry-instrumentation-langchain`), prefer the framework's auto-instrumentation, then layer manual spans for tool calls and pre/post-processing.

### Step 2: Configure the tracer provider

Single shared module: `evals/tracing.py`. Set up `TracerProvider`, exporter (OTLP HTTP to a collector or directly to a backend), and resource attributes (service name, environment).

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

def init_tracing(service_name: str, otlp_endpoint: str):
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

tracer = trace.get_tracer("agent")
```

### Step 3: Wrap entry points

Every endpoint handler gets wrapped at its outermost layer:

```python
with tracer.start_as_current_span("agent.request") as span:
    span.set_attribute("agent.session_id", session_id)
    span.set_attribute("agent.user_input", user_input)
    span.set_attribute("agent.feature", feature_name)
    response = run_agent(user_input)
    span.set_attribute("agent.final_output", response)
    return response
```

### Step 4: Wrap LLM, tool, and retrieval calls

Use a context-manager helper to keep call sites readable. Set the full payloads as attributes — do not summarize.

### Step 5: Verify coverage

Trigger one request through every endpoint listed in `context.md` Agent Surface Area. For each, confirm the resulting trace contains:
- A root `agent.request` span
- At least one `agent.llm.call` span
- A span for every tool call the request made
- Spans for any pre/post-processing in the code path

If a code path has no span, add one.

## Smoke-Test Checkpoint (required before signaling completion)

Run the agent end-to-end with one realistic input and pull the trace back from the configured backend. Show the user:
1. The full root span and its child tree
2. The `agent.user_input` and `agent.final_output` attributes
3. Token-by-token confirmation that no payload was truncated — pick the longest tool output in the trace and diff its length against what the code actually returned

If the trace backend is local file export (no observability vendor configured yet), dump the trace JSON to `evals/sample_trace.json` and walk through it with the user.

Do NOT mark this skill complete until the user confirms the trace matches what ran.

## Anti-Patterns

- Truncating large payloads to fit "neat" trace UIs. Eval pipelines need full context.
- Using unpinned model identifiers in `llm.model`.
- Wrapping only the top-level endpoint and assuming child calls are auto-traced. Tool calls and retrieval rarely auto-instrument in custom code.
- Sanitizing tool inputs/outputs into structured "trace-friendly" formats. Capture the raw bytes.
- Skipping pre/post-processing spans because they "feel internal." Many failures originate there.
- Marking the skill complete without the smoke-test checkpoint.
