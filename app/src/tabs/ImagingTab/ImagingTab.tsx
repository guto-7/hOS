import { useRef, useState, useCallback, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import ReactMarkdown from "react-markdown";
import styles from "./ImagingTab.module.css";

/* ── Types ─────────────────────────────────────────────────────── */

interface Finding {
  pathology: string;
  probability: number;
  level: "HIGH" | "MODERATE" | "LOW" | "MINIMAL";
  bbox?: { x1: number; y1: number; x2: number; y2: number };
  size?: { width_px: number; height_px: number; area_px: number; area_pct: number; width_mm?: number; height_mm?: number; pixel_spacing_mm?: number };
}

interface ExtractionResult {
  success: boolean;
  stage: string;
  record: {
    file_hash: string;
    stored_path: string;
    original_name: string;
    is_duplicate: boolean;
  };
  image_metadata: {
    width: number;
    height: number;
    channels: number;
    bit_depth: number;
    format: string;
    file_size_kb: number;
    is_grayscale: boolean;
    has_exif: boolean;
    orientation: number | null;
    warnings: string[];
  };
  quality: {
    warnings: string[];
    warning_count: number;
  };
}

interface AnalysisResult {
  success: boolean;
  record: {
    file_hash: string;
    stored_path: string;
    original_name: string;
    is_duplicate: boolean;
  };
  image_metadata: {
    width: number;
    height: number;
    channels: number;
    bit_depth: number;
    format: string;
    file_size_kb: number;
    is_grayscale: boolean;
  };
  model: string;
  findings: Finding[];
  summary: {
    high_probability: string[];
    moderate_probability: string[];
    total_pathologies_screened: number;
    flagged_count: number;
  };
  heatmap?: string;
  heatmap_pathology?: string;
  interpretation?: string;
}

interface HistoryRecord {
  file_hash: string;
  original_name: string;
  width: number | null;
  height: number | null;
  format: string | null;
  flagged_count: number | null;
  total_screened: number | null;
}

type Status = "loading" | "idle" | "selecting" | "extracting" | "confirming" | "processing" | "done" | "error";

const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/webp", "image/tiff"];

type ModelKey = "chest-xray" | "fracture";

const MODELS: { key: ModelKey; label: string; description: string }[] = [
  { key: "chest-xray", label: "Chest X-ray", description: "18 pathology screening (TorchXRayVision)" },
  { key: "fracture", label: "Fracture Detection", description: "Object detection with bounding boxes (YOLOv8)" },
];

/* ── Component ─────────────────────────────────────────────────── */

function ImagingTab() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [status, setStatus] = useState<Status>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null);
  const [currentFile, setCurrentFile] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [fileBytes, setFileBytes] = useState<number[] | null>(null);
  const [history, setHistory] = useState<HistoryRecord[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [activeHash, setActiveHash] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<ModelKey>("chest-xray");
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [interpretation, setInterpretation] = useState<string | null>(null);
  const [interpretationLoading, setInterpretationLoading] = useState(false);
  const [interpretationError, setInterpretationError] = useState<string | null>(null);

  /* ── History ──────────────────────────────────────────────────── */

  const loadHistory = useCallback(async () => {
    try {
      const json = await invoke<string>("list_imaging_results");
      const records: HistoryRecord[] = JSON.parse(json);
      setHistory(records);
      return records;
    } catch {
      return [];
    }
  }, []);

  const fetchInterpretation = useCallback(async (hash: string) => {
    setInterpretation(null);
    setInterpretationError(null);
    setInterpretationLoading(true);
    try {
      const json = await invoke<string>("interpret_image", { fileHash: hash });
      const parsed = JSON.parse(json);
      if (parsed.success) {
        setInterpretation(parsed.interpretation);
      } else {
        setInterpretationError(parsed.error || "Interpretation failed");
      }
    } catch (err) {
      setInterpretationError(String(err));
    } finally {
      setInterpretationLoading(false);
    }
  }, []);

  const loadResult = useCallback(async (hash: string) => {
    try {
      const json = await invoke<string>("load_imaging_result", { fileHash: hash });
      const parsed: AnalysisResult = JSON.parse(json);
      setResult(parsed);
      setCurrentFile(parsed.record.original_name);
      setActiveHash(hash);
      setPreviewUrl(null);
      setShowHeatmap(true);
      setStatus("done");
      // Load saved interpretation or fetch new one
      if (parsed.interpretation) {
        setInterpretation(parsed.interpretation);
        setInterpretationError(null);
        setInterpretationLoading(false);
      } else {
        fetchInterpretation(hash);
      }
    } catch (err) {
      setErrorMsg(String(err));
      setStatus("error");
    }
  }, [fetchInterpretation]);

  useEffect(() => {
    (async () => {
      const records = await loadHistory();
      if (records.length > 0) {
        await loadResult(records[0].file_hash);
      } else {
        setStatus("idle");
      }
    })();
  }, []);

  /* ── File handling ───────────────────────────────────────────── */

  const extractFile = useCallback(async (file: File) => {
    setStatus("extracting");
    setErrorMsg("");
    setCurrentFile(file.name);
    setResult(null);
    setExtraction(null);

    const url = URL.createObjectURL(file);
    setPreviewUrl(url);

    try {
      const arrayBuffer = await file.arrayBuffer();
      const bytes = Array.from(new Uint8Array(arrayBuffer));
      setFileBytes(bytes);

      const jsonString = await invoke<string>("extract_image", {
        fileName: file.name,
        fileBytes: bytes,
      });

      const parsed: ExtractionResult = JSON.parse(jsonString);
      if (!parsed.success) {
        setErrorMsg((parsed as any).error || "Extraction failed");
        setStatus("error");
        return;
      }
      setExtraction(parsed);
      setStatus("confirming");
    } catch (err) {
      setErrorMsg(String(err));
      setStatus("error");
    }
  }, []);

  const confirmAndProcess = useCallback(async () => {
    if (!fileBytes) return;
    setStatus("processing");

    try {
      const jsonString = await invoke<string>("process_image", {
        fileName: currentFile,
        fileBytes: fileBytes,
        model: selectedModel,
      });

      const parsed: AnalysisResult = JSON.parse(jsonString);
      setResult(parsed);
      setActiveHash(parsed.record.file_hash);
      setStatus("done");
      setFileBytes(null);
      await loadHistory();
      // Fire off interpretation async (non-blocking)
      fetchInterpretation(parsed.record.file_hash);
    } catch (err) {
      setErrorMsg(String(err));
      setStatus("error");
    }
  }, [fileBytes, currentFile, selectedModel, loadHistory, fetchInterpretation]);

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      const file = files[0];
      if (
        ACCEPTED_TYPES.includes(file.type) ||
        /\.(png|jpe?g|webp|tiff?)$/i.test(file.name)
      ) {
        extractFile(file);
      }
    },
    [extractFile]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleClick = () => fileInputRef.current?.click();

  const reset = () => {
    setStatus("idle");
    setResult(null);
    setExtraction(null);
    setErrorMsg("");
    setCurrentFile("");
    setFileBytes(null);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    setShowHistory(false);
    setInterpretation(null);
    setInterpretationLoading(false);
    setInterpretationError(null);
  };

  /* ── Helpers ─────────────────────────────────────────────────── */

  const levelClass = (level: string) => {
    switch (level) {
      case "HIGH": return styles.levelHigh;
      case "MODERATE": return styles.levelModerate;
      case "LOW": return styles.levelLow;
      default: return styles.levelMinimal;
    }
  };

  const barClass = (level: string) => {
    switch (level) {
      case "HIGH": return styles.probBarHigh;
      case "MODERATE": return styles.probBarModerate;
      case "LOW": return styles.probBarLow;
      default: return styles.probBarMinimal;
    }
  };

  /* ── Render ──────────────────────────────────────────────────── */

  return (
    <div className={styles.tab}>
      <h1 className={styles.heading}>Imaging</h1>
      <p className={styles.description}>
        Upload a medical image for AI-powered analysis.
        Stage 1 validates and stores your image, Stage 2 standardises it,
        then your chosen model runs inference.
      </p>

      {/* ── Loading ──────────────────────────────────────────── */}
      {status === "loading" && (
        <div className={styles.statusCard}>
          <p className={styles.statusText}>Loading...</p>
        </div>
      )}

      {/* ── Idle: model selection cards ────────────────────── */}
      {status === "idle" && (
        <>
          {history.length > 0 && (
            <div className={styles.historyBar}>
              <span className={styles.historyBarText}>
                {history.length} past scan{history.length !== 1 ? "s" : ""} available
              </span>
              <button
                className={styles.historyToggle}
                onClick={() => setShowHistory(!showHistory)}
              >
                {showHistory ? "Hide" : "Show"} history
              </button>
            </div>
          )}

          {showHistory && (
            <div className={styles.historyList}>
              {history.map((h) => (
                <button
                  key={h.file_hash}
                  className={styles.historyItem}
                  onClick={() => loadResult(h.file_hash)}
                >
                  <span className={styles.historyName}>{h.original_name}</span>
                  <span className={styles.historyMeta}>
                    {h.format} {h.width}×{h.height}
                    {h.flagged_count != null && ` · ${h.flagged_count} flagged`}
                  </span>
                </button>
              ))}
            </div>
          )}

          <div className={styles.modelPicker}>
            <p className={styles.modelPickerLabel}>Select analysis type</p>
            <div className={styles.modelOptions}>
              {MODELS.map((m) => (
                <button
                  key={m.key}
                  className={styles.modelCard}
                  onClick={() => {
                    setSelectedModel(m.key);
                    setStatus("selecting");
                  }}
                >
                  <span className={styles.modelOptionName}>{m.label}</span>
                  <span className={styles.modelOptionDesc}>{m.description}</span>
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      {/* ── Selecting: model chosen, upload image ────────────── */}
      {status === "selecting" && (
        <>
          <div className={styles.selectedModelBar}>
            <span className={styles.selectedModelLabel}>
              {MODELS.find((m) => m.key === selectedModel)?.label}
            </span>
            <button className={styles.changeModelButton} onClick={() => setStatus("idle")}>
              Change
            </button>
          </div>

          <div
            className={`${styles.dropzone} ${isDragOver ? styles.dropzoneActive : ""}`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={handleClick}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") handleClick();
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".png,.jpg,.jpeg,.webp,.tiff,.tif"
              className={styles.fileInput}
              onChange={(e) => handleFiles(e.target.files)}
            />
            <div className={styles.dropzoneIcon}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
            </div>
            <p className={styles.dropzoneText}>
              Drop your X-ray image here, or{" "}
              <span className={styles.dropzoneLink}>browse files</span>
            </p>
            <p className={styles.dropzoneHint}>PNG, JPEG, WebP, or TIFF images</p>
          </div>
        </>
      )}

      {/* ── Extracting (Stage 1) ─────────────────────────────── */}
      {status === "extracting" && (
        <div className={styles.statusCard}>
          {previewUrl && (
            <div className={styles.previewContainer}>
              <img src={previewUrl} alt="X-ray preview" className={styles.previewImage} />
            </div>
          )}
          <p className={styles.statusText}>Validating {currentFile}...</p>
          <p className={styles.statusHint}>Running Stage 1: format validation, storage, metadata extraction</p>
        </div>
      )}

      {/* ── Confirmation ─────────────────────────────────────── */}
      {status === "confirming" && extraction && (
        <div className={styles.statusCard}>
          {previewUrl && (
            <div className={styles.previewContainer}>
              <img src={previewUrl} alt="X-ray preview" className={styles.previewImage} />
            </div>
          )}

          <div className={styles.confirmationHeader}>
            <h2>Confirm Image</h2>
            <p>Review the extracted metadata before analysis</p>
          </div>

          <div className={styles.confirmationSummary}>
            <div className={styles.summaryChip}>
              {extraction.image_metadata.format}
            </div>
            <div className={styles.summaryChip}>
              {extraction.image_metadata.width} × {extraction.image_metadata.height}
            </div>
            <div className={styles.summaryChip}>
              {extraction.image_metadata.channels}ch · {extraction.image_metadata.bit_depth}-bit
            </div>
            <div className={styles.summaryChip}>
              {extraction.image_metadata.file_size_kb} KB
            </div>
            {extraction.image_metadata.is_grayscale && (
              <div className={`${styles.summaryChip} ${styles.chipGood}`}>Grayscale</div>
            )}
            {extraction.record.is_duplicate && (
              <div className={`${styles.summaryChip} ${styles.chipWarn}`}>Duplicate</div>
            )}
          </div>

          {extraction.quality.warning_count > 0 && (
            <div className={styles.warningBanner}>
              {extraction.quality.warnings.map((w, i) => (
                <p key={i}>{w}</p>
              ))}
            </div>
          )}

          <div className={styles.selectedModelBar}>
            <span className={styles.selectedModelLabel}>
              Model: {MODELS.find((m) => m.key === selectedModel)?.label}
            </span>
          </div>

          <div className={styles.confirmationActions}>
            <button className={styles.cancelButton} onClick={reset}>Cancel</button>
            <button className={styles.confirmButton} onClick={confirmAndProcess}>
              Confirm & Analyze
            </button>
          </div>
        </div>
      )}

      {/* ── Processing (Stage 2 + Model) ─────────────────────── */}
      {status === "processing" && (
        <div className={styles.statusCard}>
          {previewUrl && (
            <div className={styles.previewContainer}>
              <img src={previewUrl} alt="X-ray preview" className={styles.previewImage} />
            </div>
          )}
          <p className={styles.statusText}>Analyzing {currentFile}...</p>
          <p className={styles.statusHint}>
            Running Stage 2 standardisation + {selectedModel === "chest-xray" ? "TorchXRayVision" : "YOLOv8 fracture detection"} inference
            (this may take a moment on first run)
          </p>
        </div>
      )}

      {/* ── Error ────────────────────────────────────────────── */}
      {status === "error" && (
        <div className={styles.statusCard}>
          {previewUrl && (
            <div className={styles.previewContainer}>
              <img src={previewUrl} alt="X-ray preview" className={styles.previewImage} />
            </div>
          )}
          <p className={styles.errorText}>Analysis failed</p>
          <p className={styles.statusHint}>{errorMsg}</p>
          <button className={styles.retryButton} onClick={reset}>Try again</button>
        </div>
      )}

      {/* ── Results ──────────────────────────────────────────── */}
      {status === "done" && result && (
        <>
          <div className={styles.summaryBar}>
            <span className={styles.summaryFile}>{currentFile}</span>
            <span className={styles.summaryStats}>
              {result.summary.total_pathologies_screened} pathologies screened
              &middot; {result.summary.flagged_count} flagged
            </span>
            <div className={styles.summaryActions}>
              {history.length > 0 && (
                <button
                  className={styles.historyToggle}
                  onClick={() => setShowHistory(!showHistory)}
                >
                  {showHistory ? "Hide" : "Show"} history
                </button>
              )}
              <button className={styles.uploadAnother} onClick={reset}>
                Upload another
              </button>
            </div>
          </div>

          {showHistory && (
            <div className={styles.historyList}>
              {history.map((h) => (
                <button
                  key={h.file_hash}
                  className={`${styles.historyItem} ${h.file_hash === activeHash ? styles.historyItemActive : ""}`}
                  onClick={() => loadResult(h.file_hash)}
                >
                  <span className={styles.historyName}>{h.original_name}</span>
                  <span className={styles.historyMeta}>
                    {h.format} {h.width}×{h.height}
                    {h.flagged_count != null && ` · ${h.flagged_count} flagged`}
                  </span>
                </button>
              ))}
            </div>
          )}

          {(previewUrl || result.heatmap) && (
            <div className={styles.previewSection}>
              {result.heatmap && (
                <div className={styles.previewToggle}>
                  <button
                    className={`${styles.toggleButton} ${showHeatmap ? styles.toggleActive : ""}`}
                    onClick={() => setShowHeatmap(true)}
                  >
                    {result.findings.some((f) => f.bbox) ? "Detection" : "GradCAM Heatmap"}
                  </button>
                  {previewUrl && (
                    <button
                      className={`${styles.toggleButton} ${!showHeatmap ? styles.toggleActive : ""}`}
                      onClick={() => setShowHeatmap(false)}
                    >
                      Original
                    </button>
                  )}
                </div>
              )}
              <div className={styles.previewContainer}>
                {showHeatmap && result.heatmap ? (
                  <img
                    src={`data:image/png;base64,${result.heatmap}`}
                    alt="GradCAM heatmap"
                    className={styles.previewImage}
                  />
                ) : previewUrl ? (
                  <img src={previewUrl} alt="Analyzed X-ray" className={styles.previewImage} />
                ) : null}
              </div>
              {showHeatmap && result.heatmap_pathology && (
                <p className={styles.heatmapCaption}>
                  {result.findings.some((f) => f.bbox)
                    ? <strong>{result.heatmap_pathology}</strong>
                    : <>Activation map for: <strong>{result.heatmap_pathology}</strong></>
                  }
                </p>
              )}
            </div>
          )}

          <table className={styles.resultsTable}>
            <thead>
              <tr>
                <th>Pathology</th>
                <th>Probability</th>
                <th style={{ width: "30%" }}>Score</th>
                {result.findings.some((f) => f.size) && <th>Region Size</th>}
                <th>Level</th>
              </tr>
            </thead>
            <tbody>
              {result.findings.map((f) => (
                <tr
                  key={f.pathology}
                  className={
                    f.level === "HIGH"
                      ? styles.rowHigh
                      : f.level === "MODERATE"
                        ? styles.rowModerate
                        : ""
                  }
                >
                  <td>{f.pathology}</td>
                  <td className={styles.mono}>
                    {(f.probability * 100).toFixed(1)}%
                  </td>
                  <td>
                    <div className={styles.probBarContainer}>
                      <div className={styles.probBar}>
                        <div
                          className={`${styles.probBarFill} ${barClass(f.level)}`}
                          style={{ width: `${f.probability * 100}%` }}
                        />
                      </div>
                    </div>
                  </td>
                  {result.findings.some((fi) => fi.size) && (
                    <td className={styles.mono}>
                      {f.size
                        ? f.size.width_mm
                          ? `${f.size.width_mm}×${f.size.height_mm}mm`
                          : `${f.size.width_px.toFixed(0)}×${f.size.height_px.toFixed(0)}px`
                        : "—"}
                    </td>
                  )}
                  <td>
                    <span className={levelClass(f.level)}>{f.level}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* ── AI Interpretation (Stage 3) ────────────────────── */}
          <div className={styles.interpretationCard}>
            <h3 className={styles.interpretationHeading}>AI Interpretation</h3>
            <div className={styles.interpretationDisclaimer}>
              AI-generated interpretation for educational purposes only. Not a substitute for professional medical diagnosis.
            </div>

            {interpretationLoading && (
              <div className={styles.interpretationLoading}>
                <div className={styles.loadingDots}>
                  <span /><span /><span />
                </div>
                <p>Generating clinical interpretation...</p>
              </div>
            )}

            {interpretationError && !interpretationLoading && (
              <div className={styles.interpretationErrorState}>
                <p>Interpretation unavailable: {interpretationError}</p>
                <button
                  className={styles.retryButton}
                  onClick={() => activeHash && fetchInterpretation(activeHash)}
                >
                  Retry
                </button>
              </div>
            )}

            {interpretation && !interpretationLoading && (
              <div className={styles.interpretationContent}>
                <ReactMarkdown>{interpretation}</ReactMarkdown>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default ImagingTab;
