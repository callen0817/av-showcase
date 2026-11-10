export class AutoStackManager {
    /**
     * Evaluates spatial proximity in the target scan pool to find the nearest match.
     * Standardized signature permits future swap-ins of spatial indexes (e.g. KD-Tree)
     * without modifications to the caller logic.
     * 
     * @param {Object} referencePano - Pano from the previous scan date
     * @param {Object[]} targetScanPanos - Panos in the target scan date
     * @param {number} maxDistance - Spatial distance threshold (read from project settings)
     * @returns {Object|null} Nearest target panorama, or null if threshold exceeded (abort transit)
     */
    static findNearestPano(referencePano, targetScanPanos, maxDistance = 10.0) {
        if (!referencePano || !targetScanPanos || targetScanPanos.length === 0) {
            return null;
        }

        const refPos = referencePano.position; // Python space: [x, y, z]
        const refFloor = referencePano.floor_id;

        // Rule 1: Prioritize panoramas within vertical story tolerance (|dz| <= 1.8m) or matching floor_id
        const sameElevationPanos = targetScanPanos.filter(p => Math.abs(p.position[2] - refPos[2]) <= 1.8);
        const sameFloorPanos = targetScanPanos.filter(p => p.floor_id === refFloor);
        const searchPool = sameElevationPanos.length > 0
            ? sameElevationPanos
            : (sameFloorPanos.length > 0 ? sameFloorPanos : targetScanPanos);

        let closestPano = null;
        let minDist = Infinity;

        // Abstracted search pool loops. Swappable with spatial indexes.
        searchPool.forEach(pano => {
            const dx = pano.position[0] - refPos[0];
            const dy = pano.position[1] - refPos[1];
            const dz = pano.position[2] - refPos[2];
            const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
            
            if (dist < minDist) {
                minDist = dist;
                closestPano = pano;
            }
        });

        // Explicit fallback limit check to prevent jumping into unrelated scan sectors
        if (minDist > maxDistance) {
            console.warn(`AutoStack target nearest node is ${minDist.toFixed(2)}m away (limit: ${maxDistance}m). Aborting.`);
            return null;
        }

        return closestPano;
    }

    /**
     * Finds the panorama on a target floor that is horizontally closest (X, Y) to the current position,
     * enabling Matterport / NavVis IVION style vertical floor teleportation directly above/below.
     */
    static findNearestHorizontalPano(referencePano, targetFloorPanos) {
        if (!referencePano || !targetFloorPanos || targetFloorPanos.length === 0) {
            return null;
        }
        const refPos = referencePano.position;
        let closestPano = null;
        let minHorizDistSq = Infinity;

        targetFloorPanos.forEach(pano => {
            const dx = pano.position[0] - refPos[0];
            const dy = pano.position[1] - refPos[1];
            const distSq = dx * dx + dy * dy;
            if (distSq < minHorizDistSq) {
                minHorizDistSq = distSq;
                closestPano = pano;
            }
        });

        return closestPano;
    }
}
