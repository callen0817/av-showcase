import pye57

filepath = r"C:\Users\ChristopherAllen\Downloads\ex\av_walkthrough\mp_e57_920-5th-Ave-5A-Interior_rkpAXm3RY7k\cloud_0.e57"
e57 = pye57.E57(filepath)
root = e57.root

im0 = root["images2D"][0]
pin = im0["pinholeRepresentation"]
jpeg = pin["jpegImage"]
size = jpeg.byteCount()
print(f"JPEG size: {size} bytes")

# Try pattern 1: jpeg.read() with no args
try:
    data = jpeg.read()
    print("Pattern 1 (no args) succeeded! Data type:", type(data), "len:", len(data))
except Exception as e:
    print("Pattern 1 failed:", e)

# Try pattern 2: read into a buffer
try:
    buf = bytearray(size)
    # in C++ E57: void read(uint8_t* buf, int64_t start, int64_t count)
    # In pye57/pybind11: maybe it is binded as jpeg.read(start, count) -> bytes
    data = jpeg.read(0, size)
    print("Pattern 2 (read(0, size)) succeeded! Data type:", type(data), "len:", len(data))
    # Let's save a test file to verify it's a valid JPEG
    with open("backend/test_extracted.jpg", "wb") as f:
        f.write(data)
    print("Successfully saved backend/test_extracted.jpg")
except Exception as e:
    print("Pattern 2 failed:", e)

# Try pattern 3: inspect read methods signatures or arguments
import inspect
for method_name in ['read', 'read_buffer']:
    try:
        method = getattr(jpeg, method_name)
        print(f"\nIntrospecting method: {method_name}")
        print("  doc:", method.__doc__)
    except Exception as e:
        print("  Failed to introspect:", e)
