# AV Spatial Bundle v1.1 Interoperability Specification

Target ecosystem:
- **AV Showcase** (callen0817/av-showcase)
- **AV Structure** (callen0817/av-structure)
- **AV Scan** (callen0817/av-scan — C++17 / Qt6 QML)
- **AV ScanAR** (callen0817/av-scanar — Python / PySide6 / ROS 2)

---

## 1. Canonical Coordinate Standard (det = +1.0)

All four applications must strictly follow this right-handed frame:
- **Metric units**: meters.
- **Orientation**: Gravity-aligned Z-up.
  - `+X` = East (Forward)
  - `+Y` = North (Left)
  - `+Z` = Up (Vertical Elevation)

### 1.1 Three.js Coordinate Mapping
When rendering in Three.js (which is right-handed Y-up), the canonical transformation is a pure -90° rotation about Three.js X:
```
Three.js X =  Canonical X
Three.js Y =  Canonical Z
Three.js Z = -Canonical Y
```
Determinant: `det = (+1)*(+1)*(-(-1)) = +1.0` (preserves right-handedness without reflections).

Inverse mapping:
```
Canonical X =  Three.js X
Canonical Y = -Three.js Z
Canonical Z =  Three.js Y
```

### 1.2 Quaternion Mapping
Given canonical quaternion `[qx, qy, qz, qw]` (where qz rotates about vertical +Z):
```javascript
const qThree = new THREE.Quaternion(qx, qz, -qy, qw).normalize();
```

When leveling the panorama sphere to isolate yaw from pitch/roll:
```javascript
const euler = new THREE.Euler().setFromQuaternion(qThree, 'YXZ');
const uprightQ = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), euler.y);
panoSphere.quaternion.copy(uprightQ);
```

---

## 2. Equirectangular Panorama Projection (ASTM E2807-11 §6.5.4)

In station-local coordinates $(x_s, y_s, z_s)$:
- Azimuth: $\text{az} = \text{atan2}(y_s, x_s) \in [-\pi, \pi]$ (0 = $+X$, $+90^\circ$ = $+Y$)
- Elevation: $\text{el} = \text{atan2}(z_s, \sqrt{x_s^2 + y_s^2}) \in [-\pi/2, \pi/2]$
- Pixel coordinates (clockwise horizontal sweep, left-to-right):
  $$\text{col} = \left(\frac{\pi - \text{az}}{2\pi} \pmod{1.0}\right) \cdot W$$
  $$\text{row} = \left(\frac{\pi/2 - \text{el}}{\pi}\right) \cdot H$$

Column interpretations:
- $u = 0.5$ ($\text{col} = W/2$): looks at $+X$ (East)
- $u = 0.25$ ($\text{col} = W/4$): looks at $+Y$ (North)
- $u = 0.75$ ($\text{col} = 3W/4$): looks at $-Y$ (South)
- $u = 0.0 / 1.0$: looks at $-X$ (West)

### 2.1 Pano Sphere Setup
In Three.js, invert the sphere and rotate 180° about Y at initialization:
```javascript
const geometry = new THREE.SphereGeometry(50, 60, 40);
geometry.scale(-1, 1, 1);
geometry.rotateY(Math.PI);
```
This aligns the ASTM pixel sweep identically with Three.js world axes.

### 2.2 Camera Direction Vector (World Azimuth)
For camera pitch `lat` and compass heading `lon` ($0^\circ = +X$ East, $90^\circ = +Y$ North):
```javascript
const phi = THREE.MathUtils.degToRad(90 - lat);
const theta = THREE.MathUtils.degToRad(lon);
target.x =  50 * Math.sin(phi) * Math.cos(theta);
target.y =  50 * Math.cos(phi);
target.z = -50 * Math.sin(phi) * Math.sin(theta);
camera.lookAt(target);
```

---

## 3. Strict 4D Historical Continuity ("Dec 4 → Apr 13")

When switching datasets of the same facility across time:
1. **Never alter camera heading**: `cameraLon` and `cameraLat` remain unchanged across date switches. Because `panoSphere` is already aligned to world space, the user stays looking at the exact same physical feature (e.g. bathroom vanity).
2. **Nearest station transit**: Locate the nearest station in the target date prioritizing vertical story tolerance ($|\Delta z| \le 1.8\text{ m}$) or matching `floor_id`.
3. **Cross-Date Rigid Registration (`transform_to_project`)**: If historical scans started from different doorways, each scan stores a $4 \times 4$ rigid transform into the canonical project frame:
   $$P_{\text{project}} = T_{\text{to\_project}} \cdot P_{\text{local}}$$
   AV Showcase auto-computes this via 4-DOF ICP (coarse yaw FFT search + fine translation/yaw optimization).

---

## 4. AV Spatial Bundle v1.1 Schema

Directory structure:
```
<scan_folder>/
  ├── av_walkthrough_bundle.json   # Manifest
  ├── panos/
  │     ├── pano_000.jpg           # ASTM equirectangular 2048x1024
  │     └── ...
  ├── floors/
  │     ├── floor_1_keyplan.png    # North-up metric architectural wall-slice
  │     └── floor_2_keyplan.png
  └── cache/
        └── lod0.bin               # Downsampled 3D point cloud cache
```

Manifest JSON specification (`av_walkthrough_bundle.json`):
```json
{
  "format": "av_spatial_bundle",
  "schema_version": "1.1",
  "producer": {
    "app": "AV Showcase",
    "version": "2.0.0"
  },
  "project_id": "c1f7a049-74d6-444a-9ceb-7eb19a4bc100",
  "scan_id": "2026-12-04_1430",
  "scan_date": "2026-12-04",
  "coordinate_system": {
    "handedness": "right",
    "up": "+Z",
    "units": "meters",
    "pano_projection": "ASTM_E2807_equirectangular"
  },
  "transform_to_project": [
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0
  ],
  "point_cloud": {
    "lod0": "cache/lod0.bin",
    "format": "av_lod0_v1"
  },
  "nav_graph": "los_v1",
  "floors": [
    {
      "id": 1,
      "name": "Level 1",
      "floor_elevation": 0.00,
      "min_z": 1.55,
      "max_z": 1.65,
      "mean_z": 1.60,
      "keyplan_path": "floors/floor_1_keyplan.png",
      "world_bounds": {
        "min_x": -15.40,
        "max_x": 22.10,
        "min_y": -10.20,
        "max_y": 18.50,
        "meters_per_pixel": 0.02,
        "width_px": 1875,
        "height_px": 1435
      }
    }
  ],
  "panos": [
    {
      "id": "pano_000",
      "position": [2.45, -1.80, 1.60],
      "rotation": [0.0, 0.0, 0.0, 1.0],
      "floor_id": 1,
      "image_path": "panos/pano_000.jpg",
      "neighbors": ["pano_001", "pano_003"],
      "provenance": "SYNTHETIC_FROM_CLOUD",
      "valid_pixel_ratio": 0.942,
      "is_level": true
    }
  ]
}
```

---

## 5. Binary Point Cloud Cache (`lod0.bin`)

Format:
- **Header**: 4-byte unsigned little-endian integer (`uint32`) containing point count $N$.
- **Records**: $N$ packed 15-byte structs:
  ```c
  struct PointRecord {
      float x;   // little-endian IEEE 754 float32 (meters)
      float y;
      float z;
      uint8_t r; // 0 - 255
      uint8_t g;
      uint8_t b;
  } __attribute__((packed));
  ```
