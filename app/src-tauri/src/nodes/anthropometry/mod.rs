pub mod evaluate;
pub mod import;
pub mod pipeline;
pub mod unify;

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{EvaluationOutput, OutputContract, RawData};
use crate::pipeline::Node;

use import::BodyCompositionInput;
use unify::BodyCompositionData;

pub struct AnthropometryNode;

impl Node for AnthropometryNode {
    type ImportInput = BodyCompositionInput;
    type UnifiedData = BodyCompositionData;

    fn node_id(&self) -> &str {
        "anthropometry"
    }

    fn import(&self, input: BodyCompositionInput) -> Result<RawData, PipelineError> {
        import::import(input)
    }

    fn unify(&self, raw: &RawData) -> Result<BodyCompositionData, PipelineError> {
        unify::unify(raw)
    }

    fn evaluate(&self, data: &BodyCompositionData) -> Result<EvaluationOutput, PipelineError> {
        evaluate::evaluate(data)
    }

    fn output(
        &self,
        raw: &RawData,
        data: &BodyCompositionData,
        evaluation: &EvaluationOutput,
    ) -> Result<OutputContract, PipelineError> {
        pipeline::build_output(raw, data, evaluation)
    }
}
