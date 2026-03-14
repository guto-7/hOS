"""
storage.py — Raw image storage with SHA-256 deduplication.

Saves the original image to ~/Documents/hOS/uploads/imaging/ using a
SHA-256 hash as the filename. Provides automatic deduplication and
strips PII from the original filename.

Input:  file path or file bytes + original filename
Output: StorageResult with hash, stored path, and duplicate flag
"""

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path


DEFAULT_UPLOADS_DIR = Path.home() / "Documents" / "hOS" / "uploads" / "imaging"


@dataclass
class StorageResult:
    file_hash: str
    stored_path: Path
    original_name: str
    is_duplicate: bool


def compute_hash(file_path: str | Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_hash_from_bytes(data: bytes) -> str:
    """Compute SHA-256 hash from raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _get_extension(file_path: str | Path) -> str:
    """Get file extension, defaulting to .png."""
    ext = Path(file_path).suffix.lower()
    return ext if ext else ".png"


def store_image(
    file_path: str | Path,
    uploads_dir: str | Path = DEFAULT_UPLOADS_DIR,
) -> StorageResult:
    """
    Store an image using its SHA-256 hash as the filename.

    - If a file with the same hash already exists, skip the copy
      and return is_duplicate=True.
    - The original filename is preserved in the result for metadata.
    """
    path = Path(file_path)
    uploads = Path(uploads_dir)
    uploads.mkdir(parents=True, exist_ok=True)

    file_hash = compute_hash(path)
    ext = _get_extension(path)
    dest = uploads / f"{file_hash}{ext}"

    is_duplicate = dest.exists()
    if not is_duplicate:
        shutil.copy2(path, dest)

    return StorageResult(
        file_hash=file_hash,
        stored_path=dest,
        original_name=path.name,
        is_duplicate=is_duplicate,
    )


def store_image_from_bytes(
    data: bytes,
    original_name: str,
    uploads_dir: str | Path = DEFAULT_UPLOADS_DIR,
) -> StorageResult:
    """Store an image from raw bytes (used when receiving from Tauri frontend)."""
    uploads = Path(uploads_dir)
    uploads.mkdir(parents=True, exist_ok=True)

    file_hash = compute_hash_from_bytes(data)
    ext = _get_extension(original_name)
    dest = uploads / f"{file_hash}{ext}"

    is_duplicate = dest.exists()
    if not is_duplicate:
        dest.write_bytes(data)

    return StorageResult(
        file_hash=file_hash,
        stored_path=dest,
        original_name=original_name,
        is_duplicate=is_duplicate,
    )
