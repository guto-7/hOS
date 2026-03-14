"""
claude_interpreter.py — Stage 3: AI-powered clinical interpretation.

Uses the Claude API (multimodal) to interpret imaging findings,
providing clinical context, severity assessment, and recommended next steps.
"""

import base64
import json
from pathlib import Path

# Model to use for interpretation
CLAUDE_MODEL = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """\
You are a radiological AI assistant integrated into a medical imaging analysis platform. \
Your role is to provide an educational interpretation of AI-detected findings on medical images.

You will receive:
1. The original medical image (X-ray)
2. An annotated image showing model detections (heatmap or bounding boxes)
3. Structured findings data from the detection model

Provide your response in this exact structure using markdown:

## Clinical Interpretation
Describe what the AI model detected, correlating the findings with visible features \
in the image. Explain each significant finding in accessible clinical language.

## Severity Assessment
Assess the overall severity based on the combination of findings. \
Note any findings that may warrant urgent attention versus routine follow-up.

## Recommended Next Steps
Suggest appropriate next steps such as additional imaging, specialist referral, \
or clinical correlation.

Guidelines:
- Be concise but thorough
- Use accessible medical language
- When findings are borderline or low-confidence, note the possibility of false positives
- If no significant findings are detected, clearly state that the scan appears normal
- Do NOT include any disclaimers or caveats about being an AI — the application handles that separately\
"""


def interpret_findings(
    stored_image_path: str,
    heatmap_base64: str,
    findings: list[dict],
    summary: dict,
    model_key: str,
    image_metadata: dict,
) -> str:
    """
    Call Claude API with the original image + annotated image + findings.

    Returns the interpretation as a markdown string.
    Raises if ANTHROPIC_API_KEY is not set or API call fails.
    """
    from dotenv import load_dotenv

    # Load .env from the data directory
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(env_path)

    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    # Build content blocks
    content = []

    # 1. Original image
    original_b64, media_type = _encode_image(stored_image_path)
    if original_b64:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": original_b64,
            },
        })

    # 2. Annotated image (heatmap / bounding boxes)
    if heatmap_base64:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": heatmap_base64,
            },
        })

    # 3. Text context
    model_desc = {
        "chest-xray": "TorchXRayVision DenseNet — screens for 18 chest pathologies with GradCAM heatmap",
        "fracture": "YOLOv8 — bone fracture detection with bounding boxes",
    }.get(model_key, model_key)

    findings_text = json.dumps(findings, indent=2)
    summary_text = json.dumps(summary, indent=2)

    context = f"""## Analysis Context

**Model**: {model_desc}
**Image**: {image_metadata.get('format', 'Unknown')} {image_metadata.get('width', '?')}×{image_metadata.get('height', '?')}

### Detection Findings
```json
{findings_text}
```

### Summary
```json
{summary_text}
```

The first image is the original X-ray. The second image shows the model's detections \
({"GradCAM activation heatmap highlighting regions driving predictions" if model_key == "chest-xray" else "bounding boxes around detected abnormalities"}).

Please interpret these findings."""

    content.append({"type": "text", "text": context})

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    return response.content[0].text


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
