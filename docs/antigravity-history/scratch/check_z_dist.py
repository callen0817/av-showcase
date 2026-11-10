import pye57
import numpy as np

e57_path = r"C:\Users\ChristopherAllen\OneDrive - Reisource\_INTERNAL\808\808_Brannan_LB_E57wP-002.e57"
e57 = pye57.E57(e57_path)

images2d = e57.root['images2D']
count = images2d.childCount()

poses = []
for i in range(count):
    im = images2d[i]
    name = im['name'].value() if im.isDefined('name') else ''
    pose = im['pose']
    x = pose['translation']['x'].value()
    y = pose['translation']['y'].value()
    z = pose['translation']['z'].value()
    poses.append((i, name, x, y, z))

zs = [p[4] for p in poses]
print("Overall Z range:", min(zs), "to", max(zs))

# Histogram with 0.2m bins
bins = np.arange(min(zs)-0.1, max(zs)+0.3, 0.2)
hist, bin_edges = np.histogram(zs, bins=bins)
for h, b0, b1 in zip(hist, bin_edges[:-1], bin_edges[1:]):
    if h > 0:
        bar = '#' * min(50, h)
        print(f"[{b0:5.2f} to {b1:5.2f}]: {h:3d} scans {bar}")
