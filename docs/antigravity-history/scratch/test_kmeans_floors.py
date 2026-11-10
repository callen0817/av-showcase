import json
import numpy as np

proj_path = r"C:\Users\ChristopherAllen\OneDrive - Reisource\_INTERNAL\808\argos test\test argon\project.avproj"
with open(proj_path, "r") as f:
    d = json.load(f)

zs = [p['position'][2] for p in d['scans'][0]['panos']]

# What if K = len(custom_names) == 2?
# Using KMeans or quantile/histogram peak detection to find K cluster centers:
from sklearn.cluster import KMeans

kmeans = KMeans(n_clusters=2, random_state=42).fit(np.array(zs).reshape(-1, 1))
centers = sorted(kmeans.cluster_centers_.flatten())
print(f"2 clusters centers: {centers[0]:.2f}m, {centers[1]:.2f}m")
midpoint = (centers[0] + centers[1]) / 2.0
print(f"Split midpoint: {midpoint:.2f}m")
c1 = [z for z in zs if z < midpoint]
c2 = [z for z in zs if z >= midpoint]
print(f"Floor 1 scans: {len(c1)}, Z range: [{min(c1):.2f}, {max(c1):.2f}]")
print(f"Floor 2 scans: {len(c2)}, Z range: [{min(c2):.2f}, {max(c2):.2f}]")
