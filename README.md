# AV Showcase

**AV Showcase** (formerly *AV Walkthrough*) is an offline-first 3D virtual tour and scan comparison desktop application built for Architecture, Engineering, and Construction (AEC) professionals. Built as part of the Artificial Vision spatial intelligence suite, it works interoperably with **AV Structure**, **AV Scan** (C++17 / Qt6 QML), and **AV ScanAR** (Python / PySide6 / ROS 2) via the **AV Spatial Bundle v1.1** standard.

![AV Showcase Logo](./assets/av-showcase-logo.png)

---

## What's New in v2.0

* **Apple Glass (visionOS) Interface**: Re-engineered with the translucent dark glass design language matching AV Scan and AV ScanAR (gold `#BAA164` accents, warm white typography, concentric halo boot splash, and floating glass HUD panels).
* **Universal Point Cloud Walkthroughs**: Ingest raw `.ply` (ASCII and binary little/big-endian), `.pcd`, `.las`/`.laz`, `.xyz`, `.obj`, and unstructured `.e57` point clouds and synthesize an instant virtual walkthrough with auto-placed walkable stations and depth-buffered equirectangular panoramas.
* **Matterport MatterPak Ingestion**: Directly open MatterPak archives (`.zip` or unpacked folders containing colorized `.xyz`/`.ply`/`.obj` clouds + architectural floorplans).
* **AV Spatial Bundle v1.1 (< 1s Import)**: Instant folder or ZIP import sharing stations, metric keyplans, LOS navigation graph, and binary point cloud cache (`lod0.bin`).
* **4D Historical Switching Without Spin**: Fixed coordinate reflection and double-rotation bugs. Navigating between historical scan dates (e.g. bathroom Dec 4 &rarr; Apr 13) keeps your spatial position and exact world heading.
* **Auto-Aligned Cross-Date Registration (4-DOF ICP)**: Coarse FFT yaw cross-correlation + 4-DOF rigid registration aligns scans taken from different SLAM start doorways directly into the baseline project coordinate frame.
* **Calibrated 2D Key Plans**: Metric architectural wall-slice floorplans (`0.02 m/px`) with North-up orientation, interactive room-wide click-to-teleport (snapping up to 8m), and radar field-of-view cone.

---

## Interoperability Standard

Full mathematical specifications (canonical right-handed Z-up coordinates, ASTM E2807-11 §6.5.4 equirectangular projection, Three.js det = +1 mapping, and manifest JSON schema) are documented in:
👉 **[`docs/INTEROP_AV_SPATIAL_BUNDLE.md`](./docs/INTEROP_AV_SPATIAL_BUNDLE.md)**

---

## Quick Start (Local Setup)

### Prerequisites
1. **Node.js**: `v18.x`, `v20.x`, or `v24.x` LTS
2. **Python**: `3.10+` (NumPy and Pillow required; pye57, laspy, lazrs optional)

### Setup & Run
```bash
# 1. Install Node.js dependencies
npm install

# 2. Install Python backend dependencies
pip install -r backend/requirements.txt

# 3. Launch application in development mode
npm start
```

### Automated Interoperability Tests
```bash
# Run full mathematical, coordinate, ASTM, ICP, and bundle verification
npm test
```

### Packaging Windows Release
```powershell
npm run build
```
The packaged standalone distribution will be output to `release-final/AV_Showcase-win32-x64/`.

---

## Project Structure

```
av-showcase/
├── assets/
│   ├── av-showcase-logo.png      # Gold pin + calligraphic AV emblem
│   └── av-walkthrough-logo.png   # Legacy logo (preserved)
├── backend/
│   ├── app.py                    # Local REST API server (port 8000)
│   ├── ingestion.py              # Ingestion dispatcher & project manager
│   ├── walkthrough_synth.py      # Standalone universal synth engine (ASTM, slabs, ICP, keyplans)
│   ├── verify_showcase_interoperability.py # End-to-end Python test suite
│   └── requirements.txt          # Python dependencies
├── docs/
│   └── INTEROP_AV_SPATIAL_BUNDLE.md # Ecosystem contract & ASTM specs
├── src/
│   ├── App.js                    # Central application controller
│   ├── autoStack.js              # 4D historical switch comparator
│   ├── coords.js                 # Right-handed (det = +1) coordinate transforms
│   ├── dataLoader.js             # Binary lod0.bin point cloud reader
│   ├── navigation.js             # 3D rings & North-up metric 2D keyplan
│   ├── projectManager.js         # project.avproj persistence & bookmarks
│   ├── renderer.js               # Three.js viewport, ASTM pano sphere, LRU texture cache
│   └── verify_coords_and_autostack.mjs # Frontend mathematical verification suite
├── index.html                    # Apple Glass UI markup & modals
├── style.css                     # Apple Glass design system stylesheet
├── main.js                       # Electron main process
└── package.json                  # Package configuration & scripts
```
