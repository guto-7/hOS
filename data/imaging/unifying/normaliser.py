"""
normaliser.py — Model-agnostic image standardisation.

Takes a raw image file and produces a StandardisedImage: a clean,
normalised numpy array ready for any downstream model to consume.

Standardisation steps:
  1. EXIF orientation correction
  2. Grayscale conversion (single channel)
  3. Intensity normalisation to [0.0, 1.0] float64
  4. Original resolution preserved (models handle their own resize)

After Stage 2, any model adapter can take the StandardisedImage and
apply its own model-specific transforms (resize, scaling, etc.).
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


@dataclass
class StandardisedImage:
    """Model-agnostic standardised image output from Stage 2."""
    pixels: np.ndarray       # shape (H, W), float64, range [0.0, 1.0]
    original_height: int
    original_width: int
    standardised_height: int
    standardised_width: int
    was_converted_to_grayscale: bool
    was_orientation_corrected: bool

    def to_metadata_dict(self) -> dict:
        return {
            "original_height": self.original_height,
            "original_width": self.original_width,
            "standardised_height": self.standardised_height,
            "standardised_width": self.standardised_width,
            "was_converted_to_grayscale": self.was_converted_to_grayscale,
            "was_orientation_corrected": self.was_orientation_corrected,
            "dtype": str(self.pixels.dtype),
            "intensity_range": [float(self.pixels.min()), float(self.pixels.max())],
        }


def standardise_image(file_path: str | Path) -> StandardisedImage:
    """
    Load an image and standardise it for model-agnostic consumption.

    Returns a StandardisedImage with a clean [0, 1] grayscale array
    at the original resolution.
    """
    img = Image.open(file_path)
    original_width, original_height = img.size

    # Step 1: EXIF orientation correction
    was_orientation_corrected = _has_exif_rotation(img)
    img = ImageOps.exif_transpose(img)

    # Step 2: Convert to grayscale
    was_converted = img.mode not in ("L", "I", "F")
    if was_converted:
        img = img.convert("L")

    # Step 3: Convert to numpy float64 and normalise to [0, 1]
    arr = np.array(img, dtype=np.float64)

    # Handle different bit depths
    if arr.max() > 1.0:
        max_val = arr.max()
        if max_val > 0:
            arr = arr / max_val

    standardised_h, standardised_w = arr.shape

    return StandardisedImage(
        pixels=arr,
        original_height=original_height,
        original_width=original_width,
        standardised_height=standardised_h,
        standardised_width=standardised_w,
        was_converted_to_grayscale=was_converted,
        was_orientation_corrected=was_orientation_corrected,
    )


def _has_exif_rotation(img: Image.Image) -> bool:
    """Check if the image has a non-identity EXIF orientation."""
    try:
        exif = img.getexif()
        if not exif:
            return False
        # Orientation tag = 274
        orientation = exif.get(274)
        return orientation is not None and orientation != 1
    except Exception:
        return False
