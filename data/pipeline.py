#!/usr/bin/env python3
"""
hOS Blood Work Pipeline
PDF → SQLite (raw) → Match markers.json → Enrich (standardize, flag)
"""

import argparse
import json
import re
import sqlite3
import shutil
import subprocess
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent
MARKERS_JSON = DATA_DIR / "markers.json"


# ---------------------------------------------------------------------------
# Step 1: Extract text from PDF using pdftotext
# ---------------------------------------------------------------------------
PDFTOTEXT = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"


def extract_pdf_text(pdf_path: str) -> str:
    result = subprocess.run(
        [PDFTOTEXT, "-layout", pdf_path, "-"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        result = subprocess.run(
            [PDFTOTEXT, pdf_path, "-"],
            capture_output=True, text=True
        )
    if result.returncode != 0:
        sys.exit(f"pdftotext failed: {result.stderr}")
    return result.stdout


# ---------------------------------------------------------------------------
# Step 2: Parse extracted text into raw marker rows
# ---------------------------------------------------------------------------
def parse_patient_info(text: str) -> dict:
    """Extract patient demographics from the report header."""
    info = {}

    # Name
    m = re.search(r"([A-Z]+),\s+(\w[\w\s.]+)", text)
    if m:
        info["last_name"] = m.group(1).strip()
        info["first_name"] = m.group(2).strip()

    # DOB and age
    m = re.search(r"(\d{2}/\d{2}/\d{4})\s*\(Age:\s*(\d+)\)", text)
    if m:
        info["dob"] = m.group(1)
        info["age"] = int(m.group(2))

    # Sex
    m = re.search(r"\bSEX\b.*?\n+\s*(Male|Female)", text, re.IGNORECASE)
    if not m:
        m = re.search(r"\b(Male|Female)\b", text)
    if m:
        info["sex"] = m.group(1).lower()

    # Collection date
    m = re.search(r"COLLECTED.*?(\d{2}/\d{2}/\d{4})", text)
    if m:
        info["collected"] = m.group(1)

    # Fasting
    m = re.search(r"FASTING.*?(Yes|No)", text, re.IGNORECASE)
    if m:
        info["fasting"] = m.group(1).lower() == "yes"

    return info


def parse_markers_from_text(text: str) -> list[dict]:
    """
    Parse marker rows from pdftotext -layout output.
    Each data row looks like:
       MarkerName                    value      unit           ref_range         flag
    with generous whitespace between columns.
    """
    markers = []

    # Regex for a tabular marker row:
    # - Marker name (text, may include parentheses, hyphens, slashes)
    # - Value (number)
    # - Unit
    # - Reference range: "low - high" or "< high" or "> low"
    # - Optional flag (H or L)
    row_re = re.compile(
        r"^\s{2,}"                                    # leading whitespace
        r"(?P<name>[A-Za-z][A-Za-z0-9 /\-().,']+?)"  # marker name
        r"\s{3,}"                                     # gap
        r"(?P<value>[<>]?\s*-?\d+\.?\d*)"             # numeric value (may have < or > prefix)
        r"\s+"                                        # gap
        r"(?P<unit>[A-Za-z0-9µ%^/².×x]+(?:/[A-Za-z0-9µ².]+)*)" # unit
        r"\s+"                                        # gap
        r"(?P<ref>"                                   # reference range group
        r"(?:\d+\.?\d*\s*[-–]\s*\d+\.?\d*)"           #   low - high
        r"|(?:[<≤>≥]\s*\d+\.?\d*)"                    #   < high or > low
        r")"
        r"(?:\s*\([^)]*\))?"                          # optional parenthetical e.g. (post-menop.)
        r"(?:\s+(?P<flag>[HL]))?"                     # optional flag
        r"\s*$"
    )

    range_pattern = re.compile(r"(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)")
    upper_only = re.compile(r"[<≤]\s*(\d+\.?\d*)")
    lower_only = re.compile(r"[>≥]\s*(\d+\.?\d*)")

    for line in text.split("\n"):
        m = row_re.match(line)
        if not m:
            continue

        name = m.group("name").strip()
        val_str = m.group("value").strip()
        # Handle "< 37" style values — strip the comparator, store the number
        val_clean = re.sub(r"[<>≤≥]\s*", "", val_str)
        value = float(val_clean) if "." in val_clean else int(val_clean)
        unit = m.group("unit")
        ref_str = m.group("ref")
        flag = m.group("flag")

        ref_low = None
        ref_high = None
        rm = range_pattern.search(ref_str)
        um = upper_only.search(ref_str)
        lm = lower_only.search(ref_str)
        if rm:
            ref_low = float(rm.group(1))
            ref_high = float(rm.group(2))
        elif um:
            ref_high = float(um.group(1))
        elif lm:
            ref_low = float(lm.group(1))

        markers.append({
            "pdf_name": name,
            "value": value,
            "unit": unit,
            "ref_low": ref_low,
            "ref_high": ref_high,
            "lab_flag": flag,
        })

    return markers


# ---------------------------------------------------------------------------
# Step 3: Create SQLite and store raw rows
# ---------------------------------------------------------------------------
def create_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("DROP TABLE IF EXISTS bloodwork")
    conn.execute("""
        CREATE TABLE bloodwork (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            marker_name     TEXT NOT NULL,
            pdf_value       REAL,
            pdf_unit        TEXT,
            pdf_ref_low     REAL,
            pdf_ref_high    REAL,
            std_value       REAL,
            std_unit        TEXT,
            json_ref_low    REAL,
            json_ref_high   REAL,
            flag            TEXT
        )
    """)
    conn.commit()
    return conn


def insert_rows(conn: sqlite3.Connection, markers: list[dict]):
    for m in markers:
        conn.execute("""
            INSERT INTO bloodwork
                (marker_name, pdf_value, pdf_unit, pdf_ref_low, pdf_ref_high)
            VALUES (?, ?, ?, ?, ?)
        """, (
            m["pdf_name"],
            m["value"],
            m["unit"],
            m["ref_low"],
            m["ref_high"],
        ))
    conn.commit()


# ---------------------------------------------------------------------------
# Step 4: Match against markers.json and enrich
# ---------------------------------------------------------------------------
def load_markers_json(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def build_alias_index(markers_def: list[dict]) -> dict:
    """Build a lowercase alias → marker_def lookup."""
    index = {}
    for m in markers_def:
        for alias in m.get("aliases", []):
            index[alias.lower()] = m
        # Also index the id and name
        index[m["id"].lower()] = m
        index[m["name"].lower()] = m
    return index


def normalize_unit(unit: str) -> str:
    """Normalize common unit variants to a canonical form."""
    replacements = {
        "ug/l": "µg/L",
        "umol/l": "µmol/L",
        "ug/dl": "µg/dL",
        "x10^9/l": "x10⁹/L",
        "x10^12/l": "x10¹²/L",
        "ml/min/1.73m2": "mL/min/1.73m²",
    }
    return replacements.get(unit.lower(), unit)


def resolve_range(marker_def: dict, patient: dict) -> tuple:
    """Resolve the canonical reference range given patient context."""
    ranges = marker_def.get("ranges", {})

    # Simple range: {low, high}
    if "low" in ranges or "high" in ranges:
        return ranges.get("low"), ranges.get("high")

    sex = patient.get("sex", "").lower()
    age = patient.get("age")

    # Sex-differentiated: {male: {low, high}, female: {low, high}}
    if sex in ranges:
        r = ranges[sex]
        return r.get("low"), r.get("high")

    # Age-stratified ranges (e.g. IGF-1, PSA)
    # Keys like "<40", "40-49", "50-59", "16-24", "55+"
    if age is not None:
        for key, r in ranges.items():
            if isinstance(r, dict) and ("low" in r or "high" in r):
                if _age_matches(key, age):
                    return r.get("low"), r.get("high")

    # Cycle-phase based (female_follicular, etc.) - use follicular as default
    for phase_key in ["female_follicular", "female"]:
        if phase_key in ranges:
            r = ranges[phase_key]
            return r.get("low"), r.get("high")

    # Male-specific fallback
    if "male" in ranges:
        r = ranges["male"]
        return r.get("low"), r.get("high")

    return None, None


def _age_matches(key: str, age: int) -> bool:
    """Check if an age matches a range key like '<40', '40-49', '55+'."""
    key = key.strip()
    if key.startswith("<"):
        return age < int(key[1:])
    if key.startswith("<=") or key.startswith("≤"):
        return age <= int(key[2:])
    if key.endswith("+"):
        return age >= int(key[:-1])
    if "-" in key:
        parts = key.split("-")
        return int(parts[0]) <= age <= int(parts[1])
    return False


def compute_flag(value, ref_low, ref_high) -> str:
    """Compute flag from value and canonical range."""
    if value is None:
        return None
    if ref_low is not None and value < ref_low:
        return "LOW"
    if ref_high is not None and value > ref_high:
        return "HIGH"
    return "NORMAL"


def convert_unit(value, from_unit: str, marker_def: dict) -> tuple:
    """Convert value to the marker's canonical unit if needed."""
    canonical_unit = marker_def.get("unit", from_unit)
    from_normalized = normalize_unit(from_unit)

    if from_normalized == canonical_unit:
        return value, canonical_unit

    for conv in marker_def.get("unit_conversions", []):
        if normalize_unit(conv["from"]) == from_normalized:
            return round(value * conv["multiply"], 4), canonical_unit

    # No conversion found — keep as-is
    return value, from_normalized


def enrich_rows(conn: sqlite3.Connection, markers_def: list[dict], patient: dict):
    alias_index = build_alias_index(markers_def)

    rows = conn.execute("SELECT id, marker_name, pdf_value, pdf_unit FROM bloodwork").fetchall()

    for row_id, marker_name, value, unit in rows:
        marker_def = alias_index.get(marker_name.lower())

        if not marker_def:
            for alias_key, mdef in alias_index.items():
                if alias_key in marker_name.lower() or marker_name.lower() in alias_key:
                    marker_def = mdef
                    break

        if not marker_def:
            continue

        std_value, std_unit = convert_unit(value, unit, marker_def)
        json_low, json_high = resolve_range(marker_def, patient)
        flag = compute_flag(std_value, json_low, json_high)

        conn.execute("""
            UPDATE bloodwork SET
                std_value = ?, std_unit = ?,
                json_ref_low = ?, json_ref_high = ?,
                flag = ?
            WHERE id = ?
        """, (
            std_value, std_unit,
            json_low, json_high,
            flag, row_id,
        ))

    conn.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build_result_json(conn: sqlite3.Connection, patient: dict) -> list[dict]:
    """Build the enriched JSON result from the database."""
    columns = [desc[0] for desc in conn.execute("SELECT * FROM bloodwork LIMIT 0").description]
    all_rows = conn.execute("SELECT * FROM bloodwork ORDER BY id").fetchall()
    markers = [dict(zip(columns, row)) for row in all_rows]
    return {"patient": patient, "markers": markers}


def main():
    parser = argparse.ArgumentParser(description="hOS Blood Work Pipeline")
    parser.add_argument("pdf", help="Path to blood work PDF")
    parser.add_argument("--output-dir", help="Directory for output files (default: same as script)")
    parser.add_argument("--json-stdout", action="store_true", help="Print enriched JSON to stdout (for Tauri)")
    args = parser.parse_args()

    # Resolve output paths
    out_dir = Path(args.output_dir) if args.output_dir else DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_db_path = out_dir / "bloodwork_raw.db"
    enriched_db_path = out_dir / "bloodwork_enriched.db"
    extracted_txt_path = out_dir / "bloodwork_extracted.txt"
    enriched_json_path = out_dir / "bloodwork_enriched.json"

    quiet = args.json_stdout  # suppress prints when outputting JSON

    pdf_path = args.pdf
    if not quiet:
        print(f"[1/5] Extracting text from {pdf_path}...")
    text = extract_pdf_text(pdf_path)

    extracted_txt_path.write_text(text)
    if not quiet:
        print(f"       Saved extracted text to {extracted_txt_path}")

    if not quiet:
        print("[2/5] Parsing markers from text...")
    patient = parse_patient_info(text)
    if not quiet:
        print(f"       Patient: {patient}")
    markers = parse_markers_from_text(text)
    if not quiet:
        print(f"       Found {len(markers)} markers in PDF")

    # --- Raw DB (PDF extraction only, enrichment columns left NULL) ---
    if not quiet:
        print(f"[3/5] Creating raw SQLite at {raw_db_path}...")
    raw_conn = create_db(raw_db_path)
    insert_rows(raw_conn, markers)
    if not quiet:
        raw_count = raw_conn.execute("SELECT COUNT(*) FROM bloodwork").fetchone()[0]
        print(f"       {raw_count} rows inserted")
    raw_conn.close()

    # --- Enriched DB (raw + markers.json matching + flags) ---
    if not quiet:
        print(f"[4/5] Creating enriched SQLite at {enriched_db_path}...")
    enriched_conn = create_db(enriched_db_path)
    insert_rows(enriched_conn, markers)

    if not quiet:
        print("[5/5] Matching against markers.json and enriching...")
    markers_def = load_markers_json(MARKERS_JSON)
    enrich_rows(enriched_conn, markers_def, patient)

    # Build result
    result = build_result_json(enriched_conn, patient)

    if args.json_stdout:
        # Output JSON to stdout for Tauri consumption
        print(json.dumps(result))
    else:
        # Summary
        total = enriched_conn.execute("SELECT COUNT(*) FROM bloodwork").fetchone()[0]
        matched = enriched_conn.execute("SELECT COUNT(*) FROM bloodwork WHERE std_value IS NOT NULL").fetchone()[0]
        flagged = enriched_conn.execute(
            "SELECT COUNT(*) FROM bloodwork WHERE flag IN ('HIGH', 'LOW')"
        ).fetchone()[0]

        print(f"\nDone! {matched}/{total} markers matched. {flagged} flagged.")
        print(f"Raw DB:      {raw_db_path}")
        print(f"Enriched DB: {enriched_db_path}")

        # Print enriched summary table
        print(f"\n{'Marker':<30} {'PDF Val':>8} {'PDF Unit':<12} {'Std Val':>10} {'Std Unit':<12} {'Flag':<8}")
        print("-" * 90)
        for r in result["markers"]:
            name = r["marker_name"]
            pdf_val = f"{r['pdf_value']}" if r["pdf_value"] is not None else "?"
            pdf_unit = r["pdf_unit"] or ""
            std_val = f"{r['std_value']}" if r["std_value"] is not None else ""
            std_unit = r["std_unit"] or ""
            flag = r["flag"] or ""
            flag_display = f"*** {flag} ***" if flag in ("HIGH", "LOW") else flag
            print(f"{name:<30} {pdf_val:>8} {pdf_unit:<12} {std_val:>10} {std_unit:<12} {flag_display:<8}")

    # Save enriched JSON to file
    enriched_json_path.write_text(json.dumps(result, indent=2))
    if not quiet:
        print(f"Enriched JSON: {enriched_json_path}")

    enriched_conn.close()


if __name__ == "__main__":
    main()
