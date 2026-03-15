import { useRef, useState, useCallback, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { NodeContentProps } from "../registry";
import styles from "./HepatologyContent.module.css";

/* ── Types matching OutputContract / HepatologyData from Rust ── */

interface DeviationMetric {
  value: number;
  reference_low: number | null;
  reference_high: number | null;
  unit: string;
  flag: "Normal" | "Low" | "High" | "Critical";
  deviation_fraction: number | null;
}

interface HepatologyMarker {
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

interface HepatologyData {
  markers: HepatologyMarker[];
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
  unified_data: HepatologyData;
  evaluation: EvaluationOutput;
  metadata: ContractMetadata;
}

interface HistoryRecord {
  source_hash: string;
  original_name: string | null;
  collection_date: string | null;
  produced_at: string | null;
  node_id: string;
  critical_flags_count: number;
  certainty_grade: string;
}

interface CatalogMarker {
  id: string;
  name: string;
  category: string;
  unit: string;
  ranges: { low: number; high: number };
}

type ProcessingStatus = "loading" | "idle" | "processing" | "done" | "error";

/* ── Helpers ── */

function formatRefRange(low: number | null, high: number | null): string {
  if (low !== null && high !== null) return `${low} – ${high}`;
  if (low !== null) return `> ${low}`;
  if (high !== null) return `< ${high}`;
  return "—";
}

type DeviationTier = "green" | "yellow" | "red";

function deviationTier(d: DeviationMetric): DeviationTier {
  if (d.deviation_fraction === null || d.deviation_fraction === undefined)
    return "green";
  const abs = Math.abs(d.deviation_fraction);
  if (abs <= 0.25) return "yellow";
  return "red";
}

const TIER_COLOR: Record<DeviationTier, string> = {
  green: "var(--flag-optimal)",
  yellow: "var(--flag-high)",
  red: "var(--flag-critical-high)",
};

function deviationLabel(d: DeviationMetric): string {
  if (d.deviation_fraction === null || d.deviation_fraction === undefined)
    return "Normal";
  const abs = Math.abs(d.deviation_fraction);
  const isLow = d.deviation_fraction < 0;
  if (abs <= 0.25) return isLow ? "Low" : "High";
  return isLow ? "Critical Low" : "Critical High";
}

function RangeIndicator({ marker }: { marker: HepatologyMarker }) {
  const { value, reference_low: low, reference_high: high } = marker.deviation;
  if (low === null && high === null) return <div className={styles.rangeSlot} />;

  const h = 48;
  const w = 16;
  const pad = 4;
  const usable = h - pad * 2;

  // Derive effective bounds for one-sided ranges
  let refLow: number, refHigh: number;
  if (low !== null && high !== null) {
    refLow = low;
    refHigh = high;
  } else if (low !== null) {
    const span = Math.abs(low) * 0.3 || 1;
    refLow = low;
    refHigh = low + span;
  } else {
    const span = Math.abs(high!) * 0.3 || 1;
    refLow = high! - span;
    refHigh = high!;
  }

  const refSpan = (refHigh - refLow) || 1;
  const margin = refSpan * 0.15;
  const dLow = refLow - margin;
  const dHigh = refHigh + margin;

  const toY = (v: number) =>
    pad + usable * (1 - Math.max(0, Math.min(1, (v - dLow) / (dHigh - dLow))));

  const tier = deviationTier(marker.deviation);
  const dotColor = TIER_COLOR[tier];

  return (
    <svg width={w} height={h} className={styles.rangeIndicator}>
      <line
        x1={w / 2} y1={toY(refHigh)}
        x2={w / 2} y2={toY(refLow)}
        stroke={dotColor}
        strokeWidth={2}
        strokeLinecap="round"
      />
      <circle
        cx={w / 2}
        cy={toY(value)}
        r={3.5}
        fill={dotColor}
      />
    </svg>
  );
}

function scoreColor(score: number): string {
  if (score >= 75) return "var(--flag-optimal)";
  if (score >= 25) return "var(--flag-high)";
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
  const color = scoreColor(Math.round(score));

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

function DomainCard({
  title,
  composite,
  scores,
}: {
  title: string;
  composite: DomainScore | undefined;
  scores: DomainScore[];
}) {
  return (
    <div className={styles.categoryCard}>
      <div className={styles.categoryCardHeader}>{title}</div>

      {composite && (
        <div className={styles.compositeArea}>
          <CompositeScoreRing score={composite.score} label="" />
          <div className={styles.compositeDetail}>
            <span className={styles.compositeInterp}>{composite.interpretation}</span>
            {composite.components.length > 0 && (
              <div className={styles.compositeBreakdown}>
                {composite.components.map((c, i) => (
                  <span key={i} className={styles.breakdownChip}>{c}</span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {scores.length > 0 && (
        <div className={styles.scoreGrid}>
          {scores.map((s) => (
            <div key={s.system} className={styles.scoreRow}>
              <div className={styles.scoreRowHeader}>
                <span className={styles.scoreRowName}>{s.system}</span>
                <span className={styles.scoreRowValue}>{formatScore(s.score, s.system)}</span>
              </div>
              <p className={styles.scoreRowInterp}>{s.interpretation}</p>
              {s.components.length > 0 && (
                <span className={styles.scoreRowComponents}>
                  {s.components.join(" \u00b7 ")}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ConditionsCard({ conditions }: { conditions: ConditionMatch[] }) {
  return (
    <div className={styles.categoryCard}>
      <div className={styles.categoryCardHeader}>Conditions</div>
      {conditions.map((c) => (
        <div key={c.condition} className={styles.conditionRow}>
          <div className={styles.conditionRowHeader}>
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
              <span key={i} className={cr.met ? styles.criterionMet : styles.criterionUnmet}>
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
  );
}

/* ── Main Component ── */

function HepatologyContent({ onHistoryChange, onActiveLabel, historyRef, deleteRef, resetRef, importRef }: NodeContentProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<ProcessingStatus>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [contract, setContract] = useState<OutputContract | null>(null);
  const [currentFile, setCurrentFile] = useState<string>("");
  const [history, setHistory] = useState<HistoryRecord[]>([]);
  const [catalog, setCatalog] = useState<CatalogMarker[]>([]);

  const loadHistory = useCallback(async () => {
    try {
      const jsonString = await invoke<string>("list_hepatology");
      const records: HistoryRecord[] = JSON.parse(jsonString);
      setHistory(records);
      return records;
    } catch {
      return [];
    }
  }, []);

  const loadResult = useCallback(async (hash: string, fileName: string) => {
    try {
      const jsonString = await invoke<string>("load_hepatology", { sourceHash: hash });
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
        detail: (() => {
          let imported = "";
          if (r.produced_at) {
            const d = new Date(r.produced_at);
            if (!isNaN(d.getTime())) imported = d.toLocaleDateString();
          }
          const flags = r.critical_flags_count > 0
            ? `${r.critical_flags_count} critical`
            : "No critical flags";
          return imported ? `${imported} · ${flags}` : flags;
        })(),
      }))
    );
  }, [history, onHistoryChange]);

  // Report active result label (collection date) to parent
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
        await invoke("delete_hepatology", { sourceHash: id });
        const records = await loadHistory();
        // If we deleted the currently viewed result, switch to latest or idle
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

  // Expose file picker trigger to parent
  useEffect(() => {
    if (importRef) {
      importRef.current = () => fileInputRef.current?.click();
    }
  });

  useEffect(() => {
    // Load marker catalog for empty-state rendering
    invoke<string>("get_marker_catalog").then((json) => {
      try {
        const raw = JSON.parse(json) as CatalogMarker[];
        setCatalog(raw);
      } catch { /* ignore */ }
    }).catch(() => {});

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

      const jsonString = await invoke<string>("run_hepatology", {
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

  const reset = () => {
    setStatus("idle");
    setContract(null);
    setErrorMsg("");
    setCurrentFile("");
  };

  /* ── Derived data ── */

  const markers = contract?.unified_data.markers ?? [];
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

  // Build display markers: from contract if available, otherwise from catalog
  const displayMarkers: HepatologyMarker[] = contract
    ? markers
    : catalog.map((c) => ({
        name: c.name,
        original_name: null,
        category: c.category,
        value: 0,
        unit: c.unit,
        original_value: null,
        original_unit: null,
        unit_converted: false,
        adjustment_note: null,
        deviation: {
          value: 0,
          reference_low: c.ranges.low,
          reference_high: c.ranges.high,
          unit: c.unit,
          flag: "Normal" as const,
          deviation_fraction: null,
        },
      }));

  // Group markers by category
  const groupedMarkers: { category: string; markers: HepatologyMarker[] }[] = [];
  const categoryIndex = new Map<string, number>();
  for (const m of displayMarkers) {
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
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,application/pdf"
        className={styles.fileInput}
        onChange={(e) => handleFiles(e.target.files)}
      />

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

      {(status === "done" || status === "idle" || status === "loading") && (
        <div className={styles.splitLayout}>
          {/* ── Top Half: Evaluation Findings ── */}
          <div className={styles.evalPanel}>
            {criticalFlags.length > 0 && (
              <div className={styles.warningBanner}>
                <strong>{criticalFlags.length} critical flag{criticalFlags.length > 1 ? "s" : ""}:</strong>
                {" "}{criticalFlags.join(", ")}
              </div>
            )}

            <div className={styles.evalColumns}>
              <div className={styles.evalColumn}>
                <DomainCard
                  title="Longevity"
                  composite={getComposite("Longevity")}
                  scores={getScores("Longevity")}
                />
                <DomainCard
                  title="Metabolic"
                  composite={getComposite("Metabolic")}
                  scores={getScores("Metabolic")}
                />
              </div>
              <div className={styles.evalColumn}>
                <ConditionsCard conditions={conditionMatches as ConditionMatch[]} />
                <DomainCard
                  title="Hormonal"
                  composite={getComposite("Hormonal")}
                  scores={getScores("Hormonal")}
                />
              </div>
            </div>
          </div>

          {/* ── Bottom Half: Scrollable Marker Widgets ── */}
          <div className={styles.markersPanel}>
            <div className={styles.markersScroll}>
              {groupedMarkers.map((group) => (
                <div key={group.category} className={styles.categoryCard}>
                  <div className={styles.categoryCardHeader}>{group.category}</div>
                  {group.markers.map((m, i) => {
                    const hasData = !!contract;
                    const tier = hasData ? deviationTier(m.deviation) : "green";
                    const color = TIER_COLOR[tier];
                    return (
                      <div
                        key={`${group.category}-${m.name}-${i}`}
                        className={`${styles.markerWidget} ${hasData && tier !== "green" ? styles.markerWidgetFlagged : ""}`}
                        title={`${m.name}${hasData ? `: ${m.value} ${m.unit}` : ""} (ref: ${formatRefRange(m.deviation.reference_low, m.deviation.reference_high)})`}
                      >
                        <div className={styles.markerInfo}>
                          <span className={styles.markerName}>{m.name}</span>
                        </div>
                        <div className={styles.markerStatus}>
                          {hasData && (
                            <>
                              <span
                                className={styles.statusDot}
                                style={{ backgroundColor: color }}
                              />
                              <span className={styles.statusLabel} style={{ color }}>
                                {deviationLabel(m.deviation)}
                              </span>
                            </>
                          )}
                        </div>
                        <div className={styles.markerValue}>
                          {hasData && (
                            <>
                              <span className={styles.valueNumber}>{m.value}</span>
                              <span className={styles.valueUnit}>{m.unit}</span>
                            </>
                          )}
                          {!hasData && (
                            <span className={styles.valueUnit}>{m.unit}</span>
                          )}
                        </div>
                        <span className={styles.markerRefRange}>
                          {formatRefRange(m.deviation.reference_low, m.deviation.reference_high)}
                        </span>
                        <RangeIndicator marker={m} />
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default HepatologyContent;
