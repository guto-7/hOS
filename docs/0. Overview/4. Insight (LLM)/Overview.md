### Insight (LLM)

The fourth layer of every node's pipeline. Insight contextualises the deterministic findings from Evaluation using a domain-specific LLM skill. It receives structured data — it does not feed back into the Evaluation layer. The LLM adds explanation, context, and conversational access to findings. It cannot override, modify, or influence diagnostic output.

---

### Role

Each node's Insight layer operates with a domain-specific skill — a system prompt tailored to that diagnostic medium combined with curated RAG (retrieval-augmented generation) sourced exclusively from domain-specific, evidence-based sources. No general-purpose web search. No unvetted content.

The Insight layer receives:
- Standardised data from Unifying (Layer 2)
- Evaluated findings, domain scores, condition mappings, and certainty grades from Evaluation (Layer 3)

It produces:
- Contextualised explanations of findings for the node's dashboard
- Conversational responses through the node's chat interface

---

### Boundaries

- **Cannot override Evaluation.** If the deterministic layer says iron is low, the Insight layer does not contradict that. It explains what low iron means, what the pattern suggests, and what the user might consider — but the finding itself is untouchable.
- **Cannot write back to the pipeline.** Insight is a consumer of pipeline data, not a producer. Data flows in one direction — from Evaluation to Insight. Nothing the LLM generates enters the Evaluation layer or alters stored diagnostic data.
- **Domain-scoped.** Each node's Insight skill is specific to its diagnostic medium. A blood work node's LLM does not contextualise imaging findings. Cross-domain contextualisation is handled by the Orchestrator's own Insight layer.

---

### Chat Interface

Each node provides its own chat interface where the user can ask questions about their data and findings within that domain. The Orchestrator's chat handles cross-domain and systemic questions.

Chat context is managed per node — conversations are scoped to the domain's data and findings, not shared across nodes.

---

## Future: Context Extraction Engine

> *This is an additional feature planned for future development. It is not part of the initial core product.*

The long-term vision is to extract meaningful, structured data back out of LLM conversations — insights surfaced during chat that have diagnostic value (user-reported symptoms, clarifications about medical history, patterns identified during contextualisation).

The challenge is that raw LLM output is unstructured and unreliable. It cannot be piped directly into a deterministic pipeline. The solution is a dedicated context management system:

- **Manual extraction** — the user can flag or isolate insights from conversations.
- **Automatic extraction** — custom algorithms that structure conversation context, independent of the LLM's own context management.
- **Knowledge graph storage** — conversations are broken into subthreads, tracked in a tree structure. Summarisation engines extract discrete insights. Information is isolated, typed, and traceable.

**This engine is completely isolated from the Evaluation layer.** It does not feed into Evaluation. It operates as a separate stream within the Orchestrator's pipeline — it has access to the same data as Evaluation but is encapsulated on its own. It takes in pipeline data but does not plumb back. Extracted insights are stored and surfaced independently, never mixed with deterministic diagnostic output.

This separation ensures that the deterministic principle is never compromised — even as the system gains the ability to capture useful information from conversational context.
