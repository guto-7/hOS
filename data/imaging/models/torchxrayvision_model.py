"""
torchxrayvision_model.py — TorchXRayVision model adapter.

Takes a StandardisedImage (output of Stage 2) and runs chest X-ray
pathology prediction. Handles all model-specific transforms internally:
  - Scale from [0, 1] to [-1024, 1024] (torchxrayvision convention)
  - Resize to 224x224 (DenseNet input size)
  - Add batch + channel dimensions

This adapter is separate from Stage 1+2 so the pipeline remains
model-agnostic. Other models can be added as new adapters that
consume the same StandardisedImage input.
"""

import numpy as np


def predict(standardised_pixels: np.ndarray) -> list[dict]:
    """
    Run TorchXRayVision inference on a standardised image.

    Args:
        standardised_pixels: 2D numpy array, float64, [0, 1], shape (H, W)

    Returns:
        List of findings: [{pathology, probability, level}, ...]
        sorted by probability descending.
    """
    import torch
    import torchxrayvision as xrv
    from torchvision import transforms
    import contextlib
    import io

    # Model-specific transform 1: scale to [-1024, 1024]
    img = standardised_pixels.copy()
    img = (img - 0.5) * 2048  # [0,1] → [-1024, 1024]

    # Model-specific transform 2: reshape for xrv (1, H, W)
    if img.ndim == 2:
        img = img[np.newaxis, :, :]

    # Model-specific transform 3: convert to torch tensor and resize to 224x224
    tensor = torch.from_numpy(img).float()
    resize = transforms.Compose([
        transforms.Resize(224),
        transforms.CenterCrop(224),
    ])
    tensor = resize(tensor)

    # Add batch dimension: (1, 1, 224, 224)
    tensor = tensor.unsqueeze(0)

    # Load model (suppress download output)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        model = xrv.models.DenseNet(weights="densenet121-res224-chex")
    model.eval()

    with torch.no_grad():
        preds = model(tensor)

    pathologies = model.pathologies
    probabilities = preds[0].cpu().numpy()

    findings = []
    for name, prob in zip(pathologies, probabilities):
        if not name:
            continue
        prob_val = float(prob)
        findings.append({
            "pathology": name,
            "probability": round(prob_val, 4),
            "level": _classify_level(prob_val),
        })

    findings.sort(key=lambda x: x["probability"], reverse=True)
    return findings


def _classify_level(prob: float) -> str:
    """Classify probability into a 4-level severity."""
    if prob >= 0.7:
        return "HIGH"
    elif prob >= 0.4:
        return "MODERATE"
    elif prob >= 0.2:
        return "LOW"
    else:
        return "MINIMAL"
