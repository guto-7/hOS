"""
fracture_model.py — Bone fracture detection model adapter.

Uses prithivMLmods/Bone-Fracture-Detection (SigLIP2-based) from HuggingFace
for binary classification: Fractured vs Not Fractured.

Takes a StandardisedImage (output of Stage 2) and runs fracture prediction.
Handles all model-specific transforms internally:
  - Convert grayscale [0, 1] to RGB (3-channel)
  - Resize to 224x224 via model's AutoImageProcessor
  - Run SigLIP2 inference

Accuracy: ~83% on validation set.
Model: prithivMLmods/Bone-Fracture-Detection
"""

import numpy as np

MODEL_ID = "prithivMLmods/Bone-Fracture-Detection"

ID2LABEL = {
    0: "Fractured",
    1: "Not Fractured",
}


def predict(standardised_pixels: np.ndarray) -> list[dict]:
    """
    Run fracture detection on a standardised X-ray image.

    Args:
        standardised_pixels: 2D numpy array, float64, [0, 1], shape (H, W)

    Returns:
        List of findings: [{pathology, probability, level}, ...]
        sorted by probability descending.
    """
    import torch
    from transformers import AutoImageProcessor, AutoModelForImageClassification
    from PIL import Image
    import contextlib
    import io

    # Convert standardised [0, 1] grayscale to uint8 RGB PIL Image
    img_uint8 = (standardised_pixels * 255).astype(np.uint8)
    pil_img = Image.fromarray(img_uint8, mode="L").convert("RGB")

    # Load model and processor
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        processor = AutoImageProcessor.from_pretrained(MODEL_ID)
        model = AutoModelForImageClassification.from_pretrained(MODEL_ID)
    model.eval()

    # Preprocess and run inference
    inputs = processor(images=pil_img, return_tensors="pt")

    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        probs = torch.nn.functional.softmax(logits, dim=1).squeeze().tolist()

    # Build findings
    findings = []
    for idx, prob in enumerate(probs):
        label = ID2LABEL.get(idx, f"class_{idx}")
        findings.append({
            "pathology": label,
            "probability": round(prob, 4),
            "level": _classify_level(label, prob),
        })

    findings.sort(key=lambda x: x["probability"], reverse=True)
    return findings


def _classify_level(label: str, prob: float) -> str:
    """
    Classify finding into 4-level severity.

    For "Fractured": probability maps to severity.
    For "Not Fractured": always MINIMAL.
    """
    if label == "Not Fractured":
        return "MINIMAL"

    # Fractured — severity based on confidence
    if prob >= 0.8:
        return "HIGH"
    elif prob >= 0.5:
        return "MODERATE"
    elif prob >= 0.3:
        return "LOW"
    else:
        return "MINIMAL"
