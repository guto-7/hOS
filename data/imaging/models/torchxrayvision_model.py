"""
torchxrayvision_model.py — TorchXRayVision model adapter.

Takes a StandardisedImage (output of Stage 2) and runs chest X-ray
pathology prediction. Handles all model-specific transforms internally:
  - Scale from [0, 1] to [-1024, 1024] (torchxrayvision convention)
  - Resize to 224x224 (DenseNet input size)
  - Add batch + channel dimensions

Also generates GradCAM heatmaps showing WHERE the model detected
each flagged pathology, overlaid on the original image.
"""

import numpy as np


def predict(standardised_pixels: np.ndarray) -> dict:
    """
    Run TorchXRayVision inference on a standardised image.

    Args:
        standardised_pixels: 2D numpy array, float64, [0, 1], shape (H, W)

    Returns:
        Dict with:
          - findings: [{pathology, probability, level}, ...] sorted by probability desc
          - heatmap: base64-encoded PNG of GradCAM overlay on original image
    """
    import torch
    import torchxrayvision as xrv
    from torchvision import transforms
    import contextlib
    import io

    from .gradcam import GradCAM, generate_overlay, overlay_to_base64

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

    # --- Pass 1: get predictions (no hooks, no gradients) ---
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

    # --- Pass 2: GradCAM heatmap for the top finding ---
    heatmap_base64 = ""
    if findings:
        try:
            # Reload a fresh model to avoid hook conflicts with inplace ops
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                cam_model = xrv.models.DenseNet(weights="densenet121-res224-chex")

            # Disable all inplace ReLU to avoid backward hook conflicts
            _disable_inplace_relu(cam_model)
            # Monkey-patch features2 — xrv uses F.relu(inplace=True) there
            _patch_features2(cam_model)

            target_layer = cam_model.features[-1]
            cam = GradCAM(cam_model, target_layer)

            top_pathology = findings[0]["pathology"]
            top_index = list(pathologies).index(top_pathology)

            heatmap = cam.generate(tensor.clone(), target_index=top_index)
            overlay = generate_overlay(heatmap, standardised_pixels)
            heatmap_base64 = overlay_to_base64(overlay)
        except Exception:
            pass  # Heatmap is optional — don't fail the pipeline

    return {
        "findings": findings,
        "heatmap": heatmap_base64,
        "heatmap_pathology": findings[0]["pathology"] if findings else None,
    }


def _disable_inplace_relu(model):
    """Replace all inplace ReLU operations with non-inplace versions."""
    import torch.nn as nn
    for name, module in model.named_modules():
        if isinstance(module, nn.ReLU):
            module.inplace = False


def _patch_features2(model):
    """Monkey-patch features2 to use F.relu(inplace=False).

    torchxrayvision's DenseNet.features2() calls F.relu(features, inplace=True)
    which conflicts with backward hooks needed for GradCAM.
    """
    import torch.nn.functional as F

    def features2_safe(self, x):
        features = self.features(x)
        out = F.relu(features, inplace=False)  # Changed from True
        out = F.adaptive_avg_pool2d(out, (1, 1)).view(features.size(0), -1)
        return out

    import types
    model.features2 = types.MethodType(features2_safe, model)


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
