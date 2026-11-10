import pye57

filepath = r"C:\Users\ChristopherAllen\Downloads\ex\av_walkthrough\mp_e57_920-5th-Ave-5A-Interior_rkpAXm3RY7k\cloud_0.e57"
e57 = pye57.E57(filepath)
root = e57.root

scans = root["data3D"]
num_scans = scans.childCount()
print(f"Number of scans: {num_scans}")

missing_pose = 0
missing_guid = 0

for i in range(num_scans):
    s = scans[i]
    if "guid" not in s:
        # StructureNode doesn't support 'in', let's try getting it
        try:
            g = s["guid"]
        except:
            missing_guid += 1
            
    try:
        pose = s["pose"]
        t = pose["translation"]
        r = pose["rotation"]
    except Exception as e:
        missing_pose += 1

print(f"Missing poses: {missing_pose}")
print(f"Missing guids: {missing_guid}")
