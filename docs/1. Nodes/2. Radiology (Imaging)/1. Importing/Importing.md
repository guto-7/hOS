# Radiology — Stage 1: Importing

## Purpose

Stage 1 is responsible for getting medical images into the system. It covers what file formats the user can upload, where the raw image is stored, how metadata is extracted, quality checks performed, and the user confirmation step before analysis begins.

Unlike bloodwork (which extracts structured tabular data from PDFs), radiology importing deals with raw pixel data. The goal is to validate the image, store it with deduplication, and surface enough metadata for the user to confirm before committing to model inference (which is computationally expensive).

---

## 1.1 Accepted File Formats

**Decision: Raster image formats with direct pixel access (PNG, JPEG, WebP, TIFF, BMP)**

| Format | Verdict | Reasoning |
|---|---|---|
| PNG | **Accepted** | Lossless compression. Common export format from PACS viewers and research datasets. Preserves exact pixel values — critical for reproducible inference. |
| JPEG | **Accepted** | Lossy but ubiquitous. Most consumer-facing medical image exports (patient portals, email attachments) are JPEG. Compression artifacts are tolerable for screening-level analysis. |
| TIFF | **Accepted** | Standard format for high-bit-depth medical images. Supports 16-bit grayscale (common in digital radiography). |
| WebP | **Accepted** | Modern web format. Increasingly used in browser-based PACS viewers. Supports both lossy and lossless. |
| BMP | **Accepted** | Uncompressed raster. Occasionally exported from legacy systems. |
| DICOM (.dcm) | **Rejected (v1)** | The clinical standard, but DICOM files contain complex metadata structures, multi-frame sequences, and vendor-specific private tags. Proper DICOM parsing requires a dedicated library (pydicom) and handling of transfer syntaxes, photometric interpretations, and windowing parameters. Patients rarely have direct access to raw DICOM files — they receive exported images from patient portals. Future version should add DICOM support as a priority. |
| NIfTI (.nii/.nii.gz) | **Rejected (v1)** | Research format for volumetric data (3D/4D). Not a consumer format. Would require fundamentally different UI (volume viewer vs 2D image). |
| Photo/camera capture | **Accepted (implicit)** | Phone photos of X-rays on lightboxes are just JPEG/PNG files. Accepted by format, but quality warnings will flag issues (non-grayscale, small dimensions). |

**Why these formats for v1:** They cover the vast majority of real-world user uploads — images exported from patient portals, saved from radiology reports, or photographed from physical films. PIL (Pillow) handles all of them with consistent metadata extraction. Every format produces a pixel array that Stage 2 can standardise.

**Key difference from bloodwork:** Bloodwork restricts to PDF-only because extraction accuracy matters — a misread decimal is clinically dangerous. For imaging, the raw pixels are what they are. Format validation is about ensuring the file is a readable image, not about extraction fidelity.

---

## 1.2 Raw Image Storage

**Decision: Save the original image to `~/Documents/hOS/uploads/imaging/` with a SHA-256 hash filename, preserving the original extension**

| Aspect | Decision | Reasoning |
|---|---|---|
| Storage location | `~/Documents/hOS/uploads/imaging/` | Local-first. Subdirectory under `uploads/` separates imaging files from bloodwork PDFs (which use `uploads/` root). |
| Filename | `{SHA-256 hash}.{original extension}` | Deduplication for free — same image produces same hash. Extension preserved (unlike bloodwork) because image format matters for re-processing (PNG vs JPEG vs TIFF have different pixel characteristics). |
| Original filename | Stored in `StorageResult.original_name` metadata | Preserved for display ("You uploaded chest_xray_lateral.png") but not used as storage key. Strips PII from filenames. |
| Retention | Permanent until user deletes | The raw image is the audit trail. If standardisation or model inference improves, re-process from original without re-upload. |

**Why keep the raw image?**
1. **Re-processing** — new models or improved standardisation can be applied to the original without user action
2. **Auditability** — the user can always cross-reference findings against the original image
3. **Model-agnostic storage** — raw pixels are independent of any model's preprocessing requirements

---

## 1.3 Validation and Metadata Extraction

**Decision: PIL-based validation with comprehensive metadata extraction**

### Pipeline

```
Image file
  |
  |-> PIL Image.open() + .verify() — check file is readable and not corrupt
  |
  |-> Format check — ensure format in {PNG, JPEG, TIFF, WEBP, BMP}
  |
  |-> Metadata extraction:
  |     - width, height (dimensions)
  |     - channels (1=grayscale, 3=RGB, 4=RGBA)
  |     - bit_depth (8, 16, 32 per channel)
  |     - format (string)
  |     - file_size_kb
  |     - is_grayscale (mode in {L, LA, I, F, 1, I;16})
  |     - has_exif (boolean)
  |     - orientation (EXIF tag 274, if present)
  |
  |-> Quality warnings:
  |     - Image < 100px in any dimension → "may affect analysis quality"
  |     - Not grayscale → "will be converted in Stage 2"
  |     - EXIF rotation != 1 → "will be corrected in Stage 2"
  |
  |-> SHA-256 hash computation + storage
  |
  └-> Output: ImageMetadata + StorageResult + quality report
```

### Why PIL-based validation over manual byte parsing?

| Criterion | PIL Validation | Manual Parsing |
|---|---|---|
| Format coverage | All major formats via single API | Per-format magic bytes + headers |
| Corruption detection | `.verify()` checks internal consistency | Would need per-format structural validation |
| Metadata extraction | Unified API across formats | Different metadata locations per format |
| EXIF handling | Built-in `getexif()` | Requires separate EXIF parser |
| Maintainability | Single dependency (Pillow) | Custom code per format |

**Why minimum 100px?** Below 100px, medical images lack sufficient anatomical detail for any meaningful analysis. This catches thumbnails, icons, and accidentally cropped images before they waste compute on inference.

---

## 1.4 User Confirmation

**Decision: Two-stage confirmation — Stage 1 returns for user review before committing to Stage 2 + model inference**

The confirmation screen shows:
- **Image preview** — local blob URL, not sent to any server
- **Metadata chips** — format, dimensions, channels, bit depth, file size
- **Grayscale indicator** — whether the image is already grayscale or will be converted
- **Duplicate flag** — if this image hash already exists in storage
- **Quality warnings** — highlighted in a yellow banner
- **Selected model reminder** — which model will be used for inference

### Why two-stage confirmation?

| Reason | Explanation |
|---|---|
| **Compute cost** | Model inference (especially TorchXRayVision) takes 5-30 seconds. Don't waste this on a wrong file. |
| **User trust** | The user sees what the system detected about their image before analysis begins. No black-box processing. |
| **Error prevention** | Catches wrong file type (photo vs X-ray), wrong orientation, duplicate uploads — all before spending time on inference. |
| **Model selection verification** | User confirms the right model is selected before committing (chest X-ray vs fracture detection). |

### What happens on confirm

- Stage 2 (standardisation) begins — EXIF correction, grayscale conversion, intensity normalisation
- Selected model adapter runs inference on the standardised image
- Results (findings with probabilities and severity levels) returned to frontend
- Analysis stored to `~/Documents/hOS/results/radiology/{hash}.json`

---

## 1.5 Stage 1 Summary

```
User selects analysis model (Chest X-ray or Fracture Detection)
  |
  |-> User drops/selects image file
  |-> Validate format (PNG, JPEG, WebP, TIFF, BMP)
  |-> Extract metadata via PIL (dimensions, channels, bit depth, EXIF)
  |-> Compute SHA-256 hash
  |-> Store raw image to ~/Documents/hOS/uploads/imaging/{hash}.{ext}
  |-> Generate quality warnings
  |-> Present confirmation screen to user
  |     - Image preview, metadata chips, quality warnings
  |     - Model reminder, duplicate indicator
  |-> User reviews, confirms
  └-> Hand off to Stage 2 (standardisation) + model inference
```

| Input | Output |
|---|---|
| Raw image file from user + model selection | Validated image in storage, metadata extracted, quality assessed, user confirmed |
