from scipy.spatial.transform import Rotation as R
import numpy as np

# rotation in pA: qx=-0.01113, qy=-0.00549, qz=-0.47880, qw=0.87784
# In Three.js:
# qThree = (rotation[0], rotation[2], -rotation[1], rotation[3])
# qx_three = -0.01113
# qy_three = -0.47880
# qz_three = 0.00549
# qw_three = 0.87784

r = R.from_quat([-0.01113, -0.47880, 0.00549, 0.87784])
# Euler YXZ in Three.js
# In scipy: as_euler('YXZ', degrees=True)
euler = r.as_euler('YXZ', degrees=True)
print(f"Three.js Euler Y: {euler[0]:.1f} deg")

# But wait! Look at the yaw of the camera look vector in Three.js:
# updateCamera(lat=0, lon=cameraLon)
# target.x = 50 * cos(lon)
# target.z = 50 * sin(lon)
# At lon = 0, camera looks at (+50, 0, 0) -> +X axis!
# At lon = 90, camera looks at (0, 0, +50) -> +Z axis!
# At lon = -25.2, camera looks at (+X, -Z) which is the direction of marker B!
print(f"Direction to marker B in Three.js: -25.2 deg (from +X towards +Z)")

# Now, where is the center of the equirectangular panorama mapped on the sphere?
# In SphereGeometry(50, 60, 40) scaled by (-1, 1, 1):
# For u=0.5 (center of image):
# x = -r * cos(pi) = +r (+X)
# z = r * sin(pi) = 0
# So center of image is at +X (lon=0)!
# When panoSphere is rotated by uprightQ (around Y by euler.y = -57.2 deg):
# Rotation around +Y by angle A:
# [x', z'] = [x*cos(A) + z*sin(A), -x*sin(A) + z*cos(A)] (Three.js uses standard mathematical Y rotation)
# For initial point at (1, 0):
# x' = cos(A), z' = -sin(A)
# If A = -57.2 deg:
# x' = cos(-57.2) = 0.54
# z' = -sin(-57.2) = +0.84!
# That means center of image (forward in scanner) is rotated to +Z (+57.2 deg),
# BUT in Python world coordinates, scanner heading was -57.2 deg (-Z, towards -dy)!
# IT IS ROTATED IN THE EXACT OPPOSITE (MIRRORED) DIRECTION!
