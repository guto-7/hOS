#!/usr/bin/env bash
# hOS Python environment setup
# Run from repo root or data/ directory:
#   ./data/setup.sh   (from repo root)
#   ./setup.sh         (from data/)

set -euo pipefail

# Resolve script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Setting up Python environment in $SCRIPT_DIR"

# Check for python3
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 not found. Install Python 3.10+ first."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "    Python version: $PYTHON_VERSION"

# Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "==> Creating virtual environment..."
    python3 -m venv .venv
else
    echo "    .venv already exists"
fi

echo "==> Installing dependencies..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

echo "==> Verifying critical imports..."
.venv/bin/python3 -c "
import PIL; print(f'    Pillow {PIL.__version__}')
import numpy; print(f'    NumPy {numpy.__version__}')
import torch; print(f'    PyTorch {torch.__version__}')
import anthropic; print(f'    Anthropic SDK {anthropic.__version__}')
"

echo ""
echo "Done. Python environment ready at $SCRIPT_DIR/.venv"
echo "The Tauri app will auto-detect this venv when running pipelines."
