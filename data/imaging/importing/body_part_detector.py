"""
body_part_detector.py — Auto-detect body part from X-ray using Claude Vision.

Uses Claude's multimodal capabilities to classify which body part
is shown in an X-ray image. This enables smart routing to the
correct fracture detection model.
"""

import base64
import json
from pathlib import Path


CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Body parts we can route to specific models
KNOWN_BODY_PARTS = {
    "wrist", "elbow", "fingers", "forearm", "humerus", "shoulder",
    "hand", "chest", "hip", "knee", "ankle", "spine", "pelvis",
    "foot", "leg", "ribs",
}

# Map detected body parts → model keys
BODY_PART_TO_MODEL = {
    # GRAZPEDWRI-DX wrist model (specialized, better for wrist)
    "wrist": "fracture-wrist",
    # Multi-body model covers these
    "elbow": "fracture-multibody",
    "fingers": "fracture-multibody",
    "forearm": "fracture-multibody",
    "humerus": "fracture-multibody",
    "shoulder": "fracture-multibody",
    "hand": "fracture-multibody",
    # Chest X-ray model
    "chest": "chest-xray",
    "ribs": "chest-xray",
}

SYSTEM_PROMPT = """\
You are a medical imaging classifier specialising in X-ray body part identification.

Given an X-ray image, identify the PRIMARY CLINICAL FOCUS — the specific joint or bone region being examined.

CRITICAL CLASSIFICATION RULES (apply in priority order):

1. FINGERS/HAND: If the image shows individual finger bones (phalanges) or a single digit as the main subject, or if phalanges/metacarpals dominate the image → "fingers"
2. WRIST: If carpal bones or the distal radius/ulna articulation (wrist joint) are visible anywhere in the image, even if the forearm shaft is also visible → "wrist"
3. ELBOW: If the olecranon, radial head, or elbow joint is the CENTER of the image → "elbow"
4. FOREARM: If ONLY the radius and ulna shafts are shown with NO visible wrist or elbow joint → "forearm"
5. SHOULDER: If the glenohumeral joint, clavicle, or scapula is visible → "shoulder"
6. HUMERUS: If only the humerus shaft is shown → "humerus"
7. CHEST: If ribs and lung fields are the primary subject → "chest"
8. HIP/PELVIS: If the hip joint or pelvis is shown → "hip"
9. KNEE: If the knee joint is shown → "knee"
10. ANKLE: If the ankle joint is shown → "ankle"
11. FOOT: If tarsal/metatarsal bones are shown → "foot"
12. SPINE: If vertebrae are the primary subject → "spine"

KEY PRINCIPLE: When multiple regions are visible (common in X-rays), classify by the MOST DISTAL joint visible:
  - Forearm + wrist visible → "wrist" (NOT forearm)
  - Forearm + elbow visible → focus on what is at the CENTER of the image
  - Single finger/digit → "fingers" (NOT hand or forearm)

Respond with ONLY a JSON object, no other text:
{
  "body_part": "<body part>",
  "confidence": <0.0-1.0>,
  "description": "<brief description of what you see>"
}

The body_part must be one of: wrist, elbow, fingers, forearm, humerus, shoulder, hand, chest, hip, knee, ankle, spine, pelvis, foot, leg, ribs.

If you cannot determine the body part, use "unknown".\
"""


def detect_body_part(image_path: str) -> dict:
    """
    Use Claude Vision to detect which body part is shown in an X-ray.

    Args:
        image_path: Path to the X-ray image file.

    Returns:
        Dict with:
          - body_part: detected body part string
          - confidence: 0.0-1.0
          - description: brief description
          - recommended_model: model key to use for analysis
    """
    from dotenv import load_dotenv

    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(env_path)

    import anthropic

    client = anthropic.Anthropic()

    # Encode the image
    img_b64, media_type = _encode_image(image_path)
    if not img_b64:
        return {
            "body_part": "unknown",
            "confidence": 0.0,
            "description": "Could not read image file",
            "recommended_model": None,
        }

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": img_b64,
                    },
                },
                {
                    "type": "text",
                    "text": "What body part is shown in this X-ray?",
                },
            ],
        }],
    )

    # Parse the JSON response
    raw_text = response.content[0].text.strip()
    # Handle potential markdown code blocks
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        return {
            "body_part": "unknown",
            "confidence": 0.0,
            "description": f"Failed to parse response: {raw_text[:100]}",
            "recommended_model": None,
        }

    body_part = result.get("body_part", "unknown").lower().strip()
    confidence = float(result.get("confidence", 0.0))
    description = result.get("description", "")

    recommended_model = BODY_PART_TO_MODEL.get(body_part)

    return {
        "body_part": body_part,
        "confidence": confidence,
        "description": description,
        "recommended_model": recommended_model,
    }


def _encode_image(image_path: str) -> tuple[str, str]:
    """Read an image file and return (base64_string, media_type)."""
    path = Path(image_path)
    if not path.exists():
        return "", ""

    suffix = path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
    }
    media_type = media_types.get(suffix, "image/png")

    data = path.read_bytes()
    return base64.b64encode(data).decode("utf-8"), media_type
