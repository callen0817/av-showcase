# Project Review: AV Walkthrough

This document reviews the existing AV Walkthrough codebase, assesses its current implementation status against commercial and offline-first product requirements, identifies technical debt, and outlines a prioritized implementation plan to complete the software.

---

## 1. Current Architecture

AV Walkthrough is designed as a hybrid Electron + Python desktop application:
1. **Frontend (Vite + WebGL/Three.js)**: Runs in the Electron renderer process. Responsible for panoramic texture rendering, custom WebGL coordinates navigation, 2D canvas keyplan drawing, and the user control layer.
2. **Main Process (Electron/Node.js)**: Orchestrates window management, system dialogs (directory/file pickers), raw file access, and launches the Python backend child process.
3. **Backend (Python HTTP Server)**: Implemented using standard `http.server` running locally on port 8000. It wraps performance-sensitive data ingestion, point cloud/E57 structure reading (using `pye57` and `numpy`), and spatial analysis (floor detection and KNN-based neighbor linking using `scikit-learn` and `scipy`).

---

## 2. Existing Functionality

The current codebase contains the following functional blocks:
* **Ingestion Pipelines**:
  * **Structured E57**: Reads E57 files using `pye57`, extracts `images2D` panoramas, parses camera translations/rotations (poses), and writes them to local JPGs.
  * **Matterport Matterpak**: Currently a stub that bypasses the `.xyz` file and reads panoramas from a folder, distributing them on a mock grid.
  * **E57 + Panos**: Matches E57 camera poses to a folder of external high-res panoramas.
  * **SLAM / Unstructured**: Launches a placeholder external executable `av_structure.exe`.
* **Spatial Structuring**:
  * Z-coordinate clustering to group scans into floors.
  * KNN (K-Nearest Neighbors) spatial querying to build a navigable neighborhood node graph.
* **Viewer Interaction**:
  * Immersive panorama rendering using a reverse-scaled sphere mapped with localized JPG textures.
  * Canvas-based 2D keyplan showing node networks, permitting node navigation on click, and floorplan calibration (Shift + WASD offset/scale calibration).
  * Basic measurement overlays (to be removed).

---

## 3. Technical Debt & Crucial Architectural Issues

A detailed inspection of the code reveals several critical pieces of technical debt:

### Coordinate Axis Mapping Mismatch
* **The Issue**: In `updateNavMarkers`, the horizontal plane direction vector uses Three.js `X` and `Z` axes:
  `marker.position.set(pos.x, -5, pos.z)`
  However, in `dir` calculation:
  `neighbor.position[1] - this.currentPano.position[1]` (which is Python's horizontal Y) is mapped to Three.js `Y` (which is vertical). Meanwhile, Python's height (`position[2]`) is mapped to Three.js `Z` (horizontal).
* **The Impact**: Navigation rings are oriented relative to height difference instead of the actual horizontal angle, causing navigation points to bunch up on a single line parallel to the X-axis whenever vertical height changes are negligible.
* **The Fix**: Align coordinate mappings across Python, JS, and Three.js:
  * Three.js `X` = Python `position[0]` (Horizontal X)
  * Three.js `Y` = Python `position[2]` (Vertical Z / Height)
  * Three.js `Z` = Python `position[1]` (Horizontal Y)

### Inefficient File Access & UTF-8 Corruption Risk
* **The Issue**: `main.js` only exposes a `read-file` IPC handler that forces UTF-8 encoding.
* **The Impact**: Attempting to read binary files (like LAS, LAZ, or our planned cached `pointcloud.bin`) over this channel will corrupt raw bytes.
* **The Fix**: Add a native `read-file-bin` IPC channel returning raw binary buffers.

### Ingest State Bleed
* **The Issue**: In `App.js`, when switching ingestion modes, input fields are reset, but the backend server state (`progress_state`) remains in memory as a global variable.
* **The Impact**: If a previous ingestion fails, starting a new project might display incorrect progress or instantly trigger a failure state.
* **The Fix**: Add an explicit reset route `/api/reset` or clear progress in python before running ingestion.

---

## 4. Missing Core Features (Aligned with Updated Requirements)

Based on your product goals and the exclusion of non-goals (dollhouse, measurements, CSS redesign, etc.), the following items are missing:

1. **Auto-Stack (Flagship Comparison Feature)**:
   * Current behavior: Switching scan dates resets the active panorama to `panos[0]`.
   * Required behavior: Switch date, lookup the nearest panorama in the new dataset, match the current floor, preserve camera viewing direction (yaw/pitch), and transition seamlessly.
2. **Point Cloud Ingestion & Performance Caching**:
   * E57 point extraction is not implemented (only image extraction is active).
   * XYZ parser does not read coordinate data.
   * LAS/LAZ import is not supported.
3. **Point Cloud Rendering & Toggle**:
   * No rendering of point clouds exists in the Three.js viewport.
   * We need a fast binary reader, downsampling, and a Toggle view overlay to display the point cloud aligned inside the panorama.
4. **Stable Project Format (`.avproj`)**:
   * Replace generic `project.json` directory opening with a structured project configuration named `project.avproj` containing schema versions, metadata, and relative cache file links.

---

## 5. Recommended Improvements

* **Fast Binary Points Cache (`cache/lod0.bin`)**: Rather than parsing raw E57 or XYZ point tables at runtime in Electron (which would freeze the process), the Python backend should parse and downsample them to a binary file containing structured float32/uint8 bytes on ingestion.
* **Memory Optimization**: Implement point cloud unloading when opening a new project to prevent GPU memory leaks in Three.js.
* **Auto-Stack Tolerance Warnings**: If the nearest scan in the selected date is too far away (e.g. >15 meters), display a temporary, clean indicator: `"No matching panorama within Xm. Displaying closest viewpoint."` (Distance parameterizable in settings).
* **Complete Removal of Measurements**: Completely remove the redundant measurement overlays and controls to declutter the user interface and logic.
* **Spatial Bookmarks**: Implement a progress comparison feature allowing viewport saving (XYZ coordinate, floor, yaw/pitch camera angle) that links with Auto-Stack date comparisons.

---

## 6. Proposed Implementation Order

To ensure systematic progress, I propose the following execution phases:

### Phase 1: Ingestion & Binary Caching (E57, LAS, LAZ, XYZ)
1. Add LAS/LAZ reader support in Python using `laspy`.
2. Implement E57 point table parsing, global coordinate alignment using scan poses, and uniform downsampling in `ingestion.py`.
3. Implement XYZ text file parsing and downsampling.
4. Add Managed (duplicating source file) vs. Linked (storing path/hash/modified details) point cloud importing paths.
5. Serialize downsampled point clouds into `cache/lod0.bin` in a single fast write (`arr.tobytes()`).
6. Set up structured logs (`logs/import.log`).

### Phase 2: Binary IPC & Point Cloud Rendering
1. Expose `read-file-bin` in `main.js` and `preload.js`.
2. Implement `loadPointCloud(path)` module in `src/dataLoader.js` to parse `cache/lod0.bin` and generate a `THREE.Points` object.
3. Position the point cloud relative to the camera inside the Three.js viewport.
4. Completely remove measurement UI buttons and JS functions.
5. Set up structured logs (`logs/renderer.log`, `logs/app.log`).

### Phase 3: Auto-Stack & Bookmarks Integration (Highest Priority)
1. Store camera yaw/pitch and spatial coordinates prior to scan date switching.
2. Implement abstract `findNearestPano(targetPos, searchPool)` in `autoStack.js` (floor matching first, then 3D Euclidean distances) for future-proofing.
3. If a match is found, transition to it and restore camera yaw/pitch. Handle missing coverage gracefully (warning alert if distance > max_autostack_distance).
4. Implement Bookmarks dropdown: selecting a bookmark warps the viewpoint, and switching dates comparison is maintained.
5. Validate that transitions feel fast and seamless.

### Phase 4: Project Formats & Commercial Stability
1. Change project metadata files to `.avproj` supporting schema and application versions.
2. Add error-handling fallbacks, logging to files (`logs/autosave.log`), autosave, and memory cleanup.
3. Test ingestion pipelines with mock/sample point clouds to ensure stability.
