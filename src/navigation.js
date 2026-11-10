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
        
        // Note: positions buffer is already in Three.js world space (X, Y=height, Z=depth),
        // matching pos (neighborThreePos). Restrict vertical search to [pos.y - 2.5m, pos.y - 0.8m]
        // so multi-story point clouds never pick up floors from lower stories below.
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
        // Take the median of floor slab candidates directly beneath the scanner
        const idx = Math.floor(yValues.length * 0.5);
        return yValues[idx];
    }

    /**
     * Updates 3D navigation rings inside the WebGL viewport relative to neighbors.
     * @param {Object} currentPano - The active panorama object
     * @param {Object[]} allPanos - List of all panoramas in the active scan date
     */
    updateNavMarkers(currentPano, allPanos) {
        this.renderer.navMarkersGroup.clear();
        if (!currentPano || !currentPano.neighbors) return;

        const currentThreePos = CoordsUtility.pythonToThree(currentPano.position, THREE);

        currentPano.neighbors.forEach(nid => {
            const neighbor = allPanos.find(p => p.id === nid);
            if (!neighbor) return;

            const neighborThreePos = CoordsUtility.pythonToThree(neighbor.position, THREE);

            // Resolve actual ground elevation at the neighbor position using the point cloud
            const groundY = this.findGroundHeight(neighborThreePos, this.renderer.pointCloud);
            
            // Position the marker 5cm above the resolved ground level to prevent z-fighting
            const markerPos = new THREE.Vector3(
                neighborThreePos.x - currentThreePos.x,
                groundY - currentThreePos.y + 0.05,
                neighborThreePos.z - currentThreePos.z
            );

            const isCrossFloor = neighbor.floor_id !== currentPano.floor_id;

            // Frosted Glass Ring Mesh (Cross-floor stair links highlighted in Artificial Vision Gold)
            const geometry = new THREE.RingGeometry(0.8, 1.2, 32);
            const material = new THREE.MeshBasicMaterial({ 
                color: isCrossFloor ? 0xbfa365 : 0xffffff, 
                transparent: true, 
                opacity: isCrossFloor ? 0.85 : 0.55, 
                side: THREE.DoubleSide,
                depthWrite: false
            });
            const marker = new THREE.Mesh(geometry, material);
            marker.position.copy(markerPos);
            marker.rotation.x = -Math.PI / 2; // Lay flat on the horizontal floor plane

            marker.userData = { panoId: nid, type: 'nav' };
            this.renderer.navMarkersGroup.add(marker);
            
            // Invisible larger hit-box for easier clicking interaction (Original size restored)
            const hitGeo = new THREE.CircleGeometry(2.0, 16);
            const hitMat = new THREE.MeshBasicMaterial({ visible: false });
            const hit = new THREE.Mesh(hitGeo, hitMat);
            hit.position.copy(marker.position);
            hit.rotation.copy(marker.rotation);
            hit.userData = { panoId: nid, type: 'nav' };
            this.renderer.navMarkersGroup.add(hit);
        });
    }

    /**
     * Renders keyplan networks on the 2D canvas.
     * @param {HTMLCanvasElement} canvas - Target drawing canvas
     * @param {Object} currentPano - The active panorama object
     * @param {Object[]} floorPanos - List of panoramas located on the current floor
     * @param {HTMLImageElement} [fpImg] - Optional overlay floorplan image
     * @param {Object} [fpOffset] - Calibration offset {x, y}
     * @param {number} [fpScale] - Calibration scale factor
     */
    renderKeyplan(canvas, currentPano, floorPanos, fpImg, fpOffset, fpScale, cameraYaw) {
        const ctx = canvas.getContext('2d');
        const w = canvas.parentElement.clientWidth;
        const h = canvas.parentElement.clientHeight;
        canvas.width = w;
        canvas.height = h;
        
        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = "#171717"; // Artificial Vision charcoal canvas surface
        ctx.fillRect(0, 0, w, h);

        // Render floorplan background image if uploaded
        if (fpImg) {
            const off = fpOffset || { x: 0, y: 0 };
            const fsc = fpScale || 1.0;

            const baseScale = Math.min(canvas.width / fpImg.width, canvas.height / fpImg.height) * 0.9 * fsc;
            const drawX = (canvas.width - fpImg.width * baseScale) / 2 + off.x;
            const drawY = (canvas.height - fpImg.height * baseScale) / 2 + off.y;
            ctx.globalAlpha = 0.6;
            ctx.drawImage(fpImg, drawX, drawY, fpImg.width * baseScale, fpImg.height * baseScale);
            ctx.globalAlpha = 1.0;
        }

        if (floorPanos.length === 0) {
            this.kpNodes = [];
            return;
        }

        // Calculate spatial bounds in Python space (X is index 0, Y is index 1)
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        floorPanos.forEach(p => {
            const px = p.position[0];
            const py = p.position[1];
            if (px < minX) minX = px;
            if (px > maxX) maxX = px;
            if (py < minY) minY = py;
            if (py > maxY) maxY = py;
        });

        const padding = 20;
        const scaleX = (w - padding * 2) / (maxX - minX || 1);
        const scaleY = (h - padding * 2) / (maxY - minY || 1);
        
        this.kpScale = Math.min(scaleX, scaleY);
        this.kpOffsetX = padding - minX * this.kpScale + (w - padding * 2 - (maxX - minX) * this.kpScale) / 2;
        this.kpOffsetY = padding - minY * this.kpScale + (h - padding * 2 - (maxY - minY) * this.kpScale) / 2;

        // Draw node connection paths
        ctx.strokeStyle = "rgba(255, 255, 255, 0.18)";
        ctx.lineWidth = 1;
        floorPanos.forEach(p => {
            const px = p.position[0] * this.kpScale + this.kpOffsetX;
            const py = p.position[1] * this.kpScale + this.kpOffsetY;
            if (p.neighbors) {
                p.neighbors.forEach(nid => {
                    const np = floorPanos.find(x => x.id === nid);
                    if (np) {
                        const npx = np.position[0] * this.kpScale + this.kpOffsetX;
                        const npy = np.position[1] * this.kpScale + this.kpOffsetY;
                        ctx.beginPath();
                        ctx.moveTo(px, py);
                        ctx.lineTo(npx, npy);
                        ctx.stroke();
                    }
                });
            }
        });

        // Draw individual nodes and capture canvas pixel targets
        this.kpNodes = [];
        floorPanos.forEach(p => {
            const px = p.position[0] * this.kpScale + this.kpOffsetX;
            const py = p.position[1] * this.kpScale + this.kpOffsetY;
            
            this.kpNodes.push({ id: p.id, x: px, y: py });
            const isCurrent = (currentPano && currentPano.id === p.id);
            const isNeighbor = (currentPano && currentPano.neighbors && currentPano.neighbors.includes(p.id));
            
            ctx.beginPath();
            ctx.arc(px, py, isCurrent ? 6 : (isNeighbor ? 4.5 : 3.5), 0, Math.PI * 2);
            ctx.fillStyle = isCurrent ? "#bfa365" : (isNeighbor ? "rgba(191, 163, 101, 0.85)" : "rgba(255, 255, 255, 0.45)");
            ctx.fill();
            if (isCurrent || isNeighbor) {
                ctx.strokeStyle = isCurrent ? '#ffffff' : 'rgba(255, 255, 255, 0.6)';
                ctx.lineWidth = isCurrent ? 2 : 1;
                ctx.stroke();

                if (isCurrent && cameraYaw !== undefined) {
                    const angleRad = (cameraYaw) * Math.PI / 180;
                    
                    // Draw FOV Cone (Radar wedge)
                    ctx.save();
                    ctx.beginPath();
                    ctx.moveTo(px, py);
                    const fovHalf = 25 * Math.PI / 180;
                    ctx.arc(px, py, 20, angleRad - fovHalf, angleRad + fovHalf);
                    ctx.closePath();
                    ctx.fillStyle = "rgba(191, 163, 101, 0.30)";
                    ctx.fill();
                    
                    // Draw Directional Pointer Line
                    ctx.beginPath();
                    ctx.moveTo(px, py);
                    const arrowLength = 15;
                    const ax = px + arrowLength * Math.cos(angleRad);
                    const ay = py + arrowLength * Math.sin(angleRad);
                    ctx.lineTo(ax, ay);
                    ctx.strokeStyle = "#bfa365";
                    ctx.lineWidth = 3;
                    ctx.stroke();
                    
                    // Draw Arrow Head
                    const headLen = 6;
                    ctx.beginPath();
                    ctx.moveTo(ax, ay);
                    ctx.lineTo(ax - headLen * Math.cos(angleRad - Math.PI/6), ay - headLen * Math.sin(angleRad - Math.PI/6));
                    ctx.lineTo(ax - headLen * Math.cos(angleRad + Math.PI/6), ay - headLen * Math.sin(angleRad + Math.PI/6));
                    ctx.closePath();
                    ctx.fillStyle = "#bfa365";
                    ctx.fill();
                    ctx.restore();
                }
            }
        });
    }

    /**
     * Resolves click inputs on the keyplan canvas.
     * @param {number} clkX - click X pixel relative to canvas bounding box
     * @param {number} clkY - click Y pixel relative to canvas bounding box
     * @returns {string|null} The clicked node ID, or null
     */
    handleKeyplanClick(clkX, clkY) {
        let closestId = null;
        let minDist = 324; // 18px radius squared threshold for reliable point selection
        this.kpNodes.forEach(node => {
            const d = Math.pow(node.x - clkX, 2) + Math.pow(node.y - clkY, 2);
            if (d < minDist) {
                minDist = d;
                closestId = node.id;
            }
        });
        return closestId;
    }
}
