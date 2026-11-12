export class DataLoader {
    /**
     * Loads downsampled point cloud positions and colors from the binary cache (lod0.bin).
     * Maps canonical coordinates (px, py, pz) into Three.js space (px, pz, -py) to preserve det=+1.
     *
     * @param {string} cachePath - Path to cache/lod0.bin
     * @returns {Promise<{ positions: Float32Array, colors: Float32Array }|null>}
     */
    static async loadPointCloudBin(cachePath) {
        try {
            const res = await window.electronAPI.readFileBin(cachePath);
            if (!res.success) {
                console.error("Failed to read binary point cloud cache:", res.error);
                return null;
            }

            const buffer = res.data; // Received as Uint8Array
            const dataView = new DataView(buffer.buffer, buffer.byteOffset, buffer.byteLength);
            
            // Header is a 4-byte unsigned integer detailing point count
            const numPoints = dataView.getUint32(0, true);
            
            const positions = new Float32Array(numPoints * 3);
            const colors = new Float32Array(numPoints * 3);
            
            let offset = 4;
            for (let i = 0; i < numPoints; i++) {
                // Read raw Float32 coordinate inputs from Python space: [x, y, z]
                const px = dataView.getFloat32(offset, true);
                const py = dataView.getFloat32(offset + 4, true);
                const pz = dataView.getFloat32(offset + 8, true);
                
                // Map to Three.js right-handed coordinates (det = +1):
                // Three.js X =  Python X (px)
                // Three.js Y =  Python Z (pz - vertical height)
                // Three.js Z = -Python Y (-py - horizontal depth)
                positions[i * 3]     = px;
                positions[i * 3 + 1] = pz;
                positions[i * 3 + 2] = -py;
                
                // Read colors (uint8, 0-255) and normalize to float32 (0.0 - 1.0)
                colors[i * 3]     = dataView.getUint8(offset + 12) / 255.0;
                colors[i * 3 + 1] = dataView.getUint8(offset + 13) / 255.0;
                colors[i * 3 + 2] = dataView.getUint8(offset + 14) / 255.0;
                
                offset += 15;
            }
            
            return { positions, colors };
        } catch (e) {
            console.error("DataLoader error reading cache bin:", e);
            return null;
        }
    }
}
