## ML Infrastructure — Local vs Server

---

### Hackathon

Keep everything local. Rule engines and threshold-based evaluation run directly in Rust. No external dependencies, no server infrastructure.

---

### Production — Hybrid Approach

##### Local (on-device)

- **Rule engines, decision trees, scoring algorithms, condition mapping, flagging** — lightweight, deterministic, fast. These are the core diagnostics and stay on-device.
- **Privacy** — blood work, imaging, body composition is sensitive medical data. Local-first means user data never leaves their machine for core diagnostics.
- **Regulatory** — core diagnostics (the systems targeting TGA → FDA approval) must be deterministic and local. This is the legal and regulatory advantage.

##### Server-side (our infrastructure)

- **Trained ML models** — image classifiers, complex pattern recognition models that are too large to bundle in a desktop app (hundreds of MB to GB).
- **Model updates** — retraining or improving a classifier deploys as a server-side update, not a full app release.
- **GPU inference** — imaging and other compute-heavy models benefit from GPU that a user's machine may not have.
- **Stateless inference only** — the node sends structured input, gets structured output. No user data is stored server-side. The model sees data for inference only, nothing persists.

##### Offline Fallback

- If the server is unavailable, the local pipeline still runs everything it can. Server-dependent ML evaluations are marked as unavailable rather than the whole system breaking.
- The local-first promise stays intact — the app is always functional for core diagnostics.

---

### How This Fits the Architecture

The [Data Routing](../../0.%20Overview/3.%20Evaluation%20(ML%20Diagnostics)/0.%20Data%20Routing.md) layer handles this transparently. It transforms data into the right format and sends it to the right engine — whether that engine is local or remote. Swapping a local model for a server-side one is a routing change, not an architecture change.

**Core deterministic evaluation = local.** Server-side ML is supplementary — enhances but does not replace the core. Clean separation.
