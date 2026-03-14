pub mod error;
pub mod storage;
pub mod types;

use error::PipelineError;
use types::{OutputContract, RawData};

/// The Node trait defines the 4-layer pipeline contract.
/// (Insight layer is deferred — not part of the trait.)
///
/// Each layer's implementation uses whatever tool is best for the job.
/// The trait defines what data flows where and in what shape,
/// not how each layer computes its output.
pub trait Node {
    /// Node-specific input to the Import layer.
    /// Bloodwork: file bytes + name. Imaging: file bytes + modality. Etc.
    type ImportInput;

    /// Node-specific unified data structure.
    /// Bloodwork: parsed markers. Imaging: normalised scan metadata. Etc.
    type UnifiedData;

    /// Unique identifier for this node (e.g. "bloodwork").
    fn node_id(&self) -> &str;

    /// Layer 1: Import — ingest raw data, extract collection date,
    /// validate format, produce RawData for the next layer.
    fn import(&self, input: Self::ImportInput) -> Result<RawData, PipelineError>;

    /// Layer 2: Unify — map to canonical identifiers, convert units,
    /// validate, apply initial flagging with deviation metrics.
    fn unify(&self, raw: &RawData) -> Result<Self::UnifiedData, PipelineError>;

    /// Layer 3: Evaluate — analysis engines, scoring systems,
    /// condition mapping, certainty grading. Every tool used here
    /// must be proven or provable for regulatory compliance.
    fn evaluate(&self, data: &Self::UnifiedData) -> Result<types::EvaluationOutput, PipelineError>;

    /// Layer 4: Pipeline — assemble the output contract, store results,
    /// route data to frontend and Orchestrator.
    fn output(
        &self,
        raw: &RawData,
        data: &Self::UnifiedData,
        evaluation: &types::EvaluationOutput,
    ) -> Result<OutputContract, PipelineError>;
}

/// Run the full pipeline for a node. This is the standard execution path.
pub fn run_pipeline<N: Node>(
    node: &N,
    input: N::ImportInput,
) -> Result<OutputContract, PipelineError> {
    let raw = node.import(input)?;
    let unified = node.unify(&raw)?;
    let evaluation = node.evaluate(&unified)?;
    node.output(&raw, &unified, &evaluation)
}
