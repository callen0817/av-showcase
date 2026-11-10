import numpy as np

# Test rotation
alpha_deg = 30.0 # 30 deg counter-clockwise in Python (from +X towards +Y)
alpha_rad = np.radians(alpha_deg)

# Target in Three.js:
# X = cos(30) = 0.866
# Z = sin(30) = 0.500

# Three.js rotation matrix around +Y:
# X' = X*cos(theta) + Z*sin(theta)
# Z' = -X*sin(theta) + Z*cos(theta)
# For initial point X=1, Z=0:
# If theta = -alpha_rad (-30 deg):
theta = -alpha_rad
x_prime = np.cos(theta)
z_prime = -np.sin(theta)

print(f"Target: X={np.cos(alpha_rad):.3f}, Z={np.sin(alpha_rad):.3f}")
print(f"With theta = -alpha: X'={x_prime:.3f}, Z'={z_prime:.3f}")
assert np.isclose(x_prime, np.cos(alpha_rad)) and np.isclose(z_prime, np.sin(alpha_rad)), "Mismatch!"
print("MATHEMATICALLY VERIFIED: Three.js Y-rotation angle must be -yaw!")
