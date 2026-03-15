#!/usr/bin/env python3
"""
run_anthropometry.py — CLI entry point for the anthropometry pipeline.

Orchestrates Stage 1 (Importing) and Stage 2 (Unifying) in sequence:
  Stage 1: validate -> store -> extract -> parse -> resolve -> confidence score
  Stage 2: normalise units -> resolve ranges -> compute flags + deviation

Usage:
  python run_anthropometry.py <pdf_path>
  python run_anthropometry.py <pdf_path> --json-stdout
  python run_anthropometry.py <pdf_path> --output-dir ~/Documents/hOS
  python run_anthropometry.py <pdf_path> --sex male --age 32
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from anthropometry.importing import (
    validate_pdf,
    store_pdf,
    extract_text,
    parse_markers,
    resolve_aliases,
    score_confidence,
)
from anthropometry.unifying import (
    normalise_units,
    resolve_ranges,
    compute_flags,
)
from anthropometry.unifying.ranger import UserProfile
from anthropometry.evaluating import evaluate


def run_pipeline(
    pdf_path: str,
    output_dir: str | None = None,
    profile: UserProfile | None = None,
    quiet: bool = False,
    stage1_only: bool = False,
    stage2_only: bool = False,
):
    """
    Run the full Stage 1 (Importing) + Stage 2 (Unifying) pipeline.
    Returns a dict with the enriched result.
    """
    if profile is None:
        profile = UserProfile()

    # Normalize sex to lowercase and strip whitespace (defensive)
    if profile.sex:
        profile.sex = profile.sex.lower().strip()
        if profile.sex not in ("male", "female"):
            profile.sex = None

    path = Path(pdf_path)

    # --- STAGE 1: IMPORTING ---

    # Step 1: Validate
    if not quiet:
        print(f"[1/8] Validating {path.name}...", file=sys.stderr)
    validation = validate_pdf(path)
    if not validation.valid:
        return {"success": False, "error": validation.reason}
    if not quiet:
        print(f"       {validation.reason}", file=sys.stderr)

    # Step 2: Store with SHA-256
    if not quiet:
        print("[2/8] Storing PDF with SHA-256 hash...", file=sys.stderr)
    uploads_dir = Path(output_dir) / "uploads" if output_dir else None
    storage = store_pdf(path, uploads_dir) if uploads_dir else store_pdf(path)
    if not quiet:
        status = "duplicate, skipped copy" if storage.is_duplicate else "stored"
        print(f"       {storage.file_hash[:16]}... ({status})", file=sys.stderr)

    # Step 3: Extract text
    if not quiet:
        print("[3/8] Extracting text from PDF...", file=sys.stderr)
    extraction = extract_text(storage.stored_path)
    if not extraction.success:
        return {"success": False, "error": extraction.error}
    if not quiet:
        print(f"       {extraction.page_count} pages, {len(extraction.text)} characters", file=sys.stderr)

    # Save extracted text for debugging
    if output_dir:
        txt_path = Path(output_dir) / "anthropometry_extracted.txt"
        txt_path.write_text(extraction.text)

    # Step 4: Parse markers
    if not quiet:
        print("[4/8] Parsing anthropometry markers...", file=sys.stderr)
    parse_result = parse_markers(extraction.text)
    if not quiet:
        device = parse_result.device or "Unknown device"
        print(f"       Device: {device}, found {len(parse_result.markers)} markers", file=sys.stderr)

    # Step 5: Resolve aliases + score confidence
    if not quiet:
        print("[5/8] Resolving aliases and scoring confidence...", file=sys.stderr)
    resolved = resolve_aliases(parse_result.markers)
    scored = score_confidence(resolved)
    if not quiet:
        matched = sum(1 for m in scored if m.marker_id is not None)
        print(f"       {matched}/{len(scored)} matched to anthropometry_markers.json", file=sys.stderr)

    # --- STAGE 1 COMPLETE ---

    if stage1_only:
        matched = sum(1 for m in scored if m.marker_id is not None)
        confidence_counts = {}
        for m in scored:
            confidence_counts[m.confidence] = confidence_counts.get(m.confidence, 0) + 1

        return {
            "success": True,
            "stage": "importing",
            "record": {
                "file_hash": storage.file_hash,
                "stored_path": str(storage.stored_path),
                "original_name": storage.original_name,
                "is_duplicate": storage.is_duplicate,
                "device": parse_result.device,
                "test_date": parse_result.test_date,
                "page_count": extraction.page_count,
            },
            "markers": [m.to_dict() for m in scored],
            "summary": {
                "total_extracted": len(scored),
                "matched": matched,
                "unmatched": len(scored) - matched,
                "confidence_breakdown": confidence_counts,
            },
        }

    # --- STAGE 2: UNIFYING ---

    # Step 6: Unit normalisation
    if not quiet:
        print("[6/8] Normalising units...", file=sys.stderr)
    normalised = normalise_units(scored)
    converted = sum(1 for m in normalised if m.unit_converted)
    if not quiet:
        print(f"       {converted} markers required unit conversion", file=sys.stderr)

    # Step 7: Range resolution
    if not quiet:
        print("[7/8] Resolving reference ranges...", file=sys.stderr)
        print(f"       [DEBUG] profile.sex={profile.sex!r}, profile.age={profile.age!r}", file=sys.stderr)
    ranged = resolve_ranges(normalised, profile)
    ranges_resolved = sum(1 for m in ranged if m.canonical_ref_low is not None or m.canonical_ref_high is not None)
    if not quiet:
        print(f"       {ranges_resolved}/{len(ranged)} ranges resolved", file=sys.stderr)
        if profile.sex or profile.age:
            print(f"       Profile: sex={profile.sex}, age={profile.age}", file=sys.stderr)

    # Step 8: Flag computation + deviation
    if not quiet:
        print("[8/8] Computing flags and deviations...", file=sys.stderr)
    flagged = compute_flags(ranged)

    # --- BMR lean mass cross-reference ---
    # If BMR is elevated but lean mass is also elevated, override the HIGH flag to
    # OPTIMAL and attach an explanatory adjustment note.  If BMR is low alongside
    # low muscle mass, keep the LOW flag but add context.
    _bmr_m = next((m for m in flagged if m.marker_id == "BMR"), None)
    if _bmr_m is not None:
        def _lean_tier(marker_id: str) -> str | None:
            lm = next((x for x in flagged if x.marker_id == marker_id), None)
            if lm is None:
                return None
            if lm.flag.startswith("TIER:"):
                return lm.flag[5:]
            return None

        _ffmi_tier = _lean_tier("FFMI")
        _smi_tier  = _lean_tier("SMI")

        if _bmr_m.flag == "HIGH":
            if _ffmi_tier in ("high", "normal") or _smi_tier == "normal":
                _bmr_m.adjustment_note = "Above age average — consistent with high lean mass"
                _bmr_m.flag = "OPTIMAL"
            else:
                _bmr_m.adjustment_note = "Above age average for age group"
        elif _bmr_m.flag == "LOW":
            if _smi_tier in ("low", "critically_low"):
                _bmr_m.adjustment_note = "Below age average — consistent with low muscle mass"
            else:
                _bmr_m.adjustment_note = "Below age average for age group"
        elif _bmr_m.flag == "OPTIMAL":
            ref_low = _bmr_m.canonical_ref_low
            ref_high = _bmr_m.canonical_ref_high
            if ref_low is not None and ref_high is not None:
                _bmr_m.adjustment_note = f"Within age range ({int(ref_low)}–{int(ref_high)} kcal)"

    # Flags that represent a concern worth surfacing
    _CONCERNING = {"LOW", "HIGH", "CRITICAL_LOW", "CRITICAL_HIGH"}
    _CONCERNING_TIERS = {
        "obese", "overfat", "overweight", "elevated", "high_risk",
        "underfat", "underweight", "low", "critically_low",
        "mild_imbalance", "significant_imbalance", "physiological_ceiling",
    }

    def _is_concerning(flag: str) -> bool:
        if flag in _CONCERNING:
            return True
        if flag.startswith("TIER:") and flag[5:] in _CONCERNING_TIERS:
            return True
        return False

    # Compute summary
    total = len(flagged)
    matched = sum(1 for m in flagged if m.marker_id is not None)
    flag_counts = {}
    for m in flagged:
        flag_counts[m.flag] = flag_counts.get(m.flag, 0) + 1
    abnormal = sum(1 for m in flagged if m.marker_id and _is_concerning(m.flag))

    if not quiet:
        print(f"       {abnormal} markers flagged out of {matched} matched", file=sys.stderr)

    flagged_dicts = [m.to_dict() for m in flagged]

    # --- STAGE 2 ONLY ---
    if stage2_only:
        return {
            "success": True,
            "stages_completed": ["importing", "unifying"],
            "record": {
                "file_hash": storage.file_hash,
                "stored_path": str(storage.stored_path),
                "original_name": storage.original_name,
                "is_duplicate": storage.is_duplicate,
                "device": parse_result.device,
                "test_date": parse_result.test_date,
                "page_count": extraction.page_count,
            },
            "profile": {
                "sex": profile.sex,
                "age": profile.age,
                "height_cm": profile.height_cm,
            },
            "markers": flagged_dicts,
            "summary": {
                "total_extracted": total,
                "matched": matched,
                "unmatched": total - matched,
                "flagged": abnormal,
                "flag_breakdown": flag_counts,
            },
        }

    # --- STAGE 3: EVALUATING ---

    if not quiet:
        print("[Stage 3] Running clinical evaluation...", file=sys.stderr)
    eval_result = evaluate(flagged_dicts, chronological_age=profile.age, sex=profile.sex)

    def _domain_to_dict(d):
        return {
            "domain": d.domain,
            "label": d.label,
            "score": d.score,
            "grade": d.grade,
            "markers_used": d.markers_used,
            "notes": d.notes,
        }

    def _signal_to_dict(s):
        return {
            "id": s.id,
            "label": s.label,
            "detail": s.detail,
            "severity": s.severity,
            "markers": s.markers,
        }

    evaluation_dict = {
        "body_score": eval_result.body_score,
        "body_score_label": eval_result.body_score_label,
        "body_age": eval_result.body_age,
        "chronological_age": eval_result.chronological_age,
        "domain_scores": [_domain_to_dict(d) for d in eval_result.domain_scores],
        "phenotype": {
            "id": eval_result.phenotype.id,
            "label": eval_result.phenotype.label,
            "description": eval_result.phenotype.description,
            "confidence": eval_result.phenotype.confidence,
            "contributing_signals": eval_result.phenotype.contributing_signals,
        } if eval_result.phenotype else None,
        "signals": [_signal_to_dict(s) for s in eval_result.signals],
        "certainty_grade": eval_result.certainty_grade,
        "certainty_note": eval_result.certainty_note,
        "missing_for_full_eval": eval_result.missing_for_full_eval,
    }

    if not quiet:
        grade = eval_result.certainty_grade
        ph = eval_result.phenotype.label if eval_result.phenotype else "none"
        print(f"       Certainty: {grade} | Phenotype: {ph} | Signals: {len(eval_result.signals)}", file=sys.stderr)

    result = {
        "success": True,
        "stages_completed": ["importing", "unifying", "evaluating"],
        "record": {
            "file_hash": storage.file_hash,
            "stored_path": str(storage.stored_path),
            "original_name": storage.original_name,
            "is_duplicate": storage.is_duplicate,
            "device": parse_result.device,
            "test_date": parse_result.test_date,
            "page_count": extraction.page_count,
        },
        "profile": {
            "sex": profile.sex,
            "age": profile.age,
            "height_cm": profile.height_cm,
        },
        "markers": flagged_dicts,
        "evaluation": evaluation_dict,
        "summary": {
            "total_extracted": total,
            "matched": matched,
            "unmatched": total - matched,
            "flagged": abnormal,
            "flag_breakdown": flag_counts,
        },
    }

    return result


def main():
    parser = argparse.ArgumentParser(
        description="hOS Anthropometry Pipeline — Stage 1 (Importing) + Stage 2 (Unifying)"
    )
    parser.add_argument("pdf", help="Path to BIA report PDF")
    parser.add_argument(
        "--output-dir",
        help="Directory for output files (default: ~/Documents/hOS)",
    )
    parser.add_argument(
        "--json-stdout",
        action="store_true",
        help="Print result as JSON to stdout (for Tauri integration)",
    )
    parser.add_argument(
        "--stage1-only",
        action="store_true",
        help="Run Stage 1 (Importing) only",
    )
    parser.add_argument(
        "--stage2-only",
        action="store_true",
        help="Run Stage 1 + Stage 2 (skip Stage 3 evaluation)",
    )
    parser.add_argument("--sex", choices=["male", "female"], help="User sex")
    parser.add_argument("--age", type=int, help="User age (converted to DOB internally)")
    parser.add_argument("--dob", help="Date of birth in YYYY-MM-DD format (preferred over --age)")
    parser.add_argument("--height", type=float, help="Height in centimetres (required for SMI, FFMI, FMI)")
    args = parser.parse_args()

    dob = None
    if args.dob:
        try:
            dob = date.fromisoformat(args.dob)
        except ValueError:
            print(f"Invalid --dob format '{args.dob}'. Use YYYY-MM-DD.", file=sys.stderr)
            sys.exit(1)
    elif args.age:
        today = date.today()
        dob = date(today.year - args.age, today.month, today.day)

    profile = UserProfile(
        sex=args.sex,
        dob=dob,
        height_cm=args.height,
    )

    quiet = args.json_stdout
    result = run_pipeline(
        args.pdf, args.output_dir, profile,
        quiet=quiet, stage1_only=args.stage1_only, stage2_only=args.stage2_only,
    )

    if args.json_stdout:
        print(json.dumps(result))
    else:
        if not result["success"]:
            print(f"\nPipeline failed: {result['error']}")
            sys.exit(1)

        print(f"\n{'─' * 90}")
        stages = " + ".join(result.get("stages_completed", ["importing", "unifying"]))
        print(f"{stages} complete\n")

        print(f"{'Marker':<25} {'Value':>10} {'Unit':<10} {'Ref Range':<18} {'Flag':<14} {'Confidence':<10}")
        print("─" * 87)
        _GOOD_FLAGS = {"OPTIMAL", "INFO"}
        _GOOD_TIERS = {"healthy", "normal", "sufficient", "optimal"}

        def _flag_display(flag: str) -> str:
            if flag in _GOOD_FLAGS:
                return flag
            if flag.startswith("TIER:") and flag[5:] in _GOOD_TIERS:
                return flag
            if flag == "UNRESOLVED":
                return flag
            return f"*** {flag} ***"

        for m in result["markers"]:
            if m["marker_id"] is None:
                continue
            name = m["marker_name"] or m["pdf_name"]
            val = f"{m['std_value']}"
            unit = m["std_unit"]
            ref_lo = m["canonical_ref_low"]
            ref_hi = m["canonical_ref_high"]
            tier = m.get("canonical_tier")
            if tier:
                ref = f"tier: {tier}"
            elif ref_lo is not None and ref_hi is not None:
                ref = f"{ref_lo}–{ref_hi}"
            elif ref_lo is not None:
                ref = f"≥{ref_lo}"
            elif ref_hi is not None:
                ref = f"≤{ref_hi}"
            else:
                ref = "—"
            flag = m["flag"]
            conf = m["confidence"]
            print(f"{name:<25} {val:>10} {unit:<10} {ref:<22} {_flag_display(flag):<20} {conf:<10}")

        s = result["summary"]
        print(f"\n{s['matched']}/{s['total_extracted']} matched | "
              f"{s['flagged']} concerning | "
              f"Flags: {s['flag_breakdown']}")

    if args.output_dir:
        out = Path(args.output_dir) / "anthropometry_enriched.json"
        out.write_text(json.dumps(result, indent=2))
        if not quiet:
            print(f"\nEnriched JSON saved to {out}")


if __name__ == "__main__":
    main()
