import * as THREE from 'three';

export class WalkthroughRenderer {
    /**
     * Initializes the Three.js viewport in the container element.
     * @param {HTMLElement} container - DOM container element
     */
    constructor(container) {
        this.container = container;
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.panoSphere = null;
        this.pointCloud = null;
        this.navMarkersGroup = null;

        // Efficiency & memory management: dirty-flag rendering and LRU texture cache
        this.needsRender = true;
        this.textureCache = new Map(); // key (imgPath) -> { texture, lastUsed }
        this.maxCachedTextures = 12;

        this.init();
    }

    init() {
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(75, this.container.clientWidth / this.container.clientHeight, 0.1, 1000);
        this.camera.position.set(0, 0, 0.01);

        this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
        if ('outputColorSpace' in this.renderer) {
            this.renderer.outputColorSpace = THREE.SRGBColorSpace;
        }
        this.container.appendChild(this.renderer.domElement);

        // Panorama Sphere Setup (Inverted Sphere)
        // geometry.scale(-1, 1, 1) + geometry.rotateY(Math.PI) once at init:
        // Texture col u=0.5 (+X in ASTM E2807 Section 6.5.4) maps to Three.js (+1, 0, 0).
        // Texture col u=0.25 (+Y in ASTM E2807 Section 6.5.4) maps to Three.js (0, 0, -1).
        const geometry = new THREE.SphereGeometry(50, 60, 40);
        geometry.scale(-1, 1, 1);
        geometry.rotateY(Math.PI);

        // Default neutral grid texture
        const size = 512;
        const canvas = document.createElement('canvas');
        canvas.width = size; canvas.height = size;
        const context = canvas.getContext('2d');
        context.fillStyle = '#121218';
        context.fillRect(0, 0, size, size);
        context.strokeStyle = 'rgba(186, 161, 100, 0.2)';
        for (let i = 0; i < size; i += 32) {
            context.beginPath(); context.moveTo(i, 0); context.lineTo(i, size); context.stroke();
            context.beginPath(); context.moveTo(0, i); context.lineTo(size, i); context.stroke();
        }
        const defaultTex = new THREE.CanvasTexture(canvas);
        const material = new THREE.MeshBasicMaterial({ map: defaultTex });
        
        this.panoSphere = new THREE.Mesh(geometry, material);
        this.scene.add(this.panoSphere);

        // Group for 3D navigation markers
        this.navMarkersGroup = new THREE.Group();
        this.scene.add(this.navMarkersGroup);

        this.animate();
    }

    requestRender() {
        this.needsRender = true;
    }

    /**
     * Loads and displays the panoramic texture with LRU caching.
     * @param {string} imgPath - File path / blob URL
     * @param {function} [onLoaded] - Optional callback
     */
    updatePanoTexture(imgPath, onLoaded) {
        if (this.textureCache.has(imgPath)) {
            const entry = this.textureCache.get(imgPath);
            entry.lastUsed = Date.now();
            this.panoSphere.material.map = entry.texture;
            this.panoSphere.material.needsUpdate = true;
            this.requestRender();
            if (onLoaded) onLoaded(entry.texture);
            return;
        }

        const loader = new THREE.TextureLoader();
        loader.load(imgPath, (texture) => {
            if ('colorSpace' in texture) {
                texture.colorSpace = THREE.SRGBColorSpace;
            }
            texture.generateMipmaps = true;
            texture.minFilter = THREE.LinearMipmapLinearFilter;

            this._cacheTexture(imgPath, texture);
            this.panoSphere.material.map = texture;
            this.panoSphere.material.needsUpdate = true;
            this.requestRender();
            if (onLoaded) onLoaded(texture);
        }, undefined, (err) => {
            console.error("Failed to load panorama texture:", imgPath, err);
        });
    }

    /**
     * Prefetches a neighboring panorama texture into the LRU cache.
     * @param {string} imgPath
     */
    prefetchPanoTexture(imgPath) {
        if (!imgPath || this.textureCache.has(imgPath)) return;
        const loader = new THREE.TextureLoader();
        loader.load(imgPath, (texture) => {
            if ('colorSpace' in texture) texture.colorSpace = THREE.SRGBColorSpace;
            this._cacheTexture(imgPath, texture);
        });
    }

    _cacheTexture(key, texture) {
        if (this.textureCache.size >= this.maxCachedTextures) {
            let oldestKey = null;
            let oldestTime = Infinity;
            for (const [k, v] of this.textureCache.entries()) {
                if (v.lastUsed < oldestTime) {
                    oldestTime = v.lastUsed;
                    oldestKey = k;
                }
            }
            if (oldestKey && oldestKey !== key) {
                const evicted = this.textureCache.get(oldestKey);
                if (evicted && evicted.texture) {
                    if (this.panoSphere.material.map !== evicted.texture) {
                        evicted.texture.dispose();
                    }
                }
                this.textureCache.delete(oldestKey);
            }
        }
        this.textureCache.set(key, { texture, lastUsed: Date.now() });
    }

    /**
     * Recreates the points geometry and material in Three.js and adds it to the scene.
     * @param {Float32Array} positions - point coordinates (Three.js space)
     * @param {Float32Array} colors - point color decimals
     */
    updatePointCloud(positions, colors) {
        this.unloadPointCloud();

        if (!positions || positions.length === 0) return;

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        const material = new THREE.PointsMaterial({
            size: 0.12,
            vertexColors: true,
            sizeAttenuation: true
        });

        this.pointCloud = new THREE.Points(geometry, material);
        this.pointCloud.visible = false;
        this.scene.add(this.pointCloud);
        this.requestRender();
    }

    unloadPointCloud() {
        if (this.pointCloud) {
            this.scene.remove(this.pointCloud);
            if (this.pointCloud.geometry) {
                this.pointCloud.geometry.dispose();
            }
            if (this.pointCloud.material) {
                this.pointCloud.material.dispose();
            }
            this.pointCloud = null;
            this.requestRender();
        }
    }

    /**
     * Translates the point cloud relative to the camera centered at (0,0,0)
     * @param {number[]} panoPos - python world coordinates [x, y, z] of the current panorama
     */
    alignPointCloud(panoPos) {
        if (!this.pointCloud) return;
        // Right-handed det=+1 system:
        // Three.js X =  Python X  -> offset is -panoPos[0]
        // Three.js Y =  Python Z  -> offset is -panoPos[2]
        // Three.js Z = -Python Y  -> offset is +panoPos[1]
        this.pointCloud.position.set(-panoPos[0], -panoPos[2], panoPos[1]);
        this.requestRender();
    }

    /**
     * Aligns the panorama sphere to station orientation.
     * Maps canonical quaternion [qx, qy, qz, qw] into Three.js: (qx, qz, -qy, qw).
     * @param {number[]} rotation - [qx, qy, qz, qw]
     * @param {boolean} [isLevel=true] - when true, preserves vertical alignment using yaw-only +euler.y
     */
    alignPanoSphere(rotation, isLevel = true) {
        if (!this.panoSphere) return;
        if (rotation && rotation.length === 4) {
            // Three.js Y = Canonical Z, Three.js Z = -Canonical Y
            const q = new THREE.Quaternion(rotation[0], rotation[2], -rotation[1], rotation[3]).normalize();
            
            if (isLevel) {
                // Isolate yaw about world vertical axis (0, 1, 0)
                const euler = new THREE.Euler().setFromQuaternion(q, 'YXZ');
                const uprightQ = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), euler.y);
                this.panoSphere.quaternion.copy(uprightQ);
            } else {
                this.panoSphere.quaternion.copy(q);
            }
        } else {
            this.panoSphere.quaternion.set(0, 0, 0, 1);
        }
        this.requestRender();
    }

    /**
     * Updates camera viewing direction vectors.
     * Compass azimuth: lon=0 looks at +X (East, Three.js +X), lon=90 looks at +Y (North, Three.js -Z).
     *
     * @param {number} lat - latitude/pitch angle in degrees [-85, 85]
     * @param {number} lon - longitude/yaw angle in degrees [0, 360]
     */
    updateCamera(lat, lon) {
        const phi = THREE.MathUtils.degToRad(90 - lat);
        const theta = THREE.MathUtils.degToRad(lon);

        const target = new THREE.Vector3();
        target.x = 50 * Math.sin(phi) * Math.cos(theta);
        target.y = 50 * Math.cos(phi);
        target.z = -50 * Math.sin(phi) * Math.sin(theta);

        this.camera.lookAt(target);
        this.requestRender();
    }

    resize() {
        if (!this.renderer || !this.camera) return;
        const w = this.container.clientWidth;
        const h = this.container.clientHeight;
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h);
        this.requestRender();
    }

    animate() {
        requestAnimationFrame(this.animate.bind(this));
        if (this.needsRender && this.renderer && this.scene && this.camera) {
            this.renderer.render(this.scene, this.camera);
            this.needsRender = false;
        }
    }
}
