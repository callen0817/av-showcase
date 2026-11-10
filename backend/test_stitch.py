import os
import pye57
import numpy as np
from scipy.spatial.transform import Rotation
from PIL import Image

def stitch_scan_panos(filepath, scan_index):
    print(f"Stitching panoramas for scan index {scan_index} from {filepath}")
    e57 = pye57.E57(filepath)
    root = e57.root
    
    # Get the GUID of the target scan
    target_scan = root["data3D"][scan_index]
    target_guid = target_scan["guid"].value()
    print(f"Target Scan GUID: {target_guid}")
    
    # Find all images associated with this GUID
    scan_images = []
    images2d = root["images2D"]
    for i in range(images2d.childCount()):
        im = images2d[i]
        if im["associatedData3DGuid"].value() == target_guid:
            scan_images.append(im)
            
    print(f"Found {len(scan_images)} images associated with this scan.")
    if len(scan_images) != 6:
        print("Error: Expected exactly 6 images (cubemap faces) for this scan.")
        return
        
    # Load the 6 images and their rotations
    faces = []
    for im in scan_images:
        name = im["name"].value()
        pose = im["pose"]
        translation = pose["translation"]
        rotation = pose["rotation"]
        
        # Get rotation matrix (quaternion order in pye57 is w,x,y,z, but scipy expects x,y,z,w)
        qx = rotation["x"].value()
        qy = rotation["y"].value()
        qz = rotation["z"].value()
        qw = rotation["w"].value()
        
        r = Rotation.from_quat([qx, qy, qz, qw])
        rot_matrix = r.as_matrix()
        
        # Load JPEG image
        import io
        jpeg_node = im["pinholeRepresentation"]["jpegImage"]
        arr = jpeg_node.read_buffer()
        img = Image.open(io.BytesIO(arr.tobytes())).convert("RGB")
        
        # Verify sizes
        w = im["pinholeRepresentation"]["imageWidth"].value()
        h = im["pinholeRepresentation"]["imageHeight"].value()
        cx = im["pinholeRepresentation"]["principalPointX"].value()
        cy = im["pinholeRepresentation"]["principalPointY"].value()
        # Focal length for a 90 degree field of view is half the width
        f = w / 2.0
        
        faces.append({
            "name": name,
            "img_array": np.array(img),
            "rot_matrix": rot_matrix,
            "width": w,
            "height": h,
            "cx": cx,
            "cy": cy,
            "f": f
        })
        
    # Stitch into equirectangular panorama
    # Output size: 2048 x 1024
    out_w, out_h = 2048, 1024
    pano = np.zeros((out_h, out_w, 3), dtype=np.uint8)
    
    # Vectorized target grid coordinates
    ys, xs = np.mgrid[0:out_h, 0:out_w]
    
    # Map to spherical coordinates
    # Latitude (phi) from pi/2 (top) to -pi/2 (bottom)
    phi = (0.5 - ys / out_h) * np.pi
    # Longitude (theta) from -pi (left) to pi (right)
    theta = (xs / out_w - 0.5) * 2.0 * np.pi
    
    # 3D unit direction vectors in world coordinate system
    vx = np.cos(phi) * np.cos(theta)
    vy = np.cos(phi) * np.sin(theta)
    vz = np.sin(phi)
    
    # Shape: (out_h, out_w, 3)
    v_world = np.stack([vx, vy, vz], axis=-1)
    
    # For each pixel, find which face it belongs to
    # We will compute the local camera coordinates for each face
    for face in faces:
        # v_local = R_T * v_world
        # rot_matrix is the mapping from camera local to world, so its transpose maps world to camera local
        R_T = face["rot_matrix"].T
        
        # Rotate world vectors into camera local space
        # shape: (out_h, out_w, 3)
        v_local = np.tensordot(v_world, R_T, axes=(-1, 1))
        
        # Local camera coordinates: X, Y, Z
        lx = v_local[..., 0]
        ly = v_local[..., 1]
        lz = v_local[..., 2]
        
        # The camera looks down the +Z axis (lz > 0)
        # Check field of view bounds
        with np.errstate(divide='ignore', invalid='ignore'):
            u = face["cx"] + face["f"] * lx / lz
            v = face["cy"] - face["f"] * ly / lz
            
        mask = (lz > 0) & (u >= 0) & (u < face["width"]) & (v >= 0) & (v < face["height"])
        
        if np.any(mask):
            # Sample pixels from face image
            u_idx = u[mask].astype(np.int32)
            v_idx = v[mask].astype(np.int32)
            pano[mask] = face["img_array"][v_idx, u_idx]
            
    # Save the output image
    Image.fromarray(pano).save("backend/stitched_pano.jpg")
    print("Stitched panorama successfully saved to backend/stitched_pano.jpg")

if __name__ == "__main__":
    stitch_scan_panos(r"C:\Users\ChristopherAllen\Downloads\ex\av_walkthrough\mp_e57_920-5th-Ave-5A-Interior_rkpAXm3RY7k\cloud_0.e57", 0)
