import pye57

e57_path = r"C:\Users\ChristopherAllen\OneDrive - Reisource\_INTERNAL\808\808_Brannan_LB_E57wP-002.e57"
e57 = pye57.E57(e57_path)

images2d = e57.root['images2D']
count = images2d.childCount()

names = []
for i in range(count):
    im = images2d[i]
    name = im['name'].value() if im.isDefined('name') else ''
    names.append((i, name))

print(f"Total images: {count}")
print("First 20 names:")
for i, n in names[:20]:
    print(f"  {i:3d}: {n}")

sorted_names = sorted(names, key=lambda x: x[1])
print("\nFirst 20 sorted by name:")
for orig_i, n in sorted_names[:20]:
    print(f"  orig_idx={orig_i:3d}: {n}")
