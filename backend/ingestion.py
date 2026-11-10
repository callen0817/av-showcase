import os
import json
import shutil
import math
from pathlib import Path
import traceback
import struct
import numpy as np
import logging

logger = logging.getLogger("import")

try:
    import pye57
except ImportError:
    pye57 = None

try:
    from sklearn.neighbors import NearestNeighbors
except ImportError:
    NearestNeighbors = None

try:
    import laspy
except ImportError:
    laspy = None

def dump_e57_tree(node, path="root", depth=0):
    """Recursively log the structure of an E57 tree for diagnostics."""
    try:
        logging.info(f"{'  '*depth}{path}: {type(node).__name__}")
        if hasattr(node, "childCount"):
            for i in range(node.childCount()):
                try:
                    child = node.get(i)
                    dump_e57_tree(child, f"{path}/{i}", depth+1)
                except: continue
        elif hasattr(node, "keys"):
            for key in node.keys():
                try:
                    child = node[key]
                    dump_e57_tree(child, f"{path}/{key}", depth+1)
                except: continue
    except Exception as e:
        logging.error(f"Error dumping tree at {path}: {e}")

def find_nodes_by_name(node, target_names, found=None, path="root"):
    """Recursively search for nodes by name (case-insensitive)."""
    if found is None: found = []
    target_names = [t.lower() for t in target_names]
    try:
        if hasattr(node, "keys"):
            for key in node.keys():
                child = node[key]
                if key.lower() in target_names:
                    found.append((path + "/" + key, child))
                find_nodes_by_name(child, target_names, found, path + "/" + key)
        elif hasattr(node, "childCount"):
            for i in range(node.childCount()):
                child = node.get(i)
                find_nodes_by_name(child, target_names, found, path + f"/{i}")
    except: pass
    return found

FLOOR_Z_THRESHOLD = 0.3  # ~1 foot in meters
NEIGHBOR_DISTANCE_THRESHOLD = 12.0  # 12 meters

def calculate_file_hash(filepath):
    import hashlib
    hasher = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logging.error(f"Error calculating hash for {filepath}: {e}")
        return ""

def setup_import_log(project_dir):
    log_dir = Path(project_dir) / "logs"
    log_dir.mkdir(exist_ok=True)
    import_log_path = log_dir / "import.log"
    logger = logging.getLogger("import")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(import_log_path, mode='a', encoding='utf-8')
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(fh)
    return logger

def save_point_cloud_bin(filepath, points, colors):
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    num_points = len(points)
    dt = np.dtype([
        ('x', 'f4'), ('y', 'f4'), ('z', 'f4'),
        ('r', 'u1'), ('g', 'u1'), ('b', 'u1')
    ])
    arr = np.zeros(num_points, dtype=dt)
    arr['x'] = points[:, 0]
    arr['y'] = points[:, 1]
    arr['z'] = points[:, 2]
    arr['r'] = colors[:, 0]
    arr['g'] = colors[:, 1]
    arr['b'] = colors[:, 2]
    
    with open(filepath, 'wb') as f:
        f.write(struct.pack('<I', num_points))
        f.write(arr.tobytes())

def validate_scan_contract(panos, poses, pano_files=None):
    if len(panos) == 0:
        raise RuntimeError("CONTRACT VIOLATION: zero panoramas")

    if len(poses) == 0:
        raise RuntimeError("CONTRACT VIOLATION: zero poses")

    if len(panos) != len(poses):
        raise RuntimeError(f"CONTRACT VIOLATION: Panorama/Pose mismatch: panos={len(panos)}, poses={len(poses)}")

    for p in panos:
        if len(p["position"]) != 3:
            raise RuntimeError("INVALID POSITION VECTOR")

        if len(p["rotation"]) != 4:
            raise RuntimeError("INVALID ROTATION QUATERNION")

    if pano_files is not None:
        if len(panos) != len(pano_files):
            raise RuntimeError(f"PANO/IMAGE DESYNC: panos={len(panos)}, files={len(pano_files)}")

    return True

def write_import_report(scan_dir, report_data):
    report_path = os.path.join(scan_dir, "import_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    
    txt_path = os.path.join(scan_dir, "import_report.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("=========================================\n")
        f.write("         AV WALKTHROUGH IMPORT REPORT     \n")
        f.write("=========================================\n")
        for k, v in report_data.items():
            f.write(f"{k.upper().replace('_', ' ')}: {v}\n")
        f.write("=========================================\n")

def _load_poses_from_csv(csv_path, logger=None):
    poses = []
    if not os.path.exists(csv_path):
        return poses
        
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        if not lines:
            return poses
            
        # Detect delimiter
        header_line = lines[0]
        delim = ';' if ';' in header_line else ','
        
        # Parse header to find column indices
        header_cols = [c.strip().lower() for c in header_line.replace('#', '').split(delim)]
        
        # Default fallback indices based on the NavVis pano-poses.csv standard:
        # ID; filename; timestamp; x; y; z; qw; qx; qy; qz
        idx_x, idx_y, idx_z = 3, 4, 5
        idx_qw, idx_qx, idx_qy, idx_qz = 6, 7, 8, 9
        
        # Try to find columns by name in header
        for idx, col in enumerate(header_cols):
            if 'pos_x' in col or col == 'x':
                idx_x = idx
            elif 'pos_y' in col or col == 'y':
                idx_y = idx
            elif 'pos_z' in col or col == 'z':
                idx_z = idx
            elif 'ori_w' in col or col == 'qw' or col == 'w':
                idx_qw = idx
            elif 'ori_x' in col or col == 'qx' or col == 'x_ori':
                idx_qx = idx
            elif 'ori_y' in col or col == 'qy' or col == 'y_ori':
                idx_qy = idx
            elif 'ori_z' in col or col == 'qz' or col == 'z_ori':
                idx_qz = idx

        for line in lines[1:]:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            cols = [c.strip() for c in line.split(delim)]
            if len(cols) > max(idx_x, idx_y, idx_z, idx_qw, idx_qx, idx_qy, idx_qz):
                try:
                    x = float(cols[idx_x])
                    y = float(cols[idx_y])
                    z = float(cols[idx_z])
                    qw = float(cols[idx_qw])
                    qx = float(cols[idx_qx])
                    qy = float(cols[idx_qy])
                    qz = float(cols[idx_qz])
                    
                    poses.append({
                        "position": [x, y, z],
                        "rotation": [qx, qy, qz, qw]
                    })
                except Exception as e:
                    continue
    except Exception as e:
        if logger:
            logger.error(f"Error parsing CSV poses: {e}")
            
    return poses

def transform_points(points, translation, rotation):
    qx, qy, qz, qw = rotation
    r00 = 1 - 2*(qy**2 + qz**2)
    r01 = 2*(qx*qy - qz*qw)
    r02 = 2*(qx*qz + qy*qw)
    
    r10 = 2*(qx*qy + qz*qw)
    r11 = 1 - 2*(qx**2 + qz**2)
    r12 = 2*(qy*qz - qx*qw)
    
    r20 = 2*(qx*qz - qy*qw)
    r21 = 2*(qy*qz + qx*qw)
    r22 = 1 - 2*(qx**2 + qy**2)
    
    R = np.array([
        [r00, r01, r02],
        [r10, r11, r12],
        [r20, r21, r22]
    ])
    
    return np.dot(points, R.T) + np.array(translation)

def extract_e57_pointcloud(e57_path, target_points_per_scan=10000, logger=None):
    if logger is None:
        logger = logging.getLogger("import")
    logger.info(f"Extracting point cloud from E57: {e57_path}")
    try:
        e57 = pye57.E57(e57_path)
        try:
            data3d_root = e57.root["data3D"]
        except KeyError:
            logger.warning("No data3D node found in E57.")
            return np.zeros((0, 3), dtype=np.float32), np.zeros((0, 3), dtype=np.uint8)
        
        scan_count = data3d_root.childCount() if hasattr(data3d_root, 'childCount') else 0
        
        all_points = []
        all_colors = []
        
        for i in range(scan_count):
            try:
                logger.info(f"Reading scan points {i+1} of {scan_count}...")
                scan_data = e57.read_scan(i, colors=True, ignore_missing_fields=True)
                if 'cartesianX' not in scan_data:
                    logger.warning(f"Scan {i} does not contain cartesian points. Skipping.")
                    continue
                
                x = scan_data['cartesianX']
                y = scan_data['cartesianY']
                z = scan_data['cartesianZ']
                pts = np.column_stack((x, y, z))
                
                if 'colorRed' in scan_data and 'colorGreen' in scan_data and 'colorBlue' in scan_data:
                    r = scan_data['colorRed']
                    g = scan_data['colorGreen']
                    b = scan_data['colorBlue']
                    max_val = max(np.max(r), np.max(g), np.max(b)) if len(r) > 0 else 0
                    if max_val > 255:
                        r = (r / max_val * 255.0).astype(np.uint8)
                        g = (g / max_val * 255.0).astype(np.uint8)
                        b = (b / max_val * 255.0).astype(np.uint8)
                    cols = np.column_stack((r, g, b)).astype(np.uint8)
                elif 'intensity' in scan_data:
                    intensity = scan_data['intensity']
                    max_int = np.max(intensity) if len(intensity) > 0 else 1
                    grey = (intensity / max_int * 255.0).astype(np.uint8) if max_int > 0 else np.full(len(pts), 200, dtype=np.uint8)
                    cols = np.column_stack((grey, grey, grey))
                else:
                    cols = np.full((len(pts), 3), 200, dtype=np.uint8)
                
                scan_node = data3d_root[i]
                if "pose" in scan_node:
                    pose_node = scan_node["pose"]
                    translation = pose_node["translation"]
                    rotation = pose_node["rotation"]
                    tx, ty, tz = translation["x"].value(), translation["y"].value(), translation["z"].value()
                    qw, qx, qy, qz = rotation["w"].value(), rotation["x"].value(), rotation["y"].value(), rotation["z"].value()
                    pts = transform_points(pts, [tx, ty, tz], [qx, qy, qz, qw])
                
                num_pts = len(pts)
                if num_pts > 0:
                    step = max(1, num_pts // target_points_per_scan)
                    all_points.append(pts[::step])
                    all_colors.append(cols[::step])
            except Exception as scan_err:
                logger.error(f"Error extracting points from scan {i}: {scan_err}")
                continue
                
        if all_points:
            return np.vstack(all_points).astype(np.float32), np.vstack(all_colors).astype(np.uint8)
        return np.zeros((0, 3), dtype=np.float32), np.zeros((0, 3), dtype=np.uint8)
    except Exception as e:
        logger.error(f"Error reading E57 point cloud: {e}")
        return np.zeros((0, 3), dtype=np.float32), np.zeros((0, 3), dtype=np.uint8)

def load_xyz_points(xyz_path, target_points=100000, logger=None):
    if logger is None:
        logger = logging.getLogger("import")
    logger.info(f"Parsing XYZ point cloud: {xyz_path}")
    points = []
    colors = []
    
    try:
        with open(xyz_path, 'r') as f:
            num_lines = sum(1 for _ in f)
        
        step = max(1, num_lines // target_points)
        logger.info(f"XYZ file has {num_lines} points. Downsampling step: {step}")
        
        with open(xyz_path, 'r') as f:
            for idx, line in enumerate(f):
                if idx % step != 0:
                    continue
                parts = line.strip().split()
                if len(parts) >= 3:
                    try:
                        x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                        r, g, b = 200, 200, 200
                        if len(parts) >= 6:
                            r, g, b = float(parts[3]), float(parts[4]), float(parts[5])
                            if r <= 1.0 and g <= 1.0 and b <= 1.0:
                                r, g, b = r * 255.0, g * 255.0, b * 255.0
                        points.append([x, y, z])
                        colors.append([r, g, b])
                    except ValueError:
                        continue
    except Exception as e:
        logger.error(f"Error parsing XYZ: {e}")
        
    return np.array(points, dtype=np.float32), np.array(colors, dtype=np.uint8)

def load_las_points(las_path, target_points=100000, logger=None):
    if logger is None:
        logger = logging.getLogger("import")
    logger.info(f"Parsing LAS/LAZ point cloud: {las_path}")
    try:
        import laspy
        las = laspy.read(las_path)
        num_points = len(las.points)
        step = max(1, num_points // target_points)
        logger.info(f"LAS file has {num_points} points. Downsampling step: {step}")
        
        x = np.array(las.x)[::step]
        y = np.array(las.y)[::step]
        z = np.array(las.z)[::step]
        pts = np.column_stack((x, y, z))
        
        if hasattr(las, 'red') and hasattr(las, 'green') and hasattr(las, 'blue'):
            r = np.array(las.red)[::step]
            g = np.array(las.green)[::step]
            b = np.array(las.blue)[::step]
            
            max_val = max(np.max(r), np.max(g), np.max(b)) if len(r) > 0 else 0
            if max_val > 255:
                r = (r / max_val * 255.0).astype(np.uint8)
                g = (g / max_val * 255.0).astype(np.uint8)
                b = (b / max_val * 255.0).astype(np.uint8)
            else:
                r, g, b = r.astype(np.uint8), g.astype(np.uint8), b.astype(np.uint8)
            cols = np.column_stack((r, g, b))
        else:
            if hasattr(las, 'intensity'):
                intensity = np.array(las.intensity)[::step]
                max_int = np.max(intensity) if len(intensity) > 0 else 1
                grey = (intensity / max_int * 255.0).astype(np.uint8) if max_int > 0 else np.full(len(pts), 200, dtype=np.uint8)
                cols = np.column_stack((grey, grey, grey))
            else:
                cols = np.full((len(pts), 3), 200, dtype=np.uint8)
                
        return pts.astype(np.float32), cols.astype(np.uint8)
    except Exception as e:
        logger.error(f"Error parsing LAS/LAZ: {e}")
        return np.zeros((0, 3), dtype=np.float32), np.zeros((0, 3), dtype=np.uint8)

class IngestionManager:
    def __init__(self, project_dir, project_name, floor_threshold=0.25, floor_heights=''):
        self.project_dir = Path(project_dir)
        self.project_name = project_name
        self.floor_threshold = floor_threshold
        self.floor_heights = floor_heights
        self.project_json_path = self.project_dir / "project.avproj"
        
        self.project_dir.mkdir(parents=True, exist_ok=True)
        (self.project_dir / "Scans").mkdir(exist_ok=True)
        (self.project_dir / "logs").mkdir(exist_ok=True)
        
        if not self.project_json_path.exists():
            old_path = self.project_dir / "project.json"
            if old_path.exists():
                try:
                    with open(old_path, 'r') as f:
                        old_data = json.load(f)
                    old_data["schema_version"] = "1.0"
                    old_data["application_version"] = "1.0.0"
                    old_data["bookmarks"] = []
                    old_data["settings"] = {"max_autostack_distance": 10.0, "default_unit": "metric"}
                    with open(self.project_json_path, 'w') as f:
                        json.dump(old_data, f, indent=2)
                    os.remove(old_path)
                    logging.info("Migrated project.json to project.avproj")
                except Exception as e:
                    logging.error(f"Migration error: {e}")
            
            if not self.project_json_path.exists():
                with open(self.project_json_path, "w") as f:
                    json.dump({
                        "schema_version": "1.0",
                        "application_version": "1.0.0",
                        "name": self.project_name,
                        "description": "",
                        "settings": {
                            "max_autostack_distance": 10.0,
                            "default_unit": "metric"
                        },
                        "bookmarks": [],
                        "scans": []
                    }, f, indent=2)

    def _handle_source_import(self, source_path, scan_date, import_mode):
        if not source_path or not os.path.exists(source_path):
            return ""
        
        scan_dir = self.project_dir / "Scans" / scan_date
        scan_dir.mkdir(parents=True, exist_ok=True)
        
        if import_mode == "managed":
            ext = source_path.lower().split('.')[-1]
            dest_name = f"raw_source.{ext}"
            dest_path = scan_dir / dest_name
            logging.info(f"Managed Mode: Copying {source_path} to {dest_path}")
            shutil.copy2(source_path, dest_path)
            return f"Scans/{scan_date}/{dest_name}"
        else:
            logging.info(f"Linked Mode: Storing link reference to {source_path}")
            return str(Path(source_path).resolve())

    def _write_scan_to_project(self, scan_date, description, panos, floors, import_mode, source_path, cache_rel_path):
        if len(panos) == 0:
            raise RuntimeError("CONTRACT VIOLATION: Refusing to write empty scan to project config.")
            
        source_hash = ""
        source_modified = 0.0
        if source_path and os.path.exists(source_path):
            source_hash = calculate_file_hash(source_path)
            source_modified = os.path.getmtime(source_path)
        
        with open(self.project_json_path, "r") as f:
            proj_data = json.load(f)
            
        existing_scans = [s for s in proj_data['scans'] if s['scan_date'] != scan_date]
        
        new_scan = {
            "scan_date": scan_date,
            "description": description,
            "import_mode": import_mode,
            "source_path": source_path or "",
            "source_hash": source_hash,
            "source_modified": source_modified,
            "point_cloud_cache": cache_rel_path,
            "floors": floors,
            "panos": panos
        }
        proj_data['scans'] = existing_scans + [new_scan]
        proj_data['scans'].sort(key=lambda x: x['scan_date'], reverse=True)
        
        with open(self.project_json_path, "w") as f:
            json.dump(proj_data, f, indent=2)

    def _get_z_floors(self, z_values):
        if not z_values:
            return {}, []
            
        custom_names = []
        # Option 1: User specified exact floor elevations or floor labels
        if self.floor_heights:
            raw_tokens = [h.strip() for h in str(self.floor_heights).split(",") if h.strip()]
            heights = []
            try:
                parsed = [float(t) for t in raw_tokens]
                # Only treat as explicit Z-elevations if at least 2 heights are given, or a decimal height is given
                if len(parsed) >= 2 or (len(parsed) == 1 and "." in raw_tokens[0]):
                    heights = parsed
                else:
                    custom_names = raw_tokens
            except Exception as e:
                custom_names = raw_tokens
                logger.info(f"Interpreting floor_heights '{self.floor_heights}' as custom floor labels ({custom_names}); using multi-level clustering.")
                
            if heights:
                sorted_heights = sorted(heights)
                floor_mapping = {}
                assigned_scans = {i+1: [] for i in range(len(sorted_heights))}
                
                for z in z_values:
                    # Assign to closest specified floor elevation
                    closest_idx = int(np.argmin([abs(z - h) for h in sorted_heights]))
                    floor_id = closest_idx + 1
                    floor_mapping[z] = floor_id
                    assigned_scans[floor_id].append(z)
                    
                floors = []
                for idx, h in enumerate(sorted_heights):
                    fid = idx + 1
                    scans_z = assigned_scans[fid]
                    if len(scans_z) > 0:
                        min_z = min(scans_z)
                        max_z = max(scans_z)
                    else:
                        min_z = h - 0.5
                        max_z = h + 0.5
                    floors.append({
                        "id": fid,
                        "min_z": min_z,
                        "max_z": max_z
                    })
                return floor_mapping, floors

        # Option 1B: If user provided K >= 2 custom floor labels (e.g. '1, mezz' or '1, 2, 3, 4, 5')
        # Partition into exactly K levels using 1D clustering with midpoint stair boundaries
        if len(custom_names) >= 2:
            k = len(custom_names)
            z_arr = np.array(z_values)
            percentiles = np.linspace(10, 90, k)
            centers = np.percentile(z_arr, percentiles)
            for _ in range(50):
                dists = np.abs(z_arr[:, None] - centers[None, :])
                lbls = np.argmin(dists, axis=-1)
                new_centers = np.array([np.mean(z_arr[lbls == j]) if np.any(lbls == j) else centers[j] for j in range(k)])
                if np.allclose(centers, new_centers, atol=1e-3):
                    break
                centers = new_centers
                
            sorted_order = np.argsort(centers)
            centers = centers[sorted_order]
            midpoints = (centers[:-1] + centers[1:]) / 2.0
            
            final_floor_mapping = {}
            final_floors = []
            
            for idx, c in enumerate(centers):
                fid = idx + 1
                if idx == 0:
                    scans_z = [z for z in z_values if z < midpoints[0]]
                elif idx == k - 1:
                    scans_z = [z for z in z_values if z >= midpoints[-1]]
                else:
                    scans_z = [z for z in z_values if midpoints[idx-1] <= z < midpoints[idx]]
                    
                if not scans_z:
                    scans_z = [float(c)]
                    
                for z in scans_z:
                    final_floor_mapping[z] = fid
                    
                fl_entry = {
                    "id": fid,
                    "name": custom_names[idx],
                    "min_z": float(min(scans_z)),
                    "max_z": float(max(scans_z)),
                    "mean_z": float(c)
                }
                final_floors.append(fl_entry)
                
            return final_floor_mapping, final_floors

        # Option 2: Dynamic plateau detection and inter-floor midpoint stair partition
        thresh = float(self.floor_threshold) if self.floor_threshold is not None else 0.25
        fine_thresh = min(thresh, 0.30)
        sorted_z = sorted(list(set(z_values)))
        floors = []
        current_floor_id = 1
        current_min_z = sorted_z[0]
        floor_mapping = {}
        
        for i in range(len(sorted_z)):
            z = sorted_z[i]
            if i > 0 and (z - sorted_z[i-1]) > fine_thresh:
                floors.append({
                    "id": current_floor_id,
                    "min_z": current_min_z,
                    "max_z": sorted_z[i-1]
                })
                current_floor_id += 1
                current_min_z = z
            floor_mapping[z] = current_floor_id
            
        floors.append({
            "id": current_floor_id,
            "min_z": current_min_z,
            "max_z": sorted_z[-1]
        })
        
        # Single-level fast path (preserves 100% backwards compatibility for 1-level scans)
        if len(floors) <= 1:
            fl_obj = {
                "id": 1,
                "min_z": float(sorted_z[0]),
                "max_z": float(sorted_z[-1])
            }
            if len(custom_names) == 1:
                fl_obj["name"] = custom_names[0]
            return floor_mapping, [fl_obj]

        # Populate Z values and count for each fine candidate cluster
        for f in floors:
            f["scans"] = [z for z in z_values if f["min_z"] <= z <= f["max_z"]]
            f["count"] = len(f["scans"])
            f["mean_z"] = float(np.mean(f["scans"])) if len(f["scans"]) > 0 else (f["min_z"] + f["max_z"]) / 2.0
            
        # Classify candidate clusters into Major Floors (plateaus) vs Stairs/Transitions
        major_floors = []
        stairs_floors = []
        major_count_thresh = max(12, int(0.06 * len(z_values)))
        
        for idx, f in enumerate(floors):
            is_major = f["count"] >= major_count_thresh
            
            if not is_major:
                left_count = floors[idx-1]["count"] if idx > 0 else 0
                right_count = floors[idx+1]["count"] if idx < len(floors) - 1 else 0
                if f["count"] >= 4 and f["count"] > left_count and f["count"] > right_count:
                    is_major = True
                    
            if not is_major:
                left_gap = (f["mean_z"] - floors[idx-1]["mean_z"]) if idx > 0 else 999.0
                right_gap = (floors[idx+1]["mean_z"] - f["mean_z"]) if idx < len(floors) - 1 else 999.0
                if min(left_gap, right_gap) > 0.60:
                    is_major = True
                    
            if is_major:
                f["plateau_mean_z"] = f["mean_z"]
                major_floors.append(f)
            else:
                stairs_floors.append(f)
                
        if not major_floors:
            for f in floors:
                f["plateau_mean_z"] = f["mean_z"]
            major_floors = floors
            stairs_floors = []
            
        # Distribute scans in stairs clusters using the TRUE inter-floor midpoint
        for sf in stairs_floors:
            below_majors = [mf for mf in major_floors if mf["plateau_mean_z"] < sf["mean_z"]]
            above_majors = [mf for mf in major_floors if mf["plateau_mean_z"] > sf["mean_z"]]
            
            floor_below = max(below_majors, key=lambda x: x["plateau_mean_z"]) if below_majors else None
            floor_above = min(above_majors, key=lambda x: x["plateau_mean_z"]) if above_majors else None
            
            if floor_below and floor_above:
                inter_floor_mid_z = (floor_below["plateau_mean_z"] + floor_above["plateau_mean_z"]) / 2.0
                for z in sf["scans"]:
                    if z < inter_floor_mid_z:
                        floor_below["scans"].append(z)
                    else:
                        floor_above["scans"].append(z)
            elif floor_above:
                floor_above["scans"].extend(sf["scans"])
            elif floor_below:
                floor_below["scans"].extend(sf["scans"])
                    
        final_floor_mapping = {}
        final_floors = []
        
        major_floors.sort(key=lambda x: x["plateau_mean_z"])
        
        for idx, mf in enumerate(major_floors):
            fid = idx + 1
            if not mf["scans"]:
                continue
            
            for z in mf["scans"]:
                final_floor_mapping[z] = fid
                
            fl_entry = {
                "id": fid,
                "min_z": float(min(mf["scans"])),
                "max_z": float(max(mf["scans"])),
                "mean_z": float(mf["plateau_mean_z"])
            }
            if idx < len(custom_names):
                fl_entry["name"] = custom_names[idx]
            final_floors.append(fl_entry)
            
        return final_floor_mapping, final_floors

    def _generate_navigation_graph(self, panos):
        if not panos:
            return panos

        floors_dict = {}
        for p in panos:
            fid = p['floor_id']
            if fid not in floors_dict:
                floors_dict[fid] = []
            floors_dict[fid].append(p)
            
        # 1. Smart Multi-Directional Same-Floor Navigation Graph
        # Uses 8 directional sectors (every 45 deg) + trajectory continuity + redundancy suppression
        for floor_id, floor_panos in floors_dict.items():
            n = len(floor_panos)
            if n < 2:
                p_single = floor_panos[0]
                if 'neighbors' not in p_single or p_single['neighbors'] is None:
                    p_single['neighbors'] = []
                continue
                
            pts = np.array([p['position'] for p in floor_panos])
            diff = pts[:, None, :2] - pts[None, :, :2] # 2D horizontal vector
            dists = np.linalg.norm(diff, axis=-1)
            angles = np.arctan2(diff[..., 1], diff[..., 0]) # [-pi, pi]
            
            for i, p in enumerate(floor_panos):
                nbr_set = set()
                
                # Rule 1: Sequential trajectory continuity (walk forward and backward along scan path)
                for offset in [-1, 1]:
                    adj = i + offset
                    if 0 <= adj < n and dists[i, adj] <= NEIGHBOR_DISTANCE_THRESHOLD:
                        nbr_set.add(floor_panos[adj]['id'])
                        
                # Rule 2: 8 Directional Sectors (every 45 degrees around scanner)
                # Guarantees forward, backward, left, right, and diagonal navigation
                num_sectors = 8
                sector_step = 2.0 * math.pi / num_sectors
                
                valid_mask = (dists[i] > 0.01) & (dists[i] <= NEIGHBOR_DISTANCE_THRESHOLD)
                valid_indices = np.where(valid_mask)[0]
                
                if len(valid_indices) > 0:
                    cand_dists = dists[i, valid_indices]
                    cand_angles = angles[i, valid_indices]
                    
                    sector_indices = np.floor((cand_angles + math.pi + (sector_step / 2.0)) / sector_step).astype(int) % num_sectors
                    
                    for s in range(num_sectors):
                        in_sector = np.where(sector_indices == s)[0]
                        if len(in_sector) == 0:
                            continue
                        s_dists = cand_dists[in_sector]
                        s_indices = valid_indices[in_sector]
                        
                        # Prioritize candidates >= 0.5m away to escape stationary duplicate clusters
                        far_enough = s_dists >= 0.5
                        if np.any(far_enough):
                            best_idx = s_indices[far_enough][np.argmin(s_dists[far_enough])]
                        else:
                            best_idx = s_indices[np.argmin(s_dists)]
                        nbr_set.add(floor_panos[best_idx]['id'])
                        
                # Rule 3: Add closest remaining neighbors within 2.0m up to 8 max
                sorted_by_dist = np.argsort(dists[i])
                for idx in sorted_by_dist[1:]:
                    if len(nbr_set) >= 8:
                        break
                    if dists[i, idx] <= 2.0:
                        nbr_set.add(floor_panos[idx]['id'])
                    else:
                        break
                        
                p['neighbors'] = list(nbr_set)

        # 2. Multi-level Cross-Floor Staircase Navigation Links
        # Connects the top of the bottom-half stairs (Floor F) to the bottom of the top-half stairs (Floor F+1)
        if len(floors_dict) > 1:
            sorted_fids = sorted(floors_dict.keys())
            for i in range(len(sorted_fids)):
                for j in range(i + 1, min(i + 3, len(sorted_fids))):
                    fid_a = sorted_fids[i]
                    fid_b = sorted_fids[j]
                    panos_a = floors_dict[fid_a]
                    panos_b = floors_dict[fid_b]
                    
                    stair_links = []
                    for pa in panos_a:
                        ax, ay, az = pa['position']
                        for pb in panos_b:
                            bx, by, bz = pb['position']
                            dz = abs(bz - az)
                            dxy = math.hypot(bx - ax, by - ay)
                            # Stair step/landing transition criteria:
                            # Vertical separation <= 2.2m (avoids linking through full room ceilings >= 2.8m)
                            # Horizontal proximity <= 5.5m
                            if 0.10 <= dz <= 2.20 and dxy <= 5.50:
                                d3d = math.sqrt(dxy * dxy + dz * dz)
                                stair_links.append((d3d, pa, pb))
                                
                    stair_links.sort(key=lambda x: x[0])
                    # Connect up to 4 closest stair boundary transitions between the two floors
                    linked_a = set()
                    linked_b = set()
                    for d3d, pa, pb in stair_links:
                        if len(linked_a) >= 4 and len(linked_b) >= 4:
                            break
                        if pa['id'] not in linked_a or pb['id'] not in linked_b:
                            if pb['id'] not in pa['neighbors']:
                                pa['neighbors'].append(pb['id'])
                            if pa['id'] not in pb['neighbors']:
                                pb['neighbors'].append(pa['id'])
                            linked_a.add(pa['id'])
                            linked_b.add(pb['id'])

        # Ensure symmetric edges (if A -> B then B -> A)
        pano_map = {p['id']: p for p in panos}
        for p in panos:
            for nid in list(p.get('neighbors', [])):
                np_target = pano_map.get(nid)
                if np_target and p['id'] not in np_target.get('neighbors', []):
                    np_target['neighbors'].append(p['id'])
                
        return panos
                
        return panos

    def recluster_project(self):
        """Re-computes floors and navigation graph for all scans in project.avproj in <50ms without re-ingesting E57."""
        if not self.project_json_path.exists():
            return False, "project.avproj not found"
            
        with open(self.project_json_path, "r", encoding="utf-8") as f:
            proj_data = json.load(f)
            
        for scan in proj_data.get("scans", []):
            panos = scan.get("panos", [])
            if not panos:
                continue
            z_values = [p["position"][2] for p in panos]
            floor_mapping, new_floors = self._get_z_floors(z_values)
            
            # Preserve existing floorplan calibration (fpOffset, fpScale, floorplan_path) if floor IDs match
            old_floors_by_id = {fl["id"]: fl for fl in scan.get("floors", [])}
            for nf in new_floors:
                old_fl = old_floors_by_id.get(nf["id"])
                if old_fl:
                    for key in ["fpOffset", "fpScale", "floorplan_path"]:
                        if key in old_fl:
                            nf[key] = old_fl[key]
                            
            for p in panos:
                z = p["position"][2]
                p["floor_id"] = floor_mapping.get(z, 1)
                
            scan["panos"] = self._generate_navigation_graph(panos)
            scan["floors"] = new_floors
            
        with open(self.project_json_path, "w", encoding="utf-8") as f:
            json.dump(proj_data, f, indent=2)
            
        return True, proj_data

    def process_structured_e57(self, e57_path, scan_date, import_mode="linked", description="", progress_cb=None):
        logger = setup_import_log(self.project_dir)
        logger.info(f"--- Structured E57 Ingestion ---")
        logger.info(f"e57_path: {e57_path}, import_mode: {import_mode}")
        
        try:
            if not os.path.exists(e57_path):
                raise FileNotFoundError(f"E57 file not found: {e57_path}")
            
            if progress_cb: progress_cb(5, "Resolving import modes...")
            source_import_path = self._handle_source_import(e57_path, scan_date, import_mode)
            actual_import_path = str(self.project_dir / source_import_path) if import_mode == "managed" else e57_path
            
            scan_dir = self.project_dir / "Scans" / scan_date
            panos_dir = scan_dir / "panos"
            panos_dir.mkdir(parents=True, exist_ok=True)
            
            panos = []
            z_values = []
            
            if progress_cb: progress_cb(10, "Opening E57 metadata...")
            e57 = pye57.E57(actual_import_path)
            
            # Find scans and images
            try:
                data3d_root = e57.root["data3D"]
                num_scans = data3d_root.childCount()
            except KeyError:
                raise ValueError("No scan data (data3D) found in E57.")
            
            try:
                image2D_node = e57.root["images2D"]
                total_images = image2D_node.childCount()
            except KeyError:
                image2D_node = None
                total_images = 0
            
            logger.info(f"Scans found: {num_scans}, Images found: {total_images}")
            
            # Check if we have images and what representation type they use
            is_cubemap = False
            if total_images > 0:
                first_img = image2D_node[0]
                if first_img.isDefined("pinholeRepresentation"):
                    is_cubemap = True
                    logger.info("Detected pinhole cubemap representation images (e.g. Matterport).")
                else:
                    logger.info("Detected standard representation images.")

            if is_cubemap:
                # Group images by associatedData3DGuid
                guid_to_images = {}
                for i in range(total_images):
                    im = image2D_node[i]
                    guid = im["associatedData3DGuid"].value()
                    if guid not in guid_to_images:
                        guid_to_images[guid] = []
                    guid_to_images[guid].append(im)
                
                # Traverse scans
                for i in range(num_scans):
                    if progress_cb:
                        progress_cb(10 + int(70 * i / num_scans), f"Stitching scan panorama {i+1} of {num_scans}...")
                    
                    scan_node = data3d_root[i]
                    scan_guid = scan_node["guid"].value()
                    
                    # Get pose translation and rotation
                    pose_node = scan_node["pose"]
                    translation = pose_node["translation"]
                    rotation = pose_node["rotation"]
                    
                    x, y, z = translation["x"].value(), translation["y"].value(), translation["z"].value()
                    qw, qx, qy, qz = rotation["w"].value(), rotation["x"].value(), rotation["y"].value(), rotation["z"].value()
                    z_values.append(z)
                    
                    # Match images
                    matching_images = guid_to_images.get(scan_guid, [])
                    if len(matching_images) == 6:
                        # Stitch
                        pano_bytes = self._stitch_cubemap_faces(matching_images)
                        pano_id = f"pano_{i:03d}"
                        image_filename = f"{pano_id}.jpg"
                        
                        with open(panos_dir / image_filename, "wb") as f:
                            f.write(pano_bytes)
                            
                        panos.append({
                            "id": pano_id,
                            "position": [x, y, z],
                            "rotation": [qx, qy, qz, qw],
                            "z_exact": z,
                            "image_path": f"panos/{image_filename}",
                            "neighbors": []
                        })
                    else:
                        logger.warning(f"Scan {i} GUID {scan_guid} does not have exactly 6 cubemap faces (found {len(matching_images)}). Skipping.")
            else:
                # Standard spherical panoramas
                # Sort images naturally by embedded name to preserve chronological walkthrough sequence
                import re
                def natural_sort_key(idx):
                    node = image2D_node[idx]
                    if node.isDefined("name"):
                        val = node["name"].value() if hasattr(node["name"], "value") else str(node["name"])
                        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', val)]
                    return [idx]
                
                ordered_indices = sorted(range(total_images), key=natural_sort_key)
                
                for seq_idx, i in enumerate(ordered_indices):
                    if progress_cb:
                        progress_cb(10 + int(70 * seq_idx / total_images), f"Extracting panorama {seq_idx+1} of {total_images}...")
                    
                    try:
                        img_node = image2D_node[i]
                        pose_node = img_node["pose"]
                        translation = pose_node["translation"]
                        rotation = pose_node["rotation"]
                        
                        x, y, z = translation["x"].value(), translation["y"].value(), translation["z"].value()
                        qw, qx, qy, qz = rotation["w"].value(), rotation["x"].value(), rotation["y"].value(), rotation["z"].value()
                        z_values.append(z)
                        
                        if img_node.isDefined("sphericalRepresentation"):
                            spherical_rep = img_node["sphericalRepresentation"]
                        elif img_node.isDefined("pinholeRepresentation"):
                            spherical_rep = img_node["pinholeRepresentation"]
                        else:
                            continue
                            
                        blob_node = None
                        for key in ["jpegImage", "pngImage", "imageBlob", "blob"]:
                            if spherical_rep.isDefined(key):
                                blob_node = spherical_rep[key]
                                break
                        if not blob_node:
                            continue
                            
                        image_bytes = blob_node.read_buffer().tobytes()
                        pano_id = f"pano_{seq_idx:03d}"
                        image_filename = f"{pano_id}.jpg"
                        
                        with open(panos_dir / image_filename, "wb") as f:
                            f.write(image_bytes)
                        
                        panos.append({
                            "id": pano_id,
                            "position": [x, y, z],
                            "rotation": [qx, qy, qz, qw],
                            "z_exact": z,
                            "image_path": f"panos/{image_filename}",
                            "neighbors": []
                        })
                    except Exception as node_err:
                        logger.warning(f"Image extract failed for node {i}: {node_err}")
                        continue
            
            # Floor clustering and graph linking
            floor_mapping, floors = self._get_z_floors(z_values)
            for p in panos:
                p['floor_id'] = floor_mapping[p.get('z_exact', 0)]
                del p['z_exact']
                
            panos = self._generate_navigation_graph(panos)
            
            # Point cloud extraction
            if progress_cb: progress_cb(80, "Extracting and downsampling 3D points...")
            pts, cols = extract_e57_pointcloud(actual_import_path, logger=logger)
            
            cache_rel = ""
            if len(pts) > 0:
                cache_dir = scan_dir / "cache"
                cache_dir.mkdir(exist_ok=True)
                cache_file = cache_dir / "lod0.bin"
                save_point_cloud_bin(cache_file, pts, cols)
                cache_rel = f"Scans/{scan_date}/cache/lod0.bin"
                logger.info(f"Saved cache of {len(pts)} points to {cache_rel}")
            
            # Validate scan contract
            validate_scan_contract(panos, [p["position"] for p in panos])

            # Write import report
            num_nav_edges = sum(len(p.get("neighbors", [])) for p in panos)
            report_data = {
                "scan_type": "Structured E57",
                "e57_scans_detected": num_scans,
                "panorama_images_found": total_images,
                "poses_extracted_e57": len(panos),
                "poses_extracted_csv": 0,
                "pose_source_selected": "E57 embedded metadata",
                "panos_written": len(panos),
                "navigation_edges_generated": num_nav_edges,
                "floors_generated": len(floors),
                "point_count_written": len(pts)
            }
            write_import_report(scan_dir, report_data)
            logger.info("CONTRACT: PASSED -> writing scan")

            # Write to unified project
            if progress_cb: progress_cb(95, "Finalizing project config...")
            self._write_scan_to_project(scan_date, description, panos, floors, import_mode, source_import_path, cache_rel)
            
            logger.info("Structured E57 Ingestion Successful!")
            return True
        except Exception as e:
            logger.error(f"Structured E57 Ingestion Failed: {e}")
            logger.error(traceback.format_exc())
            raise e

    def _stitch_cubemap_faces(self, images, out_w=2048, out_h=1024):
        from PIL import Image
        from scipy.spatial.transform import Rotation
        import io

        faces = []
        for im in images:
            name = im["name"].value() if hasattr(im["name"], "value") else str(im["name"])
            pose = im["pose"]
            translation = pose["translation"]
            rotation = pose["rotation"]
            
            # Get rotation matrix (pye57 order is w,x,y,z, scipy expects x,y,z,w)
            qx = rotation["x"].value()
            qy = rotation["y"].value()
            qz = rotation["z"].value()
            qw = rotation["w"].value()
            
            r = Rotation.from_quat([qx, qy, qz, qw])
            rot_matrix = r.as_matrix()
            
            # Load JPEG image
            jpeg_node = im["pinholeRepresentation"]["jpegImage"]
            arr = jpeg_node.read_buffer()
            img = Image.open(io.BytesIO(arr.tobytes())).convert("RGB")
            
            w = im["pinholeRepresentation"]["imageWidth"].value()
            h = im["pinholeRepresentation"]["imageHeight"].value()
            cx = im["pinholeRepresentation"]["principalPointX"].value()
            cy = im["pinholeRepresentation"]["principalPointY"].value()
            f = w / 2.0
            
            faces.append({
                "name": name,
                "img_array": np.array(img),
                "rot_matrix": rot_matrix,
                "width": w,
                "height": h,
                "cx": cx,
                "cy": cy,
                "f": f
            })
            
        pano = np.zeros((out_h, out_w, 3), dtype=np.uint8)
        ys, xs = np.mgrid[0:out_h, 0:out_w]
        
        phi = (0.5 - ys / out_h) * np.pi
        theta = (xs / out_w - 0.5) * 2.0 * np.pi
        
        vx = np.cos(phi) * np.cos(theta)
        vy = np.cos(phi) * np.sin(theta)
        vz = np.sin(phi)
        
        v_world = np.stack([vx, vy, vz], axis=-1)
        
        for face in faces:
            R_T = face["rot_matrix"].T
            v_local = np.tensordot(v_world, R_T, axes=(-1, 1))
            
            lx = v_local[..., 0]
            ly = v_local[..., 1]
            lz = v_local[..., 2]
            
            with np.errstate(divide='ignore', invalid='ignore'):
                u = face["cx"] + face["f"] * lx / lz
                v = face["cy"] - face["f"] * ly / lz
                
            mask = (lz > 0) & (u >= 0) & (u < face["width"]) & (v >= 0) & (v < face["height"])
            if np.any(mask):
                u_idx = u[mask].astype(np.int32)
                v_idx = v[mask].astype(np.int32)
                pano[mask] = face["img_array"][v_idx, u_idx]
                
        out_img = Image.fromarray(pano)
        img_byte_arr = io.BytesIO()
        out_img.save(img_byte_arr, format='JPEG', quality=85)
        return img_byte_arr.getvalue()

    def process_e57_plus_panos(self, e57_path, panos_src_dir, scan_date, import_mode="linked", description="E57+Panos Import", csv_pose_file=None, progress_cb=None):
        logger = setup_import_log(self.project_dir)
        logger.info(f"--- E57 + Panos Ingestion ---")
        
        try:
            if progress_cb: progress_cb(5, "Resolving import modes...")
            source_import_path = self._handle_source_import(e57_path, scan_date, import_mode)
            actual_import_path = str(self.project_dir / source_import_path) if import_mode == "managed" else e57_path
            
            scan_dir = self.project_dir / "Scans" / scan_date
            panos_dir = scan_dir / "panos"
            panos_dir.mkdir(parents=True, exist_ok=True)
            
            pano_files = sorted([f for f in os.listdir(panos_src_dir) if f.lower().endswith(('.jpg', '.jpeg'))])
            poses = []
            z_values = []
            
            # Count E57 scans
            e57_scans_count = 0
            try:
                e57 = pye57.E57(actual_import_path)
                e57_scans_count = e57.root["data3D"].childCount()
            except Exception:
                pass

            # Resolve CSV pose file (checking parameter first, then falling back to automatic search in panoramas folder)
            resolved_csv = csv_pose_file
            if not resolved_csv or not os.path.exists(resolved_csv):
                potential_csv = os.path.join(panos_src_dir, "pano-poses.csv")
                if os.path.exists(potential_csv):
                    resolved_csv = potential_csv
            if not resolved_csv or not os.path.exists(resolved_csv):
                potential_csv = os.path.join(panos_src_dir, "poses.csv")
                if os.path.exists(potential_csv):
                    resolved_csv = potential_csv

            selected_source = "E57 metadata"
            e57_poses_count = 0
            csv_poses_count = 0

            if resolved_csv and os.path.exists(resolved_csv):
                logger.info(f"Using CSV pose override file: {resolved_csv}")
                poses = _load_poses_from_csv(resolved_csv, logger=logger)
                csv_poses_count = len(poses)
                selected_source = "CSV file override"
                z_values = [cp["position"][2] for cp in poses]
            else:
                logger.info("Using E57 metadata scan poses as primary source.")
                e57 = pye57.E57(actual_import_path)
                try:
                    data3d_root = e57.root["data3D"]
                    for i in range(data3d_root.childCount()):
                        try:
                            scan_node = data3d_root[i]
                            try:
                                pose_node = scan_node["pose"]
                                translation = pose_node["translation"]
                                rotation = pose_node["rotation"]
                                x, y, z = translation["x"].value(), translation["y"].value(), translation["z"].value()
                                qw, qx, qy, qz = rotation["w"].value(), rotation["x"].value(), rotation["y"].value(), rotation["z"].value()
                                poses.append({"position": [x, y, z], "rotation": [qx, qy, qz, qw]})
                                z_values.append(z)
                            except (KeyError, ValueError, AttributeError):
                                pass
                        except Exception as node_err:
                            logger.warning(f"Failed scan pose {i}: {node_err}")
                            continue
                    e57_poses_count = len(poses)
                except KeyError:
                    logger.warning("No data3D node found in E57.")

            # Strict 1-to-1 Match Enforcement with minor tolerance trimming
            if len(poses) == 0:
                raise RuntimeError("INGESTION FAILED: No camera poses found (E57 metadata is empty, or CSV was empty/missing). Walkthrough cannot be generated.")
            
            if len(poses) != len(pano_files):
                diff = abs(len(poses) - len(pano_files))
                if diff <= 5:
                    min_len = min(len(poses), len(pano_files))
                    logger.warning(f"Minor pose/image count mismatch detected: extracted {len(poses)} poses, found {len(pano_files)} images. Automatically trimming to {min_len} to match.")
                    poses = poses[:min_len]
                    pano_files = pano_files[:min_len]
                    if len(z_values) > min_len:
                        z_values = z_values[:min_len]
                else:
                    raise RuntimeError(
                        f"INGESTION FAILED: Pose/image count mismatch. "
                        f"Extracted {len(poses)} poses, but found {len(pano_files)} panorama images. "
                        f"A strict 1-to-1 match is required to generate a walkthrough."
                    )

            panos = []
            for i in range(len(poses)):
                src_img = os.path.join(panos_src_dir, pano_files[i])
                pano_id = f"pano_{i:03d}"
                dest_img = panos_dir / f"{pano_id}.jpg"
                shutil.copy2(src_img, dest_img)
                
                panos.append({
                    "id": pano_id,
                    "position": poses[i]["position"],
                    "rotation": poses[i]["rotation"],
                    "z_exact": poses[i]["position"][2],
                    "image_path": f"panos/{pano_id}.jpg",
                    "neighbors": []
                })
                
            floor_mapping, floors = self._get_z_floors(z_values)
            for p in panos:
                p['floor_id'] = floor_mapping[p.get('z_exact', 0)]
                del p['z_exact']
                
            panos = self._generate_navigation_graph(panos)
            
            # Debug hook before write
            logger.info("=== CONTRACT CHECK ===")
            logger.info(f"Panos: {len(panos)}")
            logger.info(f"Poses: {len(poses)}")
            logger.info(f"Images: {len(pano_files)}")
            
            # Enforce validation contract
            validate_scan_contract(panos, poses, pano_files)
            logger.info("CONTRACT: PASSED")
            
            if progress_cb: progress_cb(80, "Extracting and downsampling E57 points...")
            pts, cols = extract_e57_pointcloud(actual_import_path, logger=logger)
            
            cache_rel = ""
            if len(pts) > 0:
                cache_dir = scan_dir / "cache"
                cache_dir.mkdir(exist_ok=True)
                cache_file = cache_dir / "lod0.bin"
                save_point_cloud_bin(cache_file, pts, cols)
                cache_rel = f"Scans/{scan_date}/cache/lod0.bin"
            
            # Write import report
            num_nav_edges = sum(len(p.get("neighbors", [])) for p in panos)
            report_data = {
                "scan_type": "E57 + Panos",
                "e57_scans_detected": e57_scans_count,
                "panorama_images_found": len(pano_files),
                "poses_extracted_e57": e57_poses_count,
                "poses_extracted_csv": csv_poses_count,
                "pose_source_selected": selected_source,
                "panos_written": len(panos),
                "navigation_edges_generated": num_nav_edges,
                "floors_generated": len(floors),
                "point_count_written": len(pts)
            }
            write_import_report(scan_dir, report_data)
            logger.info("CONTRACT: PASSED -> writing scan")
                
            self._write_scan_to_project(scan_date, description, panos, floors, import_mode, source_import_path, cache_rel)
            logger.info("E57+Panos Ingestion Successful!")
            return True
        except Exception as e:
            logger.error("CONTRACT: FAILED -> ingestion aborted")
            logger.error(f"E57+Panos Ingestion Failed: {e}")
            raise e

    def launch_av_structure(self, slam_path=None):
        import subprocess
        av_structure_path = slam_path if slam_path else r"C:\Program Files\AV_Structure\av_structure.exe"
        if os.path.exists(av_structure_path):
            subprocess.Popen([av_structure_path])
            return True, f"Launched AV Structure natively at {av_structure_path}"
        return False, f"AV Structure not found at {av_structure_path}"

    def launch_av_snap(self):
        import subprocess
        av_snap_path = r"C:\Program Files\AV_Snap\av_snap.exe"
        if os.path.exists(av_snap_path):
            subprocess.Popen([av_snap_path])
            return True, "Launched AV Snap"
        return False, "AV Snap not found at C:\\Program Files\\AV_Snap\\av_snap.exe"
