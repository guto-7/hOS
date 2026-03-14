### Pipeline (Data Feed)

The fifth layer of every node's pipeline. Pipeline defines what data leaves the node, where it goes, and how it gets there. Every layer before this — Importing, Unifying, Evaluation, Insight — produces data. Pipeline is responsible for packaging and routing that data to its consumers: the node's own frontend and the Orchestrator.

---

### What This Layer Defines

#### Each node must define four things at the Pipeline stage:

**1. [Data Storage](1.%20Data%20Storage.md)**
Where and how each node's data is stored. All node data — unified, evaluated, and insight artifacts — is compartmentalised to that node. Nodes do not share storage. The Orchestrator does not read from node storage directly — it consumes the output contract. This isolation ensures scalability, clean migrations, and full modularity.

**2. [Node Output Contract](2.%20Node%20Output%20Contract.md)**
The standardised structure that all pipeline output must follow. This is the schema that makes everything downstream possible — a defined shape with required fields, metadata, and versioning that every output conforms to regardless of where it is sent. Without a consistent contract, neither the frontend nor the Orchestrator can reliably consume node output.

**3. [Frontend Data Feed](3.%20Frontend%20Data%20Feed.md)**
What data is sent to the node's own dashboard and chat, and how. This covers how evaluation outputs — general analysis, domain scores, condition mappings, certainty grades, incompleteness disclosures — are structured and formatted for rendering. The frontend feed serves the user's direct interaction with their data within a single diagnostic domain.

**4. [Orchestrator Data Feed](4.%20Orchestrator%20Data%20Feed.md)**
What data is sent up to the Orchestrator, and how. This covers how node output is packaged for cross-diagnostic consumption — the structured contract that the Orchestrator ingests as its own Import layer. The Orchestrator feed must be consistent enough across all nodes that the Orchestrator can process any node's output without node-specific parsing logic.

---

## How This Layer Evolves

Pipeline is directly shaped by what the Evaluation layer produces. As Evaluation grows — new conditions, new domain scores, new analysis engines — the output contract and data feeds must grow with it. This layer will evolve as the system matures, and its definitions should be treated as living documents that are updated alongside Evaluation changes.

---

### Why This Matters

Pipeline is the bridge between analysis and action. If data is evaluated but never reaches the user or the Orchestrator in a usable format, the evaluation has no impact. If the format is inconsistent or poorly defined, downstream consumers break as the system scales. This layer ensures that every piece of diagnostic output has a defined path from where it is produced to where it is consumed.
