import json
import re
import os
import pye57

e57_path = r"C:\Users\ChristopherAllen\OneDrive - Reisource\_INTERNAL\808\808_Brannan_LB_E57wP-002.e57"
proj_path = r"C:\Users\ChristopherAllen\OneDrive - Reisource\_INTERNAL\808\argos test\test argon\project.avproj"

e57 = pye57.E57(e57_path)
images2d = e57.root['images2D']
count = images2d.childCount()

def natural_sort_key(idx):
    node = images2d[idx]
    if node.isDefined("name"):
        val = node["name"].value() if hasattr(node["name"], "value") else str(node["name"])
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', val)]
    return [idx]

ordered_indices = sorted(range(count), key=natural_sort_key)
print(f"Total images: {count}")
print("First 10 naturally sorted indices and names:")
for seq_idx, orig_i in enumerate(ordered_indices[:10]):
    node = images2d[orig_i]
    name = node["name"].value()
    print(f"  seq={seq_idx:3d} (orig={orig_i:3d}): {name}")
