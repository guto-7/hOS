use serde::Serialize;
use std::fmt;

/// All errors that can occur within the node pipeline.
#[derive(Debug, Serialize)]
pub enum PipelineError {
    /// File not found, unreadable, or invalid format.
    Import(String),
    /// Parsing, unit conversion, or validation failure.
    Unify(String),
    /// Analysis engine failure (rule engine, model inference, etc.).
    Evaluate(String),
    /// Output contract assembly or storage failure.
    Pipeline(String),
    /// External process (Python, ONNX runtime, API call) failed.
    ExternalProcess(String),
    /// Storage read/write failure.
    Storage(String),
}

impl fmt::Display for PipelineError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            PipelineError::Import(msg) => write!(f, "Import error: {msg}"),
            PipelineError::Unify(msg) => write!(f, "Unify error: {msg}"),
            PipelineError::Evaluate(msg) => write!(f, "Evaluate error: {msg}"),
            PipelineError::Pipeline(msg) => write!(f, "Pipeline error: {msg}"),
            PipelineError::ExternalProcess(msg) => write!(f, "External process error: {msg}"),
            PipelineError::Storage(msg) => write!(f, "Storage error: {msg}"),
        }
    }
}

impl std::error::Error for PipelineError {}

impl From<std::io::Error> for PipelineError {
    fn from(e: std::io::Error) -> Self {
        PipelineError::Storage(e.to_string())
    }
}
