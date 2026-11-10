import pye57
from collections import Counter

e57_path = r"C:\Users\ChristopherAllen\OneDrive - Reisource\_INTERNAL\808\808_Brannan_LB_E57wP-002.e57"
e57 = pye57.E57(e57_path)

images2d = e57.root['images2D']
count = images2d.childCount()

missions = []
for i in range(count):
    im = images2d[i]
    name = im['name'].value() if im.isDefined('name') else ''
    missions.append(name)

print("Mission substrings found:")
prefix_counts = Counter([n.split('_Base_')[0].split('_2026')[0] if '_Base_' in n else n.split('_2026')[0] for n in missions])
for k, v in prefix_counts.items():
    print(f"  {k}: {v} images")

# Check Z-heights per mission
import numpy as np
mission_zs = {}
for i in range(count):
    im = images2d[i]
    name = im['name'].value() if im.isDefined('name') else ''
    prefix = name.split('_2026')[0]
    # get scan group name
    tag = 'L1' if 'LB-L1' in name else ('Base' if 'LB_Base' in name else 'Other')
    pose = im['pose']
    z = pose['translation']['z'].value()
    x = pose['translation']['x'].value()
    y = pose['translation']['y'].value()
    if tag not in mission_zs: mission_zs[tag] = []
    mission_zs[tag].append((i, name, x, y, z))

print("\nScan groups summary:")
for tag, items in mission_zs.items():
    zs = [it[4] for it in items]
    print(f"Group '{tag}': {len(items)} scans, Z range: [{min(zs):.2f}, {max(zs):.2f}], Mean Z: {np.mean(zs):.2f}")
