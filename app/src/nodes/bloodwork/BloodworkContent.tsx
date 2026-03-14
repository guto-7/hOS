import { useRef, useState, useCallback, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import styles from "./BloodworkContent.module.css";

/* ── Types matching OutputContract / BloodworkData from Rust ── */

interface DeviationMetric {
  value: number;
  reference_low: number | null;
  reference_high: number | null;
  unit: string;
  flag: "Normal" | "Low" | "High" | "Critical";
  deviation_fraction: number | null;
}

interface BloodworkMarker {
  name: string;
  original_name: string | null;
  category: string | null;
  value: number;
  unit: string;
  original_value: number | null;
  original_unit: string | null;
  unit_converted: boolean;
  adjustment_note: string | null;
  deviation: DeviationMetric;
}

interface BloodworkData {
  markers: BloodworkMarker[];
  validation: {
    status: string | { Warning: string } | { NeedsResolution: string };
    field_issues: { field: string; issue: string }[];
  };
  lab_provider: string | null;
  collection_date: string | null;
}

interface DomainScore {
  domain: string;
  system: string;
  score: number;
  interpretation: string;
  components: string[];
  version: string;
}

interface CriterionResult {
  criterion: string;
  met: boolean;
  observed: string | null;
  expected: string;
}

interface CertaintyGrade {
  grade: "High" | "Moderate" | "Low" | "Insufficient";
  confidence: number;
  missing_data: string[];
  incompleteness_impact: string;
}

interface ConditionMatch {
  condition: string;
  criteria: CriterionResult[];
  certainty: CertaintyGrade;
}

interface EvaluationOutput {
  critical_flags: string[];
  categories: Record<string, string[]>;
  domain_scores: DomainScore[];
  condition_matches: ConditionMatch[];
  certainty: CertaintyGrade;
  engine_versions: Record<string, string>;
}

interface ContractMetadata {
  source_hash: string | null;
  original_name: string | null;
  engine_versions: Record<string, string>;
  processing_notes: string[];
}

interface OutputContract {
  node_id: string;
  schema_version: string;
  produced_at: string;
  collection_date: string | null;
  unified_data: BloodworkData;
  evaluation: EvaluationOutput;
  metadata: ContractMetadata;
}

interface HistoryRecord {
  source_hash: string;
  original_name: string | null;
  collection_date: string | null;
  node_id: string;
  critical_flags_count: number;
  certainty_grade: string;
}

type ProcessingStatus = "loading" | "idle" | "processing" | "done" | "error";

/* ── Helpers ── */

function formatRefRange(low: number | null, high: number | null): string {
  if (low !== null && high !== null) return `${low} – ${high}`;
  if (low !== null) return `> ${low}`;
  if (high !== null) return `< ${high}`;
  return "—";
}

function flagClass(flag: string, s: typeof styles): string {
  if (flag === "Critical") return s.flagCritical;
  if (flag === "High" || flag === "Low") return s.flagAbnormal;
  return s.flagOptimal;
}

function scoreColor(score: number): string {
  if (score >= 80) return "var(--flag-normal)";
  if (score >= 60) return "var(--flag-optimal)";
  if (score >= 40) return "var(--flag-high)";
  return "var(--flag-critical-high)";
}

function formatScore(score: number, system: string): string {
  // Composite scores are 0-100
  if (system.endsWith("Health") || system === "Longevity Optimals") {
    return `${Math.round(score)}`;
  }
  // PhenoAge shows years
  if (system === "PhenoAge") return score.toFixed(1);
  // Allostatic load is integer
  if (system === "Allostatic Load") return `${Math.round(score)}`;
  // Most others show 1-2 decimals
  if (Number.isInteger(score)) return `${score}`;
  return score.toFixed(2);
}

/* ── Evaluation Sub-components ── */

function CompositeScoreRing({ score, label }: { score: number; label: string }) {
  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = scoreColor(score);

  return (
    <div className={styles.ringContainer}>
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle
          cx="36" cy="36" r={radius}
          fill="none"
          stroke="var(--border-color)"
          strokeWidth="5"
        />
        <circle
          cx="36" cy="36" r={radius}
          fill="none"
          stroke={color}
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 36 36)"
        />
        <text
          x="36" y="36"
          textAnchor="middle"
          dominantBaseline="central"
          fill="var(--text-primary)"
          fontSize="16"
          fontWeight="600"
        >
          {Math.round(score)}
        </text>
      </svg>
      <span className={styles.ringLabel}>{label}</span>
    </div>
  );
}

function DomainSection({
  title,
  composite,
  scores,
}: {
  title: string;
  composite: DomainScore | undefined;
  scores: DomainScore[];
}) {
  if (scores.length === 0 && !composite) return null;

  return (
    <div className={styles.domainSection}>
      <div className={styles.domainHeader}>
        {composite && (
          <CompositeScoreRing score={composite.score} label={title} />
        )}
        {!composite && <span className={styles.domainTitle}>{title}</span>}
        {composite && (
          <span className={styles.domainInterp}>{composite.interpretation}</span>
        )}
      </div>
      <div className={styles.scoreGrid}>
        {scores.map((s) => (
          <div key={s.system} className={styles.scoreCard}>
            <div className={styles.scoreCardHeader}>
              <span className={styles.scoreSystem}>{s.system}</span>
              <span className={styles.scoreValue}>{formatScore(s.score, s.system)}</span>
            </div>
            <p className={styles.scoreInterp}>{s.interpretation}</p>
            <span className={styles.scoreVersion}>{s.version}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ConditionsPanel({ conditions }: { conditions: ConditionMatch[] }) {
  if (conditions.length === 0) return null;

  return (
    <div className={styles.conditionsSection}>
      <h3 className={styles.evalSectionTitle}>Conditions Detected</h3>
      <div className={styles.conditionsList}>
        {conditions.map((c) => (
          <div key={c.condition} className={styles.conditionCard}>
            <div className={styles.conditionHeader}>
              <span className={styles.conditionName}>{c.condition}</span>
              <span className={`${styles.conditionCertainty} ${
                c.certainty.grade === "High"
                  ? styles.certaintyHigh
                  : c.certainty.grade === "Moderate"
                  ? styles.certaintyMod
                  : styles.certaintyLow
              }`}>
                {c.certainty.grade}
              </span>
            </div>
            <div className={styles.criteriaList}>
              {c.criteria.map((cr, i) => (
                <span key={i} className={styles.criterionChip}>
                  {cr.met ? "\u2713" : "\u2717"} {cr.criterion}
                  {cr.observed && (
                    <span className={styles.criterionObs}> ({cr.observed})</span>
                  )}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Main Component ── */

function BloodworkContent() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [status, setStatus] = useState<ProcessingStatus>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [contract, setContract] = useState<OutputContract | null>(null);
  const [currentFile, setCurrentFile] = useState<string>("");
  const [history, setHistory] = useState<HistoryRecord[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  const loadHistory = useCallback(async () => {
    try {
      const jsonString = await invoke<string>("list_bloodwork");
      const records: HistoryRecord[] = JSON.parse(jsonString);
      setHistory(records);
      return records;
    } catch {
      return [];
    }
  }, []);

  const loadResult = useCallback(async (hash: string, fileName: string) => {
    try {
      const jsonString = await invoke<string>("load_bloodwork", { sourceHash: hash });
      const parsed: OutputContract = JSON.parse(jsonString);
      setContract(parsed);
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
        const latest = records[0];
        loadResult(latest.source_hash, latest.original_name ?? "Unknown");
      } else {
        setStatus("idle");
      }
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const processFile = useCallback(async (file: File) => {
    setStatus("processing");
    setErrorMsg("");
    setCurrentFile(file.name);
    setContract(null);
    setShowHistory(false);

    try {
      const arrayBuffer = await file.arrayBuffer();
      const bytes = Array.from(new Uint8Array(arrayBuffer));

      const jsonString = await invoke<string>("run_bloodwork", {
        fileName: file.name,
        fileBytes: bytes,
        sex: null,
        age: null,
        pregnant: null,
        cyclePhase: null,
        fasting: null,
      });

      const parsed: OutputContract = JSON.parse(jsonString);
      setContract(parsed);
      setStatus("done");
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
    setContract(null);
    setErrorMsg("");
    setCurrentFile("");
    setShowHistory(false);
  };

  /* ── Derived data ── */

  const markers = contract?.unified_data.markers ?? [];
  const flaggedMarkers = markers.filter((m) => m.deviation.flag !== "Normal");
  const criticalFlags = contract?.evaluation.critical_flags ?? [];
  const domainScores = contract?.evaluation.domain_scores ?? [];
  const conditionMatches = contract?.evaluation.condition_matches ?? [];

  // Separate composites from individual scores
  const composites = domainScores.filter(
    (s) => s.system.endsWith("Health") || s.system === "Longevity"
  );
  const individualScores = domainScores.filter(
    (s) => !s.system.endsWith("Health") && s.system !== "Longevity"
  );

  const getComposite = (domain: string) =>
    composites.find((c) => c.domain === domain);
  const getScores = (domain: string) =>
    individualScores.filter((s) => s.domain === domain);

  // Group markers by category
  const groupedMarkers: { category: string; markers: BloodworkMarker[] }[] = [];
  const categoryIndex = new Map<string, number>();
  for (const m of markers) {
    const cat = m.category ?? "Other";
    const idx = categoryIndex.get(cat);
    if (idx !== undefined) {
      groupedMarkers[idx].markers.push(m);
    } else {
      categoryIndex.set(cat, groupedMarkers.length);
      groupedMarkers.push({ category: cat, markers: [m] });
    }
  }

  return (
    <>
      {status === "loading" && (
        <div className={styles.statusCard}>
          <p className={styles.statusText}>Loading...</p>
        </div>
      )}

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
                  key={r.source_hash}
                  className={styles.historyItem}
                  onClick={() => loadResult(r.source_hash, r.original_name ?? "Unknown")}
                >
                  <span className={styles.historyName}>{r.original_name ?? "Unknown"}</span>
                  <span className={styles.historyMeta}>
                    {r.collection_date && `${r.collection_date} · `}
                    {r.critical_flags_count > 0
                      ? `${r.critical_flags_count} critical`
                      : "No critical flags"}
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

      {status === "processing" && (
        <div className={styles.statusCard}>
          <p className={styles.statusText}>Processing {currentFile}...</p>
          <p className={styles.statusHint}>
            Running import, unification, and evaluation pipeline
          </p>
        </div>
      )}

      {status === "error" && (
        <div className={styles.statusCard}>
          <p className={styles.errorText}>Failed to process PDF</p>
          <p className={styles.statusHint}>{errorMsg}</p>
          <button className={styles.retryButton} onClick={reset}>
            Try again
          </button>
        </div>
      )}

      {status === "done" && contract && (
        <div className={styles.splitLayout}>
          {/* ── Top Half: Evaluation Findings ── */}
          <div className={styles.evalPanel}>
            <div className={styles.summaryBar}>
              <span className={styles.summaryFile}>{currentFile}</span>
              <span className={styles.summaryStats}>
                {markers.length} markers &middot;{" "}
                {flaggedMarkers.length} flagged
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

            {showHistory && history.length > 0 && (
              <div className={styles.historyList}>
                {history.map((r) => (
                  <button
                    key={r.source_hash}
                    className={`${styles.historyItem} ${
                      contract.metadata.source_hash === r.source_hash ? styles.historyItemActive : ""
                    }`}
                    onClick={() => loadResult(r.source_hash, r.original_name ?? "Unknown")}
                  >
                    <span className={styles.historyName}>{r.original_name ?? "Unknown"}</span>
                    <span className={styles.historyMeta}>
                      {r.collection_date && `${r.collection_date} · `}
                      {r.critical_flags_count > 0
                        ? `${r.critical_flags_count} critical`
                        : "No critical flags"}
                    </span>
                  </button>
                ))}
              </div>
            )}

            {criticalFlags.length > 0 && (
              <div className={styles.warningBanner}>
                <strong>{criticalFlags.length} critical flag{criticalFlags.length > 1 ? "s" : ""}:</strong>
                {" "}{criticalFlags.join(", ")}
              </div>
            )}

            {/* Domain composite rings */}
            {composites.length > 0 && (
              <div className={styles.compositeRow}>
                {composites.map((c) => (
                  <CompositeScoreRing key={c.system} score={c.score} label={c.domain} />
                ))}
              </div>
            )}

            {/* Conditions */}
            <ConditionsPanel conditions={conditionMatches as ConditionMatch[]} />

            {/* Domain sections */}
            <DomainSection
              title="Metabolic"
              composite={getComposite("Metabolic")}
              scores={getScores("Metabolic")}
            />
            <DomainSection
              title="Longevity"
              composite={getComposite("Longevity")}
              scores={getScores("Longevity")}
            />
            <DomainSection
              title="Hormonal"
              composite={getComposite("Hormonal")}
              scores={getScores("Hormonal")}
            />
          </div>

          {/* ── Bottom Half: Scrollable Markers Table ── */}
          <div className={styles.markersPanel}>
            <h3 className={styles.markersPanelTitle}>Blood Markers</h3>
            <div className={styles.markersScroll}>
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
                  {groupedMarkers.map((group) => (
                    <>
                      <tr key={`group-${group.category}`} className={styles.groupHeader}>
                        <td colSpan={5}>{group.category}</td>
                      </tr>
                      {group.markers.map((m, i) => (
                        <tr
                          key={`${group.category}-${m.name}-${i}`}
                          className={
                            m.deviation.flag !== "Normal" ? styles.rowFlagged : ""
                          }
                        >
                          <td>{m.name}</td>
                          <td className={styles.mono}>{m.value}</td>
                          <td className={styles.mono}>{m.unit}</td>
                          <td className={styles.mono}>
                            {formatRefRange(m.deviation.reference_low, m.deviation.reference_high)}
                          </td>
                          <td>
                            <span className={flagClass(m.deviation.flag, styles)}>
                              {m.deviation.flag}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default BloodworkContent;
