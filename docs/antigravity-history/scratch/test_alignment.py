import json
import numpy as np

proj_path = r"C:\Users\ChristopherAllen\OneDrive - Reisource\_INTERNAL\808\argos test\test argon\project.avproj"
with open(proj_path, "r") as f:
    d = json.load(f)

panos = d['scans'][0]['panos']
pA = next(p for p in panos if 'pano_001.jpg' in p['image_path']) # 00000
pB = next(p for p in panos if 'pano_006.jpg' in p['image_path']) # 00001

dx = pB['position'][0] - pA['position'][0]
dy = pB['position'][1] - pA['position'][1]
dz = pB['position'][2] - pA['position'][2]

print(f"World vector A->B: dx={dx:.2f}, dy={dy:.2f}, dz={dz:.2f}")

# Python yaw of vector A->B (from East towards North)
vec_yaw = np.degrees(np.arctan2(dy, dx))
print(f"Angle of vector A->B in world: {vec_yaw:.1f} deg")

rotA = pA['rotation'] # qx, qy, qz, qw
# Scanner A yaw in world:
scannerA_yaw = np.degrees(np.arctan2(2.0 * (rotA[3]*rotA[2] + rotA[0]*rotA[1]), 1.0 - 2.0 * (rotA[1]*rotA[1] + rotA[2]*rotA[2])))
print(f"Scanner A heading in world: {scannerA_yaw:.1f} deg")

# Relative angle of B in scanner A's local camera frame:
rel_angle = vec_yaw - scannerA_yaw
print(f"Relative direction of B from scanner A: {rel_angle:.1f} deg")
