export class AutoStackManager {
    /**
     * Evaluates spatial proximity in the target scan pool to find the nearest match.
     * Enforces strict 4D historical time-travel continuity:
     *   - Priority 1: Same vertical story tolerance (|dz| <= 1.8m)
     *   - Priority 2: Same floor_id
     *   - Threshold: maxDistance meters
     *
     * @param {Object} referencePano - Pano from the current/previous scan date
     * @param {Object[]} targetScanPanos - Panos in the target scan date
     * @param {number} maxDistance - Spatial distance threshold (default 10.0m)
     * @returns {Object|null} Nearest target panorama, or null if threshold exceeded
     */
    static findNearestPano(referencePano, targetScanPanos, maxDistance = 10.0) {
        const res = this.findNearestPanoWithDistance(referencePano, targetScanPanos, maxDistance);
        return res ? res.pano : null;
    }

    /**
     * Finds nearest panorama and reports its distance (useful for threshold alerts).
     */
    static findNearestPanoWithDistance(referencePano, targetScanPanos, maxDistance = 10.0) {
        if (!referencePano || !targetScanPanos || targetScanPanos.length === 0) {
            return null;
        }

        const refPos = referencePano.position;
        const refFloor = referencePano.floor_id;

        const sameElevationPanos = targetScanPanos.filter(p => Math.abs(p.position[2] - refPos[2]) <= 1.8);
        const sameFloorPanos = targetScanPanos.filter(p => p.floor_id === refFloor);
        const searchPool = sameElevationPanos.length > 0
            ? sameElevationPanos
            : (sameFloorPanos.length > 0 ? sameFloorPanos : targetScanPanos);

        let closestPano = null;
        let minDist = Infinity;

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

        if (minDist > maxDistance) {
            return { pano: null, distance: minDist, bestOutOfRange: closestPano };
        }

        return { pano: closestPano, distance: minDist, bestOutOfRange: null };
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
