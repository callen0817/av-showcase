# AV Walkthrough

**AV Walkthrough** is an offline-first 3D virtual walkthrough and scan comparison desktop application built for Architecture, Engineering, and Construction (AEC) professionals. It bridges structured terrestrial laser scan data (E57, LAS, LAZ) with immersive 360° panoramic navigation, StructionSite-style Auto-Stack multi-date comparison, and automatic multi-level building floor detection.

![AV Walkthrough Logo](./assets/av-walkthrough-logo.png)

---

## Key Capabilities

* **Offline-First Architecture**: Runs 100% locally on Windows without requiring cloud streaming or third-party web hosting.
* **Multi-Format Ingestion**: Supports Structured E57 (e.g. NavVis, Matterport, Leica BLK), E57 + Panorama folders, and E57 + Panos + CSV pose overrides.
* **Auto-Stack Date Comparisons**: Instantly switch between scan capture dates while maintaining your 3D spatial position and viewpoint orientation.
* **Automatic Multi-Level & Stair Navigation**: Automatically detects physical building floor levels from point cloud plateaus and splits staircases at inter-floor midpoints for seamless cross-floor walking and elevator-style teleportation.
* **8-Sector Multi-Directional Navigation Graph**: Ensures comprehensive 360° navigation rings without getting trapped in stationary multi-exposure clusters.
* **Optimized Point Cloud Caching**: Downsamples millions of raw 3D coordinates into compact binary level-of-detail caches (`lod0.bin`).
* **Interactive 2D Keyplan**: Synchronized 2D radar wedge, floorplan image overlays, and Shift + WASD calibration controls.

---

## Quick Start (Local Setup)

> **Important**: This Git repository excludes heavy dependencies, binary releases (~35 GB), and point cloud caches. Please refer to **[`BUILD_EXCLUSIONS.md`](./BUILD_EXCLUSIONS.md)** for a complete breakdown of excluded items and instructions on regenerating them.

### Prerequisites
1. **Node.js**: `v18.x` or `v20.x` LTS
2. **Python**: `3.11.x` 64-bit (recommended for Windows `pye57` wheel support)

### Setup & Run
```powershell
# 1. Install Node.js dependencies
npm install

# 2. Install Python backend dependencies
pip install -r backend/requirements.txt

# 3. Launch application in development mode
npm start
```

### Packaging Windows Release
```powershell
npm run build
```
The packaged standalone distribution will be output to `release-final-31-2/AV_Walkthrough-win32-x64/`.

---

## Project Structure

```
AV_Walkthrough/
├── assets/                  # Application branding and logos
├── backend/                 # Python REST backend and ingestion pipeline
│   ├── app.py               # Local HTTP API server (port 8000)
│   ├── ingestion.py         # E57 parsing, floor detection, and navigation graph generator
│   └── requirements.txt     # Python dependencies (pye57, numpy, scipy, etc.)
├── src/                     # Modular frontend architecture (ES6 + Three.js)
│   ├── App.js               # Central application controller
│   ├── autoStack.js         # Floor-priority nearest-viewpoint comparator
│   ├── coords.js            # Centralized coordinate axis translation utility
│   ├── dataLoader.js        # lod0.bin point cloud decoder
│   ├── navigation.js        # 3D rings and 2D canvas keyplan renderer
│   ├── projectManager.js    # project.avproj serialization and autosave loop
│   └── renderer.js          # Three.js WebGL viewport & panorama sphere
├── docs/
│   └── antigravity-history/ # Full Antigravity AI conversation logs & architectural specs
├── index.html               # Main desktop interface markup
├── main.js                  # Electron main process (IPC, window lifecycle, python spawn)
├── preload.js               # Electron preload script
├── style.css                # Artificial Vision commercial dark-mode theme
├── BUILD_EXCLUSIONS.md      # Detailed repository exclusions and rebuild instructions
└── package.json             # NPM package manifest and build scripts
```

---

## Antigravity AI Development History

To view the complete evolutionary history, architectural review, design decisions, and session transcripts recorded by Google DeepMind's Antigravity assistant during development, see:
* **[`docs/antigravity-history/README.md`](./docs/antigravity-history/README.md)**
* **[`docs/antigravity-history/01_project_review.md`](./docs/antigravity-history/01_project_review.md)**
* **[`docs/antigravity-history/02_implementation_plan.md`](./docs/antigravity-history/02_implementation_plan.md)**
* **[`docs/antigravity-history/05_session_transcripts.md`](./docs/antigravity-history/05_session_transcripts.md)**
