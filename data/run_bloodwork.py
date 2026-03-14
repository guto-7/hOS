#!/usr/bin/env python3
"""
run_bloodwork.py — CLI entry point for the bloodwork pipeline.

Orchestrates Stage 1 (Importing) and Stage 2 (Unifying) in sequence:
  Stage 1: validate → store → extract → parse → resolve → confidence score
  Stage 2: normalise units → resolve ranges → compute flags + deviation

Usage:
  python run_bloodwork.py <pdf_path>
  python run_bloodwork.py <pdf_path> --json-stdout
  python run_bloodwork.py <pdf_path> --output-dir ~/Documents/hOS
  python run_bloodwork.py <pdf_path> --sex male --age 34
"""

import argparse
import json
import sys
from pathlib import Path

from bloodwork.importing import (
    validate_pdf,
    store_pdf,
    extract_text,
    parse_markers,
    resolve_aliases,
    score_confidence,
)
from bloodwork.unifying import (
    normalise_units,
    resolve_ranges,
    compute_flags,
)
from bloodwork.unifying.ranger import UserProfile


def run_pipeline(
    pdf_path: str,
    output_dir: str | None = None,
    profile: UserProfile | None = None,
    quiet: bool = False,
    stage1_only: bool = False,
):
    """
    Run the full Stage 1 (Importing) + Stage 2 (Unifying) pipeline.
    Returns a dict with the enriched result.
    """
    if profile is None:
        profile = UserProfile()

    path = Path(pdf_path)

    # ─── STAGE 1: IMPORTING ─────────────────────────────────────────────

    # Step 1: Validate
    if not quiet:
        print(f"[1/8] Validating {path.name}...")
    validation = validate_pdf(path)
    if not validation.valid:
        return {"success": False, "error": validation.reason}
    if not quiet:
        print(f"       ✓ {validation.reason}")

    # Step 2: Store with SHA-256
    if not quiet:
        print("[2/8] Storing PDF with SHA-256 hash...")
    uploads_dir = Path(output_dir) / "uploads" if output_dir else None
    storage = store_pdf(path, uploads_dir) if uploads_dir else store_pdf(path)
    if not quiet:
        status = "duplicate, skipped copy" if storage.is_duplicate else "stored"
        print(f"       ✓ {storage.file_hash[:16]}... ({status})")

    # Step 3: Extract text
    if not quiet:
        print("[3/8] Extracting text from PDF...")
    extraction = extract_text(storage.stored_path)
    if not extraction.success:
        return {"success": False, "error": extraction.error}
    if not quiet:
        print(f"       ✓ {extraction.page_count} pages, {len(extraction.text)} characters")

    # Save extracted text for debugging
    if output_dir:
        txt_path = Path(output_dir) / "bloodwork_extracted.txt"
        txt_path.write_text(extraction.text)

    # Step 4: Parse markers
    if not quiet:
        print("[4/8] Parsing markers from text...")
    parse_result = parse_markers(extraction.text)
    if not quiet:
        lab = parse_result.lab_provider or "Unknown"
        print(f"       ✓ Lab: {lab}, found {len(parse_result.markers)} markers")

    # Step 5: Resolve aliases + score confidence
    if not quiet:
        print("[5/8] Resolving aliases and scoring confidence...")
    resolved = resolve_aliases(parse_result.markers)
    scored = score_confidence(resolved)
    if not quiet:
        matched = sum(1 for m in scored if m.marker_id is not None)
        print(f"       ✓ {matched}/{len(scored)} matched to markers.json")

    # ─── STAGE 1 COMPLETE ────────────────────────────────────────────────

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
                "lab_provider": parse_result.lab_provider,
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

    # ─── STAGE 2: UNIFYING ───────────────────────────────────────────────

    # Step 6: Unit normalisation
    if not quiet:
        print("[6/8] Normalising units...")
    normalised = normalise_units(scored)
    converted = sum(1 for m in normalised if m.unit_converted)
    if not quiet:
        print(f"       ✓ {converted} markers required unit conversion")

    # Step 7: Range resolution
    if not quiet:
        print("[7/8] Resolving reference ranges...")
    ranged = resolve_ranges(normalised, profile)
    ranges_resolved = sum(1 for m in ranged if m.canonical_ref_low is not None or m.canonical_ref_high is not None)
    if not quiet:
        print(f"       ✓ {ranges_resolved}/{len(ranged)} ranges resolved")
        if profile.sex or profile.age:
            print(f"       ✓ Profile: sex={profile.sex}, age={profile.age}, pregnant={profile.pregnant}")

    # Step 8: Flag computation + deviation
    if not quiet:
        print("[8/8] Computing flags and deviations...")
    flagged = compute_flags(ranged)

    # Compute summary
    total = len(flagged)
    matched = sum(1 for m in flagged if m.marker_id is not None)
    flag_counts = {}
    for m in flagged:
        flag_counts[m.flag] = flag_counts.get(m.flag, 0) + 1
    abnormal = total - flag_counts.get("OPTIMAL", 0)

    if not quiet:
        print(f"       ✓ {abnormal} markers flagged out of {matched} matched")

    # Build result
    result = {
        "success": True,
        "stages_completed": ["importing", "unifying"],
        "record": {
            "file_hash": storage.file_hash,
            "stored_path": str(storage.stored_path),
            "original_name": storage.original_name,
            "is_duplicate": storage.is_duplicate,
            "lab_provider": parse_result.lab_provider,
            "test_date": parse_result.test_date,
            "page_count": extraction.page_count,
        },
        "profile": {
            "sex": profile.sex,
            "age": profile.age,
            "pregnant": profile.pregnant,
            "cycle_phase": profile.cycle_phase,
            "fasting": profile.fasting,
        },
        "markers": [m.to_dict() for m in flagged],
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
        description="hOS Bloodwork Pipeline — Stage 1 (Importing) + Stage 2 (Unifying)"
    )
    parser.add_argument("pdf", help="Path to blood work PDF")
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
        help="Run Stage 1 (Importing) only — returns extracted markers for user confirmation",
    )
    # User profile arguments (will come from global app profile in production)
    parser.add_argument("--sex", choices=["male", "female"], help="User sex")
    parser.add_argument("--age", type=int, help="User age")
    parser.add_argument("--pregnant", action="store_true", help="Pregnancy status")
    parser.add_argument(
        "--cycle-phase",
        choices=["follicular", "midcycle", "luteal", "postmenopausal"],
        help="Menstrual cycle phase",
    )
    parser.add_argument("--fasting", action="store_true", help="Fasting status")
    args = parser.parse_args()

    profile = UserProfile(
        sex=args.sex,
        age=args.age,
        pregnant=args.pregnant,
        cycle_phase=args.cycle_phase,
        fasting=args.fasting,
    )

    quiet = args.json_stdout
    result = run_pipeline(
        args.pdf, args.output_dir, profile,
        quiet=quiet, stage1_only=args.stage1_only,
    )

    if args.json_stdout:
        print(json.dumps(result))
    else:
        if not result["success"]:
            print(f"\n✗ Pipeline failed: {result['error']}")
            sys.exit(1)

        print(f"\n{'─' * 90}")
        print("Stage 1 (Importing) + Stage 2 (Unifying) complete\n")

        # Print enriched marker table
        print(f"{'Marker':<30} {'Std Value':>10} {'Unit':<12} {'Ref Range':<18} {'Flag':<14} {'Confidence':<10}")
        print("─" * 94)
        for m in result["markers"]:
            if m["marker_id"] is None:
                continue
            name = m["marker_name"] or m["pdf_name"]
            val = f"{m['std_value']}"
            unit = m["std_unit"]
            ref_lo = m["canonical_ref_low"]
            ref_hi = m["canonical_ref_high"]
            ref = f"{ref_lo}-{ref_hi}" if ref_lo is not None and ref_hi is not None else "—"
            flag = m["flag"]
            flag_display = f"*** {flag} ***" if flag not in ("OPTIMAL",) else flag
            conf = m["confidence"]
            print(f"{name:<30} {val:>10} {unit:<12} {ref:<18} {flag_display:<14} {conf:<10}")

        s = result["summary"]
        print(f"\n{s['matched']}/{s['total_extracted']} matched | "
              f"{s['flagged']} flagged | "
              f"Flags: {s['flag_breakdown']}")

    # Save result JSON
    if args.output_dir:
        out = Path(args.output_dir) / "bloodwork_enriched.json"
        out.write_text(json.dumps(result, indent=2))
        if not quiet:
            print(f"\nEnriched JSON saved to {out}")


if __name__ == "__main__":
    main()
