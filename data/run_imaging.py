#!/usr/bin/env python3
"""
run_imaging.py — Modular imaging pipeline orchestrator.

Three-phase flow:
  Stage 1 (Importing):  Validate → Store with SHA-256 → Extract metadata
  Stage 2 (Unifying):   Grayscale → Intensity normalise [0,1] → Orientation correct
  Model inference:       Run selected model prediction

Usage:
    python3 run_imaging.py <image_path> [--json-stdout] [--stage1-only] [--output-dir DIR] [--model MODEL]

Models:
    chest-xray         — TorchXRayVision DenseNet (18 pathologies)
    fracture-wrist     — YOLOv8 GRAZPEDWRI-DX (pediatric wrist fractures)
    fracture-multibody — YOLOv8 multi-body (elbow, fingers, forearm, humerus, shoulder, wrist)
    auto               — Auto-detect body part with Claude Vision, then route to best model
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
    "fracture-wrist": {
        "name": "YOLOv8-GRAZPEDWRI",
        "description": "YOLOv8 pediatric wrist fracture detection",
    },
    "fracture-multibody": {
        "name": "YOLOv8-MultiBone",
        "description": "YOLOv8 multi-body fracture detection (elbow, fingers, forearm, humerus, shoulder, wrist)",
    },
    # "auto" is handled specially — not a real model, but a routing mode
}

# Legacy alias
AVAILABLE_MODELS["fracture"] = AVAILABLE_MODELS["fracture-wrist"]


def run_pipeline(
    image_path: str,
    output_dir: str | None = None,
    quiet: bool = False,
    stage1_only: bool = False,
    model: str = "chest-xray",
    pixel_spacing: float | None = None,
    detect_body_part_flag: bool = False,
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
        stage1_result = {
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

        # Optionally run body part detection during Stage 1
        if detect_body_part_flag:
            if not quiet:
                print("[3.5/5] Auto-detecting body part...", file=sys.stderr)
            try:
                from imaging.importing.body_part_detector import detect_body_part
                bp_info = detect_body_part(str(storage.stored_path))
                stage1_result["body_part_detection"] = bp_info
                if not quiet:
                    print(f"      Detected: {bp_info['body_part']} "
                          f"({bp_info['confidence']:.0%} confidence)", file=sys.stderr)
            except Exception as e:
                stage1_result["body_part_detection"] = {
                    "body_part": "unknown",
                    "confidence": 0.0,
                    "description": f"Detection failed: {e}",
                    "recommended_model": None,
                }

        return stage1_result

    # ── Stage 2: Unifying ───────────────────────────────────────────
    if not quiet:
        print("[4/5] Standardising image...", file=sys.stderr)

    standardised = standardise_image(storage.stored_path)

    if not quiet:
        print(f"      {standardised.standardised_width}x{standardised.standardised_height} "
              f"grayscale, [0,1] float64", file=sys.stderr)

    # ── Auto-detect body part if model is "auto" ─────────────────────
    body_part_info = None
    if model == "auto":
        if not quiet:
            print("[4.5/6] Auto-detecting body part with Claude Vision...", file=sys.stderr)
        from imaging.importing.body_part_detector import detect_body_part
        body_part_info = detect_body_part(str(storage.stored_path))
        detected_model = body_part_info.get("recommended_model")
        if not quiet:
            print(f"      Detected: {body_part_info['body_part']} "
                  f"({body_part_info['confidence']:.0%} confidence)", file=sys.stderr)
            print(f"      → Routing to: {detected_model or 'unknown'}", file=sys.stderr)
        if detected_model and detected_model in AVAILABLE_MODELS:
            model = detected_model
        else:
            # Default to multi-body model for unknown body parts
            model = "fracture-multibody"
            if not quiet:
                print(f"      ⚠ No specialised model for '{body_part_info['body_part']}', "
                      f"using multi-body model", file=sys.stderr)

    # ── Model inference ─────────────────────────────────────────────
    if model not in AVAILABLE_MODELS:
        return {"success": False, "error": f"Unknown model '{model}'. Available: {', '.join(AVAILABLE_MODELS)}"}

    model_info = AVAILABLE_MODELS[model]

    if not quiet:
        print(f"[5/5] Running {model_info['description']}...", file=sys.stderr)

    # Resolve pixel spacing — use detected body part for better estimates
    detected_body_part = body_part_info["body_part"] if body_part_info else None
    if pixel_spacing is None and model in ("fracture-wrist", "fracture", "fracture-multibody"):
        pixel_spacing = _lookup_pixel_spacing(image_path, body_part=detected_body_part)

    if model == "chest-xray":
        from imaging.models.torchxrayvision_model import predict
        prediction = predict(standardised.pixels)
    elif model in ("fracture-wrist", "fracture"):
        from imaging.models.fracture_model import predict
        prediction = predict(standardised.pixels, pixel_spacing_mm=pixel_spacing)
        # Fallback: if wrist model finds nothing and we're in auto mode,
        # try multi-body model (image may actually be forearm/hand/etc.)
        if body_part_info and not prediction["findings"]:
            if not quiet:
                print("      No findings — falling back to multi-body model...", file=sys.stderr)
            from imaging.models.fracture_multibody_model import predict as predict_multi
            prediction = predict_multi(standardised.pixels, pixel_spacing_mm=pixel_spacing)
            model = "fracture-multibody"
            model_info = AVAILABLE_MODELS[model]
    elif model == "fracture-multibody":
        from imaging.models.fracture_multibody_model import predict
        prediction = predict(standardised.pixels, pixel_spacing_mm=pixel_spacing)
    else:
        return {"success": False, "error": f"No inference handler for model '{model}'"}
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

    result = {
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

    if body_part_info:
        result["body_part_detection"] = body_part_info

    return result


def _lookup_pixel_spacing(image_path: str, body_part: str | None = None) -> float | None:
    """Try to find pixel spacing from dataset CSV, or estimate from body part.

    Priority:
      1. Exact match in GRAZPEDWRI-DX dataset CSV (most accurate)
      2. Body-part-specific default based on typical CR/DR detector pitch
         and standard source-to-image distances for that anatomy
    """
    import csv

    stem = Path(image_path).stem
    # Search for dataset CSV near the image or in known locations
    image_dir = Path(image_path).resolve().parent
    candidates = [
        image_dir / "dataset.csv",
        image_dir.parent / "dataset.csv",
        image_dir.parent.parent / "dataset.csv",
    ]
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

    # Body-part-specific defaults (mm/pixel) — typical CR/DR values
    # Based on common detector pixel pitch (0.1–0.2mm) and standard
    # source-to-image distances for each anatomy
    BODY_PART_SPACING = {
        "wrist": 0.144,      # Standard wrist PA/lateral
        "fingers": 0.100,    # Fine detail extremity
        "hand": 0.120,       # Hand PA
        "forearm": 0.175,    # Forearm AP/lateral
        "elbow": 0.175,      # Elbow AP/lateral
        "humerus": 0.200,    # Humerus AP
        "shoulder": 0.200,   # Shoulder AP
    }

    if body_part and body_part in BODY_PART_SPACING:
        return BODY_PART_SPACING[body_part]

    # Fallback for unknown body parts
    return 0.150


def main():
    parser = argparse.ArgumentParser(description="Modular imaging pipeline")
    parser.add_argument("image_path", help="Path to medical image")
    parser.add_argument("--output-dir", help="Base output directory")
    parser.add_argument("--json-stdout", action="store_true", help="Output JSON to stdout")
    parser.add_argument("--stage1-only", action="store_true", help="Run Stage 1 only (for confirmation)")
    valid_models = list(AVAILABLE_MODELS.keys()) + ["auto"]
    parser.add_argument("--model", default="chest-xray",
                        choices=valid_models,
                        help="Model to use for analysis (default: chest-xray). Use 'auto' for smart body part detection.")
    parser.add_argument("--pixel-spacing", type=float, default=None,
                        help="Pixel spacing in mm (for real-world size estimates)")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    parser.add_argument("--detect-body-part", action="store_true",
                        help="Run body part auto-detection (useful with --stage1-only)")
    args = parser.parse_args()

    # Pixel spacing: use CLI arg if provided, otherwise resolved inside run_pipeline
    pixel_spacing = args.pixel_spacing

    result = run_pipeline(
        image_path=args.image_path,
        output_dir=args.output_dir,
        quiet=args.quiet or args.json_stdout,
        stage1_only=args.stage1_only,
        model=args.model,
        pixel_spacing=pixel_spacing,
        detect_body_part_flag=args.detect_body_part,
    )

    if args.json_stdout:
        print(json.dumps(result))
    else:
        print(json.dumps(result, indent=2))

    if not result.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
