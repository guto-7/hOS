# Anthropometry — Stage 1: Importing

## Purpose

Stage 1 is responsible for getting body composition measurements into the system.

Unlike bloodwork (PDF upload → text extraction) and radiology (image upload → pixel processing), anthropometry has no file to parse. The input method and data types for this node have not yet been defined.

---

## Current State

**Rust stub** (`nodes/anthropometry/mod.rs`):
```rust
pub struct AnthropometryInput {
    pub measurements: serde_json::Value,
}
```

The import layer accepts raw JSON and passes it through as `RawData` with source `"anthropometry-manual"`. No validation, no hashing, no storage of a raw input file.

**Frontend** (`AnthropometryContent.tsx`):
Placeholder paragraph only. No data entry UI exists.

---

## Open Decisions

These must be resolved before Stage 1 can be implemented:

- [ ] **Input method** — How does data enter the system? (manual form, file upload, device sync, etc.)
- [ ] **Accepted data types** — What measurements does this node handle?
- [ ] **Required vs optional fields** — What is the minimum viable input?
- [ ] **Unit handling** — What units are accepted? Is conversion needed?
- [ ] **Validation rules** — What plausibility checks apply? (per [Validation](../../../0.%20Overview/2.%20Unifying%20(Parsing%20%26%20Sorting)/2.%20Validation.md) framework)
- [ ] **Storage** — Is a raw input stored separately (like bloodwork PDFs / radiology images), or is the output contract sufficient?
- [ ] **Deduplication** — How is a hash generated without a source file?
- [ ] **User confirmation** — Is a confirmation step needed before processing?
- [ ] **Tauri command signatures** — What commands does the frontend invoke?

---

## Context from Overview Docs

The following is documented at the overview architecture level and should inform these decisions:

- **Validation** (`docs/0. Overview/2. Unifying/2. Validation.md`): Plausibility checks with hard biological/physical limits. Completeness — minimum required fields for a record to proceed. Consistency — cross-check relationships between measurements.
- **Initial Flagging** (`docs/0. Overview/2. Unifying/3. Initial Flagging.md`): Body composition metrics checked against population-based standards. Demographic adjustments required (age, sex, ethnicity).
- **Condition Mapping** (`docs/0. Overview/3. Evaluation/3. Condition Mapping.md`): Conditions requiring both body composition AND blood markers (e.g. metabolic syndrome) are the Orchestrator's responsibility, not this node's.
