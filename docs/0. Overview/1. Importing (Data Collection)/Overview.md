### Importing (Data Collection)

The first layer of every node's pipeline. Importing defines how raw diagnostic data enters the system. Before any parsing, evaluation, or analysis can occur, a node must establish what data it accepts, what it rejects, and how that raw data is formatted for handoff to the next layer.

---

### What This Layer Defines

#### Each node must determine three things at the Importing stage:

**1. [Data Types](1.%20Determining%20Data%20Types.md)**
What diagnostic data and sub-mediums does this node accept? This requires research into the most common data formats for that domain, why they are the standard, and — for domains with multiple sub-mediums (e.g., radiology encompasses X-ray, MRI, CT) — which are included and how they are categorised.

**2. [Limitations](0.%20Overview/1.%20Importing%20(Data%20Collection)/2.%20Limitations.md)**
What data is explicitly not accepted and why. Defining boundaries early prevents scope creep and ensures the node's downstream layers (Evaluation, Insight) are only working with data they can reliably process.

**3. [Formatting Raw Data](3.%20Formatting%20Raw%20Data.md)**
How raw data is extracted and stored before it moves to Unifying. This is not transformation — it is preservation in a format the pipeline can work with. Critically, formatting decisions at this stage must account for what downstream layers need. How an image is stored impacts what machine learning can be applied to it. How a PDF is extracted impacts what the parser can resolve. Importing cannot be designed in isolation from Evaluation.

---

### Why This Matters

A node that accepts poorly defined input will produce unreliable output at every subsequent layer. Importing is the contract between the outside world and the node's internal pipeline — it must be precise, well-researched, and deliberately scoped.
