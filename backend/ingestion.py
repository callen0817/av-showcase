import os
import json
import shutil
import math
import uuid
from pathlib import Path
import traceback
import struct
import numpy as np
import logging

import walkthrough_synth as ws

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
    return ws.save_lod0(filepath, points, colors)

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
        f.write("         AV SHOWCASE IMPORT REPORT       \n")
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
            
        header_line = lines[0]
        delim = ';' if ';' in header_line else ','
        
        header_cols = [c.strip().lower() for c in header_line.replace('#', '').split(delim)]
        
        idx_x, idx_y, idx_z = 3, 4, 5
        idx_qw, idx_qx, idx_qy, idx_qz = 6, 7, 8, 9
        
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
                except Exception:
                    continue
    except Exception as e:
        if logger:
            logger.error(f"Error parsing CSV poses: {e}")
            
    return poses

def transform_points(points, translation, rotation):
    return ws.transform_pts(points, ws.make_transform(0, translation)) if len(rotation) == 4 and rotation == [0,0,0,1] else np.dot(points, ws.quat_to_matrix(rotation).T) + np.array(translation)

def extract_e57_pointcloud(e57_path, target_points_per_scan=10000, logger=None):
    """Extracts downsampled points and colors from E57, filtering invalid states and (0,0,0)."""
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
                pts_local, cols_local, _ = ws.read_e57_scan_local(e57, i)
                if len(pts_local) == 0:
                    continue
                
                scan_node = data3d_root[i]
                pos, rot = ws._e57_pose(scan_node)
                pts_world = pts_local @ ws.quat_to_matrix(rot).T + np.asarray(pos)
                
                cols = cols_local if cols_local is not None else np.full((len(pts_world), 3), 200, dtype=np.uint8)
                
                num_pts = len(pts_world)
                if num_pts > 0:
                    step = max(1, num_pts // target_points_per_scan)
                    all_points.append(pts_world[::step])
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
    pc = ws.load_ascii_points(xyz_path, max_points=target_points)
    cols = pc.cols if pc.cols is not None else np.full((len(pc.pts), 3), 200, dtype=np.uint8)
    return pc.pts, cols

def load_las_points(las_path, target_points=100000, logger=None):
    pc = ws.load_las(las_path, max_points=target_points)
    cols = pc.cols if pc.cols is not None else np.full((len(pc.pts), 3), 200, dtype=np.uint8)
    return pc.pts, cols


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
                    with open(old_path, 'r', encoding='utf-8') as f:
                        old_data = json.load(f)
                    old_data["schema_version"] = "1.1"
                    old_data["application_version"] = "2.0.0"
                    old_data.setdefault("project_id", str(uuid.uuid4()))
                    old_data.setdefault("bookmarks", [])
                    old_data.setdefault("settings", {"max_autostack_distance": 10.0, "default_unit": "metric"})
                    with open(self.project_json_path, 'w', encoding='utf-8') as f:
                        json.dump(old_data, f, indent=2)
                    os.remove(old_path)
                    logging.info("Migrated project.json to project.avproj v1.1")
                except Exception as e:
                    logging.error(f"Migration error: {e}")
            
            if not self.project_json_path.exists():
                with open(self.project_json_path, "w", encoding='utf-8') as f:
                    json.dump({
                        "schema_version": "1.1",
                        "application_version": "2.0.0",
                        "project_id": str(uuid.uuid4()),
                        "name": self.project_name,
                        "description": "",
                        "settings": {
                            "max_autostack_distance": 10.0,
                            "default_unit": "metric"
                        },
                        "bookmarks": [],
                        "scans": []
                    }, f, indent=2)

    def _resolve_scan_ids(self, scan_date, scan_label=None):
        """Generates a stable, unique scan_id to avoid collisions between same-day datasets."""
        base_id = (scan_label.strip() if scan_label else scan_date).replace(" ", "_")
        scan_id = base_id
        with open(self.project_json_path, "r", encoding="utf-8") as f:
            proj = json.load(f)
        existing_ids = {s.get("scan_id", s.get("scan_date")) for s in proj.get("scans", [])}
        suffix = 1
        while scan_id in existing_ids:
            scan_id = f"{base_id}_{suffix}"
            suffix += 1
        scan_dir_rel = f"Scans/{scan_id}"
        scan_dir = self.project_dir / scan_dir_rel
        scan_dir.mkdir(parents=True, exist_ok=True)
        return scan_id, scan_dir_rel, scan_dir

    def _handle_source_import(self, source_path, scan_id, import_mode):
        if not source_path or not os.path.exists(source_path):
            return ""
        
        scan_dir = self.project_dir / "Scans" / scan_id
        scan_dir.mkdir(parents=True, exist_ok=True)
        
        if import_mode == "managed":
            ext = source_path.lower().split('.')[-1]
            dest_name = f"raw_source.{ext}"
            dest_path = scan_dir / dest_name
            logging.info(f"Managed Mode: Copying {source_path} to {dest_path}")
            shutil.copy2(source_path, dest_path)
            return f"Scans/{scan_id}/{dest_name}"
        else:
            logging.info(f"Linked Mode: Storing link reference to {source_path}")
            return str(Path(source_path).resolve())

    def _write_scan_to_project(self, scan_date, description, panos, floors, import_mode, source_path, cache_rel_path,
                               scan_id=None, scan_dir_rel=None, transform_to_project=None, nav_graph="sector8_v1", extra_meta=None):
        if len(panos) == 0:
            raise RuntimeError("CONTRACT VIOLATION: Refusing to write empty scan to project config.")
            
        source_hash = ""
        source_modified = 0.0
        if source_path and os.path.exists(source_path):
            source_hash = calculate_file_hash(source_path)
            source_modified = os.path.getmtime(source_path)
        
        with open(self.project_json_path, "r", encoding="utf-8") as f:
            proj_data = json.load(f)
            
        proj_data.setdefault("schema_version", "1.1")
        proj_data.setdefault("project_id", str(uuid.uuid4()))
        if "baseline_scan_id" not in proj_data and proj_data.get("scans"):
            proj_data["baseline_scan_id"] = proj_data["scans"][0].get("scan_id", proj_data["scans"][0].get("scan_date"))

        final_scan_id = scan_id or scan_date
        final_scan_dir = scan_dir_rel or f"Scans/{final_scan_id}"
        
        existing_scans = [s for s in proj_data['scans'] if s.get('scan_id', s.get('scan_date')) != final_scan_id]
        
        new_scan = {
            "scan_id": final_scan_id,
            "scan_date": scan_date,
            "scan_dir": final_scan_dir,
            "description": description,
            "import_mode": import_mode,
            "source_path": source_path or "",
            "source_hash": source_hash,
            "source_modified": source_modified,
            "point_cloud_cache": cache_rel_path,
            "transform_to_project": transform_to_project if (transform_to_project and len(transform_to_project) == 16) else [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1],
            "nav_graph": nav_graph,
            "floors": floors,
            "panos": panos
        }
        if extra_meta:
            new_scan.update(extra_meta)
            
        proj_data['scans'] = existing_scans + [new_scan]
        proj_data['scans'].sort(key=lambda x: x.get('scan_date', ''), reverse=True)
        if "baseline_scan_id" not in proj_data or not proj_data["baseline_scan_id"]:
            proj_data["baseline_scan_id"] = final_scan_id
        
        with open(self.project_json_path, "w", encoding="utf-8") as f:
            json.dump(proj_data, f, indent=2)

        # Write matching av_walkthrough_bundle.json inside the scan directory
        scan_dir_abs = self.project_dir / final_scan_dir
        ws.write_bundle_manifest(scan_dir_abs, new_scan, project_id=proj_data.get("project_id"), producer="AV Showcase")

    def _get_z_floors(self, z_values):
        if not z_values:
            return {}, []
            
        custom_names = []
        if self.floor_heights:
            raw_tokens = [h.strip() for h in str(self.floor_heights).split(",") if h.strip()]
            heights = []
            try:
                parsed = [float(t) for t in raw_tokens]
                if len(parsed) >= 2 or (len(parsed) == 1 and "." in raw_tokens[0]):
                    heights = parsed
                else:
                    custom_names = raw_tokens
            except Exception:
                custom_names = raw_tokens
                logger.info(f"Interpreting floor_heights '{self.floor_heights}' as custom floor labels ({custom_names}); using multi-level clustering.")
                
            if heights:
                sorted_heights = sorted(heights)
                floor_mapping = {}
                assigned_scans = {i+1: [] for i in range(len(sorted_heights))}
                
                for z in z_values:
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
                        "min_z": float(min_z),
                        "max_z": float(max_z),
                        "mean_z": float(h),
                        "floor_elevation": float(h - ws.EYE_HEIGHT)
                    })
                return floor_mapping, floors

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
                    "mean_z": float(c),
                    "floor_elevation": float(c - ws.EYE_HEIGHT)
                }
                final_floors.append(fl_entry)
                
            return final_floor_mapping, final_floors

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
        
        if len(floors) <= 1:
            fl_obj = {
                "id": 1,
                "name": custom_names[0] if len(custom_names) == 1 else "Level 1",
                "min_z": float(sorted_z[0]),
                "max_z": float(sorted_z[-1]),
                "mean_z": float(np.mean(sorted_z)),
                "floor_elevation": float(np.mean(sorted_z) - ws.EYE_HEIGHT)
            }
            return floor_mapping, [fl_obj]

        for f in floors:
            f["scans"] = [z for z in z_values if f["min_z"] <= z <= f["max_z"]]
            f["count"] = len(f["scans"])
            f["mean_z"] = float(np.mean(f["scans"])) if len(f["scans"]) > 0 else (f["min_z"] + f["max_z"]) / 2.0
            
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
                "name": custom_names[idx] if idx < len(custom_names) else f"Level {fid}",
                "min_z": float(min(mf["scans"])),
                "max_z": float(max(mf["scans"])),
                "mean_z": float(mf["plateau_mean_z"]),
                "floor_elevation": float(mf["plateau_mean_z"] - ws.EYE_HEIGHT)
            }
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
            
        for floor_id, floor_panos in floors_dict.items():
            n = len(floor_panos)
            if n < 2:
                p_single = floor_panos[0]
                if 'neighbors' not in p_single or p_single['neighbors'] is None:
                    p_single['neighbors'] = []
                continue
                
            pts = np.array([p['position'] for p in floor_panos])
            diff = pts[:, None, :2] - pts[None, :, :2]
            dists = np.linalg.norm(diff, axis=-1)
            angles = np.arctan2(diff[..., 1], diff[..., 0])
            
            for i, p in enumerate(floor_panos):
                nbr_set = set()
                
                for offset in [-1, 1]:
                    adj = i + offset
                    if 0 <= adj < n and dists[i, adj] <= NEIGHBOR_DISTANCE_THRESHOLD:
                        nbr_set.add(floor_panos[adj]['id'])
                        
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
                        far_enough = s_dists >= 0.5
                        if np.any(far_enough):
                            best_idx = s_indices[far_enough][np.argmin(s_dists[far_enough])]
                        else:
                            best_idx = s_indices[np.argmin(s_dists)]
                        nbr_set.add(floor_panos[best_idx]['id'])
                        
                sorted_by_dist = np.argsort(dists[i])
                for idx in sorted_by_dist[1:]:
                    if len(nbr_set) >= 8:
                        break
                    if dists[i, idx] <= 2.0:
                        nbr_set.add(floor_panos[idx]['id'])
                    else:
                        break
                        
                p['neighbors'] = list(nbr_set)

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
                            if 0.10 <= dz <= 2.20 and dxy <= 5.50:
                                d3d = math.sqrt(dxy * dxy + dz * dz)
                                stair_links.append((d3d, pa, pb))
                                
                    stair_links.sort(key=lambda x: x[0])
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
                            pa['stair_link'] = True
                            pb['stair_link'] = True

        pano_map = {p['id']: p for p in panos}
        for p in panos:
            for nid in list(p.get('neighbors', [])):
                np_target = pano_map.get(nid)
                if np_target and p['id'] not in np_target.get('neighbors', []):
                    np_target['neighbors'].append(p['id'])
                
        return panos

    def recluster_project(self):
        """Re-computes floors and navigation graph for all scans in project.avproj, skipping synthesized ones."""
        if not self.project_json_path.exists():
            return False, "project.avproj not found"
            
        with open(self.project_json_path, "r", encoding="utf-8") as f:
            proj_data = json.load(f)
            
        for scan in proj_data.get("scans", []):
            if scan.get("nav_graph") == "los_v1":
                continue  # synthesized scan with ground-truth LOS graph; preserve it
            panos = scan.get("panos", [])
            if not panos:
                continue
            z_values = [p["position"][2] for p in panos]
            floor_mapping, new_floors = self._get_z_floors(z_values)
            
            old_floors_by_id = {fl["id"]: fl for fl in scan.get("floors", [])}
            for nf in new_floors:
                old_fl = old_floors_by_id.get(nf["id"])
                if old_fl:
                    for key in ["fpOffset", "fpScale", "floorplan_path", "keyplan_path", "world_bounds", "floor_elevation", "name"]:
                        if key in old_fl and key not in nf:
                            nf[key] = old_fl[key]
                            
            for p in panos:
                z = p["position"][2]
                p["floor_id"] = floor_mapping.get(z, 1)
                
            scan["panos"] = self._generate_navigation_graph(panos)
            scan["floors"] = new_floors
            
        with open(self.project_json_path, "w", encoding="utf-8") as f:
            json.dump(proj_data, f, indent=2)
            
        return True, proj_data

    def _maybe_auto_align(self, pts, scan_dir, auto_align=False, progress_cb=None):
        """Registers a new scan to the project's baseline scan using 4-DOF ICP if requested."""
        if not auto_align:
            return ws.make_transform(), None
        try:
            with open(self.project_json_path, "r", encoding="utf-8") as f:
                proj = json.load(f)
            scans = proj.get("scans", [])
            if not scans:
                return ws.make_transform(), None
            baseline_id = proj.get("baseline_scan_id") or scans[0].get("scan_id", scans[0].get("scan_date"))
            base_scan = next((s for s in scans if s.get("scan_id", s.get("scan_date")) == baseline_id), scans[0])
            cache_rel = base_scan.get("point_cloud_cache")
            if not cache_rel:
                return ws.make_transform(), None
            base_cache_path = self.project_dir / cache_rel
            if not base_cache_path.exists():
                return ws.make_transform(), None
            if progress_cb: progress_cb(18, f"Aligning to baseline scan '{baseline_id}' (4-DOF ICP)...")
            base_pts, _ = ws.load_lod0(base_cache_path)
            T, info = ws.register_4dof(pts, base_pts, log=logger)
            return T, info
        except Exception as e:
            logger.warning(f"Auto-alignment to baseline failed: {e}; proceeding without transform.")
            return ws.make_transform(), None

    def process_point_cloud(self, cloud_path, scan_date, scan_label=None, import_mode="linked",
                            description="Universal Point Cloud Walkthrough", auto_align=False,
                            station_spacing=ws.DEFAULT_SPACING, up_axis="z", pano_width=2048,
                            progress_cb=None):
        """Universal point cloud pipeline (.ply, .pcd, .las, .laz, .xyz, .obj, unstructured .e57)."""
        logger = setup_import_log(self.project_dir)
        logger.info(f"--- Universal Point Cloud Ingestion: {cloud_path} ---")
        progress_cb = progress_cb or ws._noop_progress
        
        try:
            if not os.path.exists(cloud_path):
                raise FileNotFoundError(f"File not found: {cloud_path}")
            
            scan_id, scan_dir_rel, scan_dir = self._resolve_scan_ids(scan_date, scan_label)
            source_import_path = self._handle_source_import(cloud_path, scan_id, import_mode)
            
            progress_cb(10, f"Loading point cloud ({Path(cloud_path).suffix})...")
            pc = ws.load_point_cloud(cloud_path, max_points=8_000_000, up_axis=up_axis)
            logger.info(f"Loaded {len(pc)} points from {cloud_path}")

            T, align_info = self._maybe_auto_align(pc.pts, scan_dir, auto_align=auto_align, progress_cb=progress_cb)
            if not np.allclose(T, np.eye(4)):
                pc.pts = ws.transform_pts(pc.pts, T)
                logger.info(f"Applied baseline alignment: yaw={align_info.get('yaw_deg'):.2f} deg, t={align_info.get('translation')}")

            floor_labels = [h.strip() for h in str(self.floor_heights).split(",") if h.strip()] if self.floor_heights else None

            synth = ws.synthesize_walkthrough(
                pc, scan_dir, spacing=station_spacing, pano_width=pano_width,
                progress_cb=progress_cb, log=logger, floor_names=floor_labels
            )
            panos = synth["panos"]
            floors = synth["floors"]
            lod0_rel = f"{scan_dir_rel}/{synth['lod0_rel']}"

            validate_scan_contract(panos, [p["position"] for p in panos])
            num_edges = sum(len(p.get("neighbors", [])) for p in panos)
            report = {
                "scan_type": "Universal Point Cloud",
                "source_file": os.path.basename(cloud_path),
                "stations_synthesized": len(panos),
                "floors_generated": len(floors),
                "navigation_edges_generated": num_edges,
                "point_count_written": synth["report"]["lod0_points"],
                "alignment": align_info or "identity",
            }
            write_import_report(str(scan_dir), report)

            extra_meta = {
                "transform_to_project": ws.matrix_to_list(T),
                "nav_graph": "los_v1",
                "up_axis": up_axis,
                "synth_report": synth["report"]
            }
            progress_cb(96, "Saving project configuration...")
            self._write_scan_to_project(
                scan_date, description, panos, floors, import_mode, source_import_path, lod0_rel,
                scan_id=scan_id, scan_dir_rel=scan_dir_rel, transform_to_project=ws.matrix_to_list(T),
                nav_graph="los_v1", extra_meta=extra_meta
            )
            logger.info("Universal Point Cloud Ingestion Successful!")
            return True
        except Exception as e:
            logger.error(f"Universal Point Cloud Ingestion Failed: {e}\n{traceback.format_exc()}")
            raise

    def process_matterpak(self, pak_path, scan_date, scan_label=None, import_mode="linked",
                          description="Matterport MatterPak Import", auto_align=False,
                          station_spacing=ws.DEFAULT_SPACING, pano_width=2048, progress_cb=None):
        """Matterport MatterPak folder or .zip (.xyz/.ply/.obj + floorplans)."""
        logger = setup_import_log(self.project_dir)
        logger.info(f"--- Matterport MatterPak Ingestion: {pak_path} ---")
        progress_cb = progress_cb or ws._noop_progress
        try:
            scan_id, scan_dir_rel, scan_dir = self._resolve_scan_ids(scan_date, scan_label)
            progress_cb(8, "Resolving MatterPak contents...")
            cloud_file, floorplans, manifest = ws.resolve_matterpak(pak_path, str(scan_dir))
            logger.info(f"MatterPak resolved: cloud={cloud_file}, {len(floorplans)} floorplans")
            
            # Use point cloud pipeline on the resolved cloud
            ok = self.process_point_cloud(
                cloud_file, scan_date, scan_label=scan_id, import_mode="linked",
                description=description, auto_align=auto_align,
                station_spacing=station_spacing, up_axis="z", pano_width=pano_width,
                progress_cb=progress_cb
            )
            return ok
        except Exception as e:
            logger.error(f"MatterPak Ingestion Failed: {e}\n{traceback.format_exc()}")
            raise

    def import_spatial_bundle(self, bundle_path, scan_date=None, scan_label=None, import_mode="managed",
                              description="AV Spatial Bundle Import", progress_cb=None):
        """Imports an AV Spatial Bundle v1.1 in <1s (copies panos, floor keyplans, and cache/lod0.bin)."""
        logger = setup_import_log(self.project_dir)
        logger.info(f"--- AV Spatial Bundle Import: {bundle_path} ---")
        progress_cb = progress_cb or ws._noop_progress
        try:
            progress_cb(10, "Reading bundle manifest...")
            bpath, bdata = ws.read_bundle_manifest(bundle_path)
            
            eff_date = scan_date or bdata.get("scan_date") or "2026-01-01"
            eff_label = scan_label or bdata.get("scan_id") or Path(bundle_path).stem
            scan_id, scan_dir_rel, scan_dir = self._resolve_scan_ids(eff_date, eff_label)
            
            progress_cb(30, "Importing bundle assets...")
            imported = ws.import_bundle_into(bpath, scan_dir)
            panos = imported["panos"]
            floors = imported["floors"]
            lod0_rel = f"{scan_dir_rel}/{imported['lod0_rel']}" if imported["lod0_rel"] else ""
            
            validate_scan_contract(panos, [p["position"] for p in panos])
            
            progress_cb(80, "Writing project manifest...")
            self._write_scan_to_project(
                eff_date, description, panos, floors, import_mode, str(bpath), lod0_rel,
                scan_id=scan_id, scan_dir_rel=scan_dir_rel,
                transform_to_project=imported.get("transform_to_project"),
                nav_graph=imported.get("nav_graph", "bundle"),
                extra_meta={"imported_from_bundle": True, "producer": imported.get("producer")}
            )
            logger.info("Spatial Bundle Import Successful!")
            return True
        except Exception as e:
            logger.error(f"Spatial Bundle Import Failed: {e}\n{traceback.format_exc()}")
            raise

    def process_structured_e57(self, e57_path, scan_date, scan_label=None, import_mode="linked",
                               description="", auto_align=False, progress_cb=None):
        logger = setup_import_log(self.project_dir)
        logger.info(f"--- Structured E57 Ingestion ---")
        logger.info(f"e57_path: {e57_path}, import_mode: {import_mode}")
        
        try:
            if not os.path.exists(e57_path):
                raise FileNotFoundError(f"E57 file not found: {e57_path}")
            
            scan_id, scan_dir_rel, scan_dir = self._resolve_scan_ids(scan_date, scan_label)
            if progress_cb: progress_cb(5, "Resolving import modes...")
            source_import_path = self._handle_source_import(e57_path, scan_id, import_mode)
            actual_import_path = str(self.project_dir / source_import_path) if import_mode == "managed" else e57_path
            
            panos_dir = scan_dir / "panos"
            panos_dir.mkdir(parents=True, exist_ok=True)
            
            panos = []
            z_values = []
            
            if progress_cb: progress_cb(10, "Opening E57 metadata...")
            e57 = pye57.E57(actual_import_path)
            
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

            # Fallback: if E57 has ZERO images2D, synthesize panoramas directly from the point cloud
            if total_images == 0:
                logger.info("Structured E57 has 0 images2D -> falling back to universal point cloud synthesis at scan poses.")
                pc = ws.load_e57(actual_import_path, max_points=6_000_000)
                poses = pc.scan_poses if (pc.scan_poses and len(pc.scan_poses) > 1) else None
                synth = ws.synthesize_walkthrough(
                    pc, scan_dir, fixed_stations=poses, progress_cb=progress_cb, log=logger
                )
                panos = synth["panos"]
                floors = synth["floors"]
                lod0_rel = f"{scan_dir_rel}/{synth['lod0_rel']}"
                self._write_scan_to_project(
                    scan_date, description or "E57 Synthesized Walkthrough", panos, floors,
                    import_mode, source_import_path, lod0_rel,
                    scan_id=scan_id, scan_dir_rel=scan_dir_rel, nav_graph="los_v1"
                )
                logger.info("Structured E57 zero-image synthesis successful!")
                return True
            
            is_cubemap = False
            first_img = image2D_node[0]
            if first_img.isDefined("pinholeRepresentation"):
                is_cubemap = True
                logger.info("Detected pinhole cubemap representation images (e.g. Matterport).")
            else:
                logger.info("Detected standard representation images.")

            if is_cubemap:
                guid_to_images = {}
                for i in range(total_images):
                    im = image2D_node[i]
                    guid = im["associatedData3DGuid"].value()
                    if guid not in guid_to_images:
                        guid_to_images[guid] = []
                    guid_to_images[guid].append(im)
                
                for i in range(num_scans):
                    if progress_cb:
                        progress_cb(10 + int(70 * i / num_scans), f"Stitching scan panorama {i+1} of {num_scans}...")
                    
                    scan_node = data3d_root[i]
                    scan_guid = scan_node["guid"].value()
                    
                    pose_node = scan_node["pose"]
                    translation = pose_node["translation"]
                    rotation = pose_node["rotation"]
                    
                    x, y, z = translation["x"].value(), translation["y"].value(), translation["z"].value()
                    z_values.append(z)
                    
                    matching_images = guid_to_images.get(scan_guid, [])
                    if len(matching_images) == 6:
                        pano_bytes = self._stitch_cubemap_faces(matching_images)
                        pano_id = f"pano_{i:03d}"
                        image_filename = f"{pano_id}.jpg"
                        
                        with open(panos_dir / image_filename, "wb") as f:
                            f.write(pano_bytes)
                            
                        # Matterport cubemap stitching bakes orientation into the equirectangular pixels.
                        # Rotation is therefore identity in world space to avoid double-rotation bug.
                        panos.append({
                            "id": pano_id,
                            "position": [x, y, z],
                            "rotation": [0.0, 0.0, 0.0, 1.0],
                            "z_exact": z,
                            "image_path": f"panos/{image_filename}",
                            "neighbors": []
                        })
                    else:
                        logger.warning(f"Scan {i} GUID {scan_guid} does not have exactly 6 cubemap faces (found {len(matching_images)}). Skipping.")
            else:
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
            
            floor_mapping, floors = self._get_z_floors(z_values)
            for p in panos:
                p['floor_id'] = floor_mapping[p.get('z_exact', 0)]
                del p['z_exact']
                
            panos = self._generate_navigation_graph(panos)
            
            if progress_cb: progress_cb(80, "Extracting and downsampling 3D points...")
            pts, cols = extract_e57_pointcloud(actual_import_path, logger=logger)
            
            cache_rel = ""
            if len(pts) > 0:
                cache_dir = scan_dir / "cache"
                cache_dir.mkdir(exist_ok=True)
                cache_file = cache_dir / "lod0.bin"
                save_point_cloud_bin(cache_file, pts, cols)
                cache_rel = f"{scan_dir_rel}/cache/lod0.bin"
                logger.info(f"Saved cache of {len(pts)} points to {cache_rel}")
                # Auto-generate calibrated top-down 2D keyplans for each floor
                ws.slabs_for_station_floors(pts, floors, panos)
                ws.generate_keyplans(pts, floors, scan_dir)
            
            validate_scan_contract(panos, [p["position"] for p in panos])

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
            write_import_report(str(scan_dir), report_data)
            logger.info("CONTRACT: PASSED -> writing scan")

            if progress_cb: progress_cb(95, "Finalizing project config...")
            self._write_scan_to_project(
                scan_date, description, panos, floors, import_mode, source_import_path, cache_rel,
                scan_id=scan_id, scan_dir_rel=scan_dir_rel
            )
            
            logger.info("Structured E57 Ingestion Successful!")
            return True
        except Exception as e:
            logger.error(f"Structured E57 Ingestion Failed: {e}")
            logger.error(traceback.format_exc())
            raise e

    def _stitch_cubemap_faces(self, images, out_w=2048, out_h=1024):
        from PIL import Image
        import io

        faces = []
        for im in images:
            name = im["name"].value() if hasattr(im["name"], "value") else str(im["name"])
            pose = im["pose"]
            rotation = pose["rotation"]
            
            qx = rotation["x"].value()
            qy = rotation["y"].value()
            qz = rotation["z"].value()
            qw = rotation["w"].value()
            
            rot_matrix = ws.quat_to_matrix([qx, qy, qz, qw])
            
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
        # ASTM E2807 Section 6.5.4 clockwise sweep: az = pi - 2pi*(xs/out_w)
        # -> theta = (0.5 - xs/out_w) * 2pi (fixes 180-deg reversal in original code)
        theta = (0.5 - xs / out_w) * 2.0 * np.pi
        
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
        out_img.save(img_byte_arr, format='JPEG', quality=88)
        return img_byte_arr.getvalue()

    def process_e57_plus_panos(self, e57_path, panos_src_dir, scan_date, scan_label=None, import_mode="linked",
                               description="E57+Panos Import", csv_pose_file=None, auto_align=False, progress_cb=None):
        logger = setup_import_log(self.project_dir)
        logger.info(f"--- E57 + Panos Ingestion ---")
        
        try:
            scan_id, scan_dir_rel, scan_dir = self._resolve_scan_ids(scan_date, scan_label)
            if progress_cb: progress_cb(5, "Resolving import modes...")
            source_import_path = self._handle_source_import(e57_path, scan_id, import_mode)
            actual_import_path = str(self.project_dir / source_import_path) if import_mode == "managed" else e57_path
            
            panos_dir = scan_dir / "panos"
            panos_dir.mkdir(parents=True, exist_ok=True)
            
            pano_files = sorted([f for f in os.listdir(panos_src_dir) if f.lower().endswith(('.jpg', '.jpeg'))])
            poses = []
            z_values = []
            
            e57_scans_count = 0
            try:
                e57 = pye57.E57(actual_import_path)
                e57_scans_count = e57.root["data3D"].childCount()
            except Exception:
                pass

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
                            pos, rot = ws._e57_pose(scan_node)
                            poses.append({"position": pos, "rotation": rot})
                            z_values.append(pos[2])
                        except Exception as node_err:
                            logger.warning(f"Failed scan pose {i}: {node_err}")
                            continue
                    e57_poses_count = len(poses)
                except KeyError:
                    logger.warning("No data3D node found in E57.")

            if len(poses) == 0:
                raise RuntimeError("INGESTION FAILED: No camera poses found (E57 metadata is empty, or CSV was empty/missing). Walkthrough cannot be generated.")
            
            if len(poses) != len(pano_files):
                diff = abs(len(poses) - len(pano_files))
                if diff <= 5:
                    min_len = min(len(poses), len(pano_files))
                    logger.warning(f"Minor pose/image count mismatch detected: extracted {len(poses)} poses, found {len(pano_files)} images. Trimming to {min_len}.")
                    poses = poses[:min_len]
                    pano_files = pano_files[:min_len]
                    if len(z_values) > min_len:
                        z_values = z_values[:min_len]
                else:
                    raise RuntimeError(
                        f"INGESTION FAILED: Pose/image count mismatch. "
                        f"Extracted {len(poses)} poses, but found {len(pano_files)} panorama images."
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
            
            validate_scan_contract(panos, poses, pano_files)
            
            if progress_cb: progress_cb(80, "Extracting and downsampling E57 points...")
            pts, cols = extract_e57_pointcloud(actual_import_path, logger=logger)
            
            cache_rel = ""
            if len(pts) > 0:
                cache_dir = scan_dir / "cache"
                cache_dir.mkdir(exist_ok=True)
                cache_file = cache_dir / "lod0.bin"
                save_point_cloud_bin(cache_file, pts, cols)
                cache_rel = f"{scan_dir_rel}/cache/lod0.bin"
                ws.slabs_for_station_floors(pts, floors, panos)
                ws.generate_keyplans(pts, floors, scan_dir)
            
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
            write_import_report(str(scan_dir), report_data)
            logger.info("CONTRACT: PASSED -> writing scan")
                
            self._write_scan_to_project(
                scan_date, description, panos, floors, import_mode, source_import_path, cache_rel,
                scan_id=scan_id, scan_dir_rel=scan_dir_rel
            )
            logger.info("E57+Panos Ingestion Successful!")
            return True
        except Exception as e:
            logger.error(f"E57+Panos Ingestion Failed: {e}")
            raise e

    def set_scan_transform(self, scan_id, new_transform):
        """Applies a manual or external 4x4 transform to an existing scan's stations, lod0 and keyplans."""
        if not self.project_json_path.exists():
            return False, "project.avproj not found"
        with open(self.project_json_path, "r", encoding="utf-8") as f:
            proj = json.load(f)
        target = next((s for s in proj.get("scans", []) if s.get("scan_id", s.get("scan_date")) == scan_id), None)
        if not target:
            return False, f"Scan '{scan_id}' not found"
        T_new = np.asarray(new_transform, dtype=np.float64).reshape(4, 4)
        T_old = np.asarray(target.get("transform_to_project", np.eye(4)), dtype=np.float64).reshape(4, 4)
        delta_T = T_new @ np.linalg.inv(T_old)

        panos, floors = ws.apply_transform_to_scan(target.get("panos", []), target.get("floors", []), delta_T)
        target["panos"] = panos
        target["floors"] = floors
        target["transform_to_project"] = ws.matrix_to_list(T_new)

        scan_dir_rel = target.get("scan_dir") or f"Scans/{scan_id}"
        scan_dir = self.project_dir / scan_dir_rel
        cache_rel = target.get("point_cloud_cache")
        if cache_rel and (self.project_dir / cache_rel).exists():
            pts, cols = ws.load_lod0(self.project_dir / cache_rel)
            pts_new = ws.transform_pts(pts, delta_T)
            ws.save_lod0(self.project_dir / cache_rel, pts_new, cols)
            ws.generate_keyplans(pts_new, floors, scan_dir)

        with open(self.project_json_path, "w", encoding="utf-8") as f:
            json.dump(proj, f, indent=2)
        ws.write_bundle_manifest(scan_dir, target, project_id=proj.get("project_id"), producer="AV Showcase")
        return True, target

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
