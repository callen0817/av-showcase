import json
import numpy as np

proj_path = r"C:\Users\ChristopherAllen\OneDrive - Reisource\_INTERNAL\808\argos test\test argon\project.avproj"
with open(proj_path, "r") as f:
    d = json.load(f)

zs = np.array([p['position'][2] for p in d['scans'][0]['panos']])

# If K custom names are provided (e.g. K=2 for '1, mezz', or K=5 for 5 levels)
# Find K centers by finding the K most prominent peaks in the histogram, or 1D k-means:
def cluster_1d(data, k, max_iters=50):
    # Initialize centers from percentiles
    percentiles = np.linspace(10, 90, k)
    centers = np.percentile(data, percentiles)
    
    for _ in range(max_iters):
        # Assign each point to closest center
        dists = np.abs(data[:, None] - centers[None, :])
        labels = np.argmin(dists, axis=-1)
        
        new_centers = np.array([data[labels == j].mean() if np.any(labels == j) else centers[j] for j in range(k)])
        if np.allclose(centers, new_centers, atol=1e-3):
            break
        centers = new_centers
        
    sorted_order = np.argsort(centers)
    centers = centers[sorted_order]
    
    # Midpoints between adjacent floor centers
    midpoints = (centers[:-1] + centers[1:]) / 2.0
    labels = np.digitize(data, midpoints) # 0 to k-1
    return centers, midpoints, labels

centers, midpoints, labels = cluster_1d(zs, 2)
print("Centers:", centers)
print("Midpoints:", midpoints)
for i in range(2):
    count = np.sum(labels == i)
    sub = zs[labels == i]
    print(f"Floor {i+1}: {count} scans, range [{sub.min():.2f}, {sub.max():.2f}], mean {sub.mean():.2f}")
