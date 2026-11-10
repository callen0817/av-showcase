import pye57

filepath = r"C:\Users\ChristopherAllen\Downloads\ex\av_walkthrough\mp_e57_920-5th-Ave-5A-Interior_rkpAXm3RY7k\cloud_0.e57"
e57 = pye57.E57(filepath)
root = e57.root

print("Root type:", type(root))
print("Root attributes:", dir(root))

print("\n--- root['data3D'] ---")
try:
    data3d = root["data3D"]
    print("data3D type:", type(data3d))
    print("data3D attributes:", dir(data3d))
    if hasattr(data3d, "childCount"):
        print("data3D childCount method:", data3d.childCount)
        print("data3D childCount value:", data3d.childCount())
    else:
        print("data3D does not have childCount")
except Exception as e:
    print("Failed to get data3D:", e)

print("\n--- root['images2D'] ---")
try:
    images2d = root["images2D"]
    print("images2D type:", type(images2d))
    print("images2D attributes:", dir(images2d))
    if hasattr(images2d, "childCount"):
        print("images2D childCount value:", images2d.childCount())
    else:
        print("images2D does not have childCount")
except Exception as e:
    print("Failed to get images2D:", e)
