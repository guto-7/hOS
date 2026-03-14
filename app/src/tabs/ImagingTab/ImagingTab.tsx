import { useRef, useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import styles from "./ImagingTab.module.css";

interface Finding {
  pathology: string;
  probability: number;
  level: "HIGH" | "MODERATE" | "LOW" | "MINIMAL";
}

interface AnalysisResult {
  image: string;
  model: string;
  findings: Finding[];
  summary: {
    high_probability: string[];
    moderate_probability: string[];
    total_pathologies_screened: number;
    flagged_count: number;
  };
}

type Status = "idle" | "processing" | "done" | "error";

const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/webp", "image/tiff"];

function ImagingTab() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [currentFile, setCurrentFile] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const processFile = useCallback(async (file: File) => {
    setStatus("processing");
    setErrorMsg("");
    setCurrentFile(file.name);
    setResult(null);

    // Create preview URL
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);

    try {
      const arrayBuffer = await file.arrayBuffer();
      const bytes = Array.from(new Uint8Array(arrayBuffer));

      const jsonString = await invoke<string>("analyze_xray", {
        fileName: file.name,
        fileBytes: bytes,
      });

      const parsed: AnalysisResult = JSON.parse(jsonString);
      setResult(parsed);
      setStatus("done");
    } catch (err) {
      setErrorMsg(String(err));
      setStatus("error");
    }
  }, []);

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      const file = files[0];
      if (
        ACCEPTED_TYPES.includes(file.type) ||
        /\.(png|jpe?g|webp|tiff?)$/i.test(file.name)
      ) {
        processFile(file);
      }
    },
    [processFile]
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
    setErrorMsg("");
    setCurrentFile("");
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
  };

  const levelClass = (level: string) => {
    switch (level) {
      case "HIGH":
        return styles.levelHigh;
      case "MODERATE":
        return styles.levelModerate;
      case "LOW":
        return styles.levelLow;
      default:
        return styles.levelMinimal;
    }
  };

  const barClass = (level: string) => {
    switch (level) {
      case "HIGH":
        return styles.probBarHigh;
      case "MODERATE":
        return styles.probBarModerate;
      case "LOW":
        return styles.probBarLow;
      default:
        return styles.probBarMinimal;
    }
  };

  return (
    <div className={styles.tab}>
      <h1 className={styles.heading}>Imaging</h1>
      <p className={styles.description}>
        Upload a chest X-ray image for AI-powered pathology screening.
        TorchXRayVision analyzes 18 pathologies using a pre-trained DenseNet
        model and returns probability scores for each finding.
      </p>

      {status === "idle" && (
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
            <svg
              width="32"
              height="32"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <polyline points="21 15 16 10 5 21" />
            </svg>
          </div>
          <p className={styles.dropzoneText}>
            Drop your chest X-ray here, or{" "}
            <span className={styles.dropzoneLink}>browse files</span>
          </p>
          <p className={styles.dropzoneHint}>
            PNG, JPEG, WebP, or TIFF images
          </p>
        </div>
      )}

      {status === "processing" && (
        <div className={styles.statusCard}>
          {previewUrl && (
            <div className={styles.previewContainer}>
              <img
                src={previewUrl}
                alt="X-ray preview"
                className={styles.previewImage}
              />
            </div>
          )}
          <p className={styles.statusText}>Analyzing {currentFile}...</p>
          <p className={styles.statusHint}>
            Loading model and running pathology prediction (this may take a
            moment on first run)
          </p>
        </div>
      )}

      {status === "error" && (
        <div className={styles.statusCard}>
          {previewUrl && (
            <div className={styles.previewContainer}>
              <img
                src={previewUrl}
                alt="X-ray preview"
                className={styles.previewImage}
              />
            </div>
          )}
          <p className={styles.errorText}>Analysis failed</p>
          <p className={styles.statusHint}>{errorMsg}</p>
          <button className={styles.retryButton} onClick={reset}>
            Try again
          </button>
        </div>
      )}

      {status === "done" && result && (
        <>
          <div className={styles.summaryBar}>
            <span className={styles.summaryFile}>{currentFile}</span>
            <span className={styles.summaryStats}>
              {result.summary.total_pathologies_screened} pathologies screened
              &middot; {result.summary.flagged_count} flagged
            </span>
            <button className={styles.uploadAnother} onClick={reset}>
              Upload another
            </button>
          </div>

          {previewUrl && (
            <div className={styles.previewContainer}>
              <img
                src={previewUrl}
                alt="Analyzed X-ray"
                className={styles.previewImage}
              />
            </div>
          )}

          <table className={styles.resultsTable}>
            <thead>
              <tr>
                <th>Pathology</th>
                <th>Probability</th>
                <th style={{ width: "35%" }}>Score</th>
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
                  <td>
                    <span className={levelClass(f.level)}>{f.level}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

export default ImagingTab;
