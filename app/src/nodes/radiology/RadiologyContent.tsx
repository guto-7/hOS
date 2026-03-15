import { useRef, useState, useCallback, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import ReactMarkdown from "react-markdown";
import styles from "./RadiologyContent.module.css";
import BodyDiagram from "./BodyDiagram";
import FractureCrop from "./FractureCrop";

/* ── Types ─────────────────────────────────────────────────────── */

interface Finding {
  pathology: string;
  probability: number;
  level: "HIGH" | "MODERATE" | "LOW" | "MINIMAL";
  body_part?: string;
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
  body_part_detection?: {
    body_part: string;
    confidence: number;
    description: string;
    recommended_model: string | null;
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
  body_part_detection?: {
    body_part: string;
    confidence: number;
    description: string;
    recommended_model: string | null;
  };
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

type Status = "loading" | "idle" | "extracting" | "confirming" | "processing" | "done" | "error";

const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/webp", "image/tiff"];

type ModelKey = "auto" | "chest-xray" | "fracture-wrist" | "fracture-multibody";

const MODELS: { key: ModelKey; label: string; description: string }[] = [
  { key: "auto", label: "Auto-Detect", description: "AI identifies body part and selects the best model automatically" },
  { key: "chest-xray", label: "Chest X-ray", description: "18 pathology screening (TorchXRayVision)" },
  { key: "fracture-wrist", label: "Wrist Fracture", description: "Pediatric wrist fracture detection (YOLOv8 GRAZPEDWRI-DX)" },
  { key: "fracture-multibody", label: "Multi-Body Fracture", description: "Elbow, fingers, forearm, humerus, shoulder, wrist (YOLOv8)" },
];

interface ModelInfo {
  name: string;
  architecture: string;
  dataset: string;
  pathologies: number;
  description: string;
}

const MODEL_ENTRIES: ModelInfo[] = [
  {
    name: "TorchXRayVision",
    architecture: "DenseNet-121",
    dataset: "CheXpert + MIMIC-CXR",
    pathologies: 18,
    description: "A deep learning model trained on over 200,000 chest X-rays from CheXpert and MIMIC-CXR datasets. Screens for 18 thoracic pathologies including pneumonia, cardiomegaly, and pleural effusion using GradCAM activation maps to highlight regions of interest.",
  },
  {
    name: "YOLOv8 GRAZPEDWRI-DX",
    architecture: "YOLOv8",
    dataset: "GRAZPEDWRI-DX (20,327 images)",
    pathologies: 4,
    description: "A real-time object detection model fine-tuned on the GRAZPEDWRI-DX dataset of 20,327 pediatric wrist radiographs. Detects fractures, bone anomalies, bone lesions, and periosteal reactions with bounding box localisation and size estimation.",
  },
  {
    name: "YOLOv8 Multi-Body",
    architecture: "YOLOv8",
    dataset: "Bone Fracture Detection",
    pathologies: 6,
    description: "A multi-region fracture detection model covering six anatomical sites: elbow, fingers, forearm, humerus, shoulder, and wrist. Trained on a diverse bone fracture dataset with bounding box annotations for precise fracture localisation.",
  },
];

// Map both model keys (e.g. "fracture-wrist") and model names from Python
// (e.g. "YOLOv8-GRAZPEDWRI") so lookup works regardless of which field arrives.
const MODEL_META: Record<string, ModelInfo> = {
  "chest-xray": MODEL_ENTRIES[0],
  "densenet121-res224-chex": MODEL_ENTRIES[0],
  "fracture-wrist": MODEL_ENTRIES[1],
  "YOLOv8-GRAZPEDWRI": MODEL_ENTRIES[1],
  "fracture-multibody": MODEL_ENTRIES[2],
  "YOLOv8-MultiBone": MODEL_ENTRIES[2],
};

const BODY_PART_INFO: Record<string, { anatomy: string; common: string }> = {
  wrist: {
    anatomy: "The wrist joint includes the distal radius, ulna, and eight carpal bones. X-rays typically assess the AP and lateral projections for alignment and cortical integrity.",
    common: "Distal radius fractures, scaphoid injuries, Colles' fractures, periosteal reactions.",
  },
  chest: {
    anatomy: "The chest X-ray visualises the heart, lungs, mediastinum, ribs, and diaphragm. It is the most commonly requested radiological examination worldwide.",
    common: "Pneumonia, cardiomegaly, pleural effusion, atelectasis, pneumothorax, lung nodules.",
  },
  elbow: {
    anatomy: "The elbow joint is formed by the humerus, radius, and ulna. Key landmarks include the olecranon, radial head, and the anterior fat pad.",
    common: "Radial head fractures, olecranon fractures, supracondylar fractures, joint effusion.",
  },
  shoulder: {
    anatomy: "The shoulder comprises the glenohumeral joint, acromioclavicular joint, and surrounding soft tissues. Views assess the humeral head, glenoid, and acromion.",
    common: "Proximal humerus fractures, dislocations, acromioclavicular separation, calcific tendinitis.",
  },
  fingers: {
    anatomy: "The hand and finger X-ray shows the phalanges, metacarpals, and interphalangeal joints. Used to assess alignment, fractures, and joint spaces.",
    common: "Phalangeal fractures, metacarpal fractures (boxer's fracture), dislocations, arthritis.",
  },
  forearm: {
    anatomy: "The forearm consists of the radius and ulna, connected by the interosseous membrane. Both AP and lateral views are standard for assessment.",
    common: "Midshaft fractures, Monteggia fracture-dislocations, Galeazzi fractures, greenstick fractures.",
  },
  humerus: {
    anatomy: "The humerus is the long bone of the upper arm, extending from the shoulder to the elbow. X-rays assess the shaft, surgical neck, and condyles.",
    common: "Surgical neck fractures, midshaft fractures, spiral fractures, pathological fractures.",
  },
  hand: {
    anatomy: "The hand X-ray includes the carpals, metacarpals, and phalanges. Standard views include PA and oblique projections.",
    common: "Metacarpal fractures, scaphoid fractures, Bennett's fracture, gamekeeper's thumb.",
  },
  hip: {
    anatomy: "The hip joint is a ball-and-socket joint between the femoral head and acetabulum. X-rays assess joint space, femoral neck, and pelvic alignment.",
    common: "Femoral neck fractures, intertrochanteric fractures, osteoarthritis, avascular necrosis.",
  },
  knee: {
    anatomy: "The knee joint involves the femur, tibia, patella, and fibula. Weight-bearing views assess joint space and alignment.",
    common: "Tibial plateau fractures, patellar fractures, osteoarthritis, joint effusion.",
  },
  ankle: {
    anatomy: "The ankle joint includes the distal tibia, fibula, and talus. AP, lateral, and mortise views are standard for assessment.",
    common: "Lateral malleolus fractures, bimalleolar fractures, Weber classification injuries.",
  },
  foot: {
    anatomy: "The foot X-ray shows the tarsals, metatarsals, and phalanges. Views include AP, lateral, and oblique projections.",
    common: "Metatarsal fractures, Lisfranc injuries, calcaneal fractures, stress fractures.",
  },
  spine: {
    anatomy: "Spinal X-rays assess vertebral alignment, disc spaces, and bony integrity. Views vary by region (cervical, thoracic, lumbar).",
    common: "Compression fractures, spondylolisthesis, degenerative disc disease, scoliosis.",
  },
  pelvis: {
    anatomy: "The pelvic X-ray shows the ilium, ischium, pubis, sacrum, and hip joints. An AP view is standard for trauma assessment.",
    common: "Pelvic ring fractures, acetabular fractures, sacral fractures, pubic rami fractures.",
  },
  leg: {
    anatomy: "The lower leg consists of the tibia and fibula. AP and lateral views assess the shafts, proximal and distal joints.",
    common: "Tibial shaft fractures, fibular fractures, stress fractures, toddler's fractures.",
  },
  ribs: {
    anatomy: "Rib X-rays assess the bony thorax for fractures and alignment. Dedicated rib views or chest X-rays may be used.",
    common: "Rib fractures, flail chest, pathological fractures, costochondral separation.",
  },
};

/* ── Component ─────────────────────────────────────────────────── */

function RadiologyContent() {
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
  const [selectedModel, setSelectedModel] = useState<ModelKey>("auto");
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

      // Pre-select model based on body part detection
      if (parsed.body_part_detection?.recommended_model) {
        setSelectedModel(parsed.body_part_detection.recommended_model as ModelKey);
      } else {
        setSelectedModel("auto");
      }

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

  /* ── Render ──────────────────────────────────────────────────── */

  return (
    <div>
      {/* ── Loading ──────────────────────────────────────────── */}
      {status === "loading" && (
        <div className={styles.statusCard}>
          <p className={styles.statusText}>Loading...</p>
        </div>
      )}

      {/* ── Idle: upload image ────────────────────────────── */}
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
                    {h.format} {h.width}&times;{h.height}
                    {h.flagged_count != null && ` · ${h.flagged_count} flagged`}
                  </span>
                </button>
              ))}
            </div>
          )}

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
          <p className={styles.statusHint}>Validating format, extracting metadata, and detecting scan type...</p>
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
            <p>Review the detected scan type and metadata before analysis</p>
          </div>

          {/* Body part detection result */}
          {extraction.body_part_detection && (
            <div className={styles.bodyPartDetection}>
              <div className={styles.bodyPartDetectionHeader}>
                <span className={styles.bodyPartDetectionLabel}>Detected scan type</span>
                <span className={styles.bodyPartDetectionValue}>
                  {extraction.body_part_detection.body_part.charAt(0).toUpperCase() +
                    extraction.body_part_detection.body_part.slice(1)}
                </span>
                <span className={styles.bodyPartConfidence}>
                  {(extraction.body_part_detection.confidence * 100).toFixed(0)}% confidence
                </span>
              </div>
              {extraction.body_part_detection.description && (
                <p className={styles.bodyPartDetectionDesc}>
                  {extraction.body_part_detection.description}
                </p>
              )}
            </div>
          )}

          {/* Model selection — pre-filled from detection, user can override */}
          <div className={styles.modelOverride}>
            <p className={styles.modelOverrideLabel}>Analysis model</p>
            <div className={styles.modelOverrideOptions}>
              {MODELS.map((m) => (
                <button
                  key={m.key}
                  className={`${styles.modelOverrideOption} ${
                    selectedModel === m.key ? styles.modelOverrideActive : ""
                  }`}
                  onClick={() => setSelectedModel(m.key)}
                >
                  <span className={styles.modelOverrideName}>{m.label}</span>
                  <span className={styles.modelOverrideDesc}>{m.description}</span>
                </button>
              ))}
            </div>
          </div>

          <div className={styles.confirmationSummary}>
            <div className={styles.summaryChip}>
              {extraction.image_metadata.format}
            </div>
            <div className={styles.summaryChip}>
              {extraction.image_metadata.width} &times; {extraction.image_metadata.height}
            </div>
            <div className={styles.summaryChip}>
              {extraction.image_metadata.channels}ch &middot; {extraction.image_metadata.bit_depth}-bit
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

          <div className={styles.confirmationActions}>
            <button className={styles.cancelButton} onClick={reset}>Cancel</button>
            <button className={styles.confirmButton} onClick={confirmAndProcess}>
              Confirm &amp; Analyze
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
            {selectedModel === "auto"
              ? "Auto-detecting body part with Claude Vision, then running the best model..."
              : `Running Stage 2 standardisation + ${
                  selectedModel === "chest-xray"
                    ? "TorchXRayVision"
                    : "YOLOv8 fracture detection"
                } inference`}
            {" "}(this may take a moment on first run)
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
      {status === "done" && result && (() => {
        const modelMeta = MODEL_META[result.model] ?? null;
        // Infer body part: result detection > extraction detection > model-implied
        const MODEL_BODY_PART: Record<string, string> = {
          "fracture-wrist": "Wrist",
          "chest-xray": "Chest",
        };
        const inferredSite = result.body_part_detection?.body_part
          ?? extraction?.body_part_detection?.body_part
          ?? MODEL_BODY_PART[result.model]
          ?? null;
        const flagged = result.findings.filter((f) => f.level === "HIGH" || f.level === "MODERATE");
        const topFinding = result.findings.length > 0
          ? result.findings.reduce((a, b) => (a.probability > b.probability ? a : b))
          : null;
        const avgConfidence = result.findings.length > 0
          ? result.findings.reduce((sum, f) => sum + f.probability, 0) / result.findings.length
          : 0;
        const hasSizes = result.findings.some((f) => f.size);

        return (
          <>
            {/* Summary bar */}
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
                      {h.format} {h.width}&times;{h.height}
                      {h.flagged_count != null && ` · ${h.flagged_count} flagged`}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {/* ── Grid layout (matches wireframe) ────────────── */}
            <div className={styles.resultsGrid}>

              {/* ── Row 1, Col 1: Identified Scan ──────────────── */}
              <div className={`${styles.gridPanel} ${styles.scanPanel}`}>
                <p className={styles.gridPanelLabel}>Identified Scan</p>
                {(previewUrl || result.heatmap) && (
                  <>
                    {result.heatmap && (
                      <div className={styles.scanToggle}>
                        <button
                          className={`${styles.toggleButton} ${showHeatmap ? styles.toggleActive : ""}`}
                          onClick={() => setShowHeatmap(true)}
                        >
                          {result.findings.some((f) => f.bbox) ? "Annotated" : "Heatmap"}
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
                    <div className={styles.scanImageContainer}>
                      {showHeatmap && result.heatmap ? (
                        <img
                          src={`data:image/png;base64,${result.heatmap}`}
                          alt="Detection overlay"
                          className={styles.scanImage}
                        />
                      ) : previewUrl ? (
                        <img src={previewUrl} alt="Original scan" className={styles.scanImage} />
                      ) : null}
                    </div>
                    {showHeatmap && result.heatmap_pathology && (
                      <p className={styles.heatmapCaption}>
                        {result.findings.some((f) => f.bbox)
                          ? <strong>{result.heatmap_pathology}</strong>
                          : <>Activation map: <strong>{result.heatmap_pathology}</strong></>
                        }
                      </p>
                    )}
                  </>
                )}
              </div>

              {/* ── Row 1, Col 2: Wound Site & Severity ────────── */}
              <div className={`${styles.gridPanel} ${styles.findingsPanel}`}>
                <p className={styles.gridPanelLabel}>Wound Site &amp; Severity</p>
                <div className={styles.findingsSummary}>
                  {flagged.length === 0 && (
                    <p style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
                      No significant findings detected.
                    </p>
                  )}
                  {flagged.map((f) => {
                    const location = f.body_part ?? inferredSite ?? "Unspecified";
                    const severityDesc = f.level === "HIGH"
                      ? (f.size?.width_mm
                          ? `Significant (${f.size.width_mm}×${f.size.height_mm} mm)`
                          : f.size
                            ? `Significant (${f.size.area_pct.toFixed(1)}% of image)`
                            : "Significant")
                      : (f.size?.width_mm
                          ? `Moderate (${f.size.width_mm}×${f.size.height_mm} mm)`
                          : f.size
                            ? `Moderate (${f.size.area_pct.toFixed(1)}% of image)`
                            : "Moderate");

                    return (
                      <div key={f.pathology} className={styles.findingCard}>
                        <div className={styles.findingCardHeader}>
                          <span className={styles.findingName}>{f.pathology}</span>
                          <span className={`${styles.findingLevel} ${levelClass(f.level)}`}>{f.level}</span>
                        </div>
                        <div className={styles.findingCardMeta}>
                          <span className={styles.findingLocation}>
                            Site: {location}
                          </span>
                          <span className={styles.findingSeverity}>
                            Severity: {severityDesc}
                          </span>
                        </div>
                        <p className={styles.findingContext}>
                          {f.level === "HIGH"
                            ? `${f.pathology} detected in the ${location}. Recommend urgent clinical review and follow-up imaging.`
                            : `Indicators of ${f.pathology.toLowerCase()} in the ${location} region. Consider clinical correlation and monitoring.`}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* ── Row 1-2, Col 3: LLM Interpretation ─────────── */}
              <div className={`${styles.gridPanel} ${styles.interpretationPanel}`}>
                <div className={styles.interpretationInner}>
                  <p className={styles.gridPanelLabel}>LLM Interpretation</p>
                  <div className={styles.interpretationDisclaimer}>
                    AI-generated — not a substitute for professional diagnosis.
                  </div>

                  <div className={styles.interpretationScroll}>
                    {interpretationLoading && (
                      <div className={styles.interpretationLoading}>
                        <div className={styles.loadingDots}>
                          <span /><span /><span />
                        </div>
                        <p>Generating interpretation...</p>
                      </div>
                    )}

                    {interpretationError && !interpretationLoading && (
                      <div className={styles.interpretationErrorState}>
                        <p>Unavailable: {interpretationError}</p>
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
                </div>
              </div>

              {/* ── Row 2, Col 1-2: Healing / Follow-up ────────── */}
              <div className={`${styles.gridPanel} ${styles.healingPanel}`}>
                <p className={styles.gridPanelLabel}>Healing &amp; Follow-up Action</p>
                {interpretation ? (
                  <div className={styles.modelInfoGrid}>
                    <div className={styles.modelInfoRow}>
                      <span className={styles.modelInfoKey}>Severity</span>
                      <span className={styles.modelInfoValue}>
                        {flagged.length > 0
                          ? flagged.some((f) => f.level === "HIGH") ? "High" : "Moderate"
                          : "Normal"}
                      </span>
                    </div>
                    <div className={styles.modelInfoRow}>
                      <span className={styles.modelInfoKey}>Flagged findings</span>
                      <span className={styles.modelInfoValue}>{flagged.length}</span>
                    </div>
                    <div className={styles.modelInfoRow}>
                      <span className={styles.modelInfoKey}>Recommended</span>
                      <span className={styles.modelInfoValue}>
                        {flagged.some((f) => f.level === "HIGH")
                          ? "Urgent follow-up"
                          : flagged.length > 0
                            ? "Routine follow-up"
                            : "No action required"}
                      </span>
                    </div>
                  </div>
                ) : (
                  <p style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
                    Awaiting interpretation...
                  </p>
                )}
              </div>

              {/* ── Row 3, Col 1: Original Scan ────────────────── */}
              <div className={`${styles.gridPanel} ${styles.originalScanPanel}`}>
                <p className={styles.gridPanelLabel}>Original Scan</p>
                <div className={styles.scanImageContainer}>
                  {previewUrl ? (
                    <img src={previewUrl} alt="Original scan" className={styles.scanImage} />
                  ) : result.heatmap ? (
                    <img
                      src={`data:image/png;base64,${result.heatmap}`}
                      alt="Scan"
                      className={styles.scanImage}
                    />
                  ) : (
                    <p style={{ padding: "var(--space-4)", color: "var(--text-muted)", fontSize: "var(--text-sm)" }}>
                      Original not available (loaded from history)
                    </p>
                  )}
                </div>
              </div>

              {/* ── Row 3, Col 2: Classifier Accuracy ──────────── */}
              <div className={`${styles.gridPanel} ${styles.accuracyPanel}`}>
                <p className={styles.gridPanelLabel}>% Classifier Accuracy</p>
                {topFinding ? (() => {
                  const pct = topFinding.probability * 100;
                  const radius = 54;
                  const stroke = 10;
                  const circumference = 2 * Math.PI * radius;
                  const filled = (pct / 100) * circumference;
                  const gap = circumference - filled;

                  return (
                    <div className={styles.pieContainer}>
                      <svg viewBox="0 0 128 128" className={styles.pieSvg}>
                        <circle
                          cx="64" cy="64" r={radius}
                          fill="none"
                          stroke="var(--bg-surface-raised)"
                          strokeWidth={stroke}
                        />
                        <circle
                          cx="64" cy="64" r={radius}
                          fill="none"
                          stroke="var(--accent-primary)"
                          strokeWidth={stroke}
                          strokeDasharray={`${filled} ${gap}`}
                          strokeDashoffset={circumference * 0.25}
                          strokeLinecap="round"
                        />
                        <text
                          x="64" y="60"
                          textAnchor="middle"
                          className={styles.pieValue}
                        >
                          {pct.toFixed(1)}%
                        </text>
                        <text
                          x="64" y="76"
                          textAnchor="middle"
                          className={styles.pieSubtext}
                        >
                          confidence
                        </text>
                      </svg>
                      <div className={styles.accuracyLabel}>
                        Top finding: {topFinding.pathology}
                      </div>
                      <div className={styles.accuracyLabel}>
                        Avg across {result.findings.length} findings: {(avgConfidence * 100).toFixed(1)}%
                      </div>
                    </div>
                  );
                })() : (
                  <div className={styles.accuracyLabel}>No findings to score</div>
                )}
              </div>

              {/* ── Row 3, Col 3: Info about Model ─────────────── */}
              <div className={`${styles.gridPanel} ${styles.modelInfoPanel}`}>
                <p className={styles.gridPanelLabel}>Info about Model</p>
                <div className={styles.modelInfoHeader}>
                  <span className={styles.modelInfoName}>{modelMeta?.name ?? result.model}</span>
                  {modelMeta && (
                    <span className={styles.modelInfoArch}>{modelMeta.architecture}</span>
                  )}
                </div>
                {modelMeta && (
                  <p className={styles.modelInfoDescription}>{modelMeta.description}</p>
                )}
              </div>

              {/* ── Row 4, Col 1: Body Diagram ─────────────────── */}
              <div className={`${styles.gridPanel} ${styles.bodyDiagramPanel}`}>
                <BodyDiagram
                  bodyPart={inferredSite ?? undefined}
                  className={styles.bodyDiagramSvg}
                />
              </div>

              {/* ── Row 4, Col 2-3: Body Part ──────────────────── */}
              <div className={`${styles.gridPanel} ${styles.bodyPartPanel}`}>
                <p className={styles.gridPanelLabel}>Body Part</p>
                {inferredSite ? (() => {
                  const info = BODY_PART_INFO[inferredSite.toLowerCase()];
                  return (
                    <>
                      <span className={styles.bodyPartName}>{inferredSite}</span>
                      {result.body_part_detection && (
                        <span className={styles.bodyPartConf}>
                          {(result.body_part_detection.confidence * 100).toFixed(0)}% confidence
                        </span>
                      )}
                      {info && (
                        <>
                          <p className={styles.bodyPartAnatomy}>{info.anatomy}</p>
                          <p className={styles.bodyPartCommon}>
                            <strong>Common findings:</strong> {info.common}
                          </p>
                        </>
                      )}
                    </>
                  );
                })() : (
                  <p style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
                    Body part not detected.
                  </p>
                )}
              </div>

              {/* ── Row 5, Col 1: Fracture Zoom ──────────────── */}
              <div className={`${styles.gridPanel} ${styles.changedScanPanel}`}>
                <p className={styles.gridPanelLabel}>Fracture Close-up</p>
                {result.heatmap && result.findings.some((f) => f.bbox) ? (
                  <FractureCrop
                    imageSrc={`data:image/png;base64,${result.heatmap}`}
                    bboxes={result.findings
                      .filter((f): f is Finding & { bbox: NonNullable<Finding["bbox"]> } => !!f.bbox)
                      .map((f, i) => ({
                        bbox: f.bbox,
                        label: `${f.pathology} #${i + 1}${f.size?.width_mm ? ` — ${f.size.width_mm}×${f.size.height_mm} mm` : ""}`,
                      }))}
                  />
                ) : (
                  <p style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
                    No bounding box data available for zoom.
                  </p>
                )}
              </div>

              {/* ── Row 5, Col 2-3: Fracture Size ──────────────── */}
              <div className={`${styles.gridPanel} ${styles.sizePanel}`}>
                <p className={styles.gridPanelLabel}>Fracture Size</p>
                {hasSizes ? (
                  <div className={styles.sizeGrid}>
                    {result.findings
                      .filter((f) => f.size)
                      .map((f, i) => {
                        const imgW = result.image_metadata.width;
                        const imgH = result.image_metadata.height;
                        const cx = f.bbox ? ((f.bbox.x1 + f.bbox.x2) / 2 / imgW) : null;
                        const cy = f.bbox ? ((f.bbox.y1 + f.bbox.y2) / 2 / imgH) : null;
                        const posLabel = cx !== null && cy !== null
                          ? `${cy < 0.33 ? "Upper" : cy > 0.66 ? "Lower" : "Mid"}-${cx < 0.33 ? "left" : cx > 0.66 ? "right" : "centre"}`
                          : null;

                        return (
                          <div key={`${f.pathology}-${i}`} className={styles.sizeCard}>
                            <div className={styles.sizeCardHeader}>
                              <span className={styles.sizeStatValue}>
                                {f.size!.width_mm
                                  ? `${f.size!.width_mm} × ${f.size!.height_mm} mm`
                                  : `${f.size!.width_px.toFixed(0)} × ${f.size!.height_px.toFixed(0)} px`}
                              </span>
                              <span className={styles.sizeStatLabel}>
                                {f.size!.area_pct > 0 ? `${f.size!.area_pct.toFixed(1)}% of image` : ""}
                              </span>
                            </div>
                            <div className={styles.sizeCardMeta}>
                              <span>{f.pathology} #{i + 1}</span>
                              {posLabel && <span>Region: {posLabel}</span>}
                            </div>
                          </div>
                        );
                      })}
                  </div>
                ) : (
                  <p style={{ fontSize: "var(--text-sm)", color: "var(--text-secondary)" }}>
                    No region measurements available.
                  </p>
                )}
              </div>

            </div>
          </>
        );
      })()}
    </div>
  );
}

export default RadiologyContent;
