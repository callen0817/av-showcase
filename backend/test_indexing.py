import pye57

filepath = r"C:\Users\ChristopherAllen\Downloads\ex\av_walkthrough\mp_e57_920-5th-Ave-5A-Interior_rkpAXm3RY7k\cloud_0.e57"
e57 = pye57.E57(filepath)
root = e57.root

print("data3D length:", len(root["data3D"]))
print("images2D length:", len(root["images2D"]))

# Let's inspect first data3D element
d0 = root["data3D"][0]
print("\n--- root['data3D'][0] ---")
print("Type:", type(d0))
print("elementName:", d0.elementName())
print("Keys (using dir/attributes):")
# StructureNode can be treated as dictionary? Let's check keys() or similar
for k in ['guid', 'name', 'pose', 'points', 'pointCount', 'cartesianBounds']:
    try:
        print(f"  {k}: defined={d0[k].isDefined() if hasattr(d0[k], 'isDefined') else 'yes'}")
    except Exception as e:
        print(f"  {k} failed: {e}")

# Let's check rotation & translation keys
try:
    pose = d0["pose"]
    translation = pose["translation"]
    rotation = pose["rotation"]
    print("Translation X, Y, Z:", translation["x"].value(), translation["y"].value(), translation["z"].value())
    print("Rotation W, X, Y, Z:", rotation["w"].value(), rotation["x"].value(), rotation["y"].value(), rotation["z"].value())
except Exception as e:
    print("Failed to get pose:", e)

# Let's inspect first images2D element
im0 = root["images2D"][0]
print("\n--- root['images2D'][0] ---")
print("Type:", type(im0))
print("elementName:", im0.elementName())
# Let's see what keys are defined in images2D structure node
# Typically images2D has: guid, name, pose, associatedData3DGuid, pinholeRepresentation, sphericalRepresentation, visualReferenceRepresentation, etc.
# We can find out which elements are defined by checking all elements or using a try-except loop
possible_keys = [
    'guid', 'name', 'description', 'associatedData3DGuid', 'sensorPose', 'pose',
    'pinholeRepresentation', 'sphericalRepresentation', 'cylindricalRepresentation', 'visualReferenceRepresentation'
]
for k in possible_keys:
    try:
        val = im0[k]
        print(f"  {k} (Type: {type(val).__name__}): defined")
    except Exception as e:
        pass

# Let's inspect the visualReferenceRepresentation if defined
try:
    vis = im0["visualReferenceRepresentation"]
    print("  visualReferenceRepresentation keys:")
    for k in ['jpegImage', 'pngImage', 'imageWidth', 'imageHeight', 'imageMask', 'imageMaskType']:
        try:
            val = vis[k]
            print(f"    {k} (Type: {type(val).__name__})")
        except:
            pass
except Exception as e:
    pass

# Let's inspect the sphericalRepresentation if defined
try:
    vis = im0["sphericalRepresentation"]
    print("  sphericalRepresentation keys:")
    for k in ['jpegImage', 'pngImage', 'imageWidth', 'imageHeight', 'imageMask', 'imageMaskType', 'pixelWidth', 'pixelHeight']:
        try:
            val = vis[k]
            print(f"    {k} (Type: {type(val).__name__})")
        except:
            pass
except Exception as e:
    pass
