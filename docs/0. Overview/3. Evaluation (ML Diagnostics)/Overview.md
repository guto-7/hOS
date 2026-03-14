### Evaluation (Diagnostics)

The third layer of every node's pipeline. Evaluation is where standardised, validated, and flagged data becomes diagnostic insight. This is the core analytical layer — all analysis here is deterministic. The same input will always produce the same output, making it testable, auditable, and independent of any external model provider.

---

### The Deterministic Principle

Every evaluation in this layer must be reproducible. Rule engines, decision trees, scoring algorithms, classical machine learning — the computational method varies by what is being evaluated, but the requirement is constant: no probabilistic inference, no LLM involvement. Each file in this layer must document not only *what* is being evaluated but *how* — the diagnostic method, the machine learning pathway, and the clinical research that supports it.

This is what makes hOS legally defensible. The diagnostics produced here are based on established clinical criteria that can be tested and approved by medical bodies. This layer is the product — everything else supports it.

---

#### Modular Analysis Engines

Each node selects its own computational methods for evaluation — rule engines, decision trees, scoring algorithms, classical ML classifiers, or any combination. There is no single mandated approach. A blood work node may use threshold-based rule engines for condition mapping while the imaging node uses trained classifiers for structural analysis. The Orchestrator, dealing with cross-diagnostic data at scale, may require entirely different methods again.

This is by design. The pipeline architecture (Importing → Unifying → Evaluation → Insight → Pipeline) is fixed. The analytical engines within Evaluation are not. They are modular and replaceable — scoped to the node, documented alongside the evaluations they serve, and independent of each other.

This allows the system to grow in two directions:

- **Depth** — as a node's domain scope expands (more conditions, more data points, finer evaluation criteria), its analysis engines can be extended or upgraded without restructuring the pipeline or affecting other nodes.
- **Breadth** — as the clinical field itself evolves (new diagnostic methods, new validated scoring systems, better algorithms), engines can be swapped for improved versions. The input contract (standardised data from Unifying) and the output contract (structured findings to Pipeline) remain the same — only the engine changes.

The only constraint is the deterministic principle: whatever method is used, same input must produce same output.

---

### What This Layer Defines

#### Each node must define four things at the Evaluation stage:

**1. [General Analysis](1.%20General%20Analysis.md)**
The first pass over the data. Surface critically flagged individual data points that demand immediate attention, then group all data points into domain-specific categories (e.g., hormonal, metabolic, lipid panels for blood work). These groupings must be researched and defined for each node's medium — they structure how the user sees their data and how downstream evaluations are organised.

**2. [Domain Analysis](2.%20Domain%20Analysis.md)**
Holistic assessment of the diagnostic medium as a whole. Composite metrics derived from multiple data points that give a high-level read on overall status — longevity scores, metabolic health indices, inflammatory burden, and similar. Every metric must be backed by validated, evidence-based scoring systems and documented research. No invented metrics.

**3. [Condition Mapping](3.%20Condition%20Mapping.md)**
Multi-variable pattern recognition. Specific combinations of data points that indicate clinical conditions. Each condition is a defined set of criteria — not a single flag but a pattern across multiple values. The criteria, the computational method for detecting them, and the clinical literature supporting them must all be documented.

**4. [Diagnostic Certainty](4.%20Diagnostic%20Certainty.md)**
Not every evaluation has complete data. When a condition requires five data points and only three are present, the system must quantify how strong that signal is. Diagnostic certainty defines how partial evidence is graded and communicated — ensuring the user and the Insight layer both understand the strength of any finding.

---

### Why This Matters

This layer is the reason the pipeline exists. Everything before it — Importing, Unifying — prepares data for this stage. Everything after it — Insight, Pipeline — contextualises and distributes what this stage produces. If Evaluation is unreliable, the entire system is unreliable. If Evaluation is sound, the system delivers genuine diagnostic value regardless of whether an LLM is involved at all.
