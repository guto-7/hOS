"""
validator.py — Image format validation and metadata extraction.

Validates that the uploaded file is a supported medical image format,
extracts dimensional/colour metadata, and performs basic quality checks.

Input:  file path to an image
Output: ImageMetadata with dimensions, channels, bit depth, quality warnings
"""

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ExifTags


SUPPORTED_FORMATS = {"PNG", "JPEG", "TIFF", "WEBP", "BMP"}
MIN_DIMENSION = 100  # pixels — reject tiny images


@dataclass
class ImageMetadata:
    width: int
    height: int
    channels: int
    bit_depth: int
    format: str
    file_size_kb: float
    is_grayscale: bool
    has_exif: bool
    orientation: int | None  # EXIF orientation tag if present
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "channels": self.channels,
            "bit_depth": self.bit_depth,
            "format": self.format,
            "file_size_kb": round(self.file_size_kb, 1),
            "is_grayscale": self.is_grayscale,
            "has_exif": self.has_exif,
            "orientation": self.orientation,
            "warnings": self.warnings,
        }


def _get_bit_depth(img: Image.Image) -> int:
    """Derive per-channel bit depth from PIL mode."""
    mode_bits = {
        "1": 1, "L": 8, "P": 8, "RGB": 8, "RGBA": 8,
        "CMYK": 8, "YCbCr": 8, "I": 32, "F": 32,
        "I;16": 16, "I;16L": 16, "I;16B": 16,
        "LA": 8, "PA": 8, "RGBa": 8,
    }
    return mode_bits.get(img.mode, 8)


def _get_channels(img: Image.Image) -> int:
    """Count channels from PIL mode."""
    mode_channels = {
        "1": 1, "L": 1, "P": 1, "RGB": 3, "RGBA": 4,
        "CMYK": 4, "YCbCr": 3, "I": 1, "F": 1,
        "I;16": 1, "LA": 2, "PA": 2,
    }
    return mode_channels.get(img.mode, len(img.getbands()))


def _get_exif_orientation(img: Image.Image) -> int | None:
    """Extract EXIF orientation tag if present."""
    try:
        exif = img.getexif()
        if not exif:
            return None
        for tag_id, value in exif.items():
            tag = ExifTags.TAGS.get(tag_id, "")
            if tag == "Orientation":
                return int(value)
    except Exception:
        pass
    return None


def validate_image(file_path: str | Path) -> ImageMetadata:
    """
    Validate image format and extract metadata.

    Raises ValueError if the image is unsupported or corrupt.
    """
    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"File not found: {path}")

    file_size_kb = path.stat().st_size / 1024

    try:
        img = Image.open(path)
        img.verify()  # check for corruption
        img = Image.open(path)  # re-open after verify (verify closes it)
    except Exception as e:
        raise ValueError(f"Cannot open image: {e}")

    fmt = (img.format or "").upper()
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported format '{fmt}'. Supported: {', '.join(sorted(SUPPORTED_FORMATS))}"
        )

    width, height = img.size
    channels = _get_channels(img)
    bit_depth = _get_bit_depth(img)
    is_grayscale = img.mode in ("L", "LA", "I", "F", "1", "I;16", "I;16L", "I;16B")
    has_exif = bool(img.getexif())
    orientation = _get_exif_orientation(img)

    warnings = []
    if width < MIN_DIMENSION or height < MIN_DIMENSION:
        warnings.append(f"Image is very small ({width}x{height}px) — may affect analysis quality")
    if not is_grayscale:
        warnings.append("Image is not grayscale — will be converted in Stage 2")
    if orientation and orientation != 1:
        warnings.append("Image has EXIF rotation — will be corrected in Stage 2")

    return ImageMetadata(
        width=width,
        height=height,
        channels=channels,
        bit_depth=bit_depth,
        format=fmt,
        file_size_kb=file_size_kb,
        is_grayscale=is_grayscale,
        has_exif=has_exif,
        orientation=orientation,
        warnings=warnings,
    )
