import * as THREE from 'three';
import fs from 'fs';

const proj = JSON.parse(fs.readFileSync('C:/Users/ChristopherAllen/OneDrive - Reisource/_INTERNAL/808/argos test/test argon/project.avproj', 'utf8'));
const panos = proj.scans[0].panos;

// Find two panos where one is in front of the other
// In check_all_names, 00000 (orig_idx 1) and 00001 (orig_idx 6)
// Let's find pano_001 and pano_006 or whichever has those images
const pA = panos.find(p => p.image_path.includes('pano_001.jpg')); // 00000
const pB = panos.find(p => p.image_path.includes('pano_006.jpg')); // 00001

console.log('Pano A:', pA.id, pA.position, pA.rotation);
console.log('Pano B:', pB.id, pB.position, pB.rotation);

// Python vector from A to B:
const dx = pB.position[0] - pA.position[0];
const dy = pB.position[1] - pA.position[1];
const dz = pB.position[2] - pA.position[2];
console.log(`World vector A->B: dx=${dx.toFixed(2)}, dy=${dy.toFixed(2)}, dz=${dz.toFixed(2)}`);

// Three.js coords: X=arr[0], Y=arr[2], Z=arr[1]
const vThree = new THREE.Vector3(dx, dz, dy);
console.log(`Three.js vector A->B: x=${vThree.x.toFixed(2)}, y=${vThree.y.toFixed(2)}, z=${vThree.z.toFixed(2)}`);
// Angle of B relative to A in Three.js horizontal plane (X, Z):
const angleThree = Math.atan2(vThree.z, vThree.x) * 180 / Math.PI;
console.log(`Angle of B from A in Three.js (from +X towards +Z): ${angleThree.toFixed(1)} deg`);

// Now what is the scanner orientation at A?
// pA.rotation is [qx, qy, qz, qw]
const rotA = pA.rotation;
const q = new THREE.Quaternion(rotA[0], rotA[2], -rotA[1], rotA[3]);
const euler = new THREE.Euler().setFromQuaternion(q, 'YXZ');
const uprightQ = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), euler.y);
console.log(`Euler Y in Three.js: ${(euler.y * 180 / Math.PI).toFixed(1)} deg`);

// In Python, yaw of scanner A:
const pyYaw = Math.atan2(2.0 * (rotA[3]*rotA[2] + rotA[0]*rotA[1]), 1.0 - 2.0 * (rotA[1]*rotA[1] + rotA[2]*rotA[2])) * 180 / Math.PI;
console.log(`Python yaw of scanner A: ${pyYaw.toFixed(1)} deg`);
