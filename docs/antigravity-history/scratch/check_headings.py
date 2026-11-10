import json
import numpy as np

proj_path = r"C:\Users\ChristopherAllen\OneDrive - Reisource\_INTERNAL\808\argos test\test argon\project.avproj"
with open(proj_path, "r") as f:
    d = json.load(f)

panos = d['scans'][0]['panos']

print("Pano IDs and their sequence:")
for i in range(10):
    p = panos[i]
    q = p['rotation'] # [qx, qy, qz, qw]
    # yaw from quaternion: rotation around Z axis in Python
    # qx, qy, qz, qw
    yaw = np.arctan2(2.0 * (q[3]*q[2] + q[0]*q[1]), 1.0 - 2.0 * (q[1]*q[1] + q[2]*q[2]))
    yaw_deg = np.degrees(yaw)
    print(f"{p['id']}: pos=({p['position'][0]:.2f}, {p['position'][1]:.2f}) yaw={yaw_deg:.1f} deg")

# Check path between consecutive scans if we sort them by scan ID or trajectory
# Look at consecutive pairs in original order:
print("\nVector between consecutive panos in panos list:")
for i in range(5):
    p1 = panos[i]
    p2 = panos[i+1]
    dx = p2['position'][0] - p1['position'][0]
    dy = p2['position'][1] - p1['position'][1]
    dist = np.hypot(dx, dy)
    angle = np.degrees(np.arctan2(dy, dx))
    print(f"{p1['id']} -> {p2['id']}: dist={dist:.2f}m dx={dx:.2f} dy={dy:.2f} move_angle={angle:.1f} deg")
