pub mod evaluate;
pub mod import;
pub mod pipeline;
pub mod unify;

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::{EvaluationOutput, OutputContract, RawData};
use crate::pipeline::Node;

use import::RadiologyInput;
use unify::RadiologyData;

pub struct RadiologyNode;

impl Node for RadiologyNode {
    type ImportInput = RadiologyInput;
    type UnifiedData = RadiologyData;

    fn node_id(&self) -> &str {
        "radiology"
    }

    fn import(&self, input: RadiologyInput) -> Result<RawData, PipelineError> {
        import::import(input)
    }

    fn unify(&self, raw: &RawData) -> Result<RadiologyData, PipelineError> {
        unify::unify(raw)
    }

    fn evaluate(&self, data: &RadiologyData) -> Result<EvaluationOutput, PipelineError> {
        evaluate::evaluate(data)
    }

    fn output(
        &self,
        raw: &RawData,
        data: &RadiologyData,
        evaluation: &EvaluationOutput,
    ) -> Result<OutputContract, PipelineError> {
        pipeline::build_output(raw, data, evaluation)
    }
}
