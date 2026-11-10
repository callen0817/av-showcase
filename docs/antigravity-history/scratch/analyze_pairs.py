import pye57
import numpy as np

e57_path = r"C:\Users\ChristopherAllen\OneDrive - Reisource\_INTERNAL\808\808_Brannan_LB_E57wP-002.e57"
e57 = pye57.E57(e57_path)

images2d = e57.root['images2D']
count = images2d.childCount()

items = []
for i in range(count):
    im = images2d[i]
    name = im['name'].value() if im.isDefined('name') else ''
    pose = im['pose']
    x = pose['translation']['x'].value()
    y = pose['translation']['y'].value()
    z = pose['translation']['z'].value()
    group = 'L1' if 'LB-L1' in name else 'Base'
    items.append({'i': i, 'name': name, 'group': group, 'pos': (x, y, z)})

# Check pairs < 0.6m
print("=== Pairs within 0.6m and their groups ===")
same_group_count = 0
diff_group_count = 0
for i in range(count):
    for j in range(i+1, count):
        p1 = items[i]['pos']
        p2 = items[j]['pos']
        d = np.hypot(p2[0]-p1[0], p2[1]-p1[1])
        if d < 0.6:
            if items[i]['group'] == items[j]['group']:
                same_group_count += 1
            else:
                diff_group_count += 1
            if d < 0.3:
                print(f"d={d:.2f}m: [{items[i]['group']}] {items[i]['name'][:25]} <--> [{items[j]['group']}] {items[j]['name'][:25]}")

print(f"Total pairs < 0.6m: same_group={same_group_count}, diff_group={diff_group_count}")
