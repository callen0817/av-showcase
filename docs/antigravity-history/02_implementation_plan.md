# Implementation Plan: AV Walkthrough Core Integration (Approved Final)

This plan implements the AV Walkthrough core capabilities, focusing on modular data ingestion, point cloud caching and rendering, walkthrough navigation, and StructionSite-style Auto-Stack comparison. It explicitly preserves the existing GUI layout and styling, modularizes code out of `App.js`, removes Dollhouse and measurement features, and introduces spatial bookmarks, logging, and import flexibility.

---

## Guiding Principle

> **Architect for extension, not prediction**: We will implement only the functionality required for this release, but organize modules, interfaces, and data formats so future capabilities (such as LOD caches, additional import formats, annotations, or spatial indexing) can be added without breaking existing projects or requiring major refactoring.

---

## Final Sanity Refinements

1. **Centralized Coordinate Utility (`src/coords.js`)**: To prevent spatial drift or coordinate mismatch bugs, all axis mappings and conversions between Python/Keyplan (`[x, y, z]`) and Three.js (`[x, y, z]`) space are centralized inside a single conversion utility module.
2. **Runtime Scene State Object**: We will establish a single, authoritative `SceneState` object managed in the main controller (`App.js`) to prevent desynchronization of viewport date selectors, active floors, bookmarks, and coordinate targets.
3. **Deterministic Bookmarks**: Bookmarks will explicitly store the `scan_date` they were created under, ensuring complete determinism during time-based transitions.
4. **Explicit Auto-Stack Fallback**: If no panorama in the target scan is located within the `max_autostack_distance`, the system will abort date transit, keep the user on the current scan date, and present a clear HUD toast notification: `"No viewpoint coverage on this date within X meters. Switch canceled."`
5. **Cache Isolation**: All generated binary caching files must live under `/cache/` and must never be loaded or read directly by the UI layout layer.

---

## Project Format (`project.avproj`) Specification

The file `project.avproj` is saved at the root of the project directory. It stores all metadata for the project and its individual scan dates:

```json
{
  "schema_version": "1.0",
  "application_version": "1.0.0",
  "name": "Project Name",
  "description": "Project Description",
  "created_at": "2026-07-02T03:52:00Z",
  "settings": {
    "max_autostack_distance": 10.0,
    "default_unit": "metric"
  },
  "bookmarks": [
    {
      "name": "Kitchen Area",
      "scan_date": "2026-07-02",
      "position": [2.4, 5.8, 1.2],
      "rotation": [0.0, 0.0],
      "floor_id": 1
    }
  ],
  "scans": [
    {
      "scan_date": "2026-07-02",
      "description": "Ingested E57 Scan",
      "import_mode": "linked",
      "source_path": "C:/Scans/large_building_floor1.e57",
      "source_hash": "a1b2c3d4...",
      "source_modified": 1782845600,
      "point_cloud_cache": "Scans/2026-07-02/cache/lod0.bin",
      "floors": [
        {
          "id": 1,
          "min_z": -1.0,
          "max_z": 1.0,
          "fpOffset": {"x": 0, "y": 0},
          "fpScale": 1.0
        }
      ],
      "panos": [
        {
          "id": "pano_000",
          "image_path": "Scans/2026-07-02/panos/pano_000.jpg",
          "position": [0.0, 0.0, 0.0],
          "rotation": [0.0, 0.0, 0.0, 1.0],
          "floor_id": 1,
          "neighbors": ["pano_001"]
        }
      ]
    }
  ]
}
```

---

## Proposed Changes

### 1. Python Backend Ingestion (LAS, LAZ, E57, XYZ)

#### [MODIFY] [ingestion.py](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/backend/ingestion.py)
* **LAS/LAZ Import**: Add `load_las_points(las_path, target_points)` using `laspy` to read, scale, and downsample point data.
* **E57 Points & Poses Extraction**: Add `extract_e57_pointcloud(e57_path, target_points_per_scan)` to parse data3D coordinate tables, apply rotation quaternions and translation offsets, downsample scans, and bundle points.
* **XYZ text parsing**: Add `load_xyz_points(xyz_path, target_points)` to parse XYZ format.
* **Managed vs. Linked Modes**:
  * If `import_mode` is `managed`, copy the raw file to `Scans/<scan_date>/raw_source.<ext>`.
  * If `import_mode` is `linked`, calculate and store the path, file hash, and modification time without copying.
* **LOD Rendering Caching**: Write `save_point_cloud_bin(filepath, points, colors)` to write raw coordinates and RGB values to `cache/lod0.bin` utilizing numpy structured array buffer dumps (`tobytes()`).
* **Ingestion Logs**: Write ingestion status and error diagnostics to `logs/import.log` inside the project.
* **Unified Project Update**: Update ingestion tasks to save output coordinates and metadata into the unified `project.avproj` schema.

---

### 2. Electron Main Process & Preload

#### [MODIFY] [main.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/main.js)
* Implement the `read-file-bin` IPC handler for reading raw file buffers.
* Update `select-file` dialog filters to target `.avproj` files.
* Log Electron process occurrences to `logs/app.log`.

#### [MODIFY] [preload.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/preload.js)
* Expose `readFileBin: (path) => ipcRenderer.invoke('read-file-bin', { path })` to the renderer.

---

### 3. Modular Frontend Architecture

#### [NEW] [coords.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/coords.js)
* Centralized point conversion utility. maps `pythonToThree` and `threeToPython` vectors:
  * Three.js X = Python X
  * Three.js Y = Python Z (height)
  * Three.js Z = Python Y

#### [NEW] [projectManager.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/projectManager.js)
* Manages loading, parsing, and saving the unified `project.avproj` configuration.
* Manages autosave loops (writing to `logs/autosave.log`), recent project listings, bookmarks registration, and error recovery tracking.

#### [NEW] [dataLoader.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/dataLoader.js)
* Handles loading and byte-level decoding of the custom `cache/lod0.bin` binary structure. Returns parsed Float32 positions and colors.

#### [NEW] [renderer.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/renderer.js)
* Instantiates Three.js WebGL rendering context, loads panorama textures onto the inverted sphere, creates the `THREE.Points` object, and manages point cloud rendering.
* Positions the point cloud relative to the camera in panorama view using the centralized coordinates mapping utility.
* Write rendering warnings and performance logs to `logs/renderer.log`.

#### [NEW] [navigation.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/navigation.js)
* Draws the 2D Canvas keyplan nodes, connections, active indicator, and floorplan overlays.
* Generates Three.js 3D navigation markers using `src/coords.js` conversions.

#### [NEW] [autoStack.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/autoStack.js)
* Implements search interface `findNearestPano(targetPos, searchPool)` to determine the closest panorama in a target scan date, prioritizing floor matching before evaluated distances.
* Encapsulates the calculation logic to swap for a KD-tree index later without breaking caller integrations.
* Returns spatial matches or abort triggers if closest points exceed settings.

#### [MODIFY] [App.js](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/App.js)
* Establish authoritative `SceneState` runtime tracking object.
* Remove all measurement functions, variables, and listeners.
* Clean out Three.js setups, keyplans, dialogs, and loaders, delegating those tasks to the newly defined modules.
* Act as a controller forwarding events, handling UI initialization, managing the Bookmarks dropdown selector, and tracking global project state.

---

### 4. Interface Updates

#### [MODIFY] [index.html](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/index.html)
* Remove `#unit-selector` dropdown, `#btn-measure` button, and `#measurement-tooltip` overlay entirely.
* Add `#bookmark-selector` dropdown select list in the control panel to manage viewport bookmarks.
* Update file open cards to target `.avproj` projects.

#### [MODIFY] [style.css](file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/style.css)
* Add a simple styling rule for `#bookmark-selector` to match the existing dropdown selector style. No other rules are changed or refactored.

---

## Verification Plan

### Backend & Ingestion
* Import a test E57 file under both *managed* and *linked* modes. Verify:
  * In linked mode, `raw_source` is not copied, but path/hash/date are logged.
  * In managed mode, a copy of the source `.e57` is written.
  * `cache/lod0.bin` is generated with valid binary sizes.
  * `logs/import.log` contains detailed records of points processed and extraction timings.
  * Unified `project.avproj` contains valid scans, floors, and panorama poses.

### Auto-Stack Date Comparison
* Open a project with two scans of different dates.
* Stand in a specific room, look in a direction, and switch dates.
* Verify that you land in the nearest scan node on the same floor, looking in the same direction.

### Bookmarks Navigation
* Open a project, navigate to a viewpoint, choose "Add Bookmark", name it, and save.
* Go to another location, then select the bookmark from the dropdown. Verify that the view instantly warps back to the bookmarked floor, coordinate, and camera yaw/pitch.
* Toggle the date dropdown while active on a bookmark and check that Auto-Stack transports you to the closest location on the new date.

### UI Consistency & Regressions
* Ensure other features (recent projects, home screen, project load, keyplan drawing, floorplan upload calibration) continue to function exactly as before with no regressions.
