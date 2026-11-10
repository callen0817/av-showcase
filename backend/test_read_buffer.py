import pye57

filepath = r"C:\Users\ChristopherAllen\Downloads\ex\av_walkthrough\mp_e57_920-5th-Ave-5A-Interior_rkpAXm3RY7k\cloud_0.e57"
e57 = pye57.E57(filepath)
root = e57.root

im0 = root["images2D"][0]
pin = im0["pinholeRepresentation"]
jpeg = pin["jpegImage"]

try:
    arr = jpeg.read_buffer()
    print("Array type:", type(arr))
    print("Array shape:", arr.shape)
    print("Array dtype:", arr.dtype)
    
    data = arr.tobytes()
    print("Bytes len:", len(data))
    
    with open("backend/test_extracted.jpg", "wb") as f:
        f.write(data)
        
    print("Saved backend/test_extracted.jpg successfully! File size is:", len(data))
except Exception as e:
    print("Failed to use read_buffer:", e)
