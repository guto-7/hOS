import { useRef, useState, useCallback, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { NodeContentProps } from "../registry";
import styles from "./AnthropometryContent.module.css";

/* ── Types ── */

interface DeviationMetric {
  value: number;
  reference_low: number | null;
  reference_high: number | null;
  unit: string;
  flag: "Normal" | "Low" | "High" | "Critical" | "Info";
  deviation_fraction: number | null;
}

interface AnthropometryMarker {
  name: string;
  original_name: string | null;
  category: string | null;
  value: number;
  unit: string;
  original_value: number | null;
  original_unit: string | null;
  unit_converted: boolean;
  adjustment_note: string | null;
  canonical_tier: string | null;
  is_derived: boolean;
  evaluation_type: string | null;
  deviation: DeviationMetric;
}

interface PythonDomainScore {
  domain: string;
  label: string;
  score: number;
  grade: string;
  markers_used: string[];
  notes: string[];
}

interface PythonPhenotype {
  id: string;
  label: string;
  description: string;
  confidence: "high" | "moderate" | "low";
  contributing_signals: string[];
}

interface PythonSignal {
  id: string;
  label: string;
  detail: string;
  severity: "info" | "warning" | "concern";
  markers: string[];
}

interface PythonEvaluation {
  body_score: number;
  body_score_label: "Optimal" | "Good" | "Needs Attention" | "At Risk";
  domain_scores: PythonDomainScore[];
  phenotype: PythonPhenotype | null;
  signals: PythonSignal[];
  certainty_grade: "high" | "moderate" | "low" | "insufficient";
  certainty_note: string;
  missing_for_full_eval: string[];
}

interface AnthropometryData {
  markers: AnthropometryMarker[];
  validation: {
    status: string | { Warning: string } | { NeedsResolution: string };
    field_issues: { field: string; issue: string }[];
  };
  device: string | null;
  collection_date: string | null;
  python_evaluation: PythonEvaluation | null;
}

interface CertaintyGrade {
  grade: "High" | "Moderate" | "Low" | "Insufficient";
  confidence: number;
  missing_data: string[];
  incompleteness_impact: string;
}

interface EvaluationOutput {
  critical_flags: string[];
  categories: Record<string, string[]>;
  domain_scores: unknown[];
  condition_matches: unknown[];
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
  unified_data: AnthropometryData;
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

/* ── Tier display ── */

const TIER_DISPLAY: Record<string, [string, string]> = {
  underfat:              ["Low Body Fat",           "yellow"],
  healthy:               ["Healthy",               "green"],
  overfat:               ["Elevated Body Fat",      "orange"],
  obese:                 ["Obese",                 "red"],
  normal:                ["Normal",                "green"],
  sufficient:            ["Sufficient",            "green"],
  optimal:               ["Optimal",               "green"],
  symmetric:             ["Symmetric",             "green"],
  asymmetric:            ["Asymmetric",            "orange"],
  elevated:              ["Elevated",              "orange"],
  high_risk:             ["High Risk",             "red"],
  mild_imbalance:        ["Mild Imbalance",        "yellow"],
  significant_imbalance: ["Significant Imbalance", "red"],
  low:                   ["Low",                   "orange"],
  critically_low:        ["Critically Low",        "red"],
  high:                  ["High",                  "blue"],
  physiological_ceiling: ["Above Natural Ceiling", "red"],
  underweight:           ["Underweight",           "yellow"],
  overweight:            ["Overweight",            "orange"],
};

const COLOR_CLASS: Record<string, string> = {
  green:  styles.flagGreen,
  yellow: styles.flagYellow,
  orange: styles.flagOrange,
  red:    styles.flagRed,
  blue:   styles.flagBlue,
  grey:   styles.flagGrey,
};

function getFlagDisplay(m: AnthropometryMarker): [string, string] {
  const { flag } = m.deviation;
  if (flag === "Critical") return ["Critical", "red"];
  if (m.canonical_tier) {
    return TIER_DISPLAY[m.canonical_tier] ?? [
      m.canonical_tier.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      "grey",
    ];
  }
  if (flag === "Low")    return ["Low",    "orange"];
  if (flag === "High")   return ["High",   "orange"];
  if (flag === "Normal") return ["Normal", "green"];
  return ["—", "grey"];
}

function getRangeDisplay(m: AnthropometryMarker): string {
  const { reference_low: low, reference_high: high } = m.deviation;
  if (low === null && high === null) return "—";
  if (low === null)  return `< ${high}`;
  if (high === null) return `≥ ${low}`;
  return `${low} – ${high}`;
}

function hasResolvedRange(m: AnthropometryMarker): boolean {
  return (
    m.canonical_tier !== null ||
    m.deviation.reference_low !== null ||
    m.deviation.reference_high !== null
  );
}

function isConcerning(m: AnthropometryMarker): boolean {
  const { flag } = m.deviation;
  if (flag === "Critical" || flag === "Low" || flag === "High") return true;
  if (m.canonical_tier) {
    const [, color] = TIER_DISPLAY[m.canonical_tier] ?? ["", "grey"];
    return color === "red" || color === "orange" || color === "yellow";
  }
  return false;
}

/* ── Bucketing ── */

interface Buckets {
  evaluated: AnthropometryMarker[];
  unresolved: AnthropometryMarker[];
  raw: AnthropometryMarker[];
}

function bucketMarkers(markers: AnthropometryMarker[]): Buckets {
  const evaluated: AnthropometryMarker[] = [];
  const unresolved: AnthropometryMarker[] = [];
  const raw: AnthropometryMarker[] = [];
  for (const m of markers) {
    if (m.evaluation_type === "direct") {
      if (hasResolvedRange(m)) evaluated.push(m);
      else unresolved.push(m);
    } else {
      raw.push(m);
    }
  }
  return { evaluated, unresolved, raw };
}

/* ── Category grouping ── */

const CATEGORY_ORDER = [
  "Obesity Analysis",
  "Muscularity",
  "Fluid Analysis",
  "Cellular Health",
  "Segmental Analysis",
];

function groupByCategory(markers: AnthropometryMarker[]): [string, AnthropometryMarker[]][] {
  const grouped: Record<string, AnthropometryMarker[]> = {};
  for (const m of markers) {
    const cat = m.category ?? "Other";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(m);
  }
  const ordered: [string, AnthropometryMarker[]][] = [];
  for (const cat of CATEGORY_ORDER) {
    if (grouped[cat]) ordered.push([cat, grouped[cat]]);
  }
  for (const [cat, items] of Object.entries(grouped)) {
    if (!CATEGORY_ORDER.includes(cat)) ordered.push([cat, items]);
  }
  return ordered;
}

/* ── Domain score helpers ── */

const GRADE_COLOR: Record<string, string> = {
  // Legacy grade strings
  optimal:    styles.flagGreen,
  good:       styles.flagGreen,
  borderline: styles.flagYellow,
  poor:       styles.flagOrange,
  critical:   styles.flagRed,
  // New status labels (adiposity, muscularity, fluid health, metabolic health)
  Optimal:                    styles.flagGreen,
  Normal:                     styles.flagGreen,
  Good:                       styles.flagGreen,
  Moderate:                   styles.flagYellow,
  "Below Average":            styles.flagYellow,
  "Asymmetry Detected":       styles.flagYellow,
  "Cellular Health Concern":  styles.flagYellow,
  Low:                        styles.flagOrange,
  Elevated:                   styles.flagOrange,
  Suppressed:                 styles.flagOrange,
  "Mild Imbalance":           styles.flagOrange,
  "High Risk":                styles.flagRed,
  "Critically Low":           styles.flagRed,
  "Significant Imbalance":    styles.flagRed,
  "Above Natural Ceiling":    styles.flagRed,
  Critical:                   styles.flagRed,
};

const SEVERITY_COLOR: Record<string, string> = {
  info:    styles.flagBlue,
  warning: styles.flagYellow,
  concern: styles.flagOrange,
};

/* ── Component ── */

function AnthropometryContent({ onHistoryChange, onActiveLabel, historyRef, deleteRef, resetRef }: NodeContentProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [status, setStatus] = useState<ProcessingStatus>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [contract, setContract] = useState<OutputContract | null>(null);
  const [currentFile, setCurrentFile] = useState<string>("");
  const [history, setHistory] = useState<HistoryRecord[]>([]);

  // Profile state — optional; passed to pipeline for demographic adjustment
  const [profileSex, setProfileSex] = useState<"" | "male" | "female">("");
  const [profileAge, setProfileAge] = useState<string>("");
  const [profileHeight, setProfileHeight] = useState<string>("");

  // Refs so processFile always reads the latest values, regardless of closure age.
  // Updated SYNCHRONOUSLY in onChange handlers — not via useEffect — to avoid the
  // async-after-paint gap that could cause a stale value if the user changes sex and
  // immediately drops a file within the same browser frame.
  const profileSexRef = useRef<"" | "male" | "female">("");
  const profileAgeRef = useRef<string>("");
  const profileHeightRef = useRef<string>("");

  const loadHistory = useCallback(async () => {
    try {
      const jsonString = await invoke<string>("list_anthropometry");
      const records: HistoryRecord[] = JSON.parse(jsonString);
      setHistory(records);
      return records;
    } catch {
      return [];
    }
  }, []);

  const loadResult = useCallback(async (hash: string, fileName: string) => {
    try {
      const jsonString = await invoke<string>("load_anthropometry", { sourceHash: hash });
      const parsed: OutputContract = JSON.parse(jsonString);
      setContract(parsed);
      setCurrentFile(fileName);
      setStatus("done");
    } catch (err) {
      setErrorMsg(String(err));
      setStatus("error");
    }
  }, []);

  // Report history to parent whenever it changes
  useEffect(() => {
    onHistoryChange?.(
      history.map((r) => ({
        id: r.source_hash,
        label: r.original_name ?? "Unknown",
        detail: r.collection_date
          ? `${r.collection_date} · ${r.critical_flags_count > 0 ? `${r.critical_flags_count} critical` : "No critical flags"}`
          : r.critical_flags_count > 0 ? `${r.critical_flags_count} critical` : "No critical flags",
      }))
    );
  }, [history, onHistoryChange]);

  // Report active result label to parent
  useEffect(() => {
    if (contract?.produced_at) {
      const ts = Number(contract.produced_at);
      const d = ts > 0 ? new Date(ts * 1000) : new Date(contract.produced_at);
      onActiveLabel?.(isNaN(d.getTime()) ? null : d.toLocaleDateString());
    } else {
      onActiveLabel?.(null);
    }
  }, [contract, onActiveLabel]);

  // Expose loadResult to parent via ref
  useEffect(() => {
    if (historyRef) {
      historyRef.current = (id: string) => {
        const record = history.find((r) => r.source_hash === id);
        if (record) {
          loadResult(record.source_hash, record.original_name ?? "Unknown");
        }
      };
    }
  }, [historyRef, history, loadResult]);

  // Expose delete to parent via ref
  useEffect(() => {
    if (deleteRef) {
      deleteRef.current = async (id: string) => {
        await invoke("delete_anthropometry", { sourceHash: id });
        const records = await loadHistory();
        if (contract?.metadata.source_hash === id) {
          if (records.length > 0) {
            const latest = records[0];
            loadResult(latest.source_hash, latest.original_name ?? "Unknown");
          } else {
            setContract(null);
            setCurrentFile("");
            setStatus("idle");
          }
        }
      };
    }
  }, [deleteRef, loadHistory, loadResult, contract]);

  // Expose reset to parent via ref
  useEffect(() => {
    if (resetRef) {
      resetRef.current = reset;
    }
  });

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

    try {
      const arrayBuffer = await file.arrayBuffer();
      const bytes = Array.from(new Uint8Array(arrayBuffer));
      // Read from refs to guarantee latest values even if state update and file
      // drop race against each other.
      const currentSex = profileSexRef.current || null;
      const currentAge = profileAgeRef.current ? parseInt(profileAgeRef.current, 10) : null;
      const currentHeight = profileHeightRef.current ? parseFloat(profileHeightRef.current) : null;

      const jsonString = await invoke<string>("run_anthropometry", {
        fileName: file.name,
        fileBytes: bytes,
        sex: currentSex,
        age: currentAge && !isNaN(currentAge) ? currentAge : null,
        heightCm: currentHeight && !isNaN(currentHeight) ? currentHeight : null,
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

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    handleFiles(e.dataTransfer.files);
  }, [handleFiles]);

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
  };

  const allMarkers = contract?.unified_data.markers ?? [];
  const { evaluated, unresolved, raw } = bucketMarkers(allMarkers);
  const grouped = groupByCategory(evaluated);
  const criticalFlags = contract?.evaluation.critical_flags ?? [];
  const pyEval = contract?.unified_data.python_evaluation ?? null;

  return (
    <>
      {status === "loading" && (
        <div className={styles.statusCard}>
          <p className={styles.statusText}>Loading...</p>
        </div>
      )}

      {status === "idle" && (
        <>
          {/* Profile inputs */}
          <div className={styles.profileRow}>
            <label className={styles.profileField}>
              <span className={styles.profileLabel}>Sex</span>
              <select
                className={styles.profileSelect}
                value={profileSex}
                onChange={(e) => {
                  const val = e.target.value as "" | "male" | "female";
                  profileSexRef.current = val;
                  setProfileSex(val);
                }}
              >
                <option value="">—</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
              </select>
            </label>
            <label className={styles.profileField}>
              <span className={styles.profileLabel}>Age</span>
              <input
                type="number"
                className={styles.profileInput}
                placeholder="e.g. 32"
                min={1}
                max={120}
                value={profileAge}
                onChange={(e) => {
                  profileAgeRef.current = e.target.value;
                  setProfileAge(e.target.value);
                }}
              />
            </label>
            <label className={styles.profileField}>
              <span className={styles.profileLabel}>Height (cm)</span>
              <input
                type="number"
                className={styles.profileInput}
                placeholder="e.g. 175"
                min={50}
                max={250}
                value={profileHeight}
                onChange={(e) => {
                  profileHeightRef.current = e.target.value;
                  setProfileHeight(e.target.value);
                }}
              />
            </label>
            <span className={styles.profileHint}>Optional — improves range resolution and derived metrics</span>
          </div>

          <div
            className={`${styles.dropzone} ${isDragOver ? styles.dropzoneActive : ""}`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={handleClick}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") handleClick(); }}
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
              Drop your anthropometry PDF here, or{" "}
              <span className={styles.dropzoneLink}>browse files</span>
            </p>
            <p className={styles.dropzoneHint}>InBody, Tanita, or other BIA report PDFs</p>
          </div>
        </>
      )}

      {status === "processing" && (
        <div className={styles.statusCard}>
          <p className={styles.statusText}>Processing {currentFile}...</p>
          <p className={styles.statusHint}>Running import, unification, and evaluation pipeline</p>
        </div>
      )}

      {status === "error" && (
        <div className={styles.statusCard}>
          <p className={styles.errorText}>Failed to process PDF</p>
          <p className={styles.statusHint}>{errorMsg}</p>
          <button className={styles.retryButton} onClick={reset}>Try again</button>
        </div>
      )}

      {status === "done" && contract && (
        <>
          {criticalFlags.length > 0 && (
            <div className={styles.warningBanner}>
              <strong>{criticalFlags.length} critical flag{criticalFlags.length > 1 ? "s" : ""}:</strong>
              {" "}{criticalFlags.join(", ")}
            </div>
          )}

          {/* Stage 3 — Body Score headline */}
          {pyEval && pyEval.body_score != null && (
            <div className={styles.bodyScoreBar}>
              <div className={styles.bodyScoreContent}>
                <span className={styles.bodyScoreTitle}>Body Score</span>
                <div className={styles.bodyScoreLeft}>
                  <span className={styles.bodyScoreNum}>{pyEval.body_score}</span>
                  <span className={styles.bodyScoreSlash}> / 100</span>
                  <span className={`${styles.bodyScoreLabel} ${
                    pyEval.body_score >= 85 ? styles.flagGreen :
                    pyEval.body_score >= 70 ? styles.flagGreen :
                    pyEval.body_score >= 50 ? styles.flagOrange :
                    styles.flagRed
                  }`}>
                    {pyEval.body_score_label}
                  </span>
                </div>
              </div>
              {pyEval.certainty_grade === "low" || pyEval.certainty_grade === "insufficient" ? (
                <span className={styles.bodyScoreCaveat}>Limited data</span>
              ) : null}
            </div>
          )}

          {/* Stage 3 — Domain score cards */}
          {pyEval && pyEval.domain_scores.length > 0 && (
            <div className={styles.domainGrid}>
              {pyEval.domain_scores.map((d) => (
                <div key={d.domain} className={styles.domainCard}>
                  <div className={styles.domainCardHeader}>
                    <span className={styles.domainLabel}>{d.label}</span>
                    <span className={`${styles.domainGrade} ${GRADE_COLOR[d.grade] ?? styles.flagGrey}`}>
                      {d.grade}
                    </span>
                  </div>
                  {d.notes.length > 0 && (
                    <ul className={styles.domainNotes}>
                      {d.notes.slice(0, 3).map((n, i) => (
                        <li key={i} className={styles.domainNote}>{n}</li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Stage 3 — Phenotype */}
          {pyEval?.phenotype && (
            <div className={styles.phenotypeCard}>
              <div className={styles.phenotypeHeader}>
                <span className={styles.phenotypeLabel}>{pyEval.phenotype.label}</span>
                <span className={`${styles.phenotypeConfidence} ${
                  pyEval.phenotype.confidence === "high" ? styles.flagOrange :
                  pyEval.phenotype.confidence === "moderate" ? styles.flagYellow :
                  styles.flagGrey
                }`}>
                  {pyEval.phenotype.confidence} confidence
                </span>
              </div>
              <p className={styles.phenotypeDescription}>{pyEval.phenotype.description}</p>
              {pyEval.phenotype.contributing_signals.length > 0 && (
                <div className={styles.phenotypeSignals}>
                  {pyEval.phenotype.contributing_signals.map((s) => (
                    <span key={s} className={styles.phenotypeSignalTag}>{s}</span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Stage 3 — Signals */}
          {pyEval && pyEval.signals.length > 0 && (
            <div className={styles.signalsList}>
              {pyEval.signals.map((s) => (
                <div key={s.id} className={`${styles.signalItem} ${styles[`signal_${s.severity}`]}`}>
                  <div className={styles.signalHeader}>
                    <span className={`${styles.signalLabel} ${SEVERITY_COLOR[s.severity] ?? styles.flagGrey}`}>
                      {s.label}
                    </span>
                    <span className={styles.signalSeverity}>{s.severity}</span>
                  </div>
                  <p className={styles.signalDetail}>{s.detail}</p>
                </div>
              ))}
            </div>
          )}

          {/* Main evaluated table */}
          {evaluated.length > 0 && (
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
                {grouped.map(([category, categoryMarkers]) => (
                  <>
                    <tr key={`cat-${category}`} className={styles.categoryRow}>
                      <td colSpan={5} className={styles.categoryHeader}>{category}</td>
                    </tr>
                    {categoryMarkers.map((m, i) => {
                      const [flagLabel, flagColor] = getFlagDisplay(m);
                      return (
                        <tr
                          key={`${m.name}-${i}`}
                          className={isConcerning(m) ? styles.rowFlagged : ""}
                        >
                          <td>
                            <span className={styles.markerName}>{m.name}</span>
                            {m.is_derived && (
                              <span className={styles.derivedBadge}>computed</span>
                            )}
                          </td>
                          <td className={styles.mono}>{m.value}</td>
                          <td className={styles.mono}>{m.unit}</td>
                          <td
                            className={styles.mono}
                            title={m.adjustment_note ?? undefined}
                          >
                            {getRangeDisplay(m)}
                            {m.adjustment_note && (
                              <span className={styles.adjustmentDot} title={m.adjustment_note}>·</span>
                            )}
                          </td>
                          <td>
                            <span className={COLOR_CLASS[flagColor] ?? styles.flagGrey}>
                              {flagLabel}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </>
                ))}
              </tbody>
            </table>
          )}

          {/* Unresolved — needs patient context */}
          {unresolved.length > 0 && (
            <div className={styles.unresolvedSection}>
              <p className={styles.unresolvedTitle}>
                {unresolved.length} metric{unresolved.length > 1 ? "s" : ""} could not be evaluated
              </p>
              <p className={styles.unresolvedHint}>
                Age, sex, or height is required to resolve reference ranges for these metrics.
              </p>
              <div className={styles.unresolvedList}>
                {unresolved.map((m) => (
                  <span key={m.name} className={styles.unresolvedItem}>{m.name}</span>
                ))}
              </div>
            </div>
          )}

          {/* Raw measurements — always visible */}
          {raw.length > 0 && (
            <div className={styles.rawSection}>
              <p className={styles.rawSectionTitle}>Raw Measurements</p>
              <div className={styles.rawGrid}>
                {raw.map((m) => (
                  <div key={m.name} className={styles.rawItem}>
                    <span className={styles.rawName}>{m.name}</span>
                    <span className={styles.rawValue}>{m.value} {m.unit}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}

export default AnthropometryContent;
