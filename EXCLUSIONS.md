# Operational Exclusions & Local Rebuild Manifest (`EXCLUSIONS.md`)

This file explicitly documents all heavy runtime dependencies, compiled binaries, precomputed point cloud caches, and build outputs that are excluded from this Git repository, providing **complete instructions to rebuild and restore everything locally for full operational capability**.

---

## 1. Heavy Things Required for Operation (Included in this Exclusions Manifest)

These items are **essential for running and operating AV Walkthrough**, but were excluded from the Git repository due to binary size (over 35 GB), machine-specific compilation, or proprietary data contracts.

### A. Heavy Python Native C++ Extensions & Wheels
* **What is excluded**: Python virtual environment (`.venv/`, `env/`), compiled C/C++ wheel binaries.
* **Why it is required**: 
  * `pye57`: Required to read ASTM E57 structured files, parse the `data3D` scan trees, extract embedded camera poses (translation/quaternions), and decode pinhole cubemaps or spherical panoramas.
  * `numpy` & `scipy`: Required for vector math, coordinate transformations, and binary point cloud serialization.
  * `laspy`: Required for ingesting airborne or mobile LAS/LAZ lidar point clouds.
  * `Pillow`: Required for image decompression, face stitching, and JPEG export.
* **How to rebuild locally**:
  ```powershell
  # 1. Ensure Python 3.11 is installed (64-bit on Windows)
  # 2. Install all required operational packages:
  pip install -r backend/requirements.txt
  ```
  *(Note: Python 3.11 is specified because precompiled binary wheels for `pye57` install seamlessly without needing Visual C++ Build Tools).*

---

### B. Packaged Electron & Chromium Runtime Distributions (`release-final-*/`, `release-live/`)
* **What is excluded**: Packaged desktop releases such as `release-final-31-2/AV_Walkthrough-win32-x64/` (~35+ GB across release iterations).
* **Why it is required**: Contains the standalone bundled `AV_Walkthrough.exe`, Chromium rendering engine, and Electron framework so end users can launch the app without a terminal.
* **How to rebuild locally**:
  ```powershell
  # 1. Install Node.js dependencies
  npm install

  # 2. Build and package the production desktop application:
  npm run build:electron
  ```
  This automatically outputs a clean, standalone distribution into `release-final-31-2/AV_Walkthrough-win32-x64/AV_Walkthrough.exe`.

---

### C. Node.js Runtime Dependencies (`node_modules/`)
* **What is excluded**: `node_modules/` (~721 MB).
* **Why it is required**: Contains Electron (`v34`), Three.js (`v0.174`), GSAP animations (`v3.12`), and packaging tools.
* **How to rebuild locally**:
  ```powershell
  npm install
  ```

---

### D. 3D Point Cloud Binary Caches (`Scans/<date>/cache/lod0.bin`)
* **What is excluded**: `cache/lod0.bin` and raw scan outputs under `Scans/`.
* **Why it is required**: The viewer loads this compact binary file into GPU memory to render the 3D point cloud overlay aligned with the 360° panoramas, as well as to compute floor heights for navigation rings.
* **Format Specification**: Packed binary buffer created using numpy structured arrays:
  * 4-byte header: unsigned integer `uint32` containing point count $N$.
  * $N \times 15$ bytes: `float32 x`, `float32 y`, `float32 z`, `uint8 r`, `uint8 g`, `uint8 b`.
* **How to rebuild / regenerate locally**:
  * You do not need to construct this manually.
  * Simply launch the app (`npm start` or via `AV_Walkthrough.exe`), click **"New Project"**, select an `.e57`, `.las`, `.laz`, or `.xyz` scan file, and click **Process**.
  * The backend ingestion engine ([`backend/ingestion.py`](./backend/ingestion.py)) automatically parses the point cloud, downsamples it, and writes `lod0.bin`.

---

### E. Panorama Image Cache (`Scans/<date>/panos/`)
* **What is excluded**: High-resolution stitched spherical JPEG images (`pano_000.jpg`, `pano_001.jpg`, etc.).
* **Why it is required**: The viewer's inverted sphere texture maps to these files as the user navigates viewpoint to viewpoint.
* **How to rebuild / regenerate locally**:
  * Generated automatically alongside `lod0.bin` during the ingestion step. Panoramas are extracted in chronological sequence with natural alphanumeric ordering directly from the scanner data.

---

### F. External Companion Executables (Optional Integrations)
* **What is excluded**: 
  * `AV_Structure.exe` (Default expected path: `C:\Program Files\AV_Structure\av_structure.exe` or custom user path).
  * `AV_Snap.exe` (Default expected path: `C:\Program Files\AV_Snap\av_snap.exe`).
* **Why it is required**: If the user selects the **SLAM** scan pipeline or clicks **Align Floorplan**, AV Walkthrough delegates native processing to these companion tools.
* **How to restore locally**:
  * Install AV Structure or AV Snap to their default program folders, or browse to their location in the modal UI. If not using SLAM, the primary E57 and panorama pipelines function completely independently.

---

## 2. Excluded Test & Ephemeral Files (Safe to Omit)

These items were generated during debugging, testing, or session logging and can be **safely omitted without affecting software operation**:

| Excluded Item | Description | Impact if Missing |
| :--- | :--- | :--- |
| `backend/test_extracted.jpg` | Scratch JPEG generated while testing E57 blob extraction. | None (temporary test file). |
| `backend/stitched_pano.jpg` | Scratch JPEG generated while testing cubemap rotation. | None (temporary test file). |
| `*.log` (`av_backend.log`, `app.log`) | Local runtime stdout/stderr log files. | Recreated automatically when app starts. |
| `out.txt`, `run_stdout.log` | Shell capture logs from previous test commands. | None. |
| `backend/build/` | Temporary object files produced by PyInstaller. | Recreated if `npm run build:python` is run. |

---

## 3. Quick-Start Local Rebuild Sequence

```powershell
# 1. Clone repository
git clone https://github.com/callen0817/av-walkthrough.git
cd av-walkthrough

# 2. Install Node.js dependencies
npm install

# 3. Install Python 3.11 operational requirements
pip install -r backend/requirements.txt

# 4. Launch in development mode
npm start

# 5. (Optional) Compile packaged release
npm run build
```
