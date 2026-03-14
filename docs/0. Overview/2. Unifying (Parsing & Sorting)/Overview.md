### Unifying (Parsing & Sorting)

The second layer of every node's pipeline. Unifying takes the raw formatted data from Importing and transforms it into a structured, standardised, and validated internal representation. This is where raw input becomes trusted data — mapped to canonical identifiers, converted to standardised units, checked for integrity, and annotated with surface-level flags.

---

### What This Layer Defines

#### Each node must determine three things at the Unifying stage:

**1. [Standardised Data Format](1.%20Standardised%20Data%20Format.md)**
How the node's data is represented internally. This includes the storage schema, canonical identifiers that raw data maps to (resolving aliases across providers), and unit conversion to a single standardised unit system. Every node must define what its internal data model looks like — this is the structure everything downstream reads from.

**2. [Validation](2.%20Validation.md)**
Integrity checks applied to parsed data before it enters the standardised store. Importing rejects bad files — Validation catches bad data. Physically impossible values, incomplete records, and extraction artifacts are identified here. Data that fails validation does not proceed to flagging or evaluation.

**3. [Initial Flagging](3.%20Initial%20Flagging.md)**
Surface-level annotation of individual data points against known references. For blood work, this is comparing a marker value to its reference range. For imaging, this is comparing a measurement to established anatomical norms. This is not diagnostic analysis — it is per-value annotation. The distinction from Evaluation (Layer 3): this layer flags individual values against their own reference; Evaluation detects patterns across multiple values.

---

### Why This Matters

The Unifying layer is the trust boundary. Everything before it is raw and unverified. Everything after it — Evaluation, Insight, the Orchestrator — assumes the data is correctly parsed, validated, and consistently structured. If this layer is unreliable, every downstream conclusion is unreliable.
