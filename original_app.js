Created At: 2026-07-02T03:41:54Z
Completed At: 2026-07-02T03:41:54Z
File Path: `file:///c:/Users/ChristopherAllen/OneDrive%20-%20Reisource/Desktop/AV_Walkthrough/src/App.js`
Total Lines: 871
Total Bytes: 36172
Showing lines 1 to 800
The following code has been modified to include a line number before every line, in the format: <line_number>: <original_line>. Please note that any changes targeting the original code should remove the line number, colon, and leading space.
1: import * as THREE from 'three';
2: import { gsap } from 'gsap';
3: 
4: class WalkthroughApp {
5:     constructor() {
6:         this.container = document.getElementById('viewer-container');
7:         this.projectData = null;
8:         this.currentScan = null;
9:         this.currentPano = null;
10:         this.projectPath = null;
11:         
12:         this.floors = [];
13:         this.currentFloorId = null;
14: 
15:         this.measurementMode = false;
16:         this.measurementPoints = [];
17:         this.measurementLine = null;
18:         this.unitType = 'metric'; // 'metric' or 'imperial'
19:         this.floorplans = {}; // floor_id: ImageElement
20:         this.recentProjects = [];
21:         
22:         // Architecture Correction: Single Source of Truth
23:         this.appState = {
24:             inputType: 'Structured E57',
25:             files: {
26:                 e57: null,
27:                 xyz: null,
28:                 panos: null,
29:                 slam: null
30:             }
31:         };
32: 
33: 
34:         this.initThree();
35:         this.initUI();
36:     }
37: 
38:     initThree() {
39:         this.scene = new THREE.Scene();
40:         this.camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
41:         this.camera.position.set(0, 0, 0.01);
42: 
43:         this.renderer = new THREE.WebGLRenderer({ antialias: true });
44:         this.renderer.setSize(window.innerWidth, window.innerHeight);
45:         this.container.appendChild(this.renderer.domElement);
<truncated 34422 bytes>
ine.userData = { points: [this.measurementPoints[0].clone(), this.measurementPoints[1].clone()] };
758:             this.measurementGroup.add(this.measurementLine);
759: 
760:             this.updateMeasurementLabels();
761:             
762:             // Reset for next
763:             this.measurementPoints = [];
764:         }
765:     }
766: 
767:     updateMeasurementLabels() {
768:         const tooltip = document.getElementById('measurement-tooltip');
769:         if (!this.measurementLine) {
770:             tooltip.style.display = 'none';
771:             return;
772:         }
773: 
774:         const p1 = this.measurementLine.userData.points[0];
775:         const p2 = this.measurementLine.userData.points[1];
776:         const distMeters = p1.distanceTo(p2) * 0.1; // Using same mock scale factor
777: 
778:         let displayStr = "";
779:         if (this.unitType === 'imperial') {
780:             const totalFeet = distMeters * 3.28084;
781:             const feet = Math.floor(totalFeet);
782:             const inches = Math.round((totalFeet - feet) * 12);
783:             displayStr = `${feet}' ${inches}"`;
784:         } else {
785:             displayStr = `${distMeters.toFixed(2)}m`;
786:         }
787: 
788:         tooltip.innerText = displayStr;
789:         tooltip.style.display = 'block';
790:         tooltip.style.position = 'absolute';
791:         tooltip.style.left = '50%';
792:         tooltip.style.top = '90%'; // Move to bottom center for better visibility
793:         tooltip.style.background = 'rgba(0,0,0,0.8)';
794:         tooltip.style.padding = '8px 15px';
795:         tooltip.style.color = 'white';
796:         tooltip.style.borderRadius = '20px';
797:         tooltip.style.border = '1px solid rgba(255,255,255,0.2)';
798:         tooltip.style.transform = 'translateX(-50%)';
799:     }
800: 
The above content does NOT show the entire file contents. If you need to view any lines of the file which were not shown to complete your task, call this tool again to view those lines.
