export class CoordsUtility {
    /**
     * Converts Python/E57 coordinate array [x, y, z] to Three.js Vector3.
     * @param {number[]} arr - [x, y, z] from Python
     * @param {Object} THREE - Three.js namespace
     * @returns {Object} THREE.Vector3
     */
    static pythonToThree(arr, THREE) {
        if (!arr || arr.length < 3) return new THREE.Vector3(0, 0, 0);
        // Standard transformation:
        // Three.js X = Python X
        // Three.js Y = Python Z (vertical height)
        // Three.js Z = Python Y (horizontal depth)
        return new THREE.Vector3(arr[0], arr[2], arr[1]);
    }

    /**
     * Converts Three.js coordinate Vector3 back to Python coordinates [x, y, z].
     * @param {Object} vec - THREE.Vector3
     * @returns {number[]} [x, y, z]
     */
    static threeToPython(vec) {
        return [vec.x, vec.z, vec.y];
    }
}
