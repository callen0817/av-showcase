export class CoordsUtility {
    /**
     * Converts Python / E57 / AV Spatial Bundle canonical coordinates [x, y, z]
     * (right-handed, Z-up: +X East, +Y North, +Z Up) to Three.js Vector3 (right-handed, Y-up).
     *
     * Transformation matrix (det = +1.0, pure rotation of -90 deg about Three.js X):
     *   Three.js X =  Python X  (East)
     *   Three.js Y =  Python Z  (Up)
     *   Three.js Z = -Python Y  (South / camera-back)
     *
     * @param {number[]} arr - [x, y, z] in meters
     * @param {Object} THREE - Three.js namespace
     * @returns {Object} THREE.Vector3
     */
    static pythonToThree(arr, THREE) {
        if (!arr || arr.length < 3) return new THREE.Vector3(0, 0, 0);
        return new THREE.Vector3(arr[0], arr[2], -arr[1]);
    }

    /**
     * Converts Three.js coordinate Vector3 back to canonical Python/E57 coordinates [x, y, z].
     * Inverse: [v.x, -v.z, v.y]
     *
     * @param {Object} vec - THREE.Vector3
     * @returns {number[]} [x, y, z] in meters
     */
    static threeToPython(vec) {
        return [vec.x, -vec.z, vec.y];
    }
}
