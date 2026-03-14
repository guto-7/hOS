"""
fracture_model.py — Bone fracture detection model adapter.

Uses YOLOv8 trained on GRAZPEDWRI-DX (20,327 pediatric wrist X-rays)
for object detection with bounding boxes around fracture sites.

Returns an annotated image with bounding boxes drawn over the original
and a list of findings with class, confidence, and bbox coordinates.
"""

import numpy as np
from pathlib import Path

YOLO_WEIGHTS = Path(__file__).parent / "yolov8_fracture.pt"

# YOLO classes we care about clinically
CLINICAL_CLASSES = {"fracture", "boneanomaly", "bonelesion", "periostealreaction"}

# Readable labels
CLASS_LABELS = {
    "fracture": "Fracture",
    "boneanomaly": "Bone Anomaly",
    "bonelesion": "Bone Lesion",
    "periostealreaction": "Periosteal Reaction",
}

# Colors per class (BGR for OpenCV)
CLASS_COLORS = {
    "fracture": (0, 0, 255),        # red
    "boneanomaly": (0, 165, 255),    # orange
    "bonelesion": (0, 255, 255),     # yellow
    "periostealreaction": (255, 0, 255),  # magenta
}


def predict(standardised_pixels: np.ndarray, pixel_spacing_mm: float | None = None) -> dict:
    """
    Run fracture detection on a standardised image.

    Args:
        standardised_pixels: 2D numpy array, float64, [0, 1], shape (H, W)
        pixel_spacing_mm: Optional mm per pixel (from DICOM/dataset metadata).
                          When provided, fracture sizes are reported in mm.

    Returns:
        Dict with:
          - findings: [{pathology, probability, level, bbox, size}, ...]
          - heatmap: base64-encoded PNG of annotated image with bounding boxes
          - heatmap_pathology: summary label
    """
    import os
    os.environ["YOLO_VERBOSE"] = "false"

    from PIL import Image
    from ultralytics import YOLO

    # Convert standardised [0,1] grayscale to RGB PIL
    img_uint8 = (standardised_pixels * 255).astype(np.uint8)
    pil_img = Image.fromarray(img_uint8, mode="L").convert("RGB")

    if not YOLO_WEIGHTS.exists():
        return {
            "findings": [],
            "heatmap": "",
            "heatmap_pathology": "No model weights found",
        }

    model = YOLO(str(YOLO_WEIGHTS))
    results = model.predict(pil_img, verbose=False, conf=0.15)
    result = results[0]

    img_h, img_w = standardised_pixels.shape[:2]
    img_area = img_h * img_w

    findings = []
    boxes_to_draw = []

    for box in result.boxes:
        cls_id = int(box.cls[0])
        cls_name = model.names[cls_id]
        conf = float(box.conf[0])
        xyxy = box.xyxy[0].tolist()

        if cls_name not in CLINICAL_CLASSES:
            continue

        label = CLASS_LABELS.get(cls_name, cls_name)

        # Calculate fracture region size
        bbox_w = xyxy[2] - xyxy[0]
        bbox_h = xyxy[3] - xyxy[1]
        bbox_area = bbox_w * bbox_h
        area_pct = (bbox_area / img_area) * 100

        size_info = {
            "width_px": round(bbox_w, 1),
            "height_px": round(bbox_h, 1),
            "area_px": round(bbox_area, 1),
            "area_pct": round(area_pct, 2),
        }

        if pixel_spacing_mm:
            size_info["width_mm"] = round(bbox_w * pixel_spacing_mm, 1)
            size_info["height_mm"] = round(bbox_h * pixel_spacing_mm, 1)
            size_info["pixel_spacing_mm"] = pixel_spacing_mm

        findings.append({
            "pathology": label,
            "probability": round(conf, 4),
            "level": _classify_level(conf),
            "bbox": {
                "x1": round(xyxy[0], 1),
                "y1": round(xyxy[1], 1),
                "x2": round(xyxy[2], 1),
                "y2": round(xyxy[3], 1),
            },
            "size": size_info,
        })

        if pixel_spacing_mm:
            size_label = f"{bbox_w * pixel_spacing_mm:.1f}x{bbox_h * pixel_spacing_mm:.1f}mm"
        else:
            size_label = f"{bbox_w:.0f}x{bbox_h:.0f}px"
        boxes_to_draw.append({
            "xyxy": xyxy,
            "label": f"{label} {conf:.0%} ({size_label})",
            "color": CLASS_COLORS.get(cls_name, (0, 255, 0)),
        })

    findings.sort(key=lambda x: x["probability"], reverse=True)

    # Draw bounding boxes on the image
    annotated_b64 = _draw_boxes(standardised_pixels, boxes_to_draw)

    fracture_count = sum(1 for f in findings if "Fracture" in f["pathology"])
    total = len(findings)

    if fracture_count > 0:
        top_conf = max(f["probability"] for f in findings if "Fracture" in f["pathology"])
        summary_label = f"Fracture detected ({top_conf:.0%} confidence) — {total} finding{'s' if total != 1 else ''}"
    elif total > 0:
        summary_label = f"{total} abnormalit{'ies' if total != 1 else 'y'} detected"
    else:
        summary_label = "No fractures detected"

    return {
        "findings": findings,
        "heatmap": annotated_b64,
        "heatmap_pathology": summary_label,
    }


def _draw_boxes(standardised_pixels: np.ndarray, boxes: list) -> str:
    """Draw bounding boxes on the image and return as base64 PNG."""
    import cv2
    import base64

    # Convert grayscale [0,1] to BGR uint8
    img_uint8 = (standardised_pixels * 255).astype(np.uint8)
    canvas = cv2.cvtColor(img_uint8, cv2.COLOR_GRAY2BGR)

    h, w = canvas.shape[:2]
    thickness = max(2, int(min(h, w) / 200))
    font_scale = max(0.4, min(h, w) / 800)
    font = cv2.FONT_HERSHEY_SIMPLEX

    for box in boxes:
        x1, y1, x2, y2 = [int(v) for v in box["xyxy"]]
        color = box["color"]
        label = box["label"]

        # Draw box
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness)

        # Draw label background
        (tw, th), baseline = cv2.getTextSize(label, font, font_scale, 1)
        label_y = max(y1, th + 4)
        cv2.rectangle(canvas, (x1, label_y - th - 4), (x1 + tw + 4, label_y + baseline), color, -1)
        cv2.putText(canvas, label, (x1 + 2, label_y - 2), font, font_scale, (255, 255, 255), 1, cv2.LINE_AA)

    # Encode to base64 PNG
    _, buf = cv2.imencode(".png", canvas)
    return base64.b64encode(buf).decode("utf-8")


def _classify_level(prob: float) -> str:
    """Classify probability into 4-level severity."""
    if prob >= 0.7:
        return "HIGH"
    elif prob >= 0.4:
        return "MODERATE"
    elif prob >= 0.2:
        return "LOW"
    else:
        return "MINIMAL"
