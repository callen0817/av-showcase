import json
import numpy as np

# Load the project
path = r"C:\Users\ChristopherAllen\Downloads\heighttest\project.avproj"
with open(path) as f:
    data = json.load(f)

z_values = [p['position'][2] for scan in data['scans'] for p in scan['panos']]
z_arr = np.array(z_values)

print(f"Total scans: {len(z_values)}")

# 1. Get initial floors using a small threshold (0.25m)
th = 0.25
sorted_z = sorted(list(set(z_values)))
floors = []
current_floor_id = 1
current_min_z = sorted_z[0]
floor_mapping = {}

for i in range(len(sorted_z)):
    z = sorted_z[i]
    if i > 0 and (z - sorted_z[i-1]) > th:
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

# Populate Z values and compute mean
for f in floors:
    f["scans"] = [z for z in z_values if f["min_z"] <= z <= f["max_z"]]
    f["count"] = len(f["scans"])
    f["mean_z"] = np.mean(f["scans"])

print(f"\nInitial floors: {len(floors)}")
for f in floors:
    print(f"  Floor {f['id']}: count={f['count']}, range=[{f['min_z']:.3f}, {f['max_z']:.3f}], mean={f['mean_z']:.3f}")

# 2. Classify floors into Major and Stairs dynamically
major_floors = []
stairs_floors = []

for idx, f in enumerate(floors):
    # Condition 1: High scan density (always a major floor)
    is_major = f["count"] >= 15
    
    # Condition 2: Local maximum (more scans than adjacent intermediate stair floors)
    if not is_major:
        left_count = floors[idx-1]["count"] if idx > 0 else 0
        right_count = floors[idx+1]["count"] if idx < len(floors) - 1 else 0
        if f["count"] >= 4 and f["count"] > left_count and f["count"] > right_count:
            is_major = True
            
    # Condition 3: Height isolation (separated from neighbors by a significant height gap, like the roof)
    if not is_major:
        left_gap = (f["mean_z"] - floors[idx-1]["mean_z"]) if idx > 0 else 999.0
        right_gap = (floors[idx+1]["mean_z"] - f["mean_z"]) if idx < len(floors) - 1 else 999.0
        if min(left_gap, right_gap) > 0.65:
            is_major = True

    if is_major:
        major_floors.append(f)
    else:
        stairs_floors.append(f)

print(f"\nMajor Floors detected: {len(major_floors)}")
for f in major_floors:
    print(f"  Major {f['id']}: count={f['count']}, mean={f['mean_z']:.3f}")

print(f"\nStairs/Transition Floors detected: {len(stairs_floors)}")
for f in stairs_floors:
    print(f"  Stairs {f['id']}: count={f['count']}, mean={f['mean_z']:.3f}")

# 3. Distribute scans in stairs floors to nearest major floors (lower half -> below, upper half -> above)
for sf in stairs_floors:
    mid_z = (sf["min_z"] + sf["max_z"]) / 2.0
    
    # Find major floor below and above sf
    below_majors = [mf for mf in major_floors if mf["mean_z"] < sf["mean_z"]]
    above_majors = [mf for mf in major_floors if mf["mean_z"] > sf["mean_z"]]
    
    floor_below = max(below_majors, key=lambda x: x["mean_z"]) if below_majors else None
    floor_above = min(above_majors, key=lambda x: x["mean_z"]) if above_majors else None
    
    for z in sf["scans"]:
        # If below midpoint, assign to floor below (if it exists)
        if z < mid_z and floor_below:
            floor_below["scans"].append(z)
        elif floor_above:
            floor_above["scans"].append(z)
        elif floor_below:
            floor_below["scans"].append(z)

# Recompute bounds and counts of major floors
for idx, mf in enumerate(major_floors):
    mf["id"] = idx + 1
    mf["count"] = len(mf["scans"])
    mf["min_z"] = min(mf["scans"])
    mf["max_z"] = max(mf["scans"])
    mf["mean_z"] = np.mean(mf["scans"])

print(f"\nFinal grouped floors after midpoint stair partition: {len(major_floors)}")
for f in major_floors:
    print(f"  Floor {f['id']}: count={f['count']}, range=[{f['min_z']:.3f}, {f['max_z']:.3f}], mean={f['mean_z']:.3f}")
