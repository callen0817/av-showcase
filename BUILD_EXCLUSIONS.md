# Repository Exclusions & Local Rebuild Guide

This document explicitly details all dependencies, binaries, precomputed data caches, and build outputs that are excluded from this Git repository via [`.gitignore`](./.gitignore), explaining **why** each item is omitted and providing **exact instructions for rebuilding or regenerating them locally**.

---

## 1. Itemized Exclusions Overview

| Excluded Directory / File | Category | Size in Workspace | Reason Excluded from Git | Local Rebuild / Generation Command |
| :--- | :--- | :--- | :--- | :--- |
| **`node_modules/`** | Heavy Dependency | ~721 MB | Standard npm package dependencies with platform-specific native binaries. | `npm install` |
| **`release-final-*/`**<br>`release-live/` | Build Artifacts | ~35+ GB | Packaged standalone Electron application distributions (Chromium runtime, unpacked binaries, electron framework). | `npm run build:electron` or `npm run build` |
| **`dist/`**<br>`dist-web/`<br>`build/` | Build Artifacts | ~690 MB | Intermediate frontend bundler outputs and compiled assets. | `npm run build:web` |
| **`backend/dist/`**<br>`backend/build/` | Build Artifacts | ~235 MB | PyInstaller standalone executable builds (`app.exe`) and compilation caches. | `npm run build:python` |
| **`backend/__pycache__/`**<br>`*.pyc` | Python Caches | Variable | Bytecode cache files generated during Python runtime. | Generated automatically by Python runtime. |
| **`Scans/`**<br>`cache/`<br>`*.bin` | Data & Caches | Variable (GBs) | Precomputed binary point cloud caches (`lod0.bin`) and local project panorama directories. | Auto-generated during scan ingestion via UI or `ingestion.py`. |
| **`*.e57`**<br>`*.las`<br>`*.laz`<br>`*.xyz` | Raw Datasets | Multi-GB | Proprietary raw 3D scanner dataset files (e.g. NavVis, Matterport, Leica E57 files). | External source files provided by surveyor or client. |
| **`*.log`**<br>`av_backend.log`<br>`out.txt` | Ephemeral Logs | Variable | Local runtime diagnostic and process stdout/stderr logs. | Generated automatically at runtime by `app.py` and `main.js`. |
| **Temporary Images**<br>`test_extracted.jpg`<br>`stitched_pano.jpg` | Scratch Tests | ~4.5 MB | Intermediate test stitch outputs generated during pipeline validation. | Excluded (re-created by running `backend/test_stitch.py` if needed). |

---

## 2. Local Environment Rebuild Guide

To bring a fresh clone of this repository into full working condition on a local machine, follow the steps below.

### Step 1: System Prerequisites
* **Node.js**: `v18.x` or `v20.x` LTS ([Download Node.js](https://nodejs.org/))
* **Python**: `3.11.x` 64-bit ([Download Python 3.11](https://www.python.org/downloads/release/python-3119/))
  > **Important**: On Windows, Python 3.11 is strongly recommended because precompiled binary wheels for `pye57` (libE57 C++ bindings) are natively available for Python 3.11 without requiring local MSVC compilation tools.

---

### Step 2: Install Node.js Dependencies (`node_modules`)
From the project root:

```powershell
npm install
```

This installs Electron (`^34.3.0`), Three.js (`^0.174.0`), GSAP (`^3.12.7`), Vite (`^6.2.0`), and developer packaging tools.

---

### Step 3: Install Python Backend Dependencies
Ensure Python 3.11 is accessible, then install the operational backend packages:

```powershell
# Using global Python 3.11 or a virtual environment:
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
```

#### Core Operational Dependencies Installed:
* `pye57`: High-performance C++ bindings for parsing ASTM E57 structured point clouds, scanning geometry, and embedded `images2D` cubemaps/spherical panoramas.
* `numpy`: Fast coordinate transforms, quaternion rotations, and binary buffer dumping (`lod0.bin`).
* `scipy`: 3D spatial rotation conversions (`Rotation.from_quat`, Euler calculations) and distance matrices.
* `scikit-learn`: Spatial tree querying (`NearestNeighbors`) used for the multi-directional navigation graph.
* `laspy`: Point cloud parsing for LAS and LAZ compressed lidar formats.
* `Pillow`: Image buffer decoding and JPEG panorama generation.

---

### Step 4: Running in Development Mode
To launch the application locally without creating a packaged installer:

```powershell
npm start
```

* This starts the Electron main process ([`main.js`](./main.js)).
* Automatically locates the Python 3.11 executable on Windows (`%LOCALAPPDATA%\Programs\Python\Python311\python.exe` or system PATH).
* Spawns the local Python REST backend ([`backend/app.py`](./backend/app.py)) on `http://127.0.0.1:8000`.
* Opens the AV Walkthrough desktop viewer window.

---

### Step 5: Building Production Desktop Releases (`release-final-*/`)

To package a complete standalone Windows executable package:

```powershell
# Complete build (Frontend + Python + Electron packager):
npm run build
```

Or run the individual target steps:

1. **Bundle Web Application**:
   ```powershell
   npm run build:web
   ```
2. **Compile Backend to Executable** (optional standalone PyInstaller bundle):
   ```powershell
   npm run build:python
   ```
3. **Package Electron Distribution**:
   ```powershell
   npm run build:electron
   ```
   * Output directory: `release-final-31-2/AV_Walkthrough-win32-x64/`
   * Executable: `AV_Walkthrough.exe`

---

### Step 6: Regenerating Project Scans and Point Cloud Caches (`lod0.bin`)

The repository deliberately excludes proprietary multi-gigabyte point clouds and scan caches. When running the application:

1. Click **"New Project"** in the AV Walkthrough UI.
2. Select your raw dataset:
   * **Structured E57**: Direct E57 dataset with embedded camera poses and images.
   * **E57 + Panos Folder**: E57 dataset paired with a folder of 360° JPG images.
   * **E57 + Panos + CSV**: E57 scan paired with image folder and `pano-poses.csv`.
3. Enter Project Name, Scan Date, and optional Floor Elevation labels (e.g. `1, mezz`).
4. Click **Process**:
   * The backend ingestion engine ([`backend/ingestion.py`](./backend/ingestion.py)) extracts the panoramas into `Scans/<scan_date>/panos/`.
   * Automatically clusters floor plateaus and detects stair transitions.
   * Generates the multi-directional 8-sector navigation graph.
   * Downsamples the 3D point cloud and serializes it into the binary cache file at `Scans/<scan_date>/cache/lod0.bin`.
   * Creates the unified configuration file `project.avproj`.

---

## 3. Test & Diagnostic Scripts Note

The `backend/` directory contains several standalone test scripts (e.g., `diagnose_e57.py`, `check_data3d.py`, `test_stitch.py`, `regression_test.py`). These files are small Python scripts that remain tracked in Git to allow verification of newly added datasets or custom E57 tags. Any large binary test outputs (`*.jpg`, `*.bin`, test logs) generated when running these tests are explicitly ignored.
