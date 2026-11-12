"""
AV Showcase — Universal Point Cloud -> Walkthrough Synthesizer
==============================================================

Implements the AV Spatial Bundle v1.1 contract shared by AV Showcase, AV Structure,
AV Scan and AV ScanAR (see docs/INTEROP_AV_SPATIAL_BUNDLE.md).

Canonical frame (all functions in this module):
    right-handed, metric, gravity-levelled  +X = East, +Y = North, +Z = Up.

Equirectangular panoramas follow ASTM E2807-11 §6.5.4 in station-local coordinates:
    azimuth   az = atan2(y, x)            (0 = +X, +90° = +Y, counter-clockwise from above)
    elevation el = atan2(z, hypot(x, y))
    col = ((pi - az) / 2pi) * W           (u = 0.5 -> +X, u = 0.25 -> +Y)
    row = ((pi/2 - el) / pi) * H

Only numpy + Pillow are hard requirements. pye57 (E57) and laspy (+lazrs for LAZ)
are optional; an uncompressed LAS 1.0–1.4 reader is built in.
"""

import io
import json
import math
import os
import re
import shutil
import struct
import zipfile
import logging
from pathlib import Path

import numpy as np

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow is a hard requirement of the backend
    Image = None

logger = logging.getLogger("import")

BUNDLE_SCHEMA_VERSION = "1.1"
BUNDLE_FILENAME = "av_walkthrough_bundle.json"
EYE_HEIGHT = 1.60
DEFAULT_SPACING = 2.5
WALL_CLEARANCE = 0.45
KEYPLAN_SLICE = (0.35, 2.10)
KEYPLAN_MPP = 0.02
KEYPLAN_MAX_PX = 2048
KEYPLAN_COLORS = {"bg": (0x17, 0x17, 0x17), "floor": (0x22, 0x26, 0x2E), "wall": (0xE5, 0xE7, 0xEB)}
LOD0_TARGET = 450_000

POINT_CLOUD_EXTS = (".ply", ".pcd", ".las", ".laz", ".xyz", ".txt", ".pts", ".csv", ".obj", ".e57")
IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def _noop_progress(*_a, **_k):
    pass


# =====================================================================================
# 1. Loaders
# =====================================================================================

class PointCloud:
    """Simple container. pts: float32 (N,3) canonical Z-up meters. cols: uint8 (N,3) or None."""

    def __init__(self, pts, cols=None, intensity=None, scan_poses=None, source=""):
        self.pts = np.ascontiguousarray(pts, dtype=np.float32).reshape(-1, 3)
        self.cols = None if cols is None else np.ascontiguousarray(cols, dtype=np.uint8).reshape(-1, 3)
        self.intensity = None if intensity is None else np.asarray(intensity, dtype=np.float32).reshape(-1)
        self.scan_poses = scan_poses or []  # [{"position": [x,y,z], "rotation": [qx,qy,qz,qw]}]
        self.source = source

    def __len__(self):
        return len(self.pts)

    @property
    def has_rgb(self):
        return self.cols is not None

    def subset(self, mask):
        return PointCloud(
            self.pts[mask],
            None if self.cols is None else self.cols[mask],
            None if self.intensity is None else self.intensity[mask],
            self.scan_poses,
            self.source,
        )


def _to_u8(arr):
    arr = np.asarray(arr, dtype=np.float64)
    if arr.size == 0:
        return arr.astype(np.uint8)
    mx = float(np.nanmax(arr))
    if mx <= 1.0 + 1e-6:
        arr = arr * 255.0
    elif mx > 255.0:
        arr = arr / (65535.0 if mx > 4095 else mx) * 255.0
    return np.clip(arr, 0, 255).astype(np.uint8)


def _finalize(pts, cols, inten, max_points, source, scan_poses=None):
    pts = np.asarray(pts, dtype=np.float64)
    finite = np.all(np.isfinite(pts), axis=1)
    if not np.all(finite):
        pts = pts[finite]
        cols = None if cols is None else cols[finite]
        inten = None if inten is None else inten[finite]
    if max_points and len(pts) > max_points:
        rng = np.random.default_rng(7)
        sel = np.sort(rng.choice(len(pts), max_points, replace=False))
        pts = pts[sel]
        cols = None if cols is None else cols[sel]
        inten = None if inten is None else inten[sel]
    return PointCloud(pts, cols, inten, scan_poses, source)


# ---------------------------------- PLY --------------------------------------------

_PLY_TYPES = {
    "char": "i1", "int8": "i1", "uchar": "u1", "uint8": "u1",
    "short": "i2", "int16": "i2", "ushort": "u2", "uint16": "u2",
    "int": "i4", "int32": "i4", "uint": "u4", "uint32": "u4",
    "float": "f4", "float32": "f4", "double": "f8", "float64": "f8",
}


def load_ply(path, max_points=None):
    with open(path, "rb") as f:
        if f.readline().strip() != b"ply":
            raise ValueError("Not a PLY file")
        fmt = None
        elements = []  # (name, count, [(prop, type) | ('list', ...)])
        while True:
            line = f.readline()
            if not line:
                raise ValueError("Unexpected EOF in PLY header")
            tok = line.decode("ascii", "ignore").strip().split()
            if not tok:
                continue
            if tok[0] == "format":
                fmt = tok[1]
            elif tok[0] == "element":
                elements.append([tok[1], int(tok[2]), []])
            elif tok[0] == "property" and elements:
                if tok[1] == "list":
                    elements[-1][2].append(("__list__", tok[2], tok[3], tok[4]))
                else:
                    elements[-1][2].append((tok[2], tok[1]))
            elif tok[0] == "end_header":
                break
        header_end = f.tell()

    vidx = next((i for i, e in enumerate(elements) if e[0] == "vertex"), None)
    if vidx is None:
        raise ValueError("PLY has no vertex element")
    if vidx != 0:
        raise ValueError("PLY files whose first element is not 'vertex' are not supported")
    name, count, props = elements[vidx]
    if any(p[0] == "__list__" for p in props):
        raise ValueError("PLY vertex element with list properties is not supported")

    names = [p[0] for p in props]
    if fmt == "ascii":
        with open(path, "rb") as f:
            f.seek(header_end)
            data = np.loadtxt(f, max_rows=count, ndmin=2)
        col = {n: data[:, i] for i, n in enumerate(names)}
    elif fmt in ("binary_little_endian", "binary_big_endian"):
        end = "<" if fmt == "binary_little_endian" else ">"
        dt = np.dtype([(n, end + _PLY_TYPES[t]) for n, t in props])
        arr = np.fromfile(path, dtype=dt, count=count, offset=header_end)
        col = {n: arr[n] for n in names}
    else:
        raise ValueError(f"Unsupported PLY format: {fmt}")

    pts = np.column_stack([col["x"], col["y"], col["z"]])
    cols = None
    for rn, gn, bn in (("red", "green", "blue"), ("r", "g", "b"), ("diffuse_red", "diffuse_green", "diffuse_blue")):
        if rn in col and gn in col and bn in col:
            cols = np.column_stack([_to_u8(col[rn]), _to_u8(col[gn]), _to_u8(col[bn])])
            break
    inten = None
    for iname in ("intensity", "scalar_intensity", "reflectance", "scalar_Intensity"):
        if iname in col:
            inten = np.asarray(col[iname], dtype=np.float32)
            break
    return _finalize(pts, cols, inten, max_points, "ply")


# ---------------------------------- PCD --------------------------------------------

def load_pcd(path, max_points=None):
    header = {}
    with open(path, "rb") as f:
        while True:
            line = f.readline()
            if not line:
                raise ValueError("Unexpected EOF in PCD header")
            s = line.decode("ascii", "ignore").strip()
            if not s or s.startswith("#"):
                continue
            key, _, val = s.partition(" ")
            header[key.upper()] = val.split()
            if key.upper() == "DATA":
                break
        data_start = f.tell()

    fields = header["FIELDS"]
    sizes = [int(s) for s in header.get("SIZE", ["4"] * len(fields))]
    types = header.get("TYPE", ["F"] * len(fields))
    counts = [int(c) for c in header.get("COUNT", ["1"] * len(fields))]
    n = int(header.get("POINTS", header.get("WIDTH", ["0"]))[0])
    mode = header["DATA"][0].lower()

    if mode == "ascii":
        with open(path, "rb") as f:
            f.seek(data_start)
            data = np.loadtxt(f, max_rows=n, ndmin=2)
        cols_map, k = {}, 0
        for fld, c in zip(fields, counts):
            cols_map[fld] = data[:, k]
            k += c
        rgb_raw = cols_map.get("rgb", cols_map.get("rgba"))
        if rgb_raw is not None:
            rgb_raw = rgb_raw.astype(np.float32).view(np.uint32)
    elif mode == "binary":
        dt = []
        for fld, sz, ty, c in zip(fields, sizes, types, counts):
            code = {"F": "f", "I": "i", "U": "u"}[ty.upper()] + str(sz)
            dt.append((fld if fld != "_" else f"_pad{len(dt)}", "<" + code, (c,)) if c > 1 else (fld if fld != "_" else f"_pad{len(dt)}", "<" + code))
        arr = np.fromfile(path, dtype=np.dtype(dt), count=n, offset=data_start)
        cols_map = {name: arr[name] for name in arr.dtype.names}
        rgb_raw = None
        for nm in ("rgb", "rgba"):
            if nm in cols_map:
                rgb_raw = np.ascontiguousarray(cols_map[nm]).view(np.uint32)
    else:
        raise ValueError("binary_compressed PCD is not supported — re-save as binary or ascii")

    pts = np.column_stack([cols_map["x"], cols_map["y"], cols_map["z"]])
    cols = None
    if rgb_raw is not None:
        rgb_raw = rgb_raw.astype(np.uint32)
        cols = np.column_stack([(rgb_raw >> 16) & 255, (rgb_raw >> 8) & 255, rgb_raw & 255]).astype(np.uint8)
    inten = cols_map.get("intensity")
    return _finalize(pts, cols, inten, max_points, "pcd")


# ---------------------------------- ASCII XYZ / PTS / TXT / CSV / OBJ ---------------

_SPLIT_RE = re.compile(r"[,;\t ]+")


def load_ascii_points(path, max_points=None, obj_mode=False):
    """Chunked ASCII reader for x y z [i] [r g b] style files (and OBJ 'v' lines)."""
    size = os.path.getsize(path)
    est_lines = max(1, size // 40)
    stride = max(1, int(est_lines // max_points)) if max_points else 1

    ncols = None
    blocks = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        buf = []
        line_no = 0
        for line in f:
            if obj_mode:
                if not line.startswith("v "):
                    continue
                line = line[2:]
            s = line.strip()
            if not s or s[0] in "#/" or s[0].isalpha():
                continue
            line_no += 1
            if (line_no - 1) % stride:
                continue
            buf.append(s)
            if len(buf) >= 400_000:
                ncols = _flush_ascii(buf, blocks, ncols)
                buf = []
        if buf:
            ncols = _flush_ascii(buf, blocks, ncols)
    if not blocks:
        raise ValueError("No numeric point rows found")
    data = np.vstack(blocks)
    nc = data.shape[1]
    pts = data[:, :3]
    cols, inten = None, None
    if nc >= 7 and nc != 9:
        # PTS / Leica: x y z intensity r g b
        inten, cols = data[:, 3], np.column_stack([_to_u8(data[:, 4]), _to_u8(data[:, 5]), _to_u8(data[:, 6])])
    elif nc >= 6:
        cols = np.column_stack([_to_u8(data[:, 3]), _to_u8(data[:, 4]), _to_u8(data[:, 5])])
    elif nc >= 4:
        inten = data[:, 3]
    # PTS files sometimes start with a single "count" row -> 1 column, filtered by width check.
    return _finalize(pts, cols, inten, max_points, "obj" if obj_mode else "xyz")


def _flush_ascii(buf, blocks, ncols):
    if ncols is None:
        widths = [len(_SPLIT_RE.split(b)) for b in buf[:50]]
        ncols = max(set(widths), key=widths.count)
        if ncols < 3:
            ncols = None
            return ncols
    joined = " ".join(_SPLIT_RE.sub(" ", b) for b in buf)
    flat = np.array(joined.split(), dtype=np.float64) if joined else np.zeros(0)
    if flat.size % ncols == 0:
        blocks.append(flat.reshape(-1, ncols))
    else:  # ragged rows -> slow but safe path
        rows = []
        for b in buf:
            parts = _SPLIT_RE.split(b)
            if len(parts) >= ncols:
                try:
                    rows.append([float(x) for x in parts[:ncols]])
                except ValueError:
                    continue
        if rows:
            blocks.append(np.array(rows, dtype=np.float64))
    return ncols


# ---------------------------------- LAS / LAZ --------------------------------------

_LAS_RGB_OFFSET = {2: 20, 3: 28, 5: 28, 7: 30, 8: 30, 10: 30}


def load_las(path, max_points=None):
    try:
        import laspy  # optional, required for LAZ
        las = laspy.read(path)
        pts = np.column_stack([np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)])
        cols = None
        if all(hasattr(las, c) for c in ("red", "green", "blue")):
            cols = np.column_stack([_to_u8(las.red), _to_u8(las.green), _to_u8(las.blue)])
        inten = np.asarray(las.intensity, dtype=np.float32) if hasattr(las, "intensity") else None
        return _finalize(pts, cols, inten, max_points, "las")
    except ImportError:
        if str(path).lower().endswith(".laz"):
            raise RuntimeError("LAZ requires the optional packages 'laspy' and 'lazrs' (pip install laspy lazrs)")
    with open(path, "rb") as f:
        hdr = f.read(375)
    if hdr[:4] != b"LASF":
        raise ValueError("Not a LAS file")
    vmin = hdr[25]
    offset_to_points = struct.unpack_from("<I", hdr, 96)[0]
    fmt = hdr[104] & 0x3F
    rec_len = struct.unpack_from("<H", hdr, 105)[0]
    n = struct.unpack_from("<I", hdr, 107)[0]
    if vmin >= 4 and len(hdr) >= 255:
        n64 = struct.unpack_from("<Q", hdr, 247)[0]
        if n64:
            n = n64
    sx, sy, sz = struct.unpack_from("<3d", hdr, 131)
    ox, oy, oz = struct.unpack_from("<3d", hdr, 155)
    raw = np.fromfile(path, dtype=np.uint8, count=n * rec_len, offset=offset_to_points).reshape(-1, rec_len)
    xyz = raw[:, :12].copy().view("<i4").reshape(-1, 3).astype(np.float64)
    pts = np.column_stack([xyz[:, 0] * sx + ox, xyz[:, 1] * sy + oy, xyz[:, 2] * sz + oz])
    inten = raw[:, 12:14].copy().view("<u2").reshape(-1).astype(np.float32)
    cols = None
    if fmt in _LAS_RGB_OFFSET:
        o = _LAS_RGB_OFFSET[fmt]
        rgb = raw[:, o:o + 6].copy().view("<u2").reshape(-1, 3)
        cols = np.column_stack([_to_u8(rgb[:, 0]), _to_u8(rgb[:, 1]), _to_u8(rgb[:, 2])])
    return _finalize(pts, cols, inten, max_points, "las")


# ---------------------------------- E57 --------------------------------------------

def quat_to_matrix(q):
    qx, qy, qz, qw = [float(v) for v in q]
    n = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw) or 1.0
    qx, qy, qz, qw = qx / n, qy / n, qz / n, qw / n
    return np.array([
        [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
        [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
        [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)],
    ])


def _e57_pose(node):
    try:
        pose = node["pose"]
    except Exception:
        return [0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]
    try:
        t = pose["translation"]
        pos = [t["x"].value(), t["y"].value(), t["z"].value()]
    except Exception:
        pos = [0.0, 0.0, 0.0]
    try:
        r = pose["rotation"]
        rot = [r["x"].value(), r["y"].value(), r["z"].value(), r["w"].value()]
    except Exception:
        rot = [0.0, 0.0, 0.0, 1.0]
    return pos, rot


def read_e57_scan_local(e57, index):
    """Reads one data3D scan in its *sensor-local* frame with invalid points removed.

    Uses read_scan_raw (all fields, never auto-transformed) so the pose is applied exactly
    once by the caller. Filters cartesianInvalidState != 0 and exact (0,0,0) placeholders
    written by gridded scanners (FARO, Leica, AV ScanAR).
    """
    try:
        data = e57.read_scan_raw(index)
    except Exception:
        try:
            data = e57.read_scan(index, colors=True, intensity=True, ignore_missing_fields=True, transform=False)
        except TypeError:
            data = e57.read_scan(index, colors=True, intensity=True, ignore_missing_fields=True)
    if "cartesianX" in data:
        x = np.asarray(data["cartesianX"], dtype=np.float64)
        y = np.asarray(data["cartesianY"], dtype=np.float64)
        z = np.asarray(data["cartesianZ"], dtype=np.float64)
        valid = np.ones(len(x), dtype=bool)
        if "cartesianInvalidState" in data:
            valid &= np.asarray(data["cartesianInvalidState"]) == 0
    elif "sphericalRange" in data:
        rr = np.asarray(data["sphericalRange"], dtype=np.float64)
        az = np.asarray(data["sphericalAzimuth"], dtype=np.float64)
        el = np.asarray(data["sphericalElevation"], dtype=np.float64)
        x, y, z = rr * np.cos(el) * np.cos(az), rr * np.cos(el) * np.sin(az), rr * np.sin(el)
        valid = np.ones(len(x), dtype=bool)
        if "sphericalInvalidState" in data:
            valid &= np.asarray(data["sphericalInvalidState"]) == 0
    else:
        return np.zeros((0, 3)), None, None
    valid &= ~((np.abs(x) < 1e-9) & (np.abs(y) < 1e-9) & (np.abs(z) < 1e-9))
    pts = np.column_stack([x, y, z])[valid]
    cols = None
    if all(k in data for k in ("colorRed", "colorGreen", "colorBlue")):
        cols = np.column_stack([
            _to_u8(np.asarray(data["colorRed"])[valid]),
            _to_u8(np.asarray(data["colorGreen"])[valid]),
            _to_u8(np.asarray(data["colorBlue"])[valid]),
        ])
    inten = np.asarray(data["intensity"], dtype=np.float32)[valid] if "intensity" in data else None
    return pts, cols, inten


def load_e57(path, max_points=None):
    try:
        import pye57
    except ImportError:
        raise RuntimeError("E57 support requires the optional package 'pye57' (pip install pye57)")
    e57 = pye57.E57(str(path))
    try:
        root = e57.root["data3D"]
        n_scans = root.childCount()
    except Exception:
        raise ValueError("E57 has no data3D section")
    per_scan_budget = int(max_points / max(1, n_scans)) if max_points else None
    all_p, all_c, all_i, poses = [], [], [], []
    any_rgb = True
    for i in range(n_scans):
        pos, rot = _e57_pose(root[i])
        poses.append({"position": pos, "rotation": rot})
        p, c, it = read_e57_scan_local(e57, i)
        if len(p) == 0:
            continue
        if per_scan_budget and len(p) > per_scan_budget:
            sel = np.random.default_rng(i).choice(len(p), per_scan_budget, replace=False)
            p = p[sel]
            c = None if c is None else c[sel]
            it = None if it is None else it[sel]
        p = p @ quat_to_matrix(rot).T + np.asarray(pos)
        all_p.append(p)
        all_c.append(c)
        all_i.append(it)
        any_rgb &= c is not None
    if not all_p:
        raise ValueError("E57 contains no valid points")
    pts = np.vstack(all_p)
    cols = np.vstack(all_c) if any_rgb else None
    inten = np.concatenate(all_i) if all(i is not None for i in all_i) else None
    return _finalize(pts, cols, inten, None, "e57", scan_poses=poses)


# ---------------------------------- dispatcher -------------------------------------

def apply_up_axis(pc, up_axis):
    """Converts a cloud to canonical Z-up. 'y' handles Y-up exports (OBJ/glTF style)."""
    if up_axis == "auto":
        up_axis = guess_up_axis(pc.pts)
    if up_axis in ("y", "+y"):
        x, y, z = pc.pts[:, 0].copy(), pc.pts[:, 1].copy(), pc.pts[:, 2].copy()
        pc.pts = np.column_stack([x, -z, y]).astype(np.float32)
    return pc


def guess_up_axis(pts):
    """Picks the axis whose 5 cm histogram is most dominated by large horizontal planes."""
    scores = {}
    sample = pts[:: max(1, len(pts) // 400_000)]
    for name, ax in (("z", 2), ("y", 1)):
        v = sample[:, ax]
        lo, hi = np.percentile(v, [0.5, 99.5])
        if hi - lo < 0.5:
            scores[name] = 0
            continue
        h, _ = np.histogram(v, bins=max(10, int((hi - lo) / 0.05)), range=(lo, hi))
        top2 = np.sort(h)[-2:].sum()
        scores[name] = top2 / max(1, h.sum())
    return "y" if scores.get("y", 0) > scores.get("z", 0) * 1.35 else "z"


def load_point_cloud(path, max_points=8_000_000, up_axis="z"):
    ext = Path(path).suffix.lower()
    if ext == ".ply":
        pc = load_ply(path, max_points)
    elif ext == ".pcd":
        pc = load_pcd(path, max_points)
    elif ext in (".las", ".laz"):
        pc = load_las(path, max_points)
    elif ext in (".xyz", ".txt", ".pts", ".csv"):
        pc = load_ascii_points(path, max_points)
    elif ext == ".obj":
        pc = load_ascii_points(path, max_points, obj_mode=True)
        if up_axis == "z":
            up_axis = "auto"
    elif ext == ".e57":
        pc = load_e57(path, max_points)
    else:
        raise ValueError(f"Unsupported point cloud format: {ext}")
    if len(pc) == 0:
        raise ValueError("Point cloud is empty after filtering invalid points")
    return apply_up_axis(pc, up_axis)


# =====================================================================================
# 2. Geometry helpers
# =====================================================================================

def voxel_downsample(pc, voxel):
    """Keeps the first point per voxel (fast, colour-preserving)."""
    if voxel <= 0 or len(pc) == 0:
        return pc
    q = np.floor((pc.pts - pc.pts.min(axis=0)) / voxel).astype(np.int64)
    key = (q[:, 0] * 73856093) ^ (q[:, 1] * 19349663) ^ (q[:, 2] * 83492791)
    _, idx = np.unique(key, return_index=True)
    return pc.subset(np.sort(idx))


def _dilate(mask, steps=1):
    m = mask.copy()
    for _ in range(steps):
        n = m.copy()
        n[1:, :] |= m[:-1, :]
        n[:-1, :] |= m[1:, :]
        n[:, 1:] |= m[:, :-1]
        n[:, :-1] |= m[:, 1:]
        m = n
    return m


def _erode(mask, steps=1):
    return ~_dilate(~mask, steps)


def detect_floor_slabs(pts, min_floor_spacing=2.0, bin_size=0.05, cell=0.25):
    """Detects walkable floor slab elevations (meters, ascending).

    Horizontal planes are found as prominent peaks of XY-occupied area per Z bin. A plane is
    a *floor* (not a ceiling/roof) when the space just above it is mostly free while there is
    structure (walls / ceiling) further above it.
    """
    if len(pts) < 100:
        return [float(np.min(pts[:, 2])) if len(pts) else 0.0]
    sample = pts[:: max(1, len(pts) // 2_000_000)]
    z = sample[:, 2].astype(np.float64)
    zlo, zhi = np.percentile(z, [0.2, 99.8])
    if zhi - zlo < 1.0:
        return [float(zlo)]
    xy0 = sample[:, :2].min(axis=0)
    cxy = np.floor((sample[:, :2] - xy0) / cell).astype(np.int64)
    ncx = int(cxy[:, 0].max()) + 1
    cell_id = cxy[:, 1] * ncx + cxy[:, 0]
    zb = np.floor((z - zlo) / bin_size).astype(np.int64)
    nb = int((zhi - zlo) / bin_size) + 1
    keep = (zb >= 0) & (zb < nb)
    zb_k, cid_k = zb[keep], cell_id[keep]
    uniq = np.unique(zb_k * (cell_id.max() + 1) + cid_k)
    area = np.bincount(uniq // (cell_id.max() + 1), minlength=nb).astype(np.float64) * cell * cell
    sm = np.convolve(area, np.ones(3) / 3.0, mode="same")
    win = max(3, int(0.5 / bin_size))
    base = np.array([np.median(sm[max(0, i - win): i + win + 1]) for i in range(nb)])
    prom = sm - base
    thr = max(2.0, 0.06 * float(sm.max()))
    cands = []
    for i in range(nb):
        lo, hi = max(0, i - 3), min(nb, i + 4)
        if prom[i] >= thr and sm[i] == sm[lo:hi].max():
            cands.append(i)

    def plane_metrics(i):
        h = zlo + (i + 0.5) * bin_size
        in_plane = np.abs(z - h) <= 0.06
        plane_cells = np.unique(cell_id[in_plane])
        if len(plane_cells) == 0:
            return h, 0.0, 1.0, 0.0
        near_above = (z > h + 0.25) & (z < h + 1.5)
        far_above = (z >= h + 1.5) & (z < h + 4.5)
        occ_near = np.isin(plane_cells, np.unique(cell_id[near_above])).mean()
        occ_far = np.isin(plane_cells, np.unique(cell_id[far_above])).mean()
        return h, len(plane_cells) * cell * cell, float(occ_near), float(occ_far)

    planes = [plane_metrics(i) for i in cands]
    max_area = max([p[1] for p in planes], default=0.0)
    floors = [p for p in planes
              if p[1] >= max(3.0, 0.10 * max_area) and p[2] < 0.55 and p[3] >= 0.20]
    floors.sort(key=lambda p: p[0])
    # Within 1.2 m clusters (ceiling + floor-above pairs) keep the plane with the freest space above.
    clustered = []
    for p in floors:
        if clustered and p[0] - clustered[-1][0] < 1.2:
            if p[2] < clustered[-1][2]:
                clustered[-1] = p
        else:
            clustered.append(p)
    slabs = []
    for p in clustered:
        if not slabs or p[0] - slabs[-1] >= min_floor_spacing:
            slabs.append(float(p[0]))
    if not slabs:
        slabs = [float(np.percentile(z, 2.0))]
    return slabs


def floor_band_masks(z, slabs):
    """Assigns each point to a floor index: [slab_i - 0.3, slab_{i+1} - 0.3)."""
    edges = [-np.inf] + [s - 0.3 for s in slabs[1:]] + [np.inf]
    return [(z >= edges[i]) & (z < edges[i + 1]) for i in range(len(slabs))]


class FloorGrid:
    """2D occupancy rasters for one floor (cell size `res`)."""

    def __init__(self, pts_floor, slab, res=0.15, bounds=None):
        self.res = res
        self.slab = slab
        xy = pts_floor[:, :2]
        if bounds is None:
            mn, mx = xy.min(axis=0) - 1.0, xy.max(axis=0) + 1.0
        else:
            mn, mx = np.array(bounds[0]), np.array(bounds[1])
        self.origin = mn
        self.nx = int(np.ceil((mx[0] - mn[0]) / res)) + 1
        self.ny = int(np.ceil((mx[1] - mn[1]) / res)) + 1
        z = pts_floor[:, 2]
        ij = np.floor((xy - mn) / res).astype(np.int64)
        ok = (ij[:, 0] >= 0) & (ij[:, 0] < self.nx) & (ij[:, 1] >= 0) & (ij[:, 1] < self.ny)
        self._ij, self._z = ij[ok], z[ok]

    def raster(self, zmin, zmax, min_count=1):
        sel = (self._z >= zmin) & (self._z < zmax)
        ij = self._ij[sel]
        cnt = np.bincount(ij[:, 1] * self.nx + ij[:, 0], minlength=self.nx * self.ny)
        return (cnt >= min_count).reshape(self.ny, self.nx)

    def to_world(self, i, j):
        return self.origin[0] + (i + 0.5) * self.res, self.origin[1] + (j + 0.5) * self.res

    def to_cell(self, x, y):
        return int((x - self.origin[0]) / self.res), int((y - self.origin[1]) / self.res)


def place_virtual_stations(pts_floor, slab, spacing=DEFAULT_SPACING, clearance=WALL_CLEARANCE,
                           max_stations=400, res=0.15):
    """Places walkable virtual stations on one floor (returns list of (x, y))."""
    g = FloorGrid(pts_floor, slab, res)
    floor = g.raster(slab - 0.12, slab + 0.12)
    floor = _erode(_dilate(floor, 2), 2)  # close sensor gaps
    obst = g.raster(slab + 0.35, slab + 1.90)
    area = float(floor.sum()) * res * res
    if area <= 0:
        return []
    spacing = max(spacing, math.sqrt(area / max_stations))
    k = max(1, int(math.ceil(clearance / res)))
    blocked = _dilate(obst, k) | _dilate(~floor, 1)
    walk = floor & ~blocked
    if not walk.any():
        walk = floor & ~_dilate(obst, 1)
    if not walk.any():
        return []
    # Clearance rank: number of extra erosions survived (prefers room centres).
    rank = np.zeros(walk.shape, dtype=np.int16)
    cur = walk.copy()
    for step in range(1, 12):
        cur = _erode(cur, 1)
        if not cur.any():
            break
        rank[cur] = step
    jj, ii = np.nonzero(walk)
    sub = ((ii + jj) % 2 == 0) if len(ii) > 200_000 else np.ones(len(ii), bool)
    ii, jj = ii[sub], jj[sub]
    order = np.lexsort((ii, jj, -rank[jj, ii]))
    cellsz = spacing
    taken = {}
    out = []
    for o in order:
        x, y = g.to_world(ii[o], jj[o])
        cx, cy = int(x // cellsz), int(y // cellsz)
        ok = True
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for (px, py) in taken.get((cx + dx, cy + dy), ()):
                    if (px - x) ** 2 + (py - y) ** 2 < spacing * spacing:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            taken.setdefault((cx, cy), []).append((x, y))
            out.append((x, y))
    return _nn_chain(out)


def _nn_chain(points):
    if len(points) <= 2:
        return points
    P = np.array(points)
    start = int(np.argmin(P[:, 0] + P[:, 1]))
    order, left = [start], set(range(len(P))) - {start}
    while left:
        last = P[order[-1]]
        cand = np.array(sorted(left))
        nxt = cand[np.argmin(np.sum((P[cand] - last) ** 2, axis=1))]
        order.append(int(nxt))
        left.remove(int(nxt))
    return [tuple(P[i]) for i in order]


# =====================================================================================
# 3. ASTM E2807 equirectangular projection & synthetic panoramas
# =====================================================================================

def astm_project(dirs, width, height):
    """Station-local direction vectors (N,3) -> (col, row) float pixel coordinates."""
    az = np.arctan2(dirs[:, 1], dirs[:, 0])
    el = np.arctan2(dirs[:, 2], np.hypot(dirs[:, 0], dirs[:, 1]))
    col = (((np.pi - az) / (2 * np.pi)) % 1.0) * width
    row = ((np.pi / 2 - el) / np.pi) * height
    return col, row


def astm_unproject(col, row, width, height):
    """Inverse of astm_project at pixel centres -> unit direction vectors."""
    az = np.pi - (np.asarray(col, dtype=np.float64) / width) * 2 * np.pi
    el = np.pi / 2 - (np.asarray(row, dtype=np.float64) / height) * np.pi
    return np.stack([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)], axis=-1)


def render_equirect(pts, cols, center, width=2048, voxel=0.02, max_range=45.0, max_level=5,
                    shade=None, fill_passes=6):
    """Depth-buffered multi-scale splat renderer.

    Every point is splatted as a 2^L pixel block where L grows as the point gets closer
    (projected point spacing > 1 px), which closes gaps in near surfaces and prevents
    far geometry from leaking through them. Unobserved pixels stay #000000.
    Returns (rgb uint8 HxWx3, valid_ratio).
    """
    W = int(width) // 64 * 64
    H = W // 2
    d = pts.astype(np.float32) - np.asarray(center, dtype=np.float32)
    dist = np.sqrt(np.einsum("ij,ij->i", d, d))
    m = (dist > 0.05) & (dist < max_range)
    d, dist = d[m], dist[m]
    c = cols[m] if cols is not None else None
    if shade is not None:
        c = shade(d, dist)
    if len(d) == 0:
        return np.zeros((H, W, 3), np.uint8), 0.0
    colf, rowf = astm_project(d, W, H)
    col = np.minimum(colf.astype(np.int64), W - 1)
    row = np.clip(rowf.astype(np.int64), 0, H - 1)
    pix = 2 * np.pi / W
    coslat = np.sqrt(np.maximum(1e-4, 1.0 - (d[:, 2] / dist) ** 2))
    splat = (1.6 * voxel / dist) / pix / np.sqrt(np.maximum(coslat, 0.25))
    level = np.clip(np.floor(np.log2(np.maximum(splat, 1.0))), 0, max_level).astype(np.int64)

    depth = np.full((H, W), np.inf, dtype=np.float32)
    rgb = np.zeros((H, W, 3), dtype=np.uint8)
    for L in range(max_level + 1):
        sel = np.nonzero(level == L)[0]
        if len(sel) == 0:
            continue
        Wl, Hl = W >> L, H >> L
        idx = (row[sel] >> L) * Wl + (col[sel] >> L)
        order = np.lexsort((dist[sel], idx))
        idx_s = idx[order]
        first = np.ones(len(idx_s), dtype=bool)
        first[1:] = idx_s[1:] != idx_s[:-1]
        pick = sel[order[first]]
        pidx = idx_s[first]
        dbuf = np.full(Hl * Wl, np.inf, dtype=np.float32)
        cbuf = np.zeros((Hl * Wl, 3), dtype=np.uint8)
        dbuf[pidx] = dist[pick]
        cbuf[pidx] = c[pick]
        s = 1 << L
        dup = np.repeat(np.repeat(dbuf.reshape(Hl, Wl), s, axis=0), s, axis=1)
        cup = np.repeat(np.repeat(cbuf.reshape(Hl, Wl, 3), s, axis=0), s, axis=1)
        better = dup < depth
        depth[better] = dup[better]
        rgb[better] = cup[better]

    valid = np.isfinite(depth)
    acc = rgb.astype(np.float32)
    for _ in range(fill_passes):  # small hole fill (horizontal wrap-around)
        if valid.all():
            break
        tot = np.zeros_like(acc)
        cnt = np.zeros(valid.shape, dtype=np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            vs = np.roll(np.roll(valid, dy, 0), dx, 1)
            if dy == 1:
                vs[0, :] = False
            elif dy == -1:
                vs[-1, :] = False
            cs = np.roll(np.roll(acc, dy, 0), dx, 1)
            tot += cs * vs[..., None]
            cnt += vs
        fill = (~valid) & (cnt >= 2)
        acc[fill] = tot[fill] / cnt[fill][:, None]
        valid = valid | fill
    out = np.where(valid[..., None], acc, 0).astype(np.uint8)
    return out, float(valid.mean())


def make_shader(pc_has_rgb, intensity_norm=None, eye=EYE_HEIGHT):
    """Shading for clouds without RGB: intensity if present, else ambient height/depth shading."""
    def shade(d, dist):
        rel = np.clip((d[:, 2] + eye) / 2.8, 0, 1)
        fog = 0.55 + 0.45 * np.exp(-dist / 18.0)
        g = (95 + 125 * rel) * fog
        g = np.clip(g, 0, 255).astype(np.uint8)
        return np.column_stack([g, g, np.clip(g.astype(np.int16) + 6, 0, 255).astype(np.uint8)])
    return None if pc_has_rgb else shade


def intensity_to_rgb(inten):
    lo, hi = np.percentile(inten, [2, 98])
    g = np.clip((inten - lo) / max(1e-6, hi - lo), 0, 1)
    g = (40 + 205 * g).astype(np.uint8)
    return np.column_stack([g, g, g])


# =====================================================================================
# 4. Keyplans (calibrated top-down wall slices)
# =====================================================================================

def render_keyplan(pts, slab, out_path, mpp=KEYPLAN_MPP, max_px=KEYPLAN_MAX_PX, margin=0.5):
    """Renders a North-up (+X right, +Y up) wall-slice plan; returns world_bounds dict or None."""
    z = pts[:, 2]
    walls = pts[(z >= slab + KEYPLAN_SLICE[0]) & (z <= slab + KEYPLAN_SLICE[1])]
    floor = pts[(z >= slab - 0.10) & (z <= slab + 0.15)]
    ref = np.vstack([walls[:, :2], floor[:, :2]]) if len(walls) + len(floor) else None
    if ref is None or len(ref) < 50:
        return None
    lo = np.percentile(ref, 0.1, axis=0) - margin
    hi = np.percentile(ref, 99.9, axis=0) + margin
    ext = float(max(hi[0] - lo[0], hi[1] - lo[1]))
    mpp = max(mpp, ext / max_px)
    w = int(math.ceil((hi[0] - lo[0]) / mpp))
    h = int(math.ceil((hi[1] - lo[1]) / mpp))
    min_x, max_y = float(lo[0]), float(hi[1])
    max_x, min_y = min_x + w * mpp, max_y - h * mpp

    def rast(p):
        col = np.floor((p[:, 0] - min_x) / mpp).astype(np.int64)
        row = np.floor((max_y - p[:, 1]) / mpp).astype(np.int64)
        ok = (col >= 0) & (col < w) & (row >= 0) & (row < h)
        m = np.zeros((h, w), dtype=bool)
        m[row[ok], col[ok]] = True
        return m

    fm = _erode(_dilate(rast(floor), 3), 1) if len(floor) else np.zeros((h, w), bool)
    wm = _dilate(rast(walls), 1) if len(walls) else np.zeros((h, w), bool)
    img = np.empty((h, w, 3), dtype=np.uint8)
    img[:] = KEYPLAN_COLORS["bg"]
    img[fm] = KEYPLAN_COLORS["floor"]
    img[wm] = KEYPLAN_COLORS["wall"]
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img).save(out_path, optimize=True)
    return {"min_x": min_x, "max_x": float(max_x), "min_y": float(min_y), "max_y": max_y,
            "meters_per_pixel": float(mpp), "width_px": w, "height_px": h}


def generate_keyplans(pts, floors, scan_dir, rel_prefix="floors"):
    """Adds keyplan_path + world_bounds to each floor dict (needs floor['floor_elevation'])."""
    slabs = [f["floor_elevation"] for f in floors]
    masks = floor_band_masks(pts[:, 2], slabs)
    for f, m in zip(floors, masks):
        rel = f"{rel_prefix}/floor_{f['id']}_keyplan.png"
        wb = render_keyplan(pts[m], f["floor_elevation"], Path(scan_dir) / rel)
        if wb:
            f["keyplan_path"] = rel
            f["world_bounds"] = wb
    return floors


def slabs_for_station_floors(pts, floors, panos, eye=EYE_HEIGHT):
    """For capture-based scans: matches each station floor to a detected slab below its stations."""
    detected = detect_floor_slabs(pts) if len(pts) else []
    for f in floors:
        zs = [p["position"][2] for p in panos if p.get("floor_id") == f["id"]]
        mean_z = float(np.mean(zs)) if zs else f.get("mean_z", 0.0)
        below = [s for s in detected if 0.5 <= mean_z - s <= 2.4]
        f["floor_elevation"] = float(max(below)) if below else float(mean_z - eye)
    return floors


# =====================================================================================
# 5. Line-of-sight navigation graph
# =====================================================================================

def build_los_nav_graph(panos, pts, floors, max_link=6.0, res=0.05):
    by_floor = {}
    for p in panos:
        by_floor.setdefault(p["floor_id"], []).append(p)
    slab_of = {f["id"]: f.get("floor_elevation", 0.0) for f in floors}
    slabs = [f.get("floor_elevation", 0.0) for f in floors]
    masks = floor_band_masks(pts[:, 2], slabs) if len(pts) else []
    for p in panos:
        p["neighbors"] = []
    for fi, f in enumerate(floors):
        fp = by_floor.get(f["id"], [])
        if len(fp) < 2:
            continue
        slab = slab_of[f["id"]]
        sub = pts[masks[fi]] if len(masks) else np.zeros((0, 3))
        P = np.array([p["position"][:2] for p in fp])
        occ = None
        if len(sub):
            g = FloorGrid(sub, slab, res, bounds=(P.min(axis=0) - max_link - 1, P.max(axis=0) + max_link + 1))
            occ = g.raster(slab + 1.2, slab + 1.9, min_count=2)

        def visible(a, b):
            if occ is None:
                return True
            L = float(np.hypot(*(b - a)))
            n = max(2, int(L / (res * 0.8)))
            t = np.linspace(0, 1, n)
            seg = a[None, :] + (b - a)[None, :] * t[:, None]
            keep = (t * L > 0.3) & ((1 - t) * L > 0.3)
            seg = seg[keep]
            if len(seg) == 0:
                return True
            ij = np.floor((seg - g.origin) / res).astype(np.int64)
            ok = (ij[:, 0] >= 0) & (ij[:, 0] < g.nx) & (ij[:, 1] >= 0) & (ij[:, 1] < g.ny)
            ij = ij[ok]
            return not occ[ij[:, 1], ij[:, 0]].any()

        D = np.linalg.norm(P[:, None, :] - P[None, :, :], axis=-1)
        A = np.arctan2(P[None, :, 1] - P[:, None, 1], P[None, :, 0] - P[:, None, 0])
        for i in range(len(fp)):
            best = {}
            for j in np.argsort(D[i]):
                if j == i:
                    continue
                if D[i, j] > max_link:
                    break
                sector = int(np.floor((A[i, j] + np.pi + np.pi / 8) / (np.pi / 4))) % 8
                if sector in best:
                    continue
                if visible(P[i], P[j]):
                    best[sector] = j
            for j in best.values():
                _link(fp[i], fp[j])
            if not best:  # guarantee connectivity
                for j in np.argsort(D[i])[1:]:
                    if visible(P[i], P[j]) or D[i, j] <= 3.0:
                        _link(fp[i], fp[j])
                        break
                else:
                    _link(fp[i], fp[int(np.argsort(D[i])[1])])
    # Cross-floor (stair) links: closest horizontal pair between consecutive floors.
    ids = [f["id"] for f in floors]
    for a, b in zip(ids, ids[1:]):
        fa, fb = by_floor.get(a, []), by_floor.get(b, [])
        if not fa or not fb:
            continue
        PA = np.array([p["position"][:2] for p in fa])
        PB = np.array([p["position"][:2] for p in fb])
        D = np.linalg.norm(PA[:, None] - PB[None], axis=-1)
        i, j = np.unravel_index(np.argmin(D), D.shape)
        if D[i, j] <= 8.0:
            _link(fa[i], fb[j])
            fa[i]["stair_link"] = True
            fb[j]["stair_link"] = True
    return panos


def _link(a, b):
    if b["id"] not in a["neighbors"]:
        a["neighbors"].append(b["id"])
    if a["id"] not in b["neighbors"]:
        b["neighbors"].append(a["id"])


# =====================================================================================
# 6. lod0 cache
# =====================================================================================

def save_lod0(path, pts, cols, target=LOD0_TARGET):
    n = len(pts)
    if n > target:
        sel = np.sort(np.random.default_rng(3).choice(n, target, replace=False))
        pts, cols = pts[sel], cols[sel]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    dt = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
    arr = np.zeros(len(pts), dtype=dt)
    arr["x"], arr["y"], arr["z"] = pts[:, 0], pts[:, 1], pts[:, 2]
    arr["r"], arr["g"], arr["b"] = cols[:, 0], cols[:, 1], cols[:, 2]
    with open(path, "wb") as f:
        f.write(struct.pack("<I", len(arr)))
        f.write(arr.tobytes())
    return len(arr)


def load_lod0(path):
    with open(path, "rb") as f:
        n = struct.unpack("<I", f.read(4))[0]
        dt = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
        arr = np.frombuffer(f.read(n * dt.itemsize), dtype=dt)
    return np.column_stack([arr["x"], arr["y"], arr["z"]]), np.column_stack([arr["r"], arr["g"], arr["b"]])


# =====================================================================================
# 7. Full synthesis pipeline
# =====================================================================================

def synthesize_walkthrough(pc, scan_dir, spacing=DEFAULT_SPACING, pano_width=2048, fixed_stations=None,
                           progress_cb=None, log=None, floor_names=None):
    """Point cloud -> panos + floors + keyplans + LOS nav graph + lod0 (all inside scan_dir).

    fixed_stations: optional list of {"position": [x,y,z], "rotation": [...]} (e.g. E57 data3D
    poses with no images) to render at instead of auto-placed virtual stations.
    Returns dict(panos, floors, lod0_rel, report).
    """
    progress_cb = progress_cb or _noop_progress
    log = log or logger
    scan_dir = Path(scan_dir)
    (scan_dir / "panos").mkdir(parents=True, exist_ok=True)

    progress_cb(22, f"Preparing {len(pc):,} points…")
    if pc.cols is None:
        pc.cols = intensity_to_rgb(pc.intensity) if pc.intensity is not None else None
    has_rgb = pc.cols is not None
    render_pc = voxel_downsample(pc, 0.02)
    if len(render_pc) > 6_000_000:
        render_pc = voxel_downsample(pc, 0.03)
    voxel = 0.02 if len(render_pc) <= 6_000_000 else 0.03
    log.info(f"Synth: {len(pc)} pts -> {len(render_pc)} render pts (voxel {voxel} m), rgb={has_rgb}")

    progress_cb(26, "Detecting floor slabs…")
    slabs = detect_floor_slabs(render_pc.pts)
    log.info(f"Synth: detected floor slabs {slabs}")
    floors = []
    for i, s in enumerate(slabs):
        name = (floor_names[i] if floor_names and i < len(floor_names) else f"Level {i + 1}")
        floors.append({"id": i + 1, "name": name, "floor_elevation": round(float(s), 4)})
    masks = floor_band_masks(render_pc.pts[:, 2], slabs)

    stations = []  # (x, y, z, floor_id, rotation)
    if fixed_stations:
        for st in fixed_stations:
            x, y, z = st["position"]
            fid = 1 + int(np.argmin([abs((z - EYE_HEIGHT) - s) if z - s > 0 else 99 + abs(z - s) for s in slabs]))
            stations.append((x, y, z, fid, [0.0, 0.0, 0.0, 1.0]))
    else:
        for i, s in enumerate(slabs):
            progress_cb(28 + int(6 * i / max(1, len(slabs))), f"Placing virtual stations on {floors[i]['name']}…")
            xy = place_virtual_stations(render_pc.pts[masks[i]], s, spacing=spacing)
            stations += [(x, y, s + EYE_HEIGHT, i + 1, [0.0, 0.0, 0.0, 1.0]) for x, y in xy]
    if not stations:
        c = np.median(render_pc.pts, axis=0)
        stations = [(float(c[0]), float(c[1]), slabs[0] + EYE_HEIGHT, 1, [0.0, 0.0, 0.0, 1.0])]
    log.info(f"Synth: {len(stations)} stations")

    shader = make_shader(has_rgb)
    panos = []
    ratios = []
    for k, (x, y, z, fid, rot) in enumerate(stations):
        progress_cb(35 + int(45 * k / len(stations)), f"Rendering panorama {k + 1} of {len(stations)}…")
        img, ratio = render_equirect(render_pc.pts, render_pc.cols, (x, y, z), width=pano_width,
                                     voxel=voxel, shade=shader)
        pid = f"pano_{k:03d}"
        Image.fromarray(img).save(scan_dir / "panos" / f"{pid}.jpg", quality=88)
        ratios.append(ratio)
        panos.append({
            "id": pid,
            "position": [round(float(x), 4), round(float(y), 4), round(float(z), 4)],
            "rotation": [0.0, 0.0, 0.0, 1.0],
            "floor_id": int(fid),
            "image_path": f"panos/{pid}.jpg",
            "neighbors": [],
            "provenance": "SYNTHETIC_FROM_CLOUD",
            "valid_pixel_ratio": round(ratio, 4),
            "is_level": True,
        })

    for f in floors:
        zs = [p["position"][2] for p in panos if p["floor_id"] == f["id"]]
        zz = zs or [f["floor_elevation"] + EYE_HEIGHT]
        f.update({"min_z": float(min(zz)), "max_z": float(max(zz)), "mean_z": float(np.mean(zz))})
    floors = [f for f in floors if any(p["floor_id"] == f["id"] for p in panos)] or floors[:1]

    progress_cb(82, "Generating calibrated 2D key plans…")
    generate_keyplans(render_pc.pts, floors, scan_dir)
    progress_cb(88, "Building line-of-sight navigation graph…")
    build_los_nav_graph(panos, render_pc.pts, floors)
    progress_cb(92, "Writing point cloud cache…")
    cols = render_pc.cols if render_pc.cols is not None else np.full((len(render_pc), 3), 200, np.uint8)
    n_lod = save_lod0(scan_dir / "cache" / "lod0.bin", render_pc.pts, cols)

    report = {
        "stations_synthesized": len(panos),
        "floors_detected": len(floors),
        "floor_slabs_m": [round(s, 3) for s in slabs],
        "mean_valid_pixel_ratio": round(float(np.mean(ratios)) if ratios else 0.0, 4),
        "render_points": len(render_pc),
        "lod0_points": n_lod,
        "has_rgb": bool(has_rgb),
    }
    return {"panos": panos, "floors": floors, "lod0_rel": "cache/lod0.bin", "report": report}


# =====================================================================================
# 8. Cross-date registration (4-DOF: tx, ty, tz, yaw)
# =====================================================================================

def make_transform(yaw_rad=0.0, t=(0.0, 0.0, 0.0)):
    c, s = math.cos(yaw_rad), math.sin(yaw_rad)
    T = np.eye(4)
    T[:2, :2] = [[c, -s], [s, c]]
    T[:3, 3] = t
    return T


def transform_pts(pts, T):
    return (np.asarray(pts, dtype=np.float64) @ T[:3, :3].T + T[:3, 3]).astype(np.float32)


def _wall_image(pts, origin, cell, shape):
    ij = np.floor((pts[:, :2] - origin) / cell).astype(np.int64)
    ok = (ij[:, 0] >= 0) & (ij[:, 0] < shape[1]) & (ij[:, 1] >= 0) & (ij[:, 1] < shape[0])
    ij, z = ij[ok], pts[ok, 2]
    key = ij[:, 1] * shape[1] + ij[:, 0]
    zmin = np.full(shape[0] * shape[1], np.inf)
    zmax = np.full(shape[0] * shape[1], -np.inf)
    np.minimum.at(zmin, key, z)
    np.maximum.at(zmax, key, z)
    img = ((zmax - zmin) > 1.0).reshape(shape).astype(np.float32)
    return img


def _coarse_align(src, dst, cell=0.25):
    """FFT cross-correlation of vertical-structure (wall) images over yaw."""
    both = np.vstack([dst[:, :2], src[:, :2]])
    span = np.ptp(both, axis=0).max() * 2 + 10
    n = int(2 ** math.ceil(math.log2(max(64, span / cell))))
    n = min(n, 1024)
    cell = max(cell, span / n)
    dc = np.median(dst[:, :2], axis=0)
    sc = np.median(src[:, :2], axis=0)
    origin = -np.array([n * cell / 2, n * cell / 2])
    D = _wall_image(np.column_stack([dst[:, :2] - dc, dst[:, 2]]), origin, cell, (n, n))
    FD = np.fft.rfft2(D)

    def score(yaw):
        c, s = math.cos(yaw), math.sin(yaw)
        xy = (src[:, :2] - sc) @ np.array([[c, -s], [s, c]]).T
        S = _wall_image(np.column_stack([xy, src[:, 2]]), origin, cell, (n, n))
        corr = np.fft.irfft2(FD * np.conj(np.fft.rfft2(S)), s=(n, n))
        k = int(np.argmax(corr))
        iy, ix = divmod(k, n)
        if iy > n // 2:
            iy -= n
        if ix > n // 2:
            ix -= n
        return float(corr.flat[k]), np.array([ix * cell, iy * cell])

    best = (-1, 0.0, np.zeros(2))
    for deg in range(0, 360, 5):
        sc_, sh = score(math.radians(deg))
        if sc_ > best[0]:
            best = (sc_, math.radians(deg), sh)
    for deg in np.arange(-4, 5, 1.0):
        y = best[1] + math.radians(deg)
        sc_, sh = score(y)
        if sc_ > best[0]:
            best = (sc_, y, sh)
    yaw, shift = best[1], best[2]
    c, s = math.cos(yaw), math.sin(yaw)
    R = np.array([[c, -s], [s, c]])
    t_xy = dc + shift - R @ sc
    return yaw, t_xy


def _voxel_centroids(pts, r):
    q = np.floor(pts / r).astype(np.int64)
    key = _key3(q)
    uk, inv = np.unique(key, return_inverse=True)
    cnt = np.bincount(inv).astype(np.float64)
    cen = np.column_stack([np.bincount(inv, pts[:, k]) / cnt for k in range(3)])
    return uk, cen


def _key3(q):
    return (q[:, 0] + 1_048_576) * 4_398_046_511_104 + (q[:, 1] + 1_048_576) * 2_097_152 + (q[:, 2] + 1_048_576)


def _nn_voxel(src, uk, cen, r):
    """Approximate NN of src points among voxel centroids in the 27-neighbourhood."""
    q = np.floor(src / r).astype(np.int64)
    best_d = np.full(len(src), np.inf)
    best_i = np.full(len(src), -1, dtype=np.int64)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                k = _key3(q + np.array([dx, dy, dz]))
                pos = np.searchsorted(uk, k)
                pos = np.minimum(pos, len(uk) - 1)
                hit = uk[pos] == k
                d = np.full(len(src), np.inf)
                d[hit] = np.sum((cen[pos[hit]] - src[hit]) ** 2, axis=1)
                better = d < best_d
                best_d[better] = d[better]
                best_i[better] = pos[better]
    return np.sqrt(best_d), best_i


def register_4dof(src_pts, dst_pts, init=None, log=None):
    """Registers src (new scan) into dst (baseline) frame. Returns (T 4x4, info)."""
    log = log or logger
    rng = np.random.default_rng(11)
    src = np.asarray(src_pts, dtype=np.float64)
    dst = np.asarray(dst_pts, dtype=np.float64)
    if len(src) > 400_000:
        src = src[rng.choice(len(src), 400_000, replace=False)]
    if len(dst) > 800_000:
        dst = dst[rng.choice(len(dst), 800_000, replace=False)]
    if init is None:
        s_sl = detect_floor_slabs(src)
        d_sl = detect_floor_slabs(dst)
        tz = d_sl[0] - s_sl[0]
        yaw, txy = _coarse_align(src, dst)
        T = make_transform(yaw, (txy[0], txy[1], tz))
    else:
        T = np.array(init, dtype=np.float64).reshape(4, 4)
    info = {"coarse_yaw_deg": math.degrees(math.atan2(T[1, 0], T[0, 0]))}
    for r, iters in ((0.40, 15), (0.20, 15), (0.08, 20)):
        uk, cen = _voxel_centroids(dst, r)
        s_uk, s_cen = _voxel_centroids(src, r)
        for _ in range(iters):
            a = s_cen @ T[:3, :3].T + T[:3, 3]
            dist, idx = _nn_voxel(a, uk, cen, r)
            ok = np.isfinite(dist)
            if ok.sum() < 30:
                break
            thr = np.percentile(dist[ok], 80)
            ok &= dist <= thr
            A, B = a[ok], cen[idx[ok]]
            am, bm = A.mean(axis=0), B.mean(axis=0)
            Ac, Bc = A - am, B - bm
            th = math.atan2(np.sum(Ac[:, 0] * Bc[:, 1] - Ac[:, 1] * Bc[:, 0]), np.sum(Ac[:, 0] * Bc[:, 0] + Ac[:, 1] * Bc[:, 1]))
            c, s = math.cos(th), math.sin(th)
            txy = bm[:2] - np.array([[c, -s], [s, c]]) @ am[:2]
            dT = make_transform(th, (txy[0], txy[1], float(np.mean(B[:, 2] - A[:, 2]))))
            T = dT @ T
            if abs(th) < 1e-5 and np.linalg.norm(dT[:3, 3]) < 1e-4:
                break
    a = s_cen @ T[:3, :3].T + T[:3, 3]
    dist, _ = _nn_voxel(a, uk, cen, 0.08)
    inl = np.isfinite(dist) & (dist <= 0.12)
    info.update({
        "yaw_deg": math.degrees(math.atan2(T[1, 0], T[0, 0])),
        "translation": [float(v) for v in T[:3, 3]],
        "fitness": float(inl.mean()) if len(inl) else 0.0,
        "rmse": float(np.sqrt(np.mean(dist[inl] ** 2))) if inl.any() else None,
    })
    log.info(f"Registration: {info}")
    return T, info


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return [aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz]


def apply_transform_to_scan(panos, floors, T):
    """Moves station poses & floor elevations by rigid 4-DOF T (keyplans must be regenerated)."""
    T = np.asarray(T, dtype=np.float64).reshape(4, 4)
    yaw = math.atan2(T[1, 0], T[0, 0])
    qyaw = [0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2)]
    for p in panos:
        p["position"] = [round(float(v), 5) for v in (T[:3, :3] @ np.asarray(p["position"], dtype=np.float64) + T[:3, 3])]
        q = quat_mul(qyaw, p.get("rotation", [0, 0, 0, 1]))
        n = math.sqrt(sum(v * v for v in q)) or 1.0
        p["rotation"] = [float(v / n) for v in q]
    tz = float(T[2, 3])
    for f in floors:
        for k in ("min_z", "max_z", "mean_z", "floor_elevation"):
            if k in f:
                f[k] = float(f[k]) + tz
        f.pop("world_bounds", None) if f.get("keyplan_path") else None
    return panos, floors


def matrix_to_list(T):
    return [float(v) for v in np.asarray(T).reshape(-1)]


# =====================================================================================
# 9. AV Spatial Bundle v1.1 import / export & input detection
# =====================================================================================

def read_bundle_manifest(path):
    p = Path(path)
    if p.is_dir():
        p = p / BUNDLE_FILENAME
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    fmt = data.get("format", "av_spatial_bundle")
    if fmt not in ("av_spatial_bundle", "av_walkthrough_bundle"):
        raise ValueError(f"Unknown bundle format '{fmt}'")
    return p, data


def import_bundle_into(bundle_json, scan_dir):
    """Copies a bundle's panos/floors/cache into scan_dir. Returns normalized scan fields."""
    bpath, data = read_bundle_manifest(bundle_json)
    root = bpath.parent
    scan_dir = Path(scan_dir)
    scan_dir.mkdir(parents=True, exist_ok=True)
    panos = data.get("panos") or data.get("stations") or []
    if not panos:
        raise ValueError("Bundle contains no panos/stations")
    floors = data.get("floors") or [{"id": 1, "name": "Level 1"}]

    def copy_rel(rel):
        if not rel:
            return rel
        src = (root / rel).resolve()
        rel_clean = Path(rel).as_posix().lstrip("./")
        dst = scan_dir / rel_clean
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists() and src != dst.resolve():
            shutil.copy2(src, dst)
        return rel_clean

    for p in panos:
        p["image_path"] = copy_rel(p.get("image_path") or p.get("image"))
        p.setdefault("neighbors", [])
        p.setdefault("rotation", [0.0, 0.0, 0.0, 1.0])
        p.setdefault("floor_id", 1)
        p.pop("image", None)
    for f in floors:
        if f.get("keyplan_path"):
            f["keyplan_path"] = copy_rel(f["keyplan_path"])
    pc = data.get("point_cloud") or {}
    lod0 = pc.get("lod0") if isinstance(pc, dict) else None
    lod0 = lod0 or data.get("lod0_path") or data.get("point_cloud_cache")
    lod0_rel = copy_rel(lod0) if lod0 else ""
    if lod0_rel and not (scan_dir / lod0_rel).exists():
        lod0_rel = ""
    T = data.get("transform_to_project")
    return {
        "panos": panos,
        "floors": floors,
        "lod0_rel": lod0_rel,
        "scan_id": data.get("scan_id"),
        "scan_date": data.get("scan_date"),
        "transform_to_project": T if (T and len(T) == 16) else None,
        "nav_graph": data.get("nav_graph", "bundle"),
        "producer": data.get("producer", {}),
        "project_id": data.get("project_id"),
    }


def write_bundle_manifest(scan_dir, scan_entry, project_id=None, producer="AV Showcase"):
    manifest = {
        "format": "av_spatial_bundle",
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "producer": {"app": producer},
        "project_id": project_id,
        "scan_id": scan_entry.get("scan_id"),
        "scan_date": scan_entry.get("scan_date"),
        "coordinate_system": {"handedness": "right", "up": "+Z", "units": "meters",
                              "pano_projection": "ASTM_E2807_equirectangular"},
        "transform_to_project": scan_entry.get("transform_to_project", matrix_to_list(np.eye(4))),
        "point_cloud": {"lod0": "cache/lod0.bin", "format": "av_lod0_v1"},
        "nav_graph": scan_entry.get("nav_graph", "sector8_v1"),
        "floors": scan_entry.get("floors", []),
        "panos": scan_entry.get("panos", []),
    }
    with open(Path(scan_dir) / BUNDLE_FILENAME, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def e57_image_count(path):
    try:
        import pye57
        e57 = pye57.E57(str(path))
        try:
            return e57.root["images2D"].childCount()
        except Exception:
            return 0
    except Exception:
        return -1


def _find_files(folder, exts, depth=2):
    out = []
    folder = Path(folder)
    for root, dirs, files in os.walk(folder):
        if len(Path(root).relative_to(folder).parts) > depth:
            dirs[:] = []
            continue
        out += [Path(root) / f for f in files if f.lower().endswith(exts)]
    return sorted(out)


def detect_input(path):
    """Classifies a user-selected path. Returns dict(type, details...)."""
    p = Path(path)
    if not p.exists():
        return {"type": None, "error": f"Path not found: {path}"}
    if p.is_file():
        name, ext = p.name.lower(), p.suffix.lower()
        if name.endswith(".json"):
            return {"type": "AV Spatial Bundle", "bundle": str(p)}
        if ext == ".zip":
            with zipfile.ZipFile(p) as z:
                names = [n.lower() for n in z.namelist()]
            if any(n.endswith(BUNDLE_FILENAME) for n in names):
                return {"type": "AV Spatial Bundle", "zip": str(p)}
            return {"type": "Matterport MatterPak", "zip": str(p)}
        if ext == ".e57":
            n = e57_image_count(p)
            return {"type": "Structured E57", "e57": str(p), "images2D": n}
        if ext in POINT_CLOUD_EXTS:
            return {"type": "Raw Point Cloud", "cloud": str(p)}
        return {"type": None, "error": f"Unrecognised file type '{ext}'"}
    if (p / BUNDLE_FILENAME).exists():
        return {"type": "AV Spatial Bundle", "bundle": str(p / BUNDLE_FILENAME)}
    e57s = _find_files(p, (".e57",), 1)
    imgs = _find_files(p, (".jpg", ".jpeg"), 2)
    csvs = [c for c in _find_files(p, (".csv",), 2) if "pose" in c.name.lower()]
    pngs = [x for x in _find_files(p, (".png",), 2) if "floor" in x.name.lower()]
    clouds = [c for c in _find_files(p, POINT_CLOUD_EXTS, 2) if c.suffix.lower() not in (".csv", ".e57", ".txt")]
    if e57s and imgs:
        out = {"type": "E57 + Panos + CSV" if csvs else "E57 + Panos Folder", "e57": str(e57s[0]),
               "panos": str(imgs[0].parent)}
        if csvs:
            out["csv"] = str(csvs[0])
        return out
    if clouds and (pngs or (p / "bundle_manifest.json").exists()):
        return {"type": "Matterport MatterPak", "folder": str(p)}
    if e57s:
        return {"type": "Structured E57", "e57": str(e57s[0]), "images2D": e57_image_count(e57s[0])}
    if clouds:
        return {"type": "Raw Point Cloud", "cloud": str(clouds[0])}
    return {"type": None, "error": "No supported scan data found in folder"}


def resolve_matterpak(path, work_dir):
    """Extracts (if zip) and returns (cloud_path, [floorplan pngs], manifest dict or None)."""
    p = Path(path)
    if p.is_file() and p.suffix.lower() == ".zip":
        dst = Path(work_dir) / "matterpak_src"
        if dst.exists():
            shutil.rmtree(dst)
        dst.mkdir(parents=True)
        with zipfile.ZipFile(p) as z:
            for member in z.infolist():
                target = (dst / member.filename).resolve()
                if not str(target).startswith(str(dst.resolve())):
                    continue  # zip-slip guard
                z.extract(member, dst)
        p = dst
    clouds = _find_files(p, (".xyz", ".ply", ".e57", ".pts", ".las", ".laz", ".pcd", ".obj"), 3)
    if not clouds:
        raise ValueError("MatterPak contains no point cloud (.xyz/.ply/.e57/.obj)")
    pref = {".xyz": 0, ".ply": 1, ".e57": 2, ".pts": 3, ".las": 4, ".laz": 5, ".pcd": 6, ".obj": 7}
    clouds.sort(key=lambda c: (pref.get(c.suffix.lower(), 9), -c.stat().st_size))
    plans = [x for x in _find_files(p, (".png", ".jpg"), 3) if "floor" in x.name.lower() or "plan" in x.name.lower()]
    manifest = None
    for m in _find_files(p, (".json",), 3):
        if m.name.lower() == "bundle_manifest.json":
            try:
                manifest = json.loads(m.read_text(encoding="utf-8"))
            except Exception:
                manifest = None
    return str(clouds[0]), [str(x) for x in plans], manifest
