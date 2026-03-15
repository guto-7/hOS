pub mod evaluate;
pub mod import;
pub mod pipeline;
pub mod unify;

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{EvaluationOutput, OutputContract, RawData};
use crate::pipeline::Node;

use import::AnthropometryInput;
use unify::AnthropometryData;

pub struct AnthropometryNode;

impl Node for AnthropometryNode {
    type ImportInput = AnthropometryInput;
    type UnifiedData = AnthropometryData;

    fn node_id(&self) -> &str {
        "anthropometry"
    }

    fn import(&self, input: AnthropometryInput) -> Result<RawData, PipelineError> {
        import::import(input)
    }

    fn unify(&self, raw: &RawData) -> Result<AnthropometryData, PipelineError> {
        unify::unify(raw)
    }

    fn evaluate(&self, data: &AnthropometryData) -> Result<EvaluationOutput, PipelineError> {
        evaluate::evaluate(data)
    }

    fn output(
        &self,
        raw: &RawData,
        data: &AnthropometryData,
        evaluation: &EvaluationOutput,
    ) -> Result<OutputContract, PipelineError> {
        pipeline::build_output(raw, data, evaluation)
    }
}
