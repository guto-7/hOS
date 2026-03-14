import { useRef, useState, useCallback, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import styles from "./DataTab.module.css";

/* ── Stage 1 result (extracted markers before user confirmation) ── */

interface ExtractedMarker {
  pdf_name: string;
  value: number;
  unit: string;
  ref_low: number | null;
  ref_high: number | null;
  lab_flag: string | null;
  raw_text: string;
  marker_id: string | null;
  marker_name: string | null;
  category: string | null;
  match_type: string;
  unit_match: boolean;
  confidence: string;
  confidence_reasons: string[];
}

interface ExtractionResult {
  success: boolean;
  error?: string;
  stage: string;
  markers: ExtractedMarker[];
  summary: {
    total_extracted: number;
    matched: number;
    unmatched: number;
    confidence_breakdown: Record<string, number>;
  };
  record: {
    file_hash: string;
    original_name: string;
    lab_provider: string | null;
    test_date: string | null;
  };
}

/* ── Stage 2 result (enriched markers after confirmation) ── */

interface MarkerResult {
  pdf_name: string;
  marker_name: string | null;
  marker_id: string | null;
  category: string | null;
  original_value: number;
  original_unit: string;
  std_value: number;
  std_unit: string;
  unit_converted: boolean;
  lab_ref_low: number | null;
  lab_ref_high: number | null;
  canonical_ref_low: number | null;
  canonical_ref_high: number | null;
  adjustment_note: string | null;
  flag: string;
  deviation: string | null;
  deviation_pct: number | null;
  lab_flag: string | null;
  match_type: string;
  confidence: string;
  confidence_reasons: string[];
}

interface PipelineResult {
  success: boolean;
  error?: string;
  markers: MarkerResult[];
  summary: {
    total_extracted: number;
    matched: number;
    unmatched: number;
    flagged: number;
    flag_breakdown: Record<string, number>;
  };
  record: {
    file_hash: string;
    original_name: string;
    lab_provider: string | null;
    test_date: string | null;
  };
}

/* ── History record (metadata from list command) ── */

interface HistoryRecord {
  file_hash: string;
  original_name: string;
  lab_provider: string | null;
  test_date: string | null;
  matched: number | null;
  flagged: number | null;
}

type ProcessingStatus = "loading" | "idle" | "extracting" | "confirming" | "processing" | "done" | "error";

function formatRefRange(low: number | null, high: number | null): string {
  if (low !== null && high !== null) return `${low} – ${high}`;
  if (low !== null) return `> ${low}`;
  if (high !== null) return `< ${high}`;
  return "—";
}

function confidenceClass(confidence: string): string {
  if (confidence === "HIGH") return styles.confidenceHigh;
  if (confidence === "MEDIUM") return styles.confidenceMedium;
  return styles.confidenceLow;
}

function DataTab() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const fileBytesRef = useRef<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [status, setStatus] = useState<ProcessingStatus>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null);
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [currentFile, setCurrentFile] = useState<string>("");
  const [history, setHistory] = useState<HistoryRecord[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  /* ── Load history on mount ── */

  const loadHistory = useCallback(async () => {
    try {
      const jsonString = await invoke<string>("list_bloodwork_results");
      const records: HistoryRecord[] = JSON.parse(jsonString);
      setHistory(records);
      return records;
    } catch {
      return [];
    }
  }, []);

  const loadResult = useCallback(async (hash: string, fileName: string) => {
    try {
      const jsonString = await invoke<string>("load_bloodwork_result", { fileHash: hash });
      const parsed: PipelineResult = JSON.parse(jsonString);
      setResult(parsed);
      setCurrentFile(fileName);
      setStatus("done");
      setShowHistory(false);
    } catch (err) {
      setErrorMsg(String(err));
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    loadHistory().then((records) => {
      if (records.length > 0) {
        // Load the most recent result
        const latest = records[0];
        loadResult(latest.file_hash, latest.original_name);
      } else {
        setStatus("idle");
      }
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /* ── Stage 1: Extract markers for confirmation ── */

  const extractFile = useCallback(async (file: File) => {
    setStatus("extracting");
    setErrorMsg("");
    setCurrentFile(file.name);
    setExtraction(null);
    setResult(null);
    fileBytesRef.current = file;
    setShowHistory(false);

    try {
      const arrayBuffer = await file.arrayBuffer();
      const bytes = Array.from(new Uint8Array(arrayBuffer));

      const jsonString = await invoke<string>("extract_pdf", {
        fileName: file.name,
        fileBytes: bytes,
      });

      const parsed: ExtractionResult = JSON.parse(jsonString);
      if (!parsed.success) {
        throw new Error(parsed.error || "Extraction returned an error");
      }
      setExtraction(parsed);
      setStatus("confirming");
    } catch (err) {
      setErrorMsg(String(err));
      setStatus("error");
    }
  }, []);

  /* ── Stage 2: Run full pipeline after user confirms ── */

  const confirmAndProcess = useCallback(async () => {
    const file = fileBytesRef.current;
    if (!file) return;

    setStatus("processing");

    try {
      const arrayBuffer = await file.arrayBuffer();
      const bytes = Array.from(new Uint8Array(arrayBuffer));

      const jsonString = await invoke<string>("process_pdf", {
        fileName: file.name,
        fileBytes: bytes,
      });

      const parsed: PipelineResult = JSON.parse(jsonString);
      if (!parsed.success) {
        throw new Error(parsed.error || "Pipeline returned an error");
      }
      setResult(parsed);
      setStatus("done");
      // Refresh history after new upload
      loadHistory();
    } catch (err) {
      setErrorMsg(String(err));
      setStatus("error");
    }
  }, [loadHistory]);

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      const file = files[0];
      if (file.type === "application/pdf" || file.name.endsWith(".pdf")) {
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
    setExtraction(null);
    setResult(null);
    setErrorMsg("");
    setCurrentFile("");
    fileBytesRef.current = null;
    setShowHistory(false);
  };

  /* ── Derived data ── */

  const matchedMarkers = result?.markers.filter((m) => m.marker_id !== null);
  const flaggedMarkers = matchedMarkers?.filter((m) => m.flag !== "OPTIMAL");

  const extractedLow = extraction?.markers.filter((m) => m.confidence === "LOW");

  return (
    <div className={styles.tab}>
      <h1 className={styles.heading}>Data</h1>
      <p className={styles.description}>
        Upload bloodwork PDFs and track your biomarkers over time. View trends,
        flag out-of-range values, and maintain a complete history of your lab
        results.
      </p>

      {/* ── Loading ── */}

      {status === "loading" && (
        <div className={styles.statusCard}>
          <p className={styles.statusText}>Loading...</p>
        </div>
      )}

      {/* ── Idle: Drop Zone ── */}

      {status === "idle" && (
        <>
          {history.length > 0 && (
            <div className={styles.historyBar}>
              <span className={styles.historyLabel}>
                {history.length} past upload{history.length > 1 ? "s" : ""} available
              </span>
              <button
                className={styles.historyButton}
                onClick={() => setShowHistory(!showHistory)}
              >
                {showHistory ? "Hide history" : "View history"}
              </button>
            </div>
          )}

          {showHistory && history.length > 0 && (
            <div className={styles.historyList}>
              {history.map((r) => (
                <button
                  key={r.file_hash}
                  className={styles.historyItem}
                  onClick={() => loadResult(r.file_hash, r.original_name)}
                >
                  <span className={styles.historyName}>{r.original_name}</span>
                  <span className={styles.historyMeta}>
                    {r.test_date && `${r.test_date} · `}
                    {r.matched ?? 0} markers
                    {r.flagged ? ` · ${r.flagged} flagged` : ""}
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
              accept=".pdf,application/pdf"
              className={styles.fileInput}
              onChange={(e) => handleFiles(e.target.files)}
            />
            <div className={styles.dropzoneIcon}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="12" y1="18" x2="12" y2="12" />
                <line x1="9" y1="15" x2="12" y2="12" />
                <line x1="15" y1="15" x2="12" y2="12" />
              </svg>
            </div>
            <p className={styles.dropzoneText}>
              Drop your blood panel PDF here, or{" "}
              <span className={styles.dropzoneLink}>browse files</span>
            </p>
            <p className={styles.dropzoneHint}>PDF files only</p>
          </div>
        </>
      )}

      {/* ── Extracting: Stage 1 in progress ── */}

      {status === "extracting" && (
        <div className={styles.statusCard}>
          <p className={styles.statusText}>Extracting markers from {currentFile}...</p>
          <p className={styles.statusHint}>
            Parsing text, resolving aliases, and scoring confidence
          </p>
        </div>
      )}

      {/* ── Confirming: Stage 1 results for user review ── */}

      {status === "confirming" && extraction && (
        <>
          <div className={styles.confirmationHeader}>
            <div className={styles.confirmationTitle}>
              <h2>Review Extracted Markers</h2>
              <p className={styles.confirmationSubtitle}>
                Please review the extracted data before processing. Markers with low
                confidence are highlighted for your attention.
              </p>
            </div>

            <div className={styles.confirmationSummary}>
              <div className={styles.summaryChip}>
                <span className={styles.summaryChipLabel}>Extracted</span>
                <span className={styles.summaryChipValue}>{extraction.summary.total_extracted}</span>
              </div>
              <div className={styles.summaryChip}>
                <span className={styles.summaryChipLabel}>Matched</span>
                <span className={styles.summaryChipValue}>{extraction.summary.matched}</span>
              </div>
              {Object.entries(extraction.summary.confidence_breakdown).map(([level, count]) => (
                <div key={level} className={`${styles.summaryChip} ${confidenceClass(level)}`}>
                  <span className={styles.summaryChipLabel}>{level}</span>
                  <span className={styles.summaryChipValue}>{count}</span>
                </div>
              ))}
            </div>

            {extraction.record.lab_provider && (
              <p className={styles.labProvider}>
                Lab: {extraction.record.lab_provider}
                {extraction.record.test_date && ` · ${extraction.record.test_date}`}
              </p>
            )}
          </div>

          {/* LOW confidence warning */}
          {extractedLow && extractedLow.length > 0 && (
            <div className={styles.warningBanner}>
              <strong>{extractedLow.length} marker{extractedLow.length > 1 ? "s" : ""} with LOW confidence</strong>
              {" — "}these could not be matched to known biomarkers and will be excluded from analysis.
            </div>
          )}

          <table className={styles.resultsTable}>
            <thead>
              <tr>
                <th>Marker</th>
                <th>Matched To</th>
                <th>Value</th>
                <th>Unit</th>
                <th>Lab Reference</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {extraction.markers.map((m, i) => (
                <tr
                  key={`${m.pdf_name}-${i}`}
                  className={m.confidence === "LOW" ? styles.rowLowConfidence : ""}
                >
                  <td>{m.pdf_name}</td>
                  <td className={styles.mono}>
                    {m.marker_name ?? <span className={styles.textMuted}>—</span>}
                  </td>
                  <td className={styles.mono}>{m.value}</td>
                  <td className={styles.mono}>{m.unit}</td>
                  <td className={styles.mono}>
                    {formatRefRange(m.ref_low, m.ref_high)}
                  </td>
                  <td>
                    <span className={`${styles.confidenceBadge} ${confidenceClass(m.confidence)}`}>
                      {m.confidence}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Unmatched markers (LOW confidence) listed separately */}
          {extractedLow && extractedLow.length > 0 && (
            <details className={styles.unmatched}>
              <summary>{extractedLow.length} unmatched marker{extractedLow.length > 1 ? "s" : ""} (excluded)</summary>
              <ul>
                {extractedLow.map((m, i) => (
                  <li key={i}>
                    <strong>{m.pdf_name}</strong>: {m.value} {m.unit}
                    {m.confidence_reasons.length > 0 && (
                      <span className={styles.textMuted}> — {m.confidence_reasons.join(", ")}</span>
                    )}
                  </li>
                ))}
              </ul>
            </details>
          )}

          <div className={styles.confirmationActions}>
            <button className={styles.cancelButton} onClick={reset}>
              Cancel
            </button>
            <button className={styles.confirmButton} onClick={confirmAndProcess}>
              Confirm & Process
            </button>
          </div>
        </>
      )}

      {/* ── Processing: Stage 2 in progress ── */}

      {status === "processing" && (
        <div className={styles.statusCard}>
          <p className={styles.statusText}>Processing {currentFile}...</p>
          <p className={styles.statusHint}>
            Normalising units, resolving reference ranges, and computing flags
          </p>
        </div>
      )}

      {/* ── Error ── */}

      {status === "error" && (
        <div className={styles.statusCard}>
          <p className={styles.errorText}>Failed to process PDF</p>
          <p className={styles.statusHint}>{errorMsg}</p>
          <button className={styles.retryButton} onClick={reset}>
            Try again
          </button>
        </div>
      )}

      {/* ── Done: Stage 2 enriched results ── */}

      {status === "done" && result && (
        <>
          <div className={styles.summaryBar}>
            <span className={styles.summaryFile}>{currentFile}</span>
            <span className={styles.summaryStats}>
              {matchedMarkers?.length} markers matched &middot;{" "}
              {flaggedMarkers?.length} flagged
            </span>
            <div className={styles.summaryActions}>
              {history.length > 1 && (
                <button
                  className={styles.historyToggle}
                  onClick={() => setShowHistory(!showHistory)}
                >
                  History ({history.length})
                </button>
              )}
              <button className={styles.uploadAnother} onClick={reset}>
                Upload new
              </button>
            </div>
          </div>

          {/* History dropdown when viewing results */}
          {showHistory && history.length > 0 && (
            <div className={styles.historyList}>
              {history.map((r) => (
                <button
                  key={r.file_hash}
                  className={`${styles.historyItem} ${
                    result.record.file_hash === r.file_hash ? styles.historyItemActive : ""
                  }`}
                  onClick={() => loadResult(r.file_hash, r.original_name)}
                >
                  <span className={styles.historyName}>{r.original_name}</span>
                  <span className={styles.historyMeta}>
                    {r.test_date && `${r.test_date} · `}
                    {r.matched ?? 0} markers
                    {r.flagged ? ` · ${r.flagged} flagged` : ""}
                  </span>
                </button>
              ))}
            </div>
          )}

          <table className={styles.resultsTable}>
            <thead>
              <tr>
                <th>Marker</th>
                <th>Value</th>
                <th>Unit</th>
                <th>Reference Range</th>
                <th>Flag</th>
              </tr>
            </thead>
            <tbody>
              {result.markers
                .filter((m) => m.marker_id !== null)
                .map((m) => (
                  <tr
                    key={m.marker_id}
                    className={
                      m.flag !== "OPTIMAL" ? styles.rowFlagged : ""
                    }
                  >
                    <td>{m.marker_name ?? m.pdf_name}</td>
                    <td className={styles.mono}>{m.std_value}</td>
                    <td className={styles.mono}>{m.std_unit}</td>
                    <td className={styles.mono}>
                      {formatRefRange(m.canonical_ref_low, m.canonical_ref_high)}
                    </td>
                    <td>
                      <span
                        className={
                          m.flag === "OPTIMAL"
                            ? styles.flagOptimal
                            : styles.flagAbnormal
                        }
                      >
                        {m.flag}
                      </span>
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

export default DataTab;
