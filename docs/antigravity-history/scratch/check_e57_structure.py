import pye57

e57_path = r"C:\Users\ChristopherAllen\OneDrive - Reisource\_INTERNAL\808\808_Brannan_LB_E57wP-002.e57"
e57 = pye57.E57(e57_path)

data3d = e57.root['data3D']
images2d = e57.root['images2D']

print(f"data3D count: {data3d.childCount()}")
print(f"images2D count: {images2d.childCount()}")

d0 = data3d[0]
print("data3D[0] keys:", [d0.get(i).elementName() for i in range(d0.childCount())] if hasattr(d0, 'childCount') else 'none')
if d0.isDefined('guid'):
    print("data3D[0] guid:", d0['guid'].value())
if d0.isDefined('name'):
    print("data3D[0] name:", d0['name'].value())
if d0.isDefined('pose'):
    p = d0['pose']
    print("data3D[0] pose:", p['translation']['x'].value(), p['translation']['y'].value(), p['translation']['z'].value())

print("\nExamining first 5 images2D:")
for i in range(5):
    im = images2d[i]
    name = im['name'].value() if im.isDefined('name') else ''
    guid = im['guid'].value() if im.isDefined('guid') else ''
    assoc = im['associatedData3DGuid'].value() if im.isDefined('associatedData3DGuid') else 'NONE'
    pose = im['pose']
    tx, ty, tz = pose['translation']['x'].value(), pose['translation']['y'].value(), pose['translation']['z'].value()
    print(f"im[{i}]: name={name} guid={guid} assocData3D={assoc} pos=({tx:.2f}, {ty:.2f}, {tz:.2f})")
