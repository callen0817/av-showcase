import os
import shutil
import json
import re
import pye57
import numpy as np
import sys

sys.path.insert(0, r"c:\Users\ChristopherAllen\OneDrive - Reisource\Desktop\AV_Walkthrough\backend")
from ingestion import IngestionManager

e57_path = r"C:\Users\ChristopherAllen\OneDrive - Reisource\_INTERNAL\808\808_Brannan_LB_E57wP-002.e57"
proj_dir = r"C:\Users\ChristopherAllen\OneDrive - Reisource\_INTERNAL\808\argos test\test argon"
proj_path = os.path.join(proj_dir, "project.avproj")
panos_dir = os.path.join(proj_dir, "Scans", "2026-10-18", "panos")
temp_panos_dir = os.path.join(proj_dir, "Scans", "2026-10-18", "panos_temp")

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

# Copy files from temp_panos_dir (which was already created) or extract directly
panos = []
z_values = []

for seq_idx, orig_i in enumerate(ordered_indices):
    img_node = images2d[orig_i]
    pose = img_node["pose"]
    tx, ty, tz = pose["translation"]["x"].value(), pose["translation"]["y"].value(), pose["translation"]["z"].value()
    qw, qx, qy, qz = pose["rotation"]["w"].value(), pose["rotation"]["x"].value(), pose["rotation"]["y"].value(), pose["rotation"]["z"].value()
    z_values.append(tz)
    
    pano_id = f"pano_{seq_idx:03d}"
    dest_name = f"{pano_id}.jpg"
    dest_path = os.path.join(panos_dir, dest_name)
    temp_path = os.path.join(temp_panos_dir, dest_name)
    
    if os.path.exists(temp_path):
        shutil.copy2(temp_path, dest_path)
    else:
        rep = img_node["sphericalRepresentation"] if img_node.isDefined("sphericalRepresentation") else img_node["pinholeRepresentation"]
        for key in ["jpegImage", "pngImage", "imageBlob", "blob"]:
            if rep.isDefined(key):
                blob_node = rep[key]
                break
        if blob_node:
            img_bytes = blob_node.read_buffer().tobytes()
            with open(dest_path, "wb") as f:
                f.write(img_bytes)
                
    panos.append({
        "id": pano_id,
        "position": [tx, ty, tz],
        "rotation": [qx, qy, qz, qw],
        "image_path": f"panos/{dest_name}",
        "floor_id": 1,
        "neighbors": []
    })

# Clean up temp
if os.path.exists(temp_panos_dir):
    try:
        shutil.rmtree(temp_panos_dir)
    except:
        pass

print(f"Copied {len(panos)} ordered panos into place.")

mgr = IngestionManager(proj_dir, "test argon", floor_threshold=0.25, floor_heights="1, mezz")
floor_mapping, floors = mgr._get_z_floors(z_values)

for p in panos:
    p['floor_id'] = floor_mapping[p['position'][2]]

panos = mgr._generate_navigation_graph(panos)

with open(proj_path, "r", encoding="utf-8") as f:
    proj_data = json.load(f)

scan = proj_data["scans"][0]
scan["panos"] = panos
scan["floors"] = floors

with open(proj_path, "w", encoding="utf-8") as f:
    json.dump(proj_data, f, indent=2)

print("test argon successfully updated!")
