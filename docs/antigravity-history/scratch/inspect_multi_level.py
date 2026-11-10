import os
import glob
import pye57
import numpy as np

ex_dir = r"C:\Users\ChristopherAllen\Downloads\_ex"
if os.path.exists(ex_dir):
    print("Files in _ex:", os.listdir(ex_dir))

e57_path = r"C:\Users\ChristopherAllen\Downloads\_ex\250603_2e88.e57"
if os.path.exists(e57_path):
    e57 = pye57.E57(e57_path)
    image2D_node = e57.root["images2D"]
    total_images = image2D_node.childCount()
    positions = []
    for i in range(total_images):
        img_node = image2D_node[i]
        pose_node = img_node["pose"]
        t = pose_node["translation"]
        positions.append([t["x"].value(), t["y"].value(), t["z"].value()])
    positions = np.array(positions)
    print(f"Loaded {len(positions)} positions from {e57_path}")
    print("Z min/max:", positions[:, 2].min(), positions[:, 2].max())
