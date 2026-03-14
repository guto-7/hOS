#!/usr/bin/env python3
"""
run_imaging.py — Modular imaging pipeline orchestrator.

Three-phase flow:
  Stage 1 (Importing):  Validate → Store with SHA-256 → Extract metadata
  Stage 2 (Unifying):   Grayscale → Intensity normalise [0,1] → Orientation correct
  Model inference:       TorchXRayVision (or any model adapter)

Usage:
    python3 run_imaging.py <image_path> [--json-stdout] [--stage1-only] [--output-dir DIR] [--model MODEL]

Models:
    chest-xray   — TorchXRayVision DenseNet (18 pathologies)
    fracture     — SigLIP2 bone fracture detection (fractured/not fractured)
"""

import sys
import json
import argparse
from pathlib import Path

# Add parent to path so we can import imaging package
sys.path.insert(0, str(Path(__file__).resolve().parent))

from imaging.importing.storage import store_image
from imaging.importing.validator import validate_image
from imaging.unifying.normaliser import standardise_image


AVAILABLE_MODELS = {
    "chest-xray": {
        "name": "densenet121-res224-chex",
        "description": "TorchXRayVision DenseNet — 18 chest pathologies",
    },
    "fracture": {
        "name": "YOLOv8-GRAZPEDWRI",
        "description": "YOLOv8 fracture detection with bounding boxes",
    },
}


def run_pipeline(
    image_path: str,
    output_dir: str | None = None,
    quiet: bool = False,
    stage1_only: bool = False,
    model: str = "chest-xray",
    pixel_spacing: float | None = None,
) -> dict:
    """
    Run the imaging pipeline.

    Stage 1 (Importing):
      [1/3] Validate image format and extract metadata
      [2/3] Store original with SHA-256 hash
      [3/3] Quality assessment

    If stage1_only=True, return here for user confirmation.

    Stage 2 (Unifying):
      [4/5] Standardise image (grayscale, normalise, orientation)

    Model inference:
      [5/5] Run selected model prediction
    """
    path = Path(image_path)
    if not path.exists():
        return {"success": False, "error": f"File not found: {image_path}"}

    uploads_dir = None
    if output_dir:
        uploads_dir = Path(output_dir) / "uploads" / "imaging"

    # ── Stage 1: Importing ──────────────────────────────────────────
    if not quiet:
        print("[1/5] Validating image format...", file=sys.stderr)

    try:
        metadata = validate_image(path)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    if not quiet:
        print(f"      {metadata.format} {metadata.width}x{metadata.height} "
              f"({metadata.channels}ch, {metadata.bit_depth}-bit)", file=sys.stderr)

    if not quiet:
        print("[2/5] Storing original with SHA-256...", file=sys.stderr)

    if uploads_dir:
        storage = store_image(path, uploads_dir)
    else:
        storage = store_image(path)

    if not quiet:
        dup = " (duplicate)" if storage.is_duplicate else ""
        print(f"      {storage.file_hash[:12]}...{dup}", file=sys.stderr)

    if not quiet:
        print("[3/5] Quality assessment...", file=sys.stderr)
        if metadata.warnings:
            for w in metadata.warnings:
                print(f"      ⚠ {w}", file=sys.stderr)
        else:
            print("      No issues detected", file=sys.stderr)

    # ── Stage 1 early return for confirmation ───────────────────────
    if stage1_only:
        return {
            "success": True,
            "stage": "importing",
            "record": {
                "file_hash": storage.file_hash,
                "stored_path": str(storage.stored_path),
                "original_name": storage.original_name,
                "is_duplicate": storage.is_duplicate,
            },
            "image_metadata": metadata.to_dict(),
            "quality": {
                "warnings": metadata.warnings,
                "warning_count": len(metadata.warnings),
            },
        }

    # ── Stage 2: Unifying ───────────────────────────────────────────
    if not quiet:
        print("[4/5] Standardising image...", file=sys.stderr)

    standardised = standardise_image(storage.stored_path)

    if not quiet:
        print(f"      {standardised.standardised_width}x{standardised.standardised_height} "
              f"grayscale, [0,1] float64", file=sys.stderr)

    # ── Model inference ─────────────────────────────────────────────
    if model not in AVAILABLE_MODELS:
        return {"success": False, "error": f"Unknown model '{model}'. Available: {', '.join(AVAILABLE_MODELS)}"}

    model_info = AVAILABLE_MODELS[model]

    if not quiet:
        print(f"[5/5] Running {model_info['description']}...", file=sys.stderr)

    if model == "chest-xray":
        from imaging.models.torchxrayvision_model import predict
        prediction = predict(standardised.pixels)
    elif model == "fracture":
        from imaging.models.fracture_model import predict
        if pixel_spacing is None:
            pixel_spacing = _lookup_pixel_spacing(image_path)
        prediction = predict(standardised.pixels, pixel_spacing_mm=pixel_spacing)
    findings = prediction["findings"]
    heatmap_base64 = prediction.get("heatmap", "")
    heatmap_pathology = prediction.get("heatmap_pathology")

    # Generate summary
    high = [f for f in findings if f["level"] == "HIGH"]
    moderate = [f for f in findings if f["level"] == "MODERATE"]

    summary = {
        "total_pathologies_screened": len(findings),
        "flagged_count": len(high) + len(moderate),
        "high_probability": [f["pathology"] for f in high],
        "moderate_probability": [f["pathology"] for f in moderate],
    }

    if not quiet:
        print(f"      {summary['total_pathologies_screened']} screened, "
              f"{summary['flagged_count']} flagged", file=sys.stderr)

    return {
        "success": True,
        "stage": "complete",
        "record": {
            "file_hash": storage.file_hash,
            "stored_path": str(storage.stored_path),
            "original_name": storage.original_name,
            "is_duplicate": storage.is_duplicate,
        },
        "image_metadata": metadata.to_dict(),
        "standardisation": standardised.to_metadata_dict(),
        "model": model_info["name"],
        "model_key": model,
        "findings": findings,
        "summary": summary,
        "heatmap": heatmap_base64,
        "heatmap_pathology": heatmap_pathology,
    }


def _lookup_pixel_spacing(image_path: str) -> float | None:
    """Try to find pixel spacing from GRAZPEDWRI-DX dataset CSV."""
    import csv

    stem = Path(image_path).stem
    # Search for dataset CSV near the image or in known locations
    image_dir = Path(image_path).resolve().parent
    candidates = [
        image_dir / "dataset.csv",
        image_dir.parent / "dataset.csv",
        image_dir.parent.parent / "dataset.csv",
    ]
    # Also check in the data directory (where wrist_scans might be)
    script_dir = Path(__file__).resolve().parent
    candidates.append(script_dir / "wrist_scans" / "dataset.csv")

    for csv_path in candidates:
        if not csv_path.exists():
            continue
        try:
            with open(csv_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("filestem") == stem:
                        spacing = float(row["pixel_spacing"])
                        return spacing
        except Exception:
            continue

    # Default pixel spacing for wrist X-ray digitizers (common DICOM value)
    return 0.144


def main():
    parser = argparse.ArgumentParser(description="Modular imaging pipeline")
    parser.add_argument("image_path", help="Path to medical image")
    parser.add_argument("--output-dir", help="Base output directory")
    parser.add_argument("--json-stdout", action="store_true", help="Output JSON to stdout")
    parser.add_argument("--stage1-only", action="store_true", help="Run Stage 1 only (for confirmation)")
    parser.add_argument("--model", default="chest-xray",
                        choices=list(AVAILABLE_MODELS.keys()),
                        help="Model to use for analysis (default: chest-xray)")
    parser.add_argument("--pixel-spacing", type=float, default=None,
                        help="Pixel spacing in mm (for real-world size estimates)")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    args = parser.parse_args()

    # Auto-detect pixel spacing from GRAZPEDWRI-DX dataset CSV if available
    pixel_spacing = args.pixel_spacing
    if pixel_spacing is None and args.model == "fracture":
        pixel_spacing = _lookup_pixel_spacing(args.image_path)

    result = run_pipeline(
        image_path=args.image_path,
        output_dir=args.output_dir,
        quiet=args.quiet or args.json_stdout,
        stage1_only=args.stage1_only,
        model=args.model,
        pixel_spacing=pixel_spacing,
    )

    if args.json_stdout:
        print(json.dumps(result))
    else:
        print(json.dumps(result, indent=2))

    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
