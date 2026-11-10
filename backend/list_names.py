import pye57

filepath = r"C:\Users\ChristopherAllen\Downloads\ex\av_walkthrough\mp_e57_920-5th-Ave-5A-Interior_rkpAXm3RY7k\cloud_0.e57"
e57 = pye57.E57(filepath)
root = e57.root

for i in range(12):
    im = root["images2D"][i]
    print(f"Index {i}: name='{im['name'].value()}', guid='{im['associatedData3DGuid'].value()}'")
