import * as THREE from 'three';
import { CoordsUtility } from './coords.js';

export class WalkthroughNavigation {
    /**
     * Initializes navigation controls linked to the active WebGL renderer.
     * @param {WalkthroughRenderer} renderer - The active renderer instance
     */
    constructor(renderer) {
        this.renderer = renderer;
        this.kpNodes = []; // Canvas pixel coordinates for click handling
        this.kpScale = 1.0;
        this.kpOffsetX = 0;
        this.kpOffsetY = 0;
        this.cachedKeyplanBounds = null;
        this.hoveredNode = null;
    }

    /**
     * Resolves the actual ground elevation directly below a 3D position by analyzing local point cloud points.
     * @param {Object} pos - target THREE.Vector3 position
     * @param {Object} pointCloud - THREE.Points point cloud instance
     * @param {number} [defaultOffset=1.6] - fallback height offset if no points are found
     * @returns {number} resolved vertical ground Y coordinate
     */
    findGroundHeight(pos, pointCloud, defaultOffset = 1.6) {
        if (!pointCloud || !pointCloud.geometry) return pos.y - defaultOffset;
        
        const positions = pointCloud.geometry.attributes.position.array;
        const count = positions.length / 3;
        
        const R = 0.75;
        const R_sq = R * R;
        
        let yValues = [];
        const stride = Math.max(1, Math.floor(count / 50000));
        
        const minGroundY = pos.y - 2.5;
        const maxGroundY = pos.y - 0.8;
        
        for (let i = 0; i < count; i += stride) {
            const px = positions[i * 3];
            const py = positions[i * 3 + 1];
            const pz = positions[i * 3 + 2];
            
            if (py < minGroundY || py > maxGroundY) continue;
            
            const dx = px - pos.x;
            const dz = pz - pos.z;
            const distSq = dx * dx + dz * dz;
            
            if (distSq < R_sq) {
                yValues.push(py);
            }
        }
        
        if (yValues.length === 0) {
            return pos.y - defaultOffset;
        }
        
        yValues.sort((a, b) => a - b);
        const idx = Math.floor(yValues.length * 0.5);
        return yValues[idx];
    }

    /**
     * Updates 3D navigation rings inside the WebGL viewport relative to neighbors.
     * @param {Object} currentPano - The active panorama object
     * @param {Object[]} allPanos - List of all panoramas in the active scan
     */
    updateNavMarkers(currentPano, allPanos) {
        this.renderer.navMarkersGroup.clear();
        if (!currentPano || !currentPano.neighbors) return;

        const currentThreePos = CoordsUtility.pythonToThree(currentPano.position, THREE);

        currentPano.neighbors.forEach(nid => {
            const neighbor = allPanos.find(p => p.id === nid);
            if (!neighbor) return;

            const neighborThreePos = CoordsUtility.pythonToThree(neighbor.position, THREE);
            const groundY = this.findGroundHeight(neighborThreePos, this.renderer.pointCloud);
            
            const markerPos = new THREE.Vector3(
                neighborThreePos.x - currentThreePos.x,
                groundY - currentThreePos.y + 0.05,
                neighborThreePos.z - currentThreePos.z
            );

            const isCrossFloor = neighbor.floor_id !== currentPano.floor_id || neighbor.stair_link === true;

            // Glass Ring Mesh: normal is soft glass white; stair transitions use Artificial Vision Gold (#BAA164)
            const geometry = new THREE.RingGeometry(0.8, 1.2, 32);
            const material = new THREE.MeshBasicMaterial({ 
                color: isCrossFloor ? 0xbaa164 : 0xfcfbf8, 
                transparent: true, 
                opacity: isCrossFloor ? 0.90 : 0.65, 
                side: THREE.DoubleSide,
                depthWrite: false
            });
            const marker = new THREE.Mesh(geometry, material);
            marker.position.copy(markerPos);
            marker.rotation.x = -Math.PI / 2; // Flat on the floor

            marker.userData = { panoId: nid, type: 'nav', isCrossFloor };
            this.renderer.navMarkersGroup.add(marker);
            
            // Invisible larger hit-box for easy raycast selection
            const hitGeo = new THREE.CircleGeometry(2.0, 16);
            const hitMat = new THREE.MeshBasicMaterial({ visible: false });
            const hit = new THREE.Mesh(hitGeo, hitMat);
            hit.position.copy(marker.position);
            hit.rotation.copy(marker.rotation);
            hit.userData = { panoId: nid, type: 'nav' };
            this.renderer.navMarkersGroup.add(hit);
        });
        this.renderer.requestRender();
    }

    /**
     * Renders keyplan networks on the 2D canvas with DPR sharpness and North-up orientation.
     * Supports both auto-generated metric wall-slice images (world_bounds) and legacy uploads.
     *
     * @param {HTMLCanvasElement} canvas
     * @param {Object} currentPano
     * @param {Object[]} floorPanos
     * @param {HTMLImageElement} [fpImg]
     * @param {Object} [fpOffset]
     * @param {number} [fpScale]
     * @param {number} [cameraYaw] - degrees compass azimuth (0 = +X East, 90 = +Y North)
     * @param {Object} [worldBounds] - { min_x, max_x, min_y, max_y, meters_per_pixel }
     */
    renderKeyplan(canvas, currentPano, floorPanos, fpImg, fpOffset, fpScale, cameraYaw, worldBounds) {
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        const parent = canvas.parentElement;
        const w = (parent ? parent.clientWidth : canvas.clientWidth) || 300;
        const h = (parent ? parent.clientHeight : canvas.clientHeight) || 200;

        canvas.width = Math.floor(w * dpr);
        canvas.height = Math.floor(h * dpr);
        canvas.style.width = `${w}px`;
        canvas.style.height = `${h}px`;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = "#121218"; // Apple Glass dark base
        ctx.fillRect(0, 0, w, h);

        if (!floorPanos || floorPanos.length === 0) {
            this.kpNodes = [];
            return;
        }

        // Compute coordinate transformation.
        // North-up canvas orientation: +X points right, +Y points UP.
        // Canvas pixel mapping:
        //   px =  (X - min_x) * scale + marginX
        //   py = -(Y - min_y) * scale + h - marginY   ==  -Y * scale + offsetY
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        if (worldBounds && typeof worldBounds.min_x === 'number') {
            minX = worldBounds.min_x;
            maxX = worldBounds.max_x;
            minY = worldBounds.min_y;
            maxY = worldBounds.max_y;
        } else {
            floorPanos.forEach(p => {
                const x = p.position[0];
                const y = p.position[1];
                if (x < minX) minX = x;
                if (x > maxX) maxX = x;
                if (y < minY) minY = y;
                if (y > maxY) maxY = y;
            });
            // Ensure minimum padding around lone stations
            if (maxX - minX < 2.0) { minX -= 2.0; maxX += 2.0; }
            if (maxY - minY < 2.0) { minY -= 2.0; maxY += 2.0; }
        }

        const padding = 16;
        const scaleX = (w - padding * 2) / Math.max(0.1, (maxX - minX));
        const scaleY = (h - padding * 2) / Math.max(0.1, (maxY - minY));
        this.kpScale = Math.min(scaleX, scaleY);

        const spanW = (maxX - minX) * this.kpScale;
        const spanH = (maxY - minY) * this.kpScale;
        this.kpOffsetX = padding - minX * this.kpScale + (w - padding * 2 - spanW) / 2;
        // With +Y up: py = -Y * s + offY. At Y = maxY, py = margin = (h - spanH)/2
        // -> offY = margin + maxY * s
        this.kpOffsetY = (h - spanH) / 2 + maxY * this.kpScale;

        this.cachedKeyplanBounds = { minX, maxX, minY, maxY, w, h };

        // Helper: Python (X, Y) -> Canvas (px, py)
        const toCanvas = (x, y) => ({
            x: x * this.kpScale + this.kpOffsetX,
            y: -y * this.kpScale + this.kpOffsetY
        });

        // 1. Draw calibrated floorplan image if available
        if (fpImg) {
            ctx.save();
            if (worldBounds && typeof worldBounds.min_x === 'number') {
                // Metric calibration: image bounds [min_x, max_x, min_y, max_y]
                const tl = toCanvas(worldBounds.min_x, worldBounds.max_y);
                const br = toCanvas(worldBounds.max_x, worldBounds.min_y);
                ctx.globalAlpha = 0.85;
                ctx.drawImage(fpImg, tl.x, tl.y, br.x - tl.x, br.y - tl.y);
            } else {
                // Legacy uncalibrated upload with fpOffset & fpScale
                const off = fpOffset || { x: 0, y: 0 };
                const fsc = fpScale || 1.0;
                const baseScale = Math.min(w / fpImg.width, h / fpImg.height) * 0.9 * fsc;
                const drawX = (w - fpImg.width * baseScale) / 2 + off.x;
                const drawY = (h - fpImg.height * baseScale) / 2 + off.y;
                ctx.globalAlpha = 0.65;
                ctx.drawImage(fpImg, drawX, drawY, fpImg.width * baseScale, fpImg.height * baseScale);
            }
            ctx.restore();
        }

        // 2. Draw navigation edges
        ctx.strokeStyle = "rgba(186, 161, 100, 0.28)";
        ctx.lineWidth = 1;
        floorPanos.forEach(p => {
            const p1 = toCanvas(p.position[0], p.position[1]);
            if (p.neighbors) {
                p.neighbors.forEach(nid => {
                    const np = floorPanos.find(x => x.id === nid);
                    if (np && np.id > p.id) { // draw each edge once
                        const p2 = toCanvas(np.position[0], np.position[1]);
                        ctx.beginPath();
                        ctx.moveTo(p1.x, p1.y);
                        ctx.lineTo(p2.x, p2.y);
                        ctx.stroke();
                    }
                });
            }
        });

        // 3. Draw stations
        this.kpNodes = [];
        floorPanos.forEach(p => {
            const pt = toCanvas(p.position[0], p.position[1]);
            this.kpNodes.push({ id: p.id, x: pt.x, y: pt.y, world: p.position });
            const isCurrent = (currentPano && currentPano.id === p.id);
            const isNeighbor = (currentPano && currentPano.neighbors && currentPano.neighbors.includes(p.id));
            const isStair = p.stair_link === true;

            ctx.beginPath();
            const radius = isCurrent ? 6.5 : (isNeighbor ? 4.5 : 3.5);
            ctx.arc(pt.x, pt.y, radius, 0, Math.PI * 2);
            
            if (isCurrent) {
                ctx.fillStyle = "#BAA164"; // Gold active station
            } else if (isStair) {
                ctx.fillStyle = "#E5C983"; // Gold stair transition
            } else if (isNeighbor) {
                ctx.fillStyle = "rgba(229, 201, 131, 0.85)";
            } else {
                ctx.fillStyle = "rgba(252, 251, 248, 0.45)";
            }
            ctx.fill();

            if (isCurrent || isNeighbor || isStair) {
                ctx.strokeStyle = isCurrent ? '#FCFBF8' : 'rgba(186, 161, 100, 0.75)';
                ctx.lineWidth = isCurrent ? 2 : 1;
                ctx.stroke();
            }

            // Radar viewing wedge on active station
            // Compass azimuth: 0 = +X (East, right = 0 rad), 90 = +Y (North, up = -π/2 rad)
            // Canvas standard: angle = -cameraYaw * π / 180
            if (isCurrent && cameraYaw !== undefined) {
                const angleRad = -cameraYaw * Math.PI / 180;
                ctx.save();
                ctx.beginPath();
                ctx.moveTo(pt.x, pt.y);
                const fovHalf = 28 * Math.PI / 180;
                ctx.arc(pt.x, pt.y, 22, angleRad - fovHalf, angleRad + fovHalf);
                ctx.closePath();
                ctx.fillStyle = "rgba(186, 161, 100, 0.35)";
                ctx.fill();

                // Direction pointer
                ctx.beginPath();
                ctx.moveTo(pt.x, pt.y);
                const arrowLength = 16;
                const ax = pt.x + arrowLength * Math.cos(angleRad);
                const ay = pt.y + arrowLength * Math.sin(angleRad);
                ctx.lineTo(ax, ay);
                ctx.strokeStyle = "#BAA164";
                ctx.lineWidth = 2.5;
                ctx.stroke();
                ctx.restore();
            }
        });

        // 4. Hover indicator ring
        if (this.hoveredNode) {
            ctx.save();
            ctx.beginPath();
            ctx.arc(this.hoveredNode.x, this.hoveredNode.y, 9, 0, Math.PI * 2);
            ctx.strokeStyle = "rgba(186, 161, 100, 0.9)";
            ctx.lineWidth = 1.5;
            ctx.setLineDash([3, 3]);
            ctx.stroke();
            ctx.restore();
        }
    }

    /**
     * Converts a canvas pixel click into world coordinates (X, Y) and finds the closest station
     * on the active floor within maxWorldDist meters (default 8.0 m), enabling click-anywhere teleport.
     *
     * @param {number} clkX - click X in CSS pixels relative to canvas
     * @param {number} clkY - click Y in CSS pixels relative to canvas
     * @param {Object[]} [floorPanos] - panos on the current floor
     * @param {number} [maxWorldDist=8.0] - maximum snap distance in meters
     * @returns {string|null} The nearest node ID, or null if beyond threshold
     */
    handleKeyplanClick(clkX, clkY, floorPanos = null, maxWorldDist = 8.0) {
        if (!this.kpScale || this.kpScale <= 0) return null;

        // Invert canvas projection to world space:
        // px =  X * s + offX  ->  X = (px - offX) / s
        // py = -Y * s + offY  ->  Y = (offY - py) / s
        const worldX = (clkX - this.kpOffsetX) / this.kpScale;
        const worldY = (this.kpOffsetY - clkY) / this.kpScale;

        const panos = floorPanos || this.kpNodes.map(n => ({ id: n.id, position: n.world }));
        if (!panos || panos.length === 0) return null;

        let closestId = null;
        let minDistSq = maxWorldDist * maxWorldDist;

        panos.forEach(p => {
            const dx = p.position[0] - worldX;
            const dy = p.position[1] - worldY;
            const d2 = dx * dx + dy * dy;
            if (d2 < minDistSq) {
                minDistSq = d2;
                closestId = p.id;
            }
        });

        return closestId;
    }

    /**
     * Updates hover preview state when moving over the keyplan.
     */
    handleKeyplanHover(clkX, clkY) {
        if (this.kpNodes.length === 0) {
            this.hoveredNode = null;
            return null;
        }
        let closest = null;
        let minDistSq = 20 * 20; // 20px screen distance
        this.kpNodes.forEach(node => {
            const d2 = Math.pow(node.x - clkX, 2) + Math.pow(node.y - clkY, 2);
            if (d2 < minDistSq) {
                minDistSq = d2;
                closest = node;
            }
        });
        this.hoveredNode = closest;
        return closest;
    }
}
