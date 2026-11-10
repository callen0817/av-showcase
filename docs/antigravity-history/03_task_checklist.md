# Task Checklist: AV Walkthrough Core Integration

- `[x]` **Phase 1: Ingestion & Binary Caching (E57, LAS, LAZ, XYZ)**
  - `[x]` Install/verify python packages (`laspy`, etc.) in the user environment
  - `[x]` Implement LAS/LAZ reader support in `backend/ingestion.py` using `laspy`
  - `[x]` Implement E57 point cloud parser and coordinate transformer in `backend/ingestion.py`
  - `[x]` Implement XYZ text file parser in `backend/ingestion.py`
  - `[x]` Implement Managed vs. Linked source files preservation options
  - `[x]` Implement structured binary serialization to `cache/lod0.bin` using numpy Structured Arrays
  - `[x]` Create local folder logging pipeline for `logs/import.log`
  - `[x]` Test python backend ingestion functions directly

- `[x]` **Phase 2: Binary IPC & Point Cloud Rendering**
  - `[x]` Expose `read-file-bin` IPC in `main.js` and `preload.js`
  - `[x]` Add `logs/app.log` tracking in Electron main process
  - `[x]` Create coordinate system module `src/coords.js`
  - `[x]` Create binary loading module `src/dataLoader.js` to parse `cache/lod0.bin`
  - `[x]` Create rendering module `src/renderer.js` to handle Three.js and point cloud placement
  - `[x]` Position the point cloud relative to the active panorama sphere inside `renderer.js`
  - `[x]` Purge measurement features from `index.html` and `src/App.js`
  - `[x]` Verify point cloud loaded overlays inside panoramas

- `[x]` **Phase 3: Auto-Stack & Bookmarks Integration**
  - `[x]` Create spatial comparisons module `src/autoStack.js`
  - `[x]` Implement `findNearestPano(targetPos, searchPool)` with abstract interface (KD-Tree ready)
  - `[x]` Integrate floor prioritization first, then 3D Euclidean distances
  - `[x]` Implement viewing direction (yaw/pitch) preservation during transition
  - `[x]` Implement `max_autostack_distance` setting checks and cancel toast warnings
  - `[x]` Implement spatial Bookmarks: add selection UI dropdown to `index.html` and logic to `App.js`
  - `[x]` Wire Bookmarks data to `projectManager.js` and test Auto-Stack interactions

- `[x]` **Phase 4: Unified Project Formats & Stability**
  - `[x]` Create unified project manager module `src/projectManager.js` to handle `.avproj` parsing/saving
  - `[x]` Transition project open and dialog filters in `main.js` to `.avproj` files
  - `[x]` Implement project auto-save loop writing to `logs/autosave.log`
  - `[x]` Perform overall memory leak testing and validation checks

- `[x]` **Phase 5: Ingestion Contract & Rendering Stabilization**
  - `[x]` Enforce strict ingestion contract gates in `validate_scan_contract`
  - `[x]` Remove synthetic grid generators and auto-switching override heuristics from Structured E57 / LAS
  - `[x]` Prevent empty scan overwrites in `project.avproj` writer
  - `[x]` Hide point cloud overlays by default in panorama viewing mode (`visible = false`)
  - `[x]` Align panorama sphere and navigation marker groups together using quaternion rotations
  - `[x]` Implement Phase 4 runtime verification check on client project load and render
  - `[x]` Instrument the ingestion pipeline to output the import report verification file (`import_report.txt` / `.json`)
  - `[x]` Expose `file-exists` IPC channel for faster file existence checks
  - `[x]` Add support for Matterport Matterpak cameras.conf parsing if available, with grid fallback documentation

- `[x]` **Phase 6: Walkthrough-Only Consolidation & UI Redesign**
  - `[x]` Restrict Dataset Type dropdown options to exactly 3 walkthrough options in `index.html`
  - `[x]` Remove MatterPak, Generic Point Cloud, and SLAM importers from client and backend codebase
  - `[x]` Enforce strict 1-to-1 matching contract between E57/CSV poses count and external panorama files count
  - `[x]` Restrict CSV override loading strictly to the `E57 + Panos + CSV` import selection
  - `[x]` Remove point-cloud-only loading blocks and verification bypasses from `App.js` runtime
  - `[x]` Verify clean application startup with updated adapters and APIs

- `[x]` **Phase 7: Matterport E57 Cubemap Stitching Engine**
  - `[x]` Introspect Matterport E57 metadata node trees using `pye57`
  - `[x]` Verify that `images2D` contains 6 cubemap face entries per scan location linked by GUID
  - `[x]` Extract JPEG bytes from `BlobNode` via `read_buffer()`
  - `[x]` Implement vectorized sphere-to-cubemap mapping and interpolation in Python using NumPy and SciPy
  - `[x]` Save stitched panoramas into the standard `panos/` directory during structured E57 ingestion
  - `[x]` Verify seamless rendering and navigation of stitched panoramas in the WebGL walkthrough viewer
  - `[x]` Correct vertical projection coordinate flip for right-side-up panoramas
  - `[x]` Restore automatic folder-level CSV pose search fallback inside selected panoramas directory
  - `[x]` Restrict directory panorama scans strictly to JPG/JPEG files to ignore PNG quality maps

- `[x]` **Phase 8: Walkthrough Viewport & API Improvements**
  - `[x]` Implement absolute Three.js quaternion rotation of panoSphere to match scanner alignment
  - `[x]` Draw real-time radar field-of-view wedge and directional pointer arrow on the keyplan current node
  - `[x]` Unpack csv_path in POST /api/ingest handler in app.py to prevent NameError crashes
  - `[x]` Reset scan and panorama state parameters inside showHome in App.js to prevent coordinate leaks
  - `[x]` Restrict global keydown event listener in App.js to ignore typing focus inside inputs, selects, and textareas
  - `[x]` Resolve dedicated project subdirectories inside App.js when creating new walkthrough projects
  - `[x]` Implement a delete project feature (IPC file cleanup handler + home dashboard trash buttons)
  - `[x]` Align walkthrough navigation ring markers flat on the ground level below neighbor panoramas with Matterport-style dimensions
  - `[x]` Isolate and apply only vertical yaw rotation to the panorama sphere, discarding pitch/roll slant to keep view upright
  - `[x]` Implement project organizer folders on the home dashboard screen (creation, deletion, collapsibles, modal dropdowns)
  - `[x]` Implement double-click raycast navigation to transition to the nearest neighbor node in the click direction




