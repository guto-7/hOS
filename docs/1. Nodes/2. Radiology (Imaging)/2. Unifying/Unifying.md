# Radiology — Stage 2: Unifying

## Purpose

Stage 2 transforms the raw validated image from Stage 1 into a standardised, model-agnostic format. It handles orientation correction, colour space normalisation, and intensity scaling. The output is a clean pixel array that any downstream model adapter can consume without knowing about the original file format, bit depth, or colour space.

Unlike bloodwork's Stage 2 (which performs unit conversion, range resolution, and flag computation against a reference file), radiology's Stage 2 is purely about **pixel standardisation**. There is no equivalent to `markers.json` — the standardisation contract is defined by the output shape: `(H, W) float64 [0.0, 1.0] grayscale`.

---

## 2.1 Design Principle

> **Model-agnostic standardisation. Model-specific transforms stay in adapters.**

Stage 2 produces a universal intermediate format. Each model adapter then applies its own requirements:

| Concern | Who Handles It | Why |
|---|---|---|
| EXIF orientation | **Stage 2** | Orientation is a property of the file, not the image content. Every consumer needs correct orientation. |
| Grayscale conversion | **Stage 2** | Medical X-rays are inherently grayscale. RGB encoding is an artifact of the export format, not a clinical signal. |
| Intensity normalisation | **Stage 2** | Different bit depths (8-bit, 16-bit) produce different raw ranges. Normalising to [0, 1] makes the data comparable regardless of source format. |
| Resolution preservation | **Stage 2** | The standardiser does NOT resize. Original resolution may carry diagnostic information (fine detail in fractures, subtle opacities). |
| Resize to model input size | **Model adapter** | Each model has its own expected input dimensions (224×224 for DenseNet, varies for SigLIP2). Resizing is a model-specific transform. |
| Intensity rescaling | **Model adapter** | TorchXRayVision expects [-1024, 1024]. Other models expect [0, 255] or [0, 1]. This is model-specific, not universal. |
| Channel duplication (1→3) | **Model adapter** | Some models expect RGB input. Converting grayscale to 3-channel is a model requirement, not a data property. |

**Why this split matters:** If a new model is added that expects different preprocessing, Stage 2 doesn't change. Only a new adapter module is needed. This is the same architectural principle as bloodwork's separation of concerns — but applied to pixel processing instead of unit conversion.

---

## 2.2 Standardisation Pipeline

After the user confirms Stage 1 metadata:

```
Stored raw image (~/Documents/hOS/uploads/imaging/{hash}.{ext})
  |
  |-> 1. Load image via PIL
  |     img = Image.open(stored_path)
  |     Record original dimensions
  |
  |-> 2. EXIF orientation correction
  |     Check tag 274 (Orientation)
  |     Apply ImageOps.exif_transpose(img)
  |     Records whether correction was applied
  |
  |-> 3. Grayscale conversion
  |     If mode not in {L, I, F}: img.convert("L")
  |     Records whether conversion was applied
  |
  |-> 4. Intensity normalisation
  |     np.array(img, dtype=np.float64)
  |     If max > 1.0: divide by max value
  |     Result: [0.0, 1.0] range, float64
  |
  |-> 5. Preserve resolution
  |     No resize — shape is (original_H, original_W)
  |
  └-> Output: StandardisedImage
        pixels: np.ndarray (H, W) float64 [0, 1]
        + metadata about what transformations were applied
```

### Why this order matters

1. **EXIF first** — orientation must be corrected before any pixel processing. A rotated image produces incorrect model predictions.
2. **Grayscale before normalisation** — converting after normalisation would lose precision. Grayscale conversion via PIL's `convert("L")` uses the standard luminance formula (0.299R + 0.587G + 0.114B).
3. **Normalisation last** — dividing by max value works on any bit depth (8-bit: 0-255, 16-bit: 0-65535, 32-bit float: arbitrary range). The result is always [0, 1].

---

## 2.3 Output Format

```python
@dataclass
class StandardisedImage:
    pixels: np.ndarray       # shape (H, W), float64, range [0.0, 1.0]
    original_height: int
    original_width: int
    standardised_height: int
    standardised_width: int
    was_converted_to_grayscale: bool
    was_orientation_corrected: bool
```

### Metadata dict (included in pipeline JSON output)

```json
{
    "original_height": 2048,
    "original_width": 2048,
    "standardised_height": 2048,
    "standardised_width": 2048,
    "was_converted_to_grayscale": false,
    "was_orientation_corrected": false,
    "dtype": "float64",
    "intensity_range": [0.0, 1.0]
}
```

### Why each field is included

| Field | Why Included | Downstream Relevance |
|---|---|---|
| `pixels` | The actual standardised image data | Direct input to model adapters |
| `original_height/width` | Record pre-standardisation dimensions | Audit trail — user can verify no unexpected cropping |
| `standardised_height/width` | Post-standardisation dimensions | Should equal original (no resize in Stage 2). Differs only if EXIF rotation swaps dimensions. |
| `was_converted_to_grayscale` | Whether colour conversion was applied | Audit trail — user knows if original was RGB |
| `was_orientation_corrected` | Whether EXIF rotation was applied | Audit trail — user knows if image was rotated |
| `dtype` | Data type of pixel array | Verification — must be float64 |
| `intensity_range` | Actual min/max of normalised pixels | Verification — should be [0.0, 1.0] for any valid image |

---

## 2.4 How Stage 2 Connects to Model Inference

Stage 2's output flows directly to the selected model adapter. Each adapter transforms the standardised pixels to match its model's expected input:

### TorchXRayVision (Chest X-ray)

```python
# Stage 2 output: (H, W) float64 [0, 1]
img = standardised.pixels.copy()

# Model-specific: scale to [-1024, 1024]
img = (img - 0.5) * 2048

# Model-specific: add channel dim → (1, H, W)
img = img[np.newaxis, :, :]

# Model-specific: resize to 224×224
tensor = torch.from_numpy(img).float()
tensor = transforms.Compose([Resize(224), CenterCrop(224)])(tensor)

# Model-specific: add batch dim → (1, 1, 224, 224)
tensor = tensor.unsqueeze(0)
```

### SigLIP2 (Fracture Detection)

```python
# Stage 2 output: (H, W) float64 [0, 1]

# Model-specific: convert to uint8 RGB PIL Image
img_uint8 = (standardised.pixels * 255).astype(np.uint8)
pil_img = Image.fromarray(img_uint8, mode="L").convert("RGB")

# Model-specific: AutoImageProcessor handles resize
inputs = processor(images=pil_img, return_tensors="pt")
```

### Adding a new model

To add a new model adapter:
1. Create `data/imaging/models/{model_name}_model.py`
2. Implement `predict(standardised_pixels: np.ndarray) -> list[dict]`
3. Apply model-specific transforms inside `predict()`
4. Return `[{"pathology": str, "probability": float, "level": str}, ...]`
5. Register in `run_imaging.py::AVAILABLE_MODELS`
6. Add to frontend `MODELS` array in `RadiologyContent.tsx`

No changes to Stage 1 or Stage 2 required.

---

## 2.5 Comparison with Bloodwork Stage 2

| Aspect | Bloodwork Stage 2 | Radiology Stage 2 |
|---|---|---|
| **Input** | Raw extracted marker values from PDF | Raw pixel data from image file |
| **Reference data** | `markers.json` (62 markers, aliases, units, ranges) | None — no equivalent reference file |
| **Operations** | Alias resolution, unit conversion, range resolution, flag computation, deviation calculation | EXIF correction, grayscale conversion, intensity normalisation |
| **Output** | Enriched JSON with standardised markers + flags + deviations | `StandardisedImage` — clean pixel array |
| **Determinism** | Same PDF + same profile = same output | Same image = same output (fully deterministic) |
| **ML relevance** | Produces the exact feature vector for classifiers | Produces the standardised input for model adapters |
| **Complexity** | High — multi-step with demographic context | Low — three straightforward pixel operations |
| **Why different** | Bloodwork data is structured but variable (units, labs, names). Standardisation is about alignment. | Image data is already numeric. Standardisation is about format normalisation. |

---

## 2.6 Stage 2 Summary

```
Confirmed image from Stage 1 (~/Documents/hOS/uploads/imaging/{hash}.{ext})
  |
  |-> EXIF orientation correction (ImageOps.exif_transpose)
  |-> Grayscale conversion (PIL convert("L"))
  |-> Intensity normalisation (float64, [0, 1])
  |-> Resolution preserved (no resize)
  |
  └-> StandardisedImage
        |
        |-> Model adapter applies model-specific transforms
        |-> Inference produces findings [{pathology, probability, level}]
        └-> Results returned to frontend for display
```

| Input | Output |
|---|---|
| Raw image file from storage | `StandardisedImage`: (H, W) float64 [0, 1] grayscale array, model-agnostic, ready for any adapter |
