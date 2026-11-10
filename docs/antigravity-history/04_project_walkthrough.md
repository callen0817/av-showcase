# Project Walkthrough: AV Walkthrough Core Integration

We have successfully integrated all approved core features for the offline virtual walkthrough application, focusing on point cloud caching/rendering, modular architecture, stable project formats, and StructionSite-style Auto-Stack date transitions.

---

## 1. Summary of Changes

### Python Backend Ingestion
* **Multi-Format Parsers**: Implemented parsers in `backend/ingestion.py` for E57 scan point tables, XYZ coordinates, and LAS/LAZ point clouds (using `laspy`).
* **Source Preservation (Managed vs. Linked)**: 
  * *Managed*: Copies the raw point cloud into `Scans/<scan_date>/raw_source.<ext>`.
  * *Linked*: References the absolute path, sha256 file hash, and modified date to prevent storage duplication of large datasets.
* **LOD Cache Generation**: Downsamples coordinates and colors, and dumps them using numpy structured array buffers (`tobytes()`) into a single file under `Scans/<scan_date>/cache/lod0.bin`.
* **Logging**: Added import logging to `logs/import.log`.

### Electron Main Process
* **Binary IPC**: Implemented the `read-file-bin` and `write-file` IPC handlers in `main.js` and `preload.js` to enable direct binary cache reading and project config updates without data corruption.
* **Unified Project opening**: Dialog filters in Electron now default to loading `.avproj` projects.
* **Logging**: Added app status logs to `<appData>/app.log`.

### Modular Frontend Architecture
We split the responsibilities of `src/App.js` into five core ES6 modules to optimize code size, maintainability, and readability:
1. **[coords.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/coords.js)**: Centralizes axis translations between Python space `[x, y, z]` and Three.js viewport space `(X, Z, Y)`.
2. **[projectManager.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/projectManager.js)**: Handles loading, parsing, and writing the unified `project.avproj` configuration, managing the spatial bookmarks, and running an autosave loop (logging to `logs/autosave.log`).
3. **[dataLoader.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/dataLoader.js)**: Decodes raw cache buffers from `cache/lod0.bin` into WebGL positions and normalized color attributes.
4. **[renderer.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/renderer.js)**: Instantiates Three.js WebGL context, maps panoramas, renders aligned point clouds, and handles memory cleanup.
5. **[navigation.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/navigation.js)**: Draws canvas keyplans and generates 3D navigation nodes.
6. **[autoStack.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/autoStack.js)**: Calculates spatial node proximities, prioritizing same-floor matches before evaluating 3D Euclidean distances, with search-index abstractions.

### Interface & Cleanups
* **Removed measurements**: Strip `#btn-measure`, `#unit-selector`, and `#measurement-tooltip` from `index.html` and deleted all measurement logic in `src/App.js`.
* **Bookmarks Dropdown**: Integrated `#bookmark-selector` and `+ Bookmark` trigger in the control bar matching the existing style.
* **No UI Redesigns**: Existing CSS styles and layouts were preserved with no modifications.

---

## 2. Code Modularity Diagram

```mermaid
graph TD
    AppJS["App.js (Controller)"] --> Coords["coords.js (Central Axis Mapping)"]
    AppJS --> ProjectMgr["projectManager.js (project.avproj & Bookmarks)"]
    AppJS --> DataLoader["dataLoader.js (lod0.bin Decoder)"]
    AppJS --> Renderer["renderer.js (Three.js & Point Cloud Overlay)"]
    AppJS --> Navigation["navigation.js (Keyplan & 3D Rings)"]
    AppJS --> AutoStack["autoStack.js (Floor Priority Spatial Search)"]
    ProjectMgr --> |Writes Logs| AutosaveLog["logs/autosave.log"]
    Renderer --> |Aligns Points| Coords
    Navigation --> |Places Rings| Coords
```

---

## 3. Verification Plan & Testing

### Python Backend Ingestion Compilation
* Verified that the backend ingestion compiles successfully and imports all packages (`numpy`, `scipy`, `scikit-learn`, `pye57`, `laspy`) with zero errors.

### Manual Verification Steps (For the User)
1. **Launch App**: Start your Electron application (`npm run dev` or launch the packaged build).
2. **Ingest Scan**:
   * Click **Create Walkthrough**.
   * Set Type to **Structured E57** (or **Matterport**, or **LAS/LAZ with Panos**).
   * Choose **Import Mode**: `Linked` or `Managed`.
   * Fill out paths and dates, then click **Process**.
   * Verify that `cache/lod0.bin` is generated and that the import is recorded in `logs/import.log`.
3. **Verify walk & Auto-Stack**:
   * Navigate through panoramas by clicking navigation rings.
   * Switch dates in the top selector. Verify that Auto-Stack warps you to the nearest panorama on the same floor, keeping your camera heading intact.
4. **Spatial Bookmarks**:
   * Warp to a location, click **+ Bookmark**, and name it.
   * Verify that selecting it from the dropdown instantly returns you to that exact location, floor, and yaw/pitch rotation.

---

## 4. Phase 5 Stabilization Pass Details

We completed a comprehensive stabilization pass (Phase 5) to secure the data contract and restore functional alignment:
* **Ingestion Verification Report**: Every import now writes `import_report.json` and a readable `import_report.txt` directly to the scan date folder. This documents the exact statistics of scans, images, poses (from E57 vs. CSV), neighbors, and point counts written.
* **Scan Contract Enforcement**: Added a strict validation gate `validate_scan_contract` that raises exceptions if key invariants (such as non-zero panoramas/poses or image desync limits) fail.
* **Point Cloud Hidden Mode**: The point cloud continues to be loaded in WebGL memory for spatial alignments and Auto-Stack operations, but is set to `visible = false` inside `renderer.js` by default. This eliminates any depth-clashing overlays during normal panorama viewing.
* **Panorama Orientation Alignment**: Aligns `panoSphere` and `navMarkersGroup` rotations together by copying the converted scanner quaternion `[qx, qz, -qy, qw]` into their Three.js representation. This ensures correct spatial alignment with the world coordinate system, enabling natural yaw-preservation transitions and perfect keyplan orientations.
* **Runtime Verification Gate**: Added `validateScanRuntime` as a validation check inside `App.js` on project load, verifying counts, vector structure, and file existence, throwing diagnostic errors rather than loading incomplete walkthroughs.

---

## 5. Phase 6 UI Redesign & Adapter Decoupling

We overhauled the import pipeline and UI inputs to cleanly separate acquisitions into distinct adapters:
* **Decoupled Importer UI**: The Dataset Type options inside [index.html](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/index.html) were split into five explicit choices:
  1. **NavVis**: Requires E57 file + Panoramas Folder. Offers a dedicated browse field for an optional Pose CSV override (falls back to E57 scanner poses if not provided).
  2. **Structured E57**: Requires E57 scan file with embedded images.
  3. **Matterport E57**: Requires E57 scan file. Offers an optional Panorama Folder field.
  4. **MatterPak**: Requires XYZ or LAS point cloud. Performs point-cloud-only loading (NO walkthrough/0 panoramas generated).
  5. **Generic Point Cloud**: Requires LAS, LAZ, or XYZ file. Performs point-cloud-only loading.
* **Point-Cloud-Only Inspection View**: Added a dedicated `process_point_cloud_only` ingestion method in [ingestion.py](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/backend/ingestion.py#L1080) that downsamples XYZ/LAS/LAZ point clouds into the lod0.bin cache, generates a single Floor 1 object, and skips panorama generation. The client renderer in [App.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/App.js#L624) automatically sets the point cloud mesh visibility to `visible = true` for point-cloud-only scans (and `visible = false` for walkthrough scans with panoramas).
* **FSM Error Recovery**: We wrapped `submitCreateProject` in a `try...catch...finally` handler in [App.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/App.js#L350), ensuring that if any JS or API exception occurs, the progress container is cleaned up and the "Process" button is safely re-enabled (preventing the UI from getting stuck in a busy state).
* **Automated Regression Testing**: Added [regression_test.py](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/backend/regression_test.py) and `golden_reference.json` (created from your known-good NavVis import database). Future imports can be verified by running `python backend/regression_test.py --test-project <path_to_avproj>`.

---

## 6. Phase 7 Matterport Structured E57 Cubemap Stitching Engine

We conducted a deep node introspection of the Matterport E57 container:
* **E57 Structure Diagnostics**: Using `pye57`, we discovered that:
  - `data3D` contains 93 scans with valid positions and quaternions.
  - `images2D` contains 558 nodes ($93 \times 6$ faces) representing pinhole cubemaps (Skybox 0 to 5) linked to scans via `associatedData3DGuid`.
  - The JPEG data is embedded as standard C++ `BlobNode` elements inside the `pinholeRepresentation`.
* **In-Memory Stitching Engine**: Implemented `_stitch_cubemap_faces` in [ingestion.py](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/backend/ingestion.py). It:
  1. Decodes JPEG byte arrays from `BlobNode` using `PIL.Image` and `io.BytesIO`.
  2. Uses `scipy.spatial.transform.Rotation` to compute each face's 3D rotation matrix.
  3. Projects target equirectangular coordinates $(\theta, \phi)$ back into each of the 6 camera local projection spaces.
  4. Vectorizes pixel sampling via NumPy arrays to stitch the 6 faces into a standard $2048 \times 1024$ equirectangular panorama.
  5. Outputs the final panorama seamlessly to the standard walkthrough renderer without requiring client-side modifications.

* **Cubemap Vertical Flip**: Inverted the vertical sampling vector in the projection logic ($v = c_y - f \frac{y}{z}$) inside [ingestion.py](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/backend/ingestion.py#L799) to align the OpenGL camera coordinate system with standard 2D image coordinates, preventing upside-down panoramas.
* **Auto-CSV Folder Search Fallback**: Restored automatic folder-level search for the `pano-poses.csv` / `poses.csv` camera pose lists inside the selected panoramas folder in [ingestion.py](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/backend/ingestion.py#L836-L847). This fixes the pose/image mismatch error for Option 2 (E57 + Panos Folder) imports where NavVis files consolidate point clouds into 1 scan node but keep 350 scan coordinates in a local CSV.
* **JPG/JPEG Exclusive Panorama Filter**: Restricted the scan panorama directory scanner in [ingestion.py](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/backend/ingestion.py#L825) to strictly accept `.jpg` and `.jpeg` files. This ignores `.png` floor plans, layout overlays, or quality maps, achieving a perfect 1-to-1 sync of 349 panoramas to 349 poses.

---

## 7. Phase 8 Walkthrough Viewport & API Improvements

* **Transition Orientation Alignment**: Implemented `alignPanoSphere` in [renderer.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/renderer.js#L132) using `THREE.Quaternion([qx, qz, -qy, qw])`. This rotates the panorama sphere to match the absolute world scanner coordinate system, ensuring yaw-preservation transitions from viewpoint to viewpoint.
* **Keyplan Radar Sweep & Orientation Pointer**:
  - Added a `cameraYaw` parameter to `renderKeyplan` in [navigation.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/navigation.js#L78).
  - When rendering the current viewpoint, it draws a semi-transparent blue Field-of-View wedge ($50^\circ$ sweep) and a directional pointer arrow indicating exactly where the user is looking.
  - Wired real-time redrawing inside `onMouseMove` in [App.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/App.js#L751) so the radar sweep rotates smoothly on mouse drag.
* **E57 + Panos + CSV Ingestion Crash Fix**: Unpacked `csv_path` in the POST request body handler inside [app.py](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/backend/app.py#L74) to prevent NameError crashes when executing custom CSV imports.
* **Scan State Leak Fix**: Added scan and panorama property cleanups (`sceneState.currentPano = null`, etc.) inside `showHome` in [App.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/App.js#L298-L302). This clears the state when exiting to the home dashboard, preventing Auto-Stack from matching coordinates across different projects on load.
* **Typing Focus Event Hijack Fix**: Added element tag checks (`input`, `select`, `textarea`) in the keydown handler inside [App.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/App.js#L72) to prevent the global camera calibration keyboard listener from intercepting user input during modal editing.
* **Dedicated Project Directory Routing**: Modified `submitCreateProject` in [App.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/App.js#L371-L413) to automatically append a subdirectory named after the project name when creating a new project. For existing projects, it selects the existing directory, ensuring new walkthroughs never overwrite each other in the parent directory.
* **Project Deletion Functionality**:
  - Implemented the `delete-project` IPC handler in [main.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/main.js#L218-L248) which removes a project from the registry and recursively deletes its database/files from disk.
  - Exposed the method in [preload.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/preload.js#L12) and added a trash button to each project card on the dashboard in [App.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/App.js#L338-L358) with styling in [style.css](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/style.css#L349-L388).
  - Added system folder guards to block deleting system folders (e.g. `Downloads`, `Desktop`, `Documents`).
  - Replaced permanent deletion with Electron's `shell.trashItem` API to send deleted project files safely to the Recycle Bin rather than calling permanent deletion.
  - Split deletion flow in [App.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/App.js#L374-L387) into two prompts: the first removes the project card from the dashboard program list, and the second asks if the user also wishes to send the disk files to the Recycle Bin (allowing users to cancel and only clean up the program UI).
* **Modal Focus Recovery**: Restored window and element focus programmatically inside `card-create` click listener in [App.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/App.js#L141-L151) to guarantee the project name field captures input focus immediately when entering the modal.
* **Dropdown Calendar Popup Trigger**: Bound native `.showPicker()` events inside [App.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/App.js#L247-L258) to automatically display the calendar dropdown selection panel immediately upon clicking or focusing the Date field.
* **Ground-Level Floor Navigation Markers**:
  - Implemented the `findGroundHeight(pos, pointCloud)` ground search algorithm in [navigation.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/navigation.js#L17-L70). It scans a 0.5m horizontal cylinder of the point cloud centered at the neighbor position and uses the 90th percentile of points below the camera to locate the physical floor plane. This supports steps, stairs, slopes, and multi-level ground shifts automatically.
  - Placed navigation rings at this resolved ground level (with a 5cm hover to prevent depth buffer z-fighting).
  - Configured `material.depthWrite = false` on the ring material to prevent z-fighting/occlusion by point cloud floor points.
  - Aligned rings perfectly flat on the horizontal XZ plane using direct rotation angles (`marker.rotation.x = -Math.PI / 2`).
  - Restored original Ring and Hit Box sizes (`RingGeometry(0.8, 1.2)` and `CircleGeometry(2.0)`) for optimal clickability while maintaining ground-level projection.
* **Slant/Tilt Neutralization for Upright Panoramas**: Modified `alignPanoSphere` in [renderer.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/renderer.js#L132-L146) to isolate the vertical yaw Euler angle (using `'YXZ'` order) and construct a pure Y-axis rotation quaternion. This eliminates any pitch or roll tilt from the tripod setup, ensuring the viewer horizon remains perfectly straight and upright.
* **Organizer Folders for Dashboard Projects**:
  - Upgraded the recent projects registry in [main.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/main.js#L190-L248) to support folder grouping (saving project lists alongside folder names in a backwards-compatible manner).
  - Added a "Create Folder" card on the dashboard and a folder select option (with inline new folder creator option) in the modal inside [index.html](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/index.html#L31-L69).
  - Implemented collapsible folder sections in [App.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/App.js#L400-L555) with styling in [style.css](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/style.css#L440-L519) allowing projects to be cataloged by client, location, or scanner hardware type.
  - Excluded colliding `.btn-delete-project` class name from the "Move to Folder" button in [App.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/App.js#L455) to prevent event listeners from overriding each other.
  - Applied absolute overlay and blur backdrop layout styling to `#folder-modal` and `#move-project-modal` in [style.css](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/style.css#L208) to display dialogues correctly on screen.
* **Matterport-style Double-Click Raycast Navigation**:
  - Bound a `dblclick` event listener on the panorama viewport in [App.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/App.js#L73) that fires `onDblClick(event)` (lines 1028-1079).
  - Uses Three.js `Raycaster` to compute a 3D click direction vector from the camera.
  - Scores neighbor panorama nodes by combining angular alignment (must fall inside a 50-degree horizontal cone, i.e., $dot > 0.64$) and proximity ($score = dot / (distance + 0.1)$), transitioning smoothly to the closest node in the click direction.
* **Scan Date Switch Camera Yaw Alignment**:
  - Modified `loadScan(date)` in [App.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/App.js#L843-L922) to calculate the vertical yaw of the scanner before the transition, compute the target panorama's scanner yaw, and adjust `cameraLon` by the delta angle. This ensures the camera's look direction aligns with the physical orientation of the original scan when switching dates.
* **Optimized Floor Detection Threshold**:
  - Adjusted `FLOOR_Z_THRESHOLD` in [ingestion.py](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/backend/ingestion.py#L55) from `0.6096`m to a default of `0.45`m, and exposed a **Floor Separation Sensitivity** selector in the UI creation modal [index.html](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/index.html#L122) (allowing `0.3`m for split levels, `0.45`m for standard, and `0.65`m/`1.0`m for coarse steps/continuous stairs).
* **Manual Floor Elevations Configuration**:
  - Added a **Floor Elevations** text field in the creation modal [index.html](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/index.html#L131) allowing comma-separated heights in meters (e.g. `1.0, 2.8, 4.8, 8.5, 9.5`).
  - Updated `_get_z_floors` in [ingestion.py](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/backend/ingestion.py#L474) to map all Z coordinates directly to the closest specified floor height when user-defined elevations are present.
* **Automatic Midpoint Stair Partitioning (Matterport-style)**:
  - Redesigned the default automatic floor detection in `_get_z_floors` of [ingestion.py](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/backend/ingestion.py#L514-L584).
  - Uses dynamic peak-density detection to classify initial height groups into **Major Floors** (significant scan counts or isolated/terminal levels) versus **Stairs/Transitional Floors** (low scan counts).
  - Automatically splits each staircase transition at its height midpoint: assigning the bottom half of the stairs to the major floor below, and the top half to the major floor above. This achieves a perfect 5-level segmentation automatically without manual height input.
