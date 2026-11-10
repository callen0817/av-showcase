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

        this.init();
    }

    init() {
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(75, this.container.clientWidth / this.container.clientHeight, 0.1, 1000);
        this.camera.position.set(0, 0, 0.01);

        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
        this.container.appendChild(this.renderer.domElement);

        // Panorama Sphere Setup (Inverted Sphere)
        const geometry = new THREE.SphereGeometry(50, 60, 40);
        geometry.scale(-1, 1, 1);

        // Create a default grid canvas texture
        const size = 512;
        const canvas = document.createElement('canvas');
        canvas.width = size; canvas.height = size;
        const context = canvas.getContext('2d');
        context.fillStyle = '#1e293b';
        context.fillRect(0, 0, size, size);
        context.strokeStyle = '#334155';
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

    /**
     * Loads and displays the panoramic texture from the disk image path.
     * @param {string} imgPath - File path (file://)
     */
    updatePanoTexture(imgPath) {
        const loader = new THREE.TextureLoader();
        loader.load(imgPath, (texture) => {
            const oldMap = this.panoSphere.material.map;
            if (oldMap) {
                if (oldMap.image && oldMap.image.src && oldMap.image.src.startsWith('blob:')) {
                    URL.revokeObjectURL(oldMap.image.src);
                }
                oldMap.dispose();
            }
            this.panoSphere.material.map = texture;
            this.panoSphere.material.needsUpdate = true;
        }, undefined, (err) => {
            console.error("Failed to load panorama texture:", imgPath, err);
        });
    }

    /**
     * Recreates the points geometry and material in Three.js and adds it to the scene.
     * @param {Float32Array} positions - point coordinates
     * @param {Float32Array} colors - point color decimals
     */
    updatePointCloud(positions, colors) {
        // Safely dispose of existing GPU buffers to avoid memory leaks
        this.unloadPointCloud();

        if (!positions || positions.length === 0) return;

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        // Commercial parameters: size attenuation enables perspective scaling
        const material = new THREE.PointsMaterial({
            size: 0.12,
            vertexColors: true,
            sizeAttenuation: true
        });

        this.pointCloud = new THREE.Points(geometry, material);
        this.pointCloud.visible = false; // Hidden by default in panorama mode
        this.scene.add(this.pointCloud);
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
        }
    }

    /**
     * Translates the point cloud relative to the camera centered at (0,0,0)
     * @param {number[]} panoPos - python world coordinates [x, y, z] of the current panorama
     */
    alignPointCloud(panoPos) {
        if (!this.pointCloud) return;
        // Apply coordinate offset from centralized mapping rules
        // Three.js X = Python X
        // Three.js Y = Python Z (height)
        // Three.js Z = Python Y (depth)
        this.pointCloud.position.set(-panoPos[0], -panoPos[2], -panoPos[1]);
    }

    alignPanoSphere(rotation) {
        if (!this.panoSphere) return;
        if (rotation) {
            // rotation is [qx, qy, qz, qw]
            // Map to Three.js axes: Three.js Y = Pano Z, Three.js Z = Pano Y
            const q = new THREE.Quaternion(rotation[0], rotation[2], -rotation[1], rotation[3]);
            
            // Extract Euler angles using YXZ order to isolate vertical yaw rotation from pitch/roll tilt
            const euler = new THREE.Euler().setFromQuaternion(q, 'YXZ');
            
            // Re-apply yaw rotation with correct angular direction to align panorama with world nav markers
            const uprightQ = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), -euler.y);
            this.panoSphere.quaternion.copy(uprightQ);
        } else {
            this.panoSphere.quaternion.set(0, 0, 0, 1);
        }
    }

    /**
     * Updates camera viewing direction vectors.
     * @param {number} lat - latitude/pitch angle
     * @param {number} lon - longitude/yaw angle
     */
    updateCamera(lat, lon) {
        const phi = THREE.MathUtils.degToRad(90 - lat);
        const theta = THREE.MathUtils.degToRad(lon);

        const target = new THREE.Vector3();
        target.x = 50 * Math.sin(phi) * Math.cos(theta);
        target.y = 50 * Math.cos(phi);
        target.z = 50 * Math.sin(phi) * Math.sin(theta);

        this.camera.lookAt(target);
    }

    resize() {
        if (!this.renderer || !this.camera) return;
        const w = this.container.clientWidth;
        const h = this.container.clientHeight;
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h);
    }

    animate() {
        requestAnimationFrame(this.animate.bind(this));
        if (this.renderer && this.scene && this.camera) {
            this.renderer.render(this.scene, this.camera);
        }
    }
}
