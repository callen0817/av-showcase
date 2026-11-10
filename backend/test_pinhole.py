import pye57

filepath = r"C:\Users\ChristopherAllen\Downloads\ex\av_walkthrough\mp_e57_920-5th-Ave-5A-Interior_rkpAXm3RY7k\cloud_0.e57"
e57 = pye57.E57(filepath)
root = e57.root

im0 = root["images2D"][0]
print("Name of image:", im0["name"].value() if hasattr(im0["name"], "value") else str(im0["name"]))
print("Associated scan GUID:", im0["associatedData3DGuid"].value())

# Print images2D[0] pose
try:
    pose = im0["pose"]
    translation = pose["translation"]
    rotation = pose["rotation"]
    print("Image Pose Translation X, Y, Z:", translation["x"].value(), translation["y"].value(), translation["z"].value())
    print("Image Pose Rotation W, X, Y, Z:", rotation["w"].value(), rotation["x"].value(), rotation["y"].value(), rotation["z"].value())
except Exception as e:
    print("Failed to get image pose:", e)

# Print pinholeRepresentation
pin = im0["pinholeRepresentation"]
print("\npinholeRepresentation keys:")
for k in ['jpegImage', 'pngImage', 'imageWidth', 'imageHeight', 'focalLengthX', 'focalLengthY', 'principalPointX', 'principalPointY']:
    try:
        val = pin[k]
        print(f"  {k}: defined (Type: {type(val).__name__})")
        if hasattr(val, "value"):
            print(f"    value: {val.value()}")
    except Exception as e:
        print(f"  {k} failed: {e}")

# Check jpegImage attributes if it's a blob
try:
    jpeg = pin["jpegImage"]
    print("\njpegImage details:")
    print("  Type:", type(jpeg))
    print("  Attributes:", dir(jpeg))
    # In libe57, how do we get size or read data from a BlobNode?
    # Usually BlobNode has byteCount() and read()
    if hasattr(jpeg, "byteCount"):
        print("  byteCount method:", jpeg.byteCount)
        print("  byteCount value:", jpeg.byteCount())
except Exception as e:
    print("Failed to inspect jpegImage:", e)
