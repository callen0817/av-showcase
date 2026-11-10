import json
import numpy as np

proj_path = r"C:\Users\ChristopherAllen\OneDrive - Reisource\_INTERNAL\808\argos test\test argon\project.avproj"
with open(proj_path, "r") as f:
    d = json.load(f)

sc = d['scans'][0]
panos = sc['panos']
print(f"Total panos: {len(panos)}")
for p in panos[:10]:
    print(f"{p['id']}: pos=({p['position'][0]:.2f}, {p['position'][1]:.2f}, {p['position'][2]:.2f}) floor={p['floor_id']} neighbors={p['neighbors']}")

positions = np.array([p['position'] for p in panos])
diff_2d = positions[:, None, :2] - positions[None, :, :2]
dists_2d = np.linalg.norm(diff_2d, axis=-1)
np.fill_diagonal(dists_2d, 999)

close_pairs = []
for i in range(len(panos)):
    for j in range(i+1, len(panos)):
        if dists_2d[i, j] < 0.6:
            close_pairs.append((i, j, dists_2d[i, j], panos[i]['id'], panos[j]['id'], panos[i]['position'], panos[j]['position']))

print(f"\nPairs within 0.6m: {len(close_pairs)}")
for cp in close_pairs[:15]:
    p1 = [round(x, 2) for x in cp[5]]
    p2 = [round(x, 2) for x in cp[6]]
    print(f"{cp[3]} & {cp[4]}: dist={cp[2]:.3f}m pos1={p1} pos2={p2}")
