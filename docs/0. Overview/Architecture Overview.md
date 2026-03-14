### Architecture Overview

hOS is a local-first diagnostic interpretation platform. Each diagnostic domain operates as an independent **node** — a self-contained pipeline that ingests raw data, produces deterministic evaluations, and feeds both its own frontend and the system-wide Medical Orchestrator.

---

### The Node Model

Every node — including the Orchestrator — shares the same 5-layer pipeline:

**Importing → Unifying → Evaluation → Insight → Pipeline**

Each layer is documented in its own folder under `0. Overview/`.

| Layer | Purpose |
|-------|---------|
| [1. Importing (Data Collection)](1.%20Importing%20(Data%20Collection)) | Ingest raw data from the node's diagnostic medium (PDFs, imaging, measurements, or — for the Orchestrator — structured outputs from other nodes). |
| [2. Unifying (Parsing & Sorting)](2.%20Unifying%20(Parsing%20&%20Sorting)) | Normalize and map raw input to canonical, structured data. |
| [3. Evaluation (Diagnostics)](3.%20Evaluation%20(Diagnostics)) | Deterministic analysis against known clinical criteria. This is the core diagnostic layer — no LLM involvement. |
| [4. Insight (LLM)](4.%20Insight%20(LLM)) | Contextualises deterministic results using a domain-specific LLM skill (system prompt + curated RAG). Cannot override Evaluation output. |
| [5. Pipeline (Data Feed)](5.%20Pipeline%20(Data%20feed)) | Routes structured output to the node's own UI and up to the Orchestrator. |

---

### Data Flow

Each diagnostic node sends its Pipeline output in two directions:

- **To its own frontend** — full evaluated data for that domain's dashboard and chat.
- **Up to the Orchestrator** — a structured output contract consumed as the Orchestrator's import layer.

The Orchestrator runs the same 5-layer pipeline, but its Evaluation layer performs **cross-diagnostic analysis** — how findings from one domain interact with findings from another, producing a systemic view.

```
Blood Work Node    ──→  own UI  +  ──→  Orchestrator Import
Imaging Node       ──→  own UI  +  ──→  Orchestrator Import
Body Comp Node     ──→  own UI  +  ──→  Orchestrator Import
                                              │
                                     Unify → Evaluate → Insight → Pipeline
                                              │
                                     Orchestrator UI (systemic overview)
```

---

### Frontend

Each node owns its own **data dashboard** and **chat interface**, providing deep diagnostic detail for that domain. The Orchestrator's frontend provides the general overview and systemic interactions.

Nodes are traversed via the **diagnostic tree** in the navigation console. This keeps each domain self-contained while allowing the user to move between them. Adding a new diagnostic medium means adding a new node to the tree — no restructuring required.

---

### Current Nodes

| Node | Domain | Detailed in |
|------|--------|-------------|
| Medical Orchestrator | Cross-diagnostic systemic analysis | [0. Medical Orchestrator](../2.%20Nodes/0.%20Medical%20Orchestrator) |
| Hepatology | Blood work interpretation | [1. Hepatology (Blood Work)](../2.%20Nodes/1.%20Hepatology%20(Blood%20Work)) |
| Radiology | Medical imaging interpretation | [2. Radiology (Imaging)](../2.%20Nodes/2.%20Radiology%20(Imaging)) |
| Anthropometry | Body composition analysis | [3. Anthropometry (Body Composition)](../2.%20Nodes/3.%20Anthropometry%20(Body%20Compisition)) |
