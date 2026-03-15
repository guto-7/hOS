# hOS

Local-first diagnostic interpretation desktop app. Tauri v2 + React + TypeScript frontend, Rust backend, Python ML pipelines.

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Node.js | 18+ | [nodejs.org](https://nodejs.org/) |
| Rust | 1.75+ | [rustup.rs](https://rustup.rs/) |
| Python | 3.10+ | [python.org](https://www.python.org/) |

macOS also requires Xcode Command Line Tools:
```bash
xcode-select --install
```

## Setup

### 1. Clone and install frontend dependencies

```bash
git clone https://github.com/guto-7/hOS.git
cd hOS/app
npm install
```

### 2. Set up the Python environment

```bash
cd ../data
bash setup.sh
```

This creates a `.venv` in `data/` and installs all ML dependencies (PyTorch, TorchXRayVision, YOLOv8, etc.). The Tauri app auto-detects this venv at runtime.

### 3. Download model weights

The radiology pipeline requires two YOLOv8 model weight files (gitignored due to size). Download and rename them into `data/imaging/models/`:

| File | Model | Source |
|------|-------|--------|
| `yolov8_fracture.pt` | Wrist fracture (GRAZPEDWRI-DX) | [GitHub Release](https://github.com/RuiyangJu/Bone_Fracture_Detection_YOLOv8/releases/download/Trained_model/best.pt) |
| `yolov8_multibody.pt` | Multi-body fracture | [Google Drive](https://drive.google.com/drive/folders/15LnW-DVp9VOx7-hPbCGKrfb8Ot0m_qlA?usp=sharing) |

```bash
# Wrist fracture model (direct download):
curl -L -o data/imaging/models/yolov8_fracture.pt \
  https://github.com/RuiyangJu/Bone_Fracture_Detection_YOLOv8/releases/download/Trained_model/best.pt

# Multi-body fracture model:
# Download from the Google Drive link above, then:
mv ~/Downloads/best.pt data/imaging/models/yolov8_multibody.pt
```

The TorchXRayVision chest X-ray model (DenseNet) downloads automatically on first use.

### 4. Configure API key

The Claude Vision body part detection and LLM interpretation features require an Anthropic API key. Create `data/.env`:

```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > data/.env
```

This file is gitignored.

### 5. Run the app

```bash
cd app
npm run tauri dev
```

## Project Structure

```
hOS/
  app/                    # Tauri + React application
    src/                  # React frontend
    src-tauri/            # Rust backend
  data/                   # Python ML pipelines
    requirements.txt      # Python dependencies
    setup.sh              # One-command venv setup
    run_imaging.py        # Radiology pipeline entry
    run_bloodwork.py      # Hepatology pipeline entry
    run_body_composition.py  # Body composition pipeline entry
    imaging/              # Radiology ML models + processing
    bloodwork/            # Hepatology extraction + normalisation
    body_composition/     # BIA report processing
  docs/                   # Architecture and design docs
```

## Node Architecture

Each diagnostic pipeline follows the 4-layer Node trait:

1. **Import** — Ingest raw data (PDF/image), delegate to Python for extraction
2. **Unify** — Map to typed Rust structs with canonical units and reference ranges
3. **Evaluate** — Scoring systems, condition detection, certainty grading (Rust)
4. **Output** — Assemble `OutputContract` for storage and frontend consumption

Active nodes: `hepatology`, `anthropometry`, `radiology`.
