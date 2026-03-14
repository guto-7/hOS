#!/usr/bin/env python3
"""
run_interpret.py — Stage 3: Claude API interpretation of imaging results.

Reads a saved imaging result JSON, sends the original image + annotated image +
findings to Claude, and returns the interpretation.

Usage:
    python3 run_interpret.py --result-path /path/to/result.json [--json-stdout]
"""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from imaging.interpretation.claude_interpreter import interpret_findings


def main():
    parser = argparse.ArgumentParser(description="Stage 3: Claude interpretation")
    parser.add_argument("--result-path", required=True, help="Path to saved imaging result JSON")
    parser.add_argument("--json-stdout", action="store_true", help="Output JSON to stdout")
    args = parser.parse_args()

    result_path = Path(args.result_path)
    if not result_path.exists():
        output = {"success": False, "error": f"Result file not found: {result_path}"}
        print(json.dumps(output))
        sys.exit(1)

    result = json.loads(result_path.read_text())

    stored_path = result.get("record", {}).get("stored_path", "")
    heatmap_b64 = result.get("heatmap", "")
    findings = result.get("findings", [])
    summary = result.get("summary", {})
    model_key = result.get("model_key", "chest-xray")
    image_metadata = result.get("image_metadata", {})

    try:
        interpretation = interpret_findings(
            stored_image_path=stored_path,
            heatmap_base64=heatmap_b64,
            findings=findings,
            summary=summary,
            model_key=model_key,
            image_metadata=image_metadata,
        )

        output = {"success": True, "interpretation": interpretation}
    except Exception as e:
        output = {"success": False, "error": str(e)}

    if args.json_stdout:
        print(json.dumps(output))
    else:
        print(json.dumps(output, indent=2))

    if not output.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
