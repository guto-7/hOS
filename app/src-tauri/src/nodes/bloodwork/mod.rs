pub mod evaluate;
pub mod import;
pub mod pipeline;
pub mod scoring;
pub mod unify;

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{EvaluationOutput, OutputContract, RawData};
use crate::pipeline::Node;

use import::BloodworkInput;
use unify::BloodworkData;

pub struct BloodworkNode;

impl Node for BloodworkNode {
    type ImportInput = BloodworkInput;
    type UnifiedData = BloodworkData;

    fn node_id(&self) -> &str {
        "bloodwork"
    }

    fn import(&self, input: BloodworkInput) -> Result<RawData, PipelineError> {
        import::import(input)
    }

    fn unify(&self, raw: &RawData) -> Result<BloodworkData, PipelineError> {
        unify::unify(raw)
    }

    fn evaluate(&self, data: &BloodworkData) -> Result<EvaluationOutput, PipelineError> {
        evaluate::evaluate(data)
    }

    fn output(
        &self,
        raw: &RawData,
        data: &BloodworkData,
        evaluation: &EvaluationOutput,
    ) -> Result<OutputContract, PipelineError> {
        pipeline::build_output(raw, data, evaluation)
    }
}
