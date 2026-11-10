import json
import numpy as np
import math

proj_path = r"C:\Users\ChristopherAllen\OneDrive - Reisource\_INTERNAL\808\argos test\test argon\project.avproj"
with open(proj_path, "r") as f:
    d = json.load(f)

panos = d['scans'][0]['panos']
positions = np.array([p['position'] for p in panos])

# Smart Multi-Directional Graph Builder
# 1. Trajectory link: connect consecutive scans (i-1, i+1) if within 10m
# 2. 8 Directional Sectors (every 45 degrees) around the scanner:
#    In each sector, pick the closest neighbor that is at least 0.5m away (to skip stationary duplicate exposures),
#    or if none >= 0.5m, pick closest.
# 3. Plus close neighbors (< 1.5m) up to a max limit

def build_smart_graph(floor_panos, max_dist=12.0):
    n = len(floor_panos)
    pts = np.array([p['position'] for p in floor_panos])
    
    # Precompute pairwise 2D distances and azimuth angles
    diff = pts[:, None, :2] - pts[None, :, :2] # (n, n, 2)
    dists = np.linalg.norm(diff, axis=-1)
    angles = np.arctan2(diff[..., 1], diff[..., 0]) # [-pi, pi]
    
    for i in range(n):
        neighbors_set = set()
        
        # Rule 1: Trajectory continuity (walk smoothly forward and backward)
        for offset in [-1, 1]:
            adj = i + offset
            if 0 <= adj < n and dists[i, adj] <= max_dist:
                neighbors_set.add(floor_panos[adj]['id'])
                
        # Rule 2: Directional Sectors (8 sectors of 45 degrees: 0, 45, 90, 135, 180, -135, -90, -45)
        # Allows moving in all cardinal and diagonal directions (corridors, intersections, rooms)
        num_sectors = 8
        sector_step = 2.0 * math.pi / num_sectors
        
        # Candidates for node i (exclude self)
        valid_mask = (dists[i] > 0.01) & (dists[i] <= max_dist)
        valid_indices = np.where(valid_mask)[0]
        
        if len(valid_indices) > 0:
            cand_dists = dists[i, valid_indices]
            cand_angles = angles[i, valid_indices] # angle from i to neighbor
            
            # Map angles to sector index [0..7]
            sector_indices = np.floor((cand_angles + math.pi + (sector_step / 2.0)) / sector_step).astype(int) % num_sectors
            
            for s in range(num_sectors):
                in_sector = np.where(sector_indices == s)[0]
                if len(in_sector) == 0:
                    continue
                    
                s_dists = cand_dists[in_sector]
                s_indices = valid_indices[in_sector]
                
                # Prefer nodes at least 0.5m away to avoid getting trapped in stationary cluster
                far_enough = s_dists >= 0.5
                if np.any(far_enough):
                    best_local = np.argmin(s_dists[far_enough])
                    best_idx = s_indices[far_enough][best_local]
                else:
                    best_local = np.argmin(s_dists)
                    best_idx = s_indices[best_local]
                    
                neighbors_set.add(floor_panos[best_idx]['id'])
                
        # Rule 3: Add any nearby node within 1.8m (up to max 8 neighbors)
        sorted_by_dist = np.argsort(dists[i])
        for idx in sorted_by_dist[1:]:
            if len(neighbors_set) >= 8:
                break
            if dists[i, idx] <= 1.8:
                neighbors_set.add(floor_panos[idx]['id'])
            else:
                break
                
        floor_panos[i]['new_neighbors'] = list(neighbors_set)

build_smart_graph(panos)

# Check results:
zero_neighbors = [p['id'] for p in panos if len(p['new_neighbors']) == 0]
low_neighbors = [p['id'] for p in panos if len(p['new_neighbors']) < 2]
avg_neighbors = np.mean([len(p['new_neighbors']) for p in panos])
print(f"Graph stats: Avg neighbors per pano: {avg_neighbors:.1f}")
print(f"Panos with 0 neighbors: {len(zero_neighbors)}")
print(f"Panos with < 2 neighbors: {len(low_neighbors)}")

# Compare pano_000 old vs new:
p0 = panos[0]
print(f"\npano_000 old neighbors: {p0['neighbors']}")
print(f"pano_000 new neighbors: {p0['new_neighbors']}")
for nid in p0['new_neighbors']:
    np_pano = next(p for p in panos if p['id'] == nid)
    d = np.linalg.norm(np.array(np_pano['position']) - np.array(p0['position']))
    print(f"  -> {nid}: dist={d:.2f}m")
