pub mod evaluate;
pub mod import;
pub mod pipeline;
pub mod scoring;
pub mod unify;

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{EvaluationOutput, OutputContract, RawData};
use crate::pipeline::Node;

use import::HepatologyInput;
use unify::HepatologyData;

pub struct HepatologyNode;

impl Node for HepatologyNode {
    type ImportInput = HepatologyInput;
    type UnifiedData = HepatologyData;

    fn node_id(&self) -> &str {
        "hepatology"
    }

    fn import(&self, input: HepatologyInput) -> Result<RawData, PipelineError> {
        import::import(input)
    }

    fn unify(&self, raw: &RawData) -> Result<HepatologyData, PipelineError> {
        unify::unify(raw)
    }

    fn evaluate(&self, data: &HepatologyData) -> Result<EvaluationOutput, PipelineError> {
        evaluate::evaluate(data)
    }

    fn output(
        &self,
        raw: &RawData,
        data: &HepatologyData,
        evaluation: &EvaluationOutput,
    ) -> Result<OutputContract, PipelineError> {
        pipeline::build_output(raw, data, evaluation)
    }
}
