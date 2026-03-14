#!/usr/bin/env python3
"""
X-ray image analysis using TorchXRayVision.

Accepts a chest X-ray image path, runs pathology prediction using a
pre-trained DenseNet model, and outputs JSON results to stdout.

Usage:
    python3 xray_analysis.py <image_path> [--json-stdout]
"""

import sys
import json
import argparse
import numpy as np
from pathlib import Path


def load_and_preprocess(image_path: str) -> "np.ndarray":
    """Load an image and preprocess it for torchxrayvision."""
    import skimage.io
    import torchxrayvision as xrv

    # Read image as grayscale
    img = skimage.io.imread(image_path, as_gray=True)

    # Ensure float in [0, 1]
    if img.max() > 1.0:
        img = img / 255.0

    # torchxrayvision expects images scaled to [-1024, 1024]
    img = xrv.datasets.normalize(img, maxval=1.0, reshape=True)

    # Resize to 224x224 as expected by the model
    from torchvision import transforms
    import torch

    img = torch.from_numpy(img).float()

    transform = transforms.Compose([
        transforms.Resize(224),
        transforms.CenterCrop(224),
    ])
    img = transform(img)

    # Add batch dimension: (1, 1, 224, 224)
    if img.dim() == 2:
        img = img.unsqueeze(0).unsqueeze(0)
    elif img.dim() == 3:
        img = img.unsqueeze(0)

    return img


def analyze(image_path: str) -> dict:
    """Run pathology prediction on a chest X-ray image."""
    import torch
    import torchxrayvision as xrv

    # Load pre-trained DenseNet model (CheXpert/Stanford weights)
    # Suppress download/progress output that would pollute JSON stdout
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        model = xrv.models.DenseNet(weights="densenet121-res224-chex")
    model.eval()

    img = load_and_preprocess(image_path)

    with torch.no_grad():
        preds = model(img)

    # Map predictions to pathology names
    pathologies = model.pathologies
    probabilities = preds[0].cpu().numpy()

    findings = []
    for name, prob in zip(pathologies, probabilities):
        if not name:  # Skip empty pathology slots (not trained for this model)
            continue
        prob_val = float(prob)
        findings.append({
            "pathology": name,
            "probability": round(prob_val, 4),
            "level": _classify_level(prob_val),
        })

    # Sort by probability descending
    findings.sort(key=lambda x: x["probability"], reverse=True)

    return {
        "image": Path(image_path).name,
        "model": "densenet121-res224-chex",
        "findings": findings,
        "summary": _generate_summary(findings),
    }


def _classify_level(prob: float) -> str:
    """Classify probability into a severity level."""
    if prob >= 0.7:
        return "HIGH"
    elif prob >= 0.4:
        return "MODERATE"
    elif prob >= 0.2:
        return "LOW"
    else:
        return "MINIMAL"


def _generate_summary(findings: list) -> dict:
    """Generate a summary of the analysis."""
    high = [f for f in findings if f["level"] == "HIGH"]
    moderate = [f for f in findings if f["level"] == "MODERATE"]

    return {
        "high_probability": [f["pathology"] for f in high],
        "moderate_probability": [f["pathology"] for f in moderate],
        "total_pathologies_screened": len(findings),
        "flagged_count": len(high) + len(moderate),
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze chest X-ray images")
    parser.add_argument("image_path", help="Path to chest X-ray image")
    parser.add_argument(
        "--json-stdout",
        action="store_true",
        help="Output JSON to stdout",
    )
    args = parser.parse_args()

    image_path = args.image_path
    if not Path(image_path).exists():
        print(json.dumps({"error": f"File not found: {image_path}"}), file=sys.stderr)
        sys.exit(1)

    try:
        result = analyze(image_path)
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

    if args.json_stdout:
        print(json.dumps(result))
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
