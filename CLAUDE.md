# hOS

Local-first diagnostic interpretation desktop app. Tauri v2 + React + TypeScript frontend, Rust backend.

## Architecture Principles

1. **The Node trait is the contract, not the implementation.** It defines what data flows where and in what shape. It never dictates how a layer computes its output.

2. **Each layer uses whatever tool is objectively best for that specific operation.** The choice is justified per case, not defaulted by language preference. Python, Rust, ONNX, external API — whatever is demonstrably best.

3. **Every diagnostic tool must be proven or provable.** Established models must be validated and peer-reviewed. Custom-built tools must be demonstrably reproducible. This is a regulatory requirement — the goal is TGA/FDA approval as an actual medical tool.

4. **Reproducibility over determinism.** Same input + same model version = same output. This applies whether the engine is a rule-based check or a transformer model. The diagnostic pathway must be fully auditable.

5. **Compartmentalised storage.** Each node owns its storage. The Orchestrator consumes output contracts only, never reads node storage directly.

6. **The Orchestrator is a node.** Same trait, same pipeline. Its Import layer ingests output contracts instead of raw files.

7. **Output contracts are comprehensive.** The contract is the Orchestrator's only data source. All outputs include versioning and metadata sufficient for audit.

8. **No silent data loss.** Failed validation goes to a resolution interface, not silently discarded.

9. **Insight layer is deferred.** LLM-based contextualisation is a future feature, pending regulatory clarity on frontier models in clinical tools. Do not implement or stub.

## Implementation Constraints

- `lib.rs` is the Tauri entry point only — registers plugins, commands, starts the app. No business logic.
- External process delegation (Python, etc.) lives inside specific node layer implementations, never in top-level wiring.
- All stubs must compile and return placeholder data, never panic.
- `Result` for all fallible operations, no `.unwrap()` in production paths.
- Serde derive on all types that cross the Rust–frontend boundary (required by Tauri's JSON IPC).

## Project Structure

- `app/` — All application code (Tauri + React)
- `app/src/` — React frontend
- `app/src-tauri/` — Rust backend
- `data/` — Python scripts and ML models (reference implementations, called from node layers)
- `docs/` — Architecture and design documentation
