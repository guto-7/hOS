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
  body_age: number | null;
  chronological_age: number | null;
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

/* ── Simplified flag system: Normal or Out of Range ── */

function isInRange(m: AnthropometryMarker): boolean {
  const { reference_low, reference_high } = m.deviation;
  const val = m.value;
  // Simple: if value is outside the reference range, it's out of range
  if (reference_low !== null && val < reference_low) return false;
  if (reference_high !== null && val > reference_high) return false;
  return true;
}

function getFlagDisplay(m: AnthropometryMarker): [string, string] {
  return isInRange(m) ? ["Normal", "green"] : ["Out of Range", "orange"];
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
  return !isInRange(m);
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

/* ── Component ── */

function AnthropometryContent({ onHistoryChange, onActiveLabel, historyRef, deleteRef, resetRef }: NodeContentProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [status, setStatus] = useState<ProcessingStatus>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [contract, setContract] = useState<OutputContract | null>(null);
  const [currentFile, setCurrentFile] = useState<string>("");
  const [history, setHistory] = useState<HistoryRecord[]>([]);

  // Trend data — marker values across all history records, keyed by marker name
  const [trendData, setTrendData] = useState<Record<string, { date: string; value: number }[]>>({});

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

  // Load trend data from all history records
  const loadTrends = useCallback(async (records: HistoryRecord[]) => {
    const trends: Record<string, { date: string; value: number }[]> = {};
    for (const r of records) {
      try {
        const json = await invoke<string>("load_anthropometry", { sourceHash: r.source_hash });
        const parsed: OutputContract = JSON.parse(json);
        const date = parsed.collection_date ?? parsed.produced_at ?? "";
        for (const m of parsed.unified_data.markers) {
          if (!trends[m.name]) trends[m.name] = [];
          trends[m.name].push({ date, value: m.value });
        }
      } catch { /* skip failed loads */ }
    }
    // Sort each marker's data by date
    for (const key of Object.keys(trends)) {
      trends[key].sort((a, b) => a.date.localeCompare(b.date));
    }
    setTrendData(trends);
  }, []);

  useEffect(() => {
    loadHistory().then((records) => {
      if (records.length > 0) {
        const latest = records[0];
        loadResult(latest.source_hash, latest.original_name ?? "Unknown");
        loadTrends(records);
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
      const records = await loadHistory();
      loadTrends(records);
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

      {status === "done" && contract && (() => {
        // Format date string (e.g. "13.12.2024" or "2024-12-13") to "Dec 2024"
        const fmtDate = (d: string): string => {
          // Try dd.mm.yyyy
          const dotMatch = d.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})/);
          if (dotMatch) {
            const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
            return `${months[parseInt(dotMatch[2], 10) - 1]} ${dotMatch[3]}`;
          }
          // Try yyyy-mm-dd
          const isoMatch = d.match(/^(\d{4})-(\d{2})/);
          if (isoMatch) {
            const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
            return `${months[parseInt(isoMatch[2], 10) - 1]} ${isoMatch[1]}`;
          }
          return d.slice(0, 10);
        };

        // Sparkline renderer with date/value labels
        const Sparkline = ({ points }: { points: { date: string; value: number }[] }) => {
          if (points.length < 2) return <span className={styles.trendEmpty}>—</span>;
          const vals = points.map((p) => p.value);
          const min = Math.min(...vals);
          const max = Math.max(...vals);
          const range = max - min || 1;
          const w = 160;
          const h = 48;
          const padX = 8;
          const padTop = 12;
          const padBot = 12;
          const chartH = h - padTop - padBot;

          const coords = vals.map((v, i) => ({
            x: padX + (i / (vals.length - 1)) * (w - padX * 2),
            y: padTop + chartH - ((v - min) / range) * chartH,
          }));
          const polyPts = coords.map((c) => `${c.x},${c.y}`).join(" ");
          const trending = vals[vals.length - 1] > vals[0] ? "up" : vals[vals.length - 1] < vals[0] ? "down" : "flat";
          const color = trending === "up" ? "var(--flag-optimal)" : trending === "down" ? "var(--flag-high)" : "var(--text-muted)";

          return (
            <svg viewBox={`0 0 ${w} ${h}`} className={styles.sparkline}>
              <polyline
                points={polyPts}
                fill="none"
                stroke={color}
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {points.map((p, i) => (
                <g key={i}>
                  <circle cx={coords[i].x} cy={coords[i].y} r="3" fill={color}>
                    <title>{`${fmtDate(p.date)}: ${p.value}`}</title>
                  </circle>
                  <text
                    x={coords[i].x}
                    y={coords[i].y - 5}
                    textAnchor="middle"
                    className={styles.sparklineLabel}
                  >
                    {p.value}
                  </text>
                  <text
                    x={coords[i].x}
                    y={h - 1}
                    textAnchor="middle"
                    className={styles.sparklineDate}
                  >
                    {fmtDate(p.date)}
                  </text>
                </g>
              ))}
            </svg>
          );
        };

        // Combine evaluated + raw for full marker table
        const allDisplayMarkers = [...evaluated, ...raw];

        return (
          <>
            {criticalFlags.length > 0 && (
              <div className={styles.warningBanner}>
                <strong>{criticalFlags.length} critical flag{criticalFlags.length > 1 ? "s" : ""}:</strong>
                {" "}{criticalFlags.join(", ")}
              </div>
            )}

            {/* ── Top section: Body Score + Body Age ────────── */}
            {pyEval && (
              <div className={styles.topGrid}>
                {/* Body Score gauge */}
                <div className={styles.scorePanel}>
                  <p className={styles.panelLabel}>Body Score</p>
                  {(() => {
                    const pct = pyEval.body_score;
                    const radius = 54;
                    const stroke = 10;
                    const circumference = 2 * Math.PI * radius;
                    const filled = (pct / 100) * circumference;
                    const gap = circumference - filled;
                    const scoreColor = pct >= 85
                      ? "var(--flag-optimal)"
                      : pct >= 70
                        ? "var(--flag-normal)"
                        : pct >= 50
                          ? "var(--flag-high)"
                          : "var(--flag-critical-high)";

                    return (
                      <div className={styles.gaugeContainer}>
                        <svg viewBox="0 0 128 128" className={styles.gaugeSvg}>
                          <circle
                            cx="64" cy="64" r={radius}
                            fill="none"
                            stroke="var(--bg-surface-raised)"
                            strokeWidth={stroke}
                          />
                          <circle
                            cx="64" cy="64" r={radius}
                            fill="none"
                            stroke={scoreColor}
                            strokeWidth={stroke}
                            strokeDasharray={`${filled} ${gap}`}
                            strokeDashoffset={circumference * 0.25}
                            strokeLinecap="round"
                          />
                          <text x="64" y="58" textAnchor="middle" className={styles.gaugeValue}>
                            {pct}
                          </text>
                          <text x="64" y="74" textAnchor="middle" className={styles.gaugeSubtext}>
                            / 100
                          </text>
                        </svg>
                        <span className={`${styles.gaugeLabel} ${
                          pct >= 70 ? styles.flagGreen : pct >= 50 ? styles.flagOrange : styles.flagRed
                        }`}>
                          {pyEval.body_score_label}
                        </span>
                      </div>
                    );
                  })()}
                </div>

                {/* Body Age */}
                <div className={styles.agePanel}>
                  <p className={styles.panelLabel}>Body Age</p>
                  {pyEval.body_age != null ? (
                    <div className={styles.ageContainer}>
                      <span className={styles.ageValue}>{pyEval.body_age}</span>
                      <span className={styles.ageUnit}>years</span>
                      {pyEval.chronological_age != null && (
                        <span className={`${styles.ageDelta} ${
                          pyEval.body_age < pyEval.chronological_age
                            ? styles.flagGreen
                            : pyEval.body_age > pyEval.chronological_age
                              ? styles.flagOrange
                              : styles.flagGrey
                        }`}>
                          {pyEval.body_age < pyEval.chronological_age
                            ? `${pyEval.chronological_age - pyEval.body_age}y younger`
                            : pyEval.body_age > pyEval.chronological_age
                              ? `${pyEval.body_age - pyEval.chronological_age}y older`
                              : "Matches actual age"}
                        </span>
                      )}
                      {pyEval.chronological_age != null && (
                        <span className={styles.ageActual}>
                          Actual age: {pyEval.chronological_age}
                        </span>
                      )}
                    </div>
                  ) : (
                    <p className={styles.ageUnavailable}>
                      Provide age in profile to calculate body age.
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* ── Marker table with trends ──────────────────── */}
            {allDisplayMarkers.length > 0 && (
              <table className={styles.resultsTable}>
                <thead>
                  <tr>
                    <th>Marker</th>
                    <th>Value</th>
                    <th>Unit</th>
                    <th>Reference Range</th>
                    <th>Flag</th>
                    <th>Trend</th>
                  </tr>
                </thead>
                <tbody>
                  {grouped.map(([category, categoryMarkers]) => (
                    <>
                      <tr key={`cat-${category}`} className={styles.categoryRow}>
                        <td colSpan={6} className={styles.categoryHeader}>{category}</td>
                      </tr>
                      {categoryMarkers.map((m, i) => {
                        const [flagLabel, flagColor] = getFlagDisplay(m);
                        const trend = trendData[m.name] ?? [];
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
                            <td className={styles.mono} title={m.adjustment_note ?? undefined}>
                              {getRangeDisplay(m)}
                              {m.adjustment_note && (
                                <span className={styles.adjustmentDot} title={m.adjustment_note}>·</span>
                              )}
                            </td>
                            <td>
                              <span className={flagColor === "green" ? styles.flagGreen : styles.flagOrange}>
                                {flagLabel}
                              </span>
                            </td>
                            <td>
                              <Sparkline points={trend} />
                            </td>
                          </tr>
                        );
                      })}
                    </>
                  ))}
                  {/* Raw measurements */}
                  {raw.length > 0 && (
                    <>
                      <tr className={styles.categoryRow}>
                        <td colSpan={6} className={styles.categoryHeader}>Raw Measurements</td>
                      </tr>
                      {raw.map((m, i) => {
                        const hasRange = m.deviation.reference_low !== null || m.deviation.reference_high !== null;
                        const [flagLabel, flagColor] = hasRange ? getFlagDisplay(m) : ["—", "grey"];
                        const trend = trendData[m.name] ?? [];
                        return (
                          <tr key={`raw-${m.name}-${i}`}>
                            <td><span className={styles.markerName}>{m.name}</span></td>
                            <td className={styles.mono}>{m.value}</td>
                            <td className={styles.mono}>{m.unit}</td>
                            <td className={styles.mono}>{hasRange ? getRangeDisplay(m) : "—"}</td>
                            <td>
                              <span className={flagColor === "green" ? styles.flagGreen : flagColor === "orange" ? styles.flagOrange : styles.flagGrey}>
                                {flagLabel}
                              </span>
                            </td>
                            <td><Sparkline points={trend} /></td>
                          </tr>
                        );
                      })}
                    </>
                  )}
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
                  Age, sex, or height is required to resolve reference ranges.
                </p>
                <div className={styles.unresolvedList}>
                  {unresolved.map((m) => (
                    <span key={m.name} className={styles.unresolvedItem}>{m.name}</span>
                  ))}
                </div>
              </div>
            )}
          </>
        );
      })()}
    </>
  );
}

export default AnthropometryContent;
