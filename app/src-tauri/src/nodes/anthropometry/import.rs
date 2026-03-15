use std::fs;
use std::process::Command;

use crate::pipeline::error::PipelineError;
use crate::pipeline::types::RawData;
use crate::util;

/// Input to the body composition Import layer: a BIA PDF file plus optional user profile.
pub struct BodyCompositionInput {
    pub file_name: String,
    pub file_bytes: Vec<u8>,
    pub sex: Option<String>,
    pub age: Option<u32>,
    pub height_cm: Option<f64>,
}

/// Import a body composition PDF: save to temp, call run_body_composition.py for extraction.
pub fn import(input: BodyCompositionInput) -> Result<RawData, PipelineError> {
    let data = util::data_dir().map_err(PipelineError::Import)?;

    // Save PDF to temp location
    let tmp_dir = data.join("tmp");
    fs::create_dir_all(&tmp_dir)
        .map_err(|e| PipelineError::Import(format!("Failed to create tmp dir: {e}")))?;
    let pdf_path = tmp_dir.join(&input.file_name);
    fs::write(&pdf_path, &input.file_bytes)
        .map_err(|e| PipelineError::Import(format!("Failed to save PDF: {e}")))?;

    // Call Python extraction script
    let script =
        util::find_script("run_body_composition.py").map_err(PipelineError::Import)?;
    let python = util::find_venv_python(&script).map_err(PipelineError::Import)?;

    let mut cmd = Command::new(&python);
    cmd.arg(&script)
        .arg(pdf_path.to_str().unwrap_or_default())
        .arg("--output-dir")
        .arg(data.to_str().unwrap_or_default())
        .arg("--json-stdout");

    if let Some(ref sex) = input.sex {
        cmd.arg("--sex").arg(sex);
    }
    if let Some(age) = input.age {
        cmd.arg("--age").arg(age.to_string());
    }
    if let Some(height) = input.height_cm {
        cmd.arg("--height").arg(height.to_string());
    }

    let output = cmd.output().map_err(|e| {
        PipelineError::ExternalProcess(format!("Failed to run body composition script: {e}"))
    })?;

    // Clean up temp file
    let _ = fs::remove_file(&pdf_path);

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(PipelineError::ExternalProcess(format!(
            "Body composition extraction failed: {stderr}"
        )));
    }

    let json_str = String::from_utf8_lossy(&output.stdout).to_string();
    let content: serde_json::Value = serde_json::from_str(&json_str)
        .map_err(|e| PipelineError::Import(format!("Invalid JSON from extraction: {e}")))?;

    let file_hash = content
        .get("record")
        .and_then(|r| r.get("file_hash"))
        .and_then(|h| h.as_str())
        .map(String::from);

    let collection_date = content
        .get("record")
        .and_then(|r| r.get("test_date"))
        .and_then(|d| d.as_str())
        .map(String::from);

    Ok(RawData {
        source: pdf_path.to_string_lossy().to_string(),
        original_name: Some(input.file_name),
        file_hash,
        collection_date,
        content,
    })
}
