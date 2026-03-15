use crate::pipeline::error::PipelineError;
use crate::pipeline::types::OutputContract;
use std::fs;
use std::path::PathBuf;

/// Each node gets its own compartmentalised storage.
/// Nodes never read each other's storage. The Orchestrator
/// consumes OutputContracts only.
pub trait NodeStorage {
    /// Store an output contract in the node's own storage area.
    fn store_contract(&self, contract: &OutputContract) -> Result<(), PipelineError>;

    /// Retrieve a stored contract by source hash.
    fn load_contract(&self, source_hash: &str) -> Result<OutputContract, PipelineError>;

    /// List all stored contract hashes for this node.
    fn list_contracts(&self) -> Result<Vec<String>, PipelineError>;

    /// Delete a stored contract by source hash.
    fn delete_contract(&self, source_hash: &str) -> Result<(), PipelineError>;
}

/// File-system-backed storage. Each node gets a subdirectory
/// under the base data directory.
pub struct FsNodeStorage {
    /// e.g. ~/Documents/hOS/results/hepatology/
    node_dir: PathBuf,
}

impl FsNodeStorage {
    pub fn new(base_dir: &PathBuf, node_id: &str) -> Result<Self, PipelineError> {
        let node_dir = base_dir.join("results").join(node_id);
        fs::create_dir_all(&node_dir)?;
        Ok(Self { node_dir })
    }
}

impl NodeStorage for FsNodeStorage {
    fn store_contract(&self, contract: &OutputContract) -> Result<(), PipelineError> {
        let hash = contract
            .metadata
            .source_hash
            .as_deref()
            .unwrap_or("unknown");
        let path = self.node_dir.join(format!("{hash}.json"));
        let json = serde_json::to_string_pretty(contract)
            .map_err(|e| PipelineError::Storage(e.to_string()))?;
        fs::write(&path, json)?;
        Ok(())
    }

    fn load_contract(&self, source_hash: &str) -> Result<OutputContract, PipelineError> {
        let path = self.node_dir.join(format!("{source_hash}.json"));
        if !path.exists() {
            return Err(PipelineError::Storage(format!(
                "No contract found for hash {source_hash}"
            )));
        }
        let content = fs::read_to_string(&path)?;
        let contract: OutputContract = serde_json::from_str(&content)
            .map_err(|e| PipelineError::Storage(e.to_string()))?;
        Ok(contract)
    }

    fn list_contracts(&self) -> Result<Vec<String>, PipelineError> {
        let mut hashes = Vec::new();
        if !self.node_dir.exists() {
            return Ok(hashes);
        }
        let entries = fs::read_dir(&self.node_dir)?;
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().map_or(false, |ext| ext == "json") {
                if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
                    hashes.push(stem.to_string());
                }
            }
        }
        Ok(hashes)
    }

    fn delete_contract(&self, source_hash: &str) -> Result<(), PipelineError> {
        let path = self.node_dir.join(format!("{source_hash}.json"));
        if !path.exists() {
            return Err(PipelineError::Storage(format!(
                "No contract found for hash {source_hash}"
            )));
        }
        fs::remove_file(&path)?;
        Ok(())
    }
}
