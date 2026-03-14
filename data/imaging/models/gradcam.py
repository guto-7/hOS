"""
gradcam.py — Heatmap generation and overlay utilities.

Provides:
  - GradCAM for CNNs (e.g. DenseNet chest X-ray model)
  - Attention rollout for Vision Transformers (e.g. SigLIP2 fracture model)
  - Overlay/encoding helpers shared by all model adapters
"""

import numpy as np
import torch
import torch.nn.functional as F


class GradCAM:
    """
    Gradient-weighted Class Activation Mapping for CNNs.

    Usage:
        cam = GradCAM(model, target_layer)
        heatmap = cam.generate(input_tensor, target_index=3)
    """

    def __init__(self, model: torch.nn.Module, target_layer: torch.nn.Module):
        self.model = model
        self.gradients: torch.Tensor | None = None
        self.activations: torch.Tensor | None = None

        target_layer.register_forward_hook(self._save_activation)
        target_layer.register_full_backward_hook(self._save_gradient)

    def _save_activation(self, module, input, output):
        self.activations = output.detach()

    def _save_gradient(self, module, grad_input, grad_output):
        self.gradients = grad_output[0].detach()

    def generate(self, input_tensor: torch.Tensor, target_index: int) -> np.ndarray:
        """
        Generate GradCAM heatmap.

        Args:
            input_tensor: Model input (batch, channels, H, W)
            target_index: Index of the target output neuron.

        Returns:
            2D numpy array (h, w) normalised to [0, 1].
        """
        self.model.eval()
        output = self.model(input_tensor)

        self.model.zero_grad()
        target = output[0, target_index]
        target.backward(retain_graph=True)

        gradients = self.gradients   # (batch, C, h, w)
        activations = self.activations  # (batch, C, h, w)

        weights = gradients.mean(dim=(2, 3), keepdim=True)
        cam = (weights * activations).sum(dim=1, keepdim=True)
        cam = F.relu(cam)

        cam = cam.squeeze().cpu().numpy()
        if cam.max() > 0:
            cam = cam / cam.max()

        return cam


def attention_rollout(
    model: torch.nn.Module,
    input_tensor: torch.Tensor,
    head_fusion: str = "mean",
    discard_ratio: float = 0.1,
) -> np.ndarray:
    """
    Attention Rollout for Vision Transformers.

    Aggregates attention maps across all transformer layers to produce
    a spatial map showing where the model focuses.

    Args:
        model: A HuggingFace ViT-style model (must output attentions).
        input_tensor: Preprocessed pixel_values (batch, C, H, W).
        head_fusion: How to fuse attention heads — "mean", "max", or "min".
        discard_ratio: Fraction of lowest-attention tokens to zero out per layer.

    Returns:
        2D numpy array (grid_h, grid_w) normalised to [0, 1].
    """
    model.eval()

    with torch.no_grad():
        outputs = model(pixel_values=input_tensor, output_attentions=True)

    attentions = outputs.attentions  # tuple of (batch, heads, tokens, tokens)

    # Process each layer's attention
    result = torch.eye(attentions[0].size(-1))  # identity matrix (tokens x tokens)

    for attention in attentions:
        # Fuse heads
        if head_fusion == "mean":
            attention_heads_fused = attention.mean(dim=1)  # (batch, tokens, tokens)
        elif head_fusion == "max":
            attention_heads_fused = attention.max(dim=1).values
        elif head_fusion == "min":
            attention_heads_fused = attention.min(dim=1).values
        else:
            raise ValueError(f"Unknown head_fusion: {head_fusion}")

        att_mat = attention_heads_fused[0]  # (tokens, tokens) — first batch item

        # Discard lowest-attention connections
        flat = att_mat.view(-1)
        _, indices = flat.topk(int(flat.size(0) * discard_ratio), largest=False)
        flat[indices] = 0

        # Re-normalise rows to sum to 1
        row_sums = att_mat.sum(dim=-1, keepdim=True)
        row_sums = row_sums.clamp(min=1e-8)
        att_mat = att_mat / row_sums

        # Add identity (residual connection) and normalise
        identity = torch.eye(att_mat.size(0))
        att_mat = (att_mat + identity) / 2

        # Accumulate: rollout = att_mat @ previous_rollout
        result = att_mat @ result

    # Extract the CLS token's attention to all patch tokens
    # CLS token is index 0; patch tokens are 1..N
    mask = result[0, 1:]  # attention from CLS to each patch

    # Reshape to spatial grid
    num_patches = mask.size(0)
    grid_size = int(num_patches ** 0.5)

    if grid_size * grid_size != num_patches:
        # Non-square patch grid — find closest factors
        for g in range(grid_size, 0, -1):
            if num_patches % g == 0:
                grid_h, grid_w = g, num_patches // g
                break
        else:
            grid_h = grid_w = grid_size
    else:
        grid_h = grid_w = grid_size

    mask = mask[:grid_h * grid_w]  # trim if needed
    mask = mask.reshape(grid_h, grid_w).numpy()

    # Normalise to [0, 1]
    if mask.max() > mask.min():
        mask = (mask - mask.min()) / (mask.max() - mask.min())

    return mask


def generate_overlay(
    cam: np.ndarray,
    original_pixels: np.ndarray,
    alpha: float = 0.4,
) -> np.ndarray:
    """
    Overlay a heatmap on a grayscale image.

    Args:
        cam: 2D array, values in [0, 1] (any resolution).
        original_pixels: 2D array (H, W), grayscale [0, 1].
        alpha: Blend factor (0 = original only, 1 = heatmap only).

    Returns:
        RGB numpy array (H, W, 3), uint8.
    """
    from PIL import Image

    h, w = original_pixels.shape

    # Resize CAM to match original image
    cam_img = Image.fromarray((cam * 255).astype(np.uint8))
    cam_resized = np.array(cam_img.resize((w, h), Image.BILINEAR)) / 255.0

    # Apply jet colormap manually (avoid matplotlib dependency)
    heatmap_rgb = _jet_colormap(cam_resized)  # (H, W, 3) uint8

    # Convert grayscale to RGB
    gray_uint8 = (original_pixels * 255).astype(np.uint8)
    gray_rgb = np.stack([gray_uint8] * 3, axis=-1)

    # Blend
    overlay = (gray_rgb.astype(np.float32) * (1 - alpha)
               + heatmap_rgb.astype(np.float32) * alpha)
    return overlay.clip(0, 255).astype(np.uint8)


def overlay_to_base64(overlay: np.ndarray) -> str:
    """Convert RGB overlay array to base64-encoded PNG."""
    from PIL import Image
    import base64
    import io

    img = Image.fromarray(overlay)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _jet_colormap(values: np.ndarray) -> np.ndarray:
    """
    Apply a jet-like colormap to a 2D array of values in [0, 1].

    Returns (H, W, 3) uint8.
    """
    # Jet colormap: blue → cyan → green → yellow → red
    r = np.clip(1.5 - np.abs(values * 4 - 3), 0, 1)
    g = np.clip(1.5 - np.abs(values * 4 - 2), 0, 1)
    b = np.clip(1.5 - np.abs(values * 4 - 1), 0, 1)

    rgb = np.stack([r, g, b], axis=-1)
    return (rgb * 255).astype(np.uint8)
