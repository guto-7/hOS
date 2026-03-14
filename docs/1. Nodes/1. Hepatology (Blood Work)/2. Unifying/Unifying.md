# Bloodwork — Stage 2: Unifying

## Purpose

Stage 2 transforms the raw extracted data from Stage 1 into a standardised, enriched format. It handles unit normalisation, reference range resolution, flag computation, and produces the exact feature set that Stage 3's ML classifiers will consume. Every design decision in Stage 2 is made with one question: "What does the ML model need to make accurate classifications?"

---

## 2.1 Design Principle

> **Store facts, compute everything else.**

The PDF gives us facts: marker values, units, lab-printed reference ranges. Everything else — canonical name, category, flag, deviation — is **computed at read time** from `markers.json` + the global user profile.

**Why this principle matters:**
- If we store computed fields (flags, ranges), they go stale when the user updates their global profile (e.g., corrects their sex, enters pregnancy status)
- If we store computed fields, we need migration logic every time the computation changes
- By computing at read time, we guarantee consistency: same raw value + same context + same markers.json = same output, always
- This is critical for Stage 3: ML classifiers are sensitive to inconsistent features. Stale or drift-prone data corrupts both training and inference.

---

## 2.2 The Alignment Contract: markers.json

**Decision: A single JSON file is the source of truth for every marker the system recognises**

`markers.json` serves three roles across all three stages:

| Role | Stage | How |
|---|---|---|
| **PDF parsing** | Stage 1 (Importing) | `aliases[]` map whatever the lab prints ("Hb", "HGB", "Haemoglobin") to a canonical ID |
| **Unit normalisation & flagging** | Stage 2 (Unifying) | `unit_conversions[]` and `ranges` standardise and evaluate every value |
| **Training data alignment** | Stage 3 (Evaluating) | The ML model sees markers in the exact same shape at training time and inference time |

### Why JSON and not a database table?

| Option | Verdict | Reasoning |
|---|---|---|
| Cloud DB (Supabase, Firebase) | Rejected | Breaks local-first privacy promise. Adds network dependency for reference data that never changes at runtime. |
| SQLite table | Rejected | Marker definitions are static reference data, not user data. They don't benefit from SQL queries, transactions, or indexing. Adding SQL overhead for a 62-row lookup table is unnecessary complexity. |
| CSV/tabular | Rejected | Markers have **variable, nested structure** — some have pregnancy ranges, some have tiers, some have age brackets, some have unit conversions. A flat table either wastes columns (mostly empty) or forces structured data into pipe-delimited strings — which is just worse JSON. |
| **Single JSON file** | **Chosen** | Ships with the app binary. Loads into memory on startup (~15KB). Version-controlled in git. Trivially testable. Identical data available at training time and runtime. Nested structures (age brackets, tiers, sex-stratified ranges) are natural in JSON. |

### Schema (62 markers)

Every marker has 6 core fields:

```json
{
  "id": "Hb",
  "name": "Haemoglobin (Hb)",
  "category": "CBC",
  "aliases": ["Hb", "Haemoglobin", "Hemoglobin", "HGB"],
  "unit": "g/L",
  "unit_conversions": [{ "from": "g/dL", "multiply": 10 }],
  "ranges": {
    "male": { "low": 140, "high": 180 },
    "female": { "low": 120, "high": 160 }
  }
}
```

Optional fields present only when needed:

| Field | When Present | Count | Example |
|---|---|---|---|
| `pregnancy_range` | Marker range changes in pregnancy | ~13 | Potassium, Creatinine, ALP, Hb |
| `tiers` | Flags beyond LOW/NORMAL/HIGH | ~10 | Vitamin D, hsCRP, HbA1c, Ferritin |
| `alert_thresholds` | Critical values needing urgent flags | ~5 | Sodium, Potassium, Calcium |
| `calculated_from` + `calculation` | Derived from other markers | ~5 | eGFR, Adjusted Calcium |
| `applicable_sex` | Marker only applies to one sex | ~2 | PSA |

### Range Structure Examples

**Simple (no sex difference):**
```json
"ranges": { "low": 136, "high": 145 }
```

**Sex-differentiated:**
```json
"ranges": {
  "male": { "low": 140, "high": 180 },
  "female": { "low": 120, "high": 160 }
}
```

**Age-stratified:**
```json
"ranges": {
  "16-24": { "low": 182, "high": 780 },
  "25-39": { "low": 114, "high": 492 },
  "40-54": { "low": 90, "high": 360 },
  "55+": { "low": 71, "high": 290 }
}
```

**With tiers:**
```json
"ranges": { "low": 50, "high": 200 },
"tiers": {
  "optimal": { "low": 75, "high": 150 },
  "sufficient": { "low": 50, "high": 75 },
  "insufficient": { "low": 30, "high": 50 }
}
```

**With pregnancy override:**
```json
"ranges": {
  "male": { "low": 62, "high": 115 },
  "female": { "low": 44, "high": 97 }
},
"pregnancy_range": { "low": 30, "high": 70 }
```

The shape of the `ranges` value tells the code what resolution to perform — no `range_type` enum needed.

---

## 2.3 Processing Pipeline

After the user confirms their data in Stage 1:

```
Confirmed raw data (results table)
  │
  ├─→ 1. Alias resolution
  │     Map extracted marker name → canonical ID via markers.json aliases[]
  │     "HGB" → "Hb", "eGFR (CKD-EPI)" → "eGFR"
  │
  ├─→ 2. Unit normalisation
  │     If extracted unit ≠ markers.json primary unit, apply conversion
  │     e.g., Hb: 10.8 g/dL × 10 = 108 g/L
  │     Both original and standardised values are preserved
  │
  ├─→ 3. Range resolution (resolve_range function)
  │     Input: marker ID + global user profile (sex, age, pregnant, cycle_phase)
  │     Resolution order:
  │       a. If pregnant AND pregnancy_range exists → use pregnancy_range
  │       b. If ranges has age brackets → find bracket containing user age
  │       c. If ranges has sex keys → select by user sex
  │       d. If ranges is direct {low, high} → use as-is
  │     Output: { low, high, adjustment_note }
  │
  ├─→ 4. Flag computation (compute_flag function)
  │     Priority order:
  │       a. Alert thresholds → CRITICAL_LOW / CRITICAL_HIGH
  │       b. Tiers → OPTIMAL / SUFFICIENT / INSUFFICIENT / ABOVE_OPTIMAL
  │       c. Standard → LOW / NORMAL / HIGH
  │
  ├─→ 5. Deviation calculation
  │     How far out of range, as a percentage
  │     e.g., Hb 108 g/L with range 140–180 → "23% below lower limit"
  │
  └─→ Output: enriched marker data ready for display and Stage 3 ML input
```

### Why this order matters

Each step depends on the previous step's output. This is a strict sequential pipeline:

1. **Alias resolution first** — without a canonical ID, we can't look up units or ranges
2. **Unit normalisation before range resolution** — comparing a g/dL value against a g/L range produces wrong flags
3. **Range resolution before flag computation** — the flag depends on which range applies to this specific user
4. **Flag computation before deviation** — deviation measures distance from the resolved range boundaries

---

## 2.4 Storage Schema: SQLite

**Decision: Minimal SQLite with 2 core tables. Store facts only, compute everything else.**

```sql
records (
  id              TEXT PRIMARY KEY,
  test_date       DATE,
  lab_provider    TEXT,
  pdf_hash        TEXT UNIQUE,   -- SHA-256, deduplication
  pdf_path        TEXT,          -- path to stored PDF
  original_name   TEXT,          -- original filename for display
  imported_at     TIMESTAMP
)

results (
  id                      TEXT PRIMARY KEY,
  record_id               TEXT REFERENCES records(id),
  marker_id               TEXT,       -- canonical ID from markers.json
  value                   REAL,       -- standardised value (after unit conversion)
  unit                    TEXT,       -- standardised unit
  original_value          REAL,       -- as extracted from PDF
  original_unit           TEXT,       -- as extracted from PDF
  lab_ref_low             REAL,       -- what the lab printed
  lab_ref_high            REAL,       -- what the lab printed
  lab_flag                TEXT,       -- what the lab printed
  raw_text                TEXT,       -- original string for auditability
  extraction_confidence   TEXT        -- HIGH / MEDIUM / LOW
)
```

Patient context (sex, DOB, fasting, pregnancy, cycle phase) is stored in the **global user profile** at the app level, not in these tables. Range resolution and flag computation pull from the global profile at read time.

### What's NOT stored (and why)

| Field | Why Not Stored | Computed From |
|---|---|---|
| `canonical_name` | Derived from marker_id | `markers.json[marker_id].name` |
| `category` | Derived from marker_id | `markers.json[marker_id].category` |
| `reference_range` (canonical) | Changes if user profile is updated | `resolve_range(marker_id, global_user_profile)` |
| `flag` | Depends on canonical range | `compute_flag(value, resolved_range, tiers)` |
| `deviation` | Depends on canonical range | `compute_deviation(value, resolved_range)` |
| `age` | Goes stale over time | `today - DOB` from global profile |

**Why not store flags?** If the user updates their global profile (corrects sex, enters pregnancy), every sex/pregnancy-stratified marker needs different reference ranges and different flags. Because flags are computed at read time, updates are instant — no migration, no stale data.

### Why dual reference ranges (lab-printed vs canonical)?

| Purpose | Which Range | Reasoning |
|---|---|---|
| **User display** | Lab-printed | The user sees the range from their paper report. Builds trust — "the app shows what my lab showed." |
| **Flag computation & ML input** | Canonical (markers.json) | The ML model is trained on canonical ranges. Lab-specific ranges vary slightly between providers — canonical ranges ensure consistency across all uploads. |
| **Cross-check** | Both | If the lab flagged HIGH but canonical says NORMAL (or vice versa), surface the discrepancy to the user. Transparency over silent override. |

### Why SQLite?

| Option | Verdict | Reasoning |
|---|---|---|
| Cloud database | Rejected | Breaks local-first privacy. Health data never leaves the device. |
| Plain JSON files | Rejected | No relational queries. Can't efficiently join records with results or query by date range. Doesn't scale with years of uploads. |
| **SQLite** | **Chosen** | Single-file database. No server process. Fully local. Supports relational queries (join records with results). Most deployed database in the world. Easily backed up (copy one file). SQLCipher extension available for encryption at rest. |
| IndexedDB (browser) | Rejected | Tauri app runs natively, not in a browser sandbox. SQLite offers better performance, encryption options, and direct filesystem access. |

---

## 2.5 Output Format: Enriched JSON for Stage 3

**Decision: The processed output is a JSON object matching the exact shape the ML classifiers will consume**

```json
{
  "blood_panel": [
    {
      "marker": "Haemoglobin (Hb)",
      "marker_id": "Hb",
      "category": "CBC",
      "value": 108,
      "unit": "g/L",
      "reference_range": { "low": 140, "high": 180 },
      "flag": "LOW",
      "deviation": "23% below lower limit"
    },
    {
      "marker": "Ferritin",
      "marker_id": "Ferr",
      "category": "Iron Studies",
      "value": 8,
      "unit": "µg/L",
      "reference_range": { "low": 30, "high": 400 },
      "flag": "LOW",
      "deviation": "73% below lower limit"
    }
  ]
}
```

Patient context is **not** embedded per-panel — it's available globally to Stage 3 from the user profile.

### Why each field is included

| Field | Why Included | Stage 3 Relevance |
|---|---|---|
| `marker_id` | Canonical identifier | Join key to condition definitions. The ML model maps marker_id to its learned feature weights. |
| `value` + `unit` | Standardised measurement | Numeric input feature for the classifier. Must be in consistent units across all training and inference data. |
| `reference_range` | Resolved range for this user | The model needs to know what "normal" means for this specific user to reason about severity. |
| `flag` | Categorical label (LOW/NORMAL/HIGH/CRITICAL/tiered) | Can be one-hot encoded as additional features. Gives the model both the raw value and its clinical interpretation. |
| `deviation` | Percentage out of range | Continuous severity signal. Ferritin at 73% below is very different from 5% below — both are "LOW" but the clinical significance differs enormously. |
| `category` | Marker grouping | Organises markers for analysis (CBC together, Iron Studies together). Useful for feature grouping in the model. |

### Why JSON for the ML input?

| Format | Verdict | Reasoning |
|---|---|---|
| CSV/tabular | Rejected | Loses nested structure (reference_range is two values). Flattening adds redundancy and parsing ambiguity. |
| **JSON** | **Chosen** | Natural nesting. Self-describing (field names present). Identical to training data shape. No parsing ambiguity. Supported by every ML framework (Python's `json.load()` → dictionary → DataFrame). |

---

## 2.6 How Stage 2 Connects to Stage 3 (Evaluating)

Stage 3 trains traditional ML classifiers (e.g., Random Forest) per condition. Each model is trained on labelled datasets of blood panels where the condition outcome is clinically known. The model learns which marker patterns predict the condition from factual, predefined examples — it classifies based on ground truth, not probability.

### What Stage 3 needs from Stage 2

| Requirement | How Stage 2 Provides It |
|---|---|
| **Consistent numeric features** | Every marker has a standardised `value` in a consistent `unit`. A Random Forest can't learn meaningful splits if the same marker appears in g/dL in one row and g/L in another. |
| **Fixed feature set** | 62 markers, always the same IDs, always the same order. Missing markers are explicitly null, not absent. The model expects a fixed-width input vector. |
| **Normalised scale** | Unit conversion ensures values are comparable across labs. A model trained on g/L data will misclassify if given g/dL values at inference. |
| **Categorical flags as features** | `flag` (LOW/NORMAL/HIGH/CRITICAL/tiered) can be one-hot encoded as additional features alongside the raw value. This gives the model both the absolute value and its clinical interpretation. |
| **Deviation as a continuous feature** | Two "LOW" ferritin values — 28 µg/L (barely low) vs 5 µg/L (critically low) — should produce different predictions. Deviation captures this severity gradient. |
| **Deterministic output** | Because Stage 2 computes everything at read time from the same markers.json + global profile, the same raw data always produces the same feature vector. Combined with a deterministic classifier (Random Forest), the entire pipeline is end-to-end deterministic. |

### End-to-end determinism

```
Same PDF + Same user profile
  → Same extracted values (Stage 1 Importing: deterministic template parsing)
  → Same enriched features (Stage 2 Unifying: deterministic computation from markers.json)
  → Same classification (Stage 3 Evaluating: deterministic trained classifier)
```

This is essential for a health application — the user must get the same result every time, and we must be able to explain exactly why the model made its prediction. Feature importance from the Random Forest maps directly back to specific markers and their values from Stage 2.

---

## 2.7 Stage 2 Summary

```
Confirmed data from Stage 1 (SQLite: records + results)
  │
  ├─→ Alias resolution (markers.json aliases[])
  ├─→ Unit normalisation (markers.json unit_conversions[])
  ├─→ Range resolution (markers.json ranges + global user profile)
  ├─→ Flag computation (CRITICAL → tiered → standard)
  ├─→ Deviation calculation (% out of range)
  │
  └─→ Enriched JSON output (fixed 62-marker feature set)
        │
        ├─→ Display in app (Data tab: table view, trend view)
        └─→ Feed into Stage 3 ML classifiers (Evaluating)
```

| Input | Output |
|---|---|
| Raw marker data in SQLite + global user profile + markers.json | Standardised, enriched JSON with consistent features ready for ML classification |
