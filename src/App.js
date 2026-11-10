import * as THREE from 'three';
import { gsap } from 'gsap';
import { CoordsUtility } from './coords.js';
import { ProjectManager } from './projectManager.js';
import { DataLoader } from './dataLoader.js';
import { WalkthroughRenderer } from './renderer.js';
import { WalkthroughNavigation } from './navigation.js';
import { AutoStackManager } from './autoStack.js';

class WalkthroughApp {
    constructor() {
        this.container = document.getElementById('viewer-container');
        this.recentProjects = [];
        
        // Authoritative Scene State (Single Source of Truth)
        this.sceneState = {
            projectData: null,
            projectPath: null,
            currentScanDate: null,
            currentScan: null,      // Active scan date metadata object
            currentPano: null,      // Active panorama metadata object
            currentFloorId: null,   // Active floor ID
            activeBookmark: null,   // Active bookmark name if any
            pointCloudData: null,   // Loaded point cloud data: { positions, colors }
            cameraLon: 0,
            cameraLat: 0
        };

        // Create Modal Input State
        this.appState = {
            inputType: 'Structured E57',
            importMode: 'linked',
            files: {
                e57: null,
                xyz: null,
                panos: null,
                slam: null
            }
        };

        // Helper Modules
        this.projectManager = new ProjectManager();
        this.renderer = new WalkthroughRenderer(this.container);
        this.navigation = new WalkthroughNavigation(this.renderer);
        this.floorplans = {}; // Cache floorplan images: floor_id -> ImageElement
        
        // Organizer folder state
        this.recentProjects = [];
        this.registryFolders = [];
        this.collapsedFolders = new Set();

        // Interaction States
        this.controls = {
            isDragging: false,
            mouseDownTime: 0,
            previousMousePosition: { x: 0, y: 0 }
        };

        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();

        this.initControls();
        this.initUI();
    }

    initControls() {
        // Drag-to-look rotation bindings
        this.container.addEventListener('mousedown', this.onMouseDown.bind(this));
        this.container.addEventListener('mousemove', this.onMouseMove.bind(this));
        this.container.addEventListener('mouseup', this.onMouseUp.bind(this));
        this.container.addEventListener('wheel', this.onMouseWheel.bind(this));
        this.container.addEventListener('click', this.onClick.bind(this));
        this.container.addEventListener('dblclick', this.onDblClick.bind(this));

        window.addEventListener('resize', this.onWindowResize.bind(this));

        // Calibration (Shift + WASD / Shift + Arrows)
        window.addEventListener('keydown', (e) => {
            const tag = e.target.tagName.toLowerCase();
            if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
            if (!this.sceneState.currentFloorId || !this.sceneState.currentScan) return;
            if (e.shiftKey) {
                const floor = this.sceneState.currentScan.floors.find(f => f.id === this.sceneState.currentFloorId);
                if (!floor) return;
                if (!floor.fpOffset) floor.fpOffset = { x: 0, y: 0 };
                if (!floor.fpScale) floor.fpScale = 1.0;
                
                const step = 2;
                if (e.key === 'ArrowUp' || e.key === 'w') floor.fpOffset.y -= step;
                if (e.key === 'ArrowDown' || e.key === 's') floor.fpOffset.y += step;
                if (e.key === 'ArrowLeft' || e.key === 'a') floor.fpOffset.x -= step;
                if (e.key === 'ArrowRight' || e.key === 'd') floor.fpOffset.x += step;
                if (e.key === '+' || e.key === '=') floor.fpScale *= 1.02;
                if (e.key === '-') floor.fpScale *= 0.98;
                
                this.projectManager.isModified = true; // Mark project modified to save calibration
                this.renderKeyplan();
                e.preventDefault();
            }
        });
    }

    initUI() {
        const safeAddListener = (id, event, callback) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener(event, callback);
        };

        this.showHome();

        // 1. Dashboard Context
        safeAddListener('card-open', 'click', async () => {
            const paths = await window.electronAPI.selectFile([{ name: 'AV Walkthrough Project', extensions: ['avproj'] }]);
            if (paths && paths.length > 0) {
                let p = paths[0];
                if (p.endsWith('project.avproj')) {
                    p = p.substring(0, p.lastIndexOf('\\'));
                    if (p === '') p = p.substring(0, p.lastIndexOf('/'));
                }
                this.loadProject(p);
            }
        });

        safeAddListener('card-create', 'click', () => {
            const dateInput = document.getElementById('create-date');
            if (dateInput) {
                const today = new Date().toISOString().split('T')[0];
                dateInput.setAttribute('max', today);
                dateInput.value = today;
            }
            const select = document.getElementById('create-project-select');
            if (select) {
                select.innerHTML = '<option value="new">-- Create New Project --</option>';
                this.recentProjects.forEach(p => {
                    const path = p.path || p;
                    const name = p.name || path.split(/[\\\/]/).pop() || path;
                    const opt = document.createElement('option');
                    opt.value = path;
                    opt.textContent = name;
                    select.appendChild(opt);
                });
            }

            const folderSelect = document.getElementById('create-folder-select');
            if (folderSelect) {
                folderSelect.innerHTML = '<option value="">-- No Folder (Root) --</option><option value="create-new-folder">-- Create New Folder... --</option>';
                this.registryFolders.forEach(f => {
                    const opt = document.createElement('option');
                    opt.value = f;
                    opt.textContent = f;
                    folderSelect.appendChild(opt);
                });
            }

            const fgNew = document.getElementById('fg-new-project');
            if (fgNew) fgNew.style.display = 'block';
            this.updateCreateModalVisibility();
            document.getElementById('create-modal').style.display = 'flex';
            
            // Programmatically restore window focus and focus the new name input
            window.focus();
            setTimeout(() => {
                const nameInput = document.getElementById('create-name');
                if (nameInput) {
                    nameInput.focus();
                    nameInput.select();
                }
            }, 150);
        });

        safeAddListener('card-create-folder', 'click', () => {
            const input = document.getElementById('folder-modal-name');
            if (input) input.value = '';
            document.getElementById('folder-modal').style.display = 'flex';
            window.focus();
            setTimeout(() => {
                if (input) input.focus();
            }, 150);
        });

        safeAddListener('btn-cancel-folder', 'click', () => {
            document.getElementById('folder-modal').style.display = 'none';
        });

        safeAddListener('btn-submit-folder', 'click', async () => {
            const nameInput = document.getElementById('folder-modal-name');
            const name = nameInput ? nameInput.value.trim() : '';
            if (!name) return alert("Folder Name is required.");
            const res = await window.electronAPI.createFolder(name);
            if (res.success) {
                document.getElementById('folder-modal').style.display = 'none';
                await this.loadRecentProjects();
            } else {
                alert("Error creating folder: " + res.error);
            }
        });

        safeAddListener('btn-cancel-move', 'click', () => {
            document.getElementById('move-project-modal').style.display = 'none';
        });

        safeAddListener('btn-submit-move', 'click', async () => {
            if (!this.sceneState.projectToMove) return;
            const select = document.getElementById('move-project-select');
            const folder = select ? select.value : '';
            const p = this.sceneState.projectToMove;
            const res = await window.electronAPI.addRecentProject({
                name: p.name,
                path: p.path,
                folder: folder || null
            });
            if (res.success) {
                document.getElementById('move-project-modal').style.display = 'none';
                this.sceneState.projectToMove = null;
                await this.loadRecentProjects();
            } else {
                alert("Error moving project: " + res.error);
            }
        });

        // 2. Create Modal Context
        safeAddListener('create-project-select', 'change', (e) => {
            const isNew = e.target.value === 'new';
            const fgNew = document.getElementById('fg-new-project');
            if (fgNew) fgNew.style.display = isNew ? 'block' : 'none';
        });

        safeAddListener('create-folder-select', 'change', (e) => {
            const isNew = e.target.value === 'create-new-folder';
            const fgNew = document.getElementById('fg-folder-new-input');
            if (fgNew) fgNew.style.display = isNew ? 'block' : 'none';
            if (isNew) {
                setTimeout(() => {
                    const input = document.getElementById('create-folder-new-name');
                    if (input) input.focus();
                }, 100);
            }
        });

        safeAddListener('btn-cancel-create', 'click', () => {
            document.getElementById('create-modal').style.display = 'none';
            const fgNewFolder = document.getElementById('fg-folder-new-input');
            if (fgNewFolder) fgNewFolder.style.display = 'none';
        });

        safeAddListener('create-type', 'change', () => this.updateCreateModalVisibility());

        safeAddListener('btn-browse-e57', 'click', async () => {
            const filters = [{ name: 'E57 Scan', extensions: ['e57'] }];
            const paths = await window.electronAPI.selectFile(filters);
            if (paths && paths.length > 0) {
                const p = paths[0];
                this.appState.files.e57 = p;
                document.getElementById('create-e57-path').value = p;
            }
        });

        safeAddListener('btn-browse-panos', 'click', async () => {
            const paths = await window.electronAPI.selectDirectory();
            if (paths && paths.length > 0) {
                this.appState.files.panos = paths[0];
                document.getElementById('create-panos-path').value = paths[0];
            }
        });

        safeAddListener('btn-browse-slam', 'click', async () => {
            const paths = await window.electronAPI.selectFile([{ name: 'Executables', extensions: ['exe'] }]);
            if (paths && paths.length > 0) {
                this.appState.files.slam = paths[0];
                document.getElementById('create-slam-path').value = paths[0];
            }
        });

        safeAddListener('btn-browse-csv', 'click', async () => {
            const paths = await window.electronAPI.selectFile([{ name: 'CSV Pose Files', extensions: ['csv', 'txt'] }]);
            if (paths && paths.length > 0) {
                this.appState.files.csv = paths[0];
                document.getElementById('create-csv-path').value = paths[0];
            }
        });

        safeAddListener('btn-browse-dir', 'click', async () => {
            const paths = await window.electronAPI.selectDirectory();
            if (paths && paths.length > 0) document.getElementById('create-dir-path').value = paths[0];
        });

        safeAddListener('btn-submit-create', 'click', () => this.submitCreateProject());

        // 3. Viewer Topbar controls
        safeAddListener('scan-date-selector', 'change', (e) => {
            if (e.target.value) this.loadScan(e.target.value);
        });

        safeAddListener('floor-selector', 'change', (e) => {
            if (e.target.value) this.setFloor(parseInt(e.target.value));
        });

        safeAddListener('bookmark-selector', 'change', (e) => {
            if (e.target.value) this.selectBookmark(e.target.value);
        });

        safeAddListener('btn-add-bookmark', 'click', () => this.addNewBookmark());

        // 4. Keyplan controls
        safeAddListener('btn-recluster-floors', 'click', () => {
            this.reclusterCurrentProject();
        });

        safeAddListener('btn-upload-fp', 'click', () => {
            document.getElementById('floorplan-upload').click();
        });

        safeAddListener('floorplan-upload', 'change', (e) => {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = (event) => {
                    const img = new Image();
                    img.onload = () => {
                        this.floorplans[this.sceneState.currentFloorId] = img;
                        this.renderKeyplan();
                    };
                    img.src = event.target.result;
                };
                reader.readAsDataURL(file);
            }
        });
        
        safeAddListener('keyplan-canvas', 'click', (e) => {
            const canvas = document.getElementById('keyplan-canvas');
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const clickedId = this.navigation.handleKeyplanClick(x, y);
            if (clickedId) {
                this.goToPano(clickedId);
            }
        });

        safeAddListener('btn-home', 'click', () => {
            this.showHome();
            window.focus();
        });

        // Date Input Native Calendar Trigger logic
        const dateInput = document.getElementById('create-date');
        if (dateInput) {
            const triggerCalendar = () => {
                try {
                    dateInput.showPicker();
                } catch (e) {}
            };
            dateInput.addEventListener('click', triggerCalendar);
            dateInput.addEventListener('focus', triggerCalendar);
        }

        this.loadRecentProjects();
    }

    updateCreateModalVisibility() {
        const typeEl = document.getElementById('create-type');
        if (!typeEl) return;
        
        const val = typeEl.value;
        this.appState.inputType = val;
        
        this.clearAllInputs();
        
        const e57El = document.getElementById('fg-e57');
        const panosEl = document.getElementById('fg-panos');
        const csvEl = document.getElementById('fg-csv');
        const slamEl = document.getElementById('fg-slam');
        const labelEl = document.getElementById('label-dataset-file');
        const inputEl = document.getElementById('create-e57-path');

        if (e57El) e57El.style.display = 'none';
        if (panosEl) panosEl.style.display = 'none';
        if (csvEl) csvEl.style.display = 'none';
        if (slamEl) slamEl.style.display = 'none';

        if (val === 'Structured E57') {
            if (e57El) e57El.style.display = 'block';
            if (labelEl) labelEl.innerText = 'Dataset File (.e57)';
            if (inputEl) inputEl.placeholder = 'Select .e57 file...';
        } else if (val === 'E57 + Panos Folder') {
            if (e57El) e57El.style.display = 'block';
            if (labelEl) labelEl.innerText = 'Dataset File (.e57)';
            if (inputEl) inputEl.placeholder = 'Select .e57 file...';
            if (panosEl) panosEl.style.display = 'block';
        } else if (val === 'E57 + Panos + CSV') {
            if (e57El) e57El.style.display = 'block';
            if (labelEl) labelEl.innerText = 'Dataset File (.e57)';
            if (inputEl) inputEl.placeholder = 'Select .e57 file...';
            if (panosEl) panosEl.style.display = 'block';
            if (csvEl) csvEl.style.display = 'block';
        }
    }

    clearAllInputs() {
        this.appState.files = { e57: null, xyz: null, panos: null, csv: null, slam: null };
        ['create-e57-path', 'create-panos-path', 'create-csv-path', 'create-slam-path'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
    }

    showHome() {
        this.projectManager.stopAutosaveLoop();
        this.renderer.unloadPointCloud();
        
        // Clean scan state to prevent coordinate leaks across different projects
        this.sceneState.currentScanDate = null;
        this.sceneState.currentScan = null;
        this.sceneState.currentPano = null;
        this.sceneState.currentFloorId = null;
        
        document.getElementById('splash-screen').style.display = 'none';
        document.getElementById('main-ui').style.display = 'none';
        document.getElementById('home-screen').style.display = 'flex';
        document.getElementById('create-modal').style.display = 'none';
    }

    showViewer() {
        document.getElementById('splash-screen').style.display = 'none';
        document.getElementById('home-screen').style.display = 'none';
        document.getElementById('main-ui').style.display = 'block';
    }

    async loadRecentProjects() {
        const res = await window.electronAPI.getRecentProjects();
        this.recentProjects = res.projects || [];
        this.registryFolders = res.folders || [];
        this.renderRecentProjects();
    }

    renderRecentProjects() {
        const container = document.getElementById('recent-projects-list');
        const projects = this.recentProjects || [];
        const folders = this.registryFolders || [];

        if (projects.length === 0 && folders.length === 0) {
            container.innerHTML = '<p class="empty-msg">No folders or recent projects found.</p>';
            return;
        }

        container.innerHTML = '';

        // Helper function to build project card element
        const createProjectCard = (p) => {
            const card = document.createElement('div');
            card.className = 'project-card';
            card.innerHTML = `
                <div class="project-card-info">
                    <h4>${p.name}</h4>
                    <p>${p.path}</p>
                </div>
                <div class="project-card-actions" style="display: flex; gap: 8px;">
                    <button class="btn-move-project" title="Move to Folder" style="color: #64748b; background: transparent; border: none; padding: 4px; cursor: pointer;">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                        </svg>
                    </button>
                    <button class="btn-delete-project" title="Delete Project">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                    </button>
                </div>
            `;
            card.querySelector('.project-card-info').addEventListener('click', () => this.loadProject(p.path));
            card.querySelector('.btn-move-project').addEventListener('click', (e) => {
                e.stopPropagation();
                this.sceneState.projectToMove = p;
                
                const label = document.getElementById('move-project-text');
                if (label) label.innerText = `Select organizer folder to move project "${p.name}" into:`;
                
                const select = document.getElementById('move-project-select');
                if (select) {
                    select.innerHTML = '<option value="">-- No Folder (Root) --</option>';
                    this.registryFolders.forEach(f => {
                        const opt = document.createElement('option');
                        opt.value = f;
                        opt.textContent = f;
                        select.appendChild(opt);
                    });
                    select.value = p.folder || '';
                }
                
                document.getElementById('move-project-modal').style.display = 'flex';
                window.focus();
            });
            card.querySelector('.btn-delete-project').addEventListener('click', async (e) => {
                e.stopPropagation();
                if (confirm(`Remove "${p.name}" from the program dashboard?`)) {
                    const deleteDisk = confirm(`Would you also like to delete the project's files on disk?\n\n(Click Cancel to only remove it from the dashboard, or OK to move the files safely to the Recycle Bin)`);
                    const res = await window.electronAPI.deleteProject(p.path, deleteDisk);
                    if (res.success) {
                        this.loadRecentProjects();
                        if (deleteDisk && res.diskError) {
                            alert(`Project removed from dashboard.\n\nNote: Files on disk were not deleted:\n${res.diskError}`);
                        }
                    } else {
                        alert("Error removing project: " + res.error);
                    }
                }
            });
            return card;
        };

        // 1. Render Folders
        folders.forEach(fName => {
            const folderSection = document.createElement('div');
            const isCollapsed = this.collapsedFolders.has(fName);
            folderSection.className = `folder-section${isCollapsed ? ' collapsed' : ''}`;
            
            folderSection.innerHTML = `
                <div class="folder-header">
                    <div class="folder-title-area">
                        <span class="folder-toggle-icon">
                            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="6 9 12 15 18 9"></polyline>
                            </svg>
                        </span>
                        <span class="folder-title">${fName}</span>
                    </div>
                    <div class="folder-actions">
                        <button class="btn-delete-folder" title="Delete Folder">
                            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="3 6 5 6 21 6"></polyline>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                            </svg>
                        </button>
                    </div>
                </div>
                <div class="folder-projects"></div>
            `;

            // Toggle collapse
            folderSection.querySelector('.folder-title-area').addEventListener('click', () => {
                if (this.collapsedFolders.has(fName)) {
                    this.collapsedFolders.delete(fName);
                    folderSection.classList.remove('collapsed');
                } else {
                    this.collapsedFolders.add(fName);
                    folderSection.classList.add('collapsed');
                }
            });

            // Delete folder
            folderSection.querySelector('.btn-delete-folder').addEventListener('click', async (e) => {
                e.stopPropagation();
                if (confirm(`Are you sure you want to delete folder "${fName}"?\n\n(Projects inside this folder will become Uncategorized, they will NOT be deleted from disk.)`)) {
                    const res = await window.electronAPI.deleteFolder(fName);
                    if (res.success) {
                        this.loadRecentProjects();
                    } else {
                        alert("Error deleting folder: " + res.error);
                    }
                }
            });

            const folderProjectsContainer = folderSection.querySelector('.folder-projects');
            const folderProjects = projects.filter(p => p.folder === fName);
            
            if (folderProjects.length === 0) {
                folderProjectsContainer.innerHTML = '<p class="empty-msg" style="padding: 10px; grid-column: 1/-1;">No projects in this folder.</p>';
            } else {
                folderProjects.forEach(p => {
                    folderProjectsContainer.appendChild(createProjectCard(p));
                });
            }

            container.appendChild(folderSection);
        });

        // 2. Render Uncategorized/Root Projects
        const uncategorizedProjects = projects.filter(p => !p.folder || !folders.includes(p.folder));
        if (uncategorizedProjects.length > 0) {
            const rootSection = document.createElement('div');
            const isCollapsed = this.collapsedFolders.has('__root__');
            rootSection.className = `folder-section${isCollapsed ? ' collapsed' : ''}`;
            rootSection.innerHTML = `
                <div class="folder-header">
                    <div class="folder-title-area">
                        <span class="folder-toggle-icon">
                            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="6 9 12 15 18 9"></polyline>
                            </svg>
                        </span>
                        <span class="folder-title">Uncategorized Projects</span>
                    </div>
                </div>
                <div class="folder-projects"></div>
            `;

            rootSection.querySelector('.folder-title-area').addEventListener('click', () => {
                if (this.collapsedFolders.has('__root__')) {
                    this.collapsedFolders.delete('__root__');
                    rootSection.classList.remove('collapsed');
                } else {
                    this.collapsedFolders.add('__root__');
                    rootSection.classList.add('collapsed');
                }
            });

            const rootProjectsContainer = rootSection.querySelector('.folder-projects');
            uncategorizedProjects.forEach(p => {
                rootProjectsContainer.appendChild(createProjectCard(p));
            });

            container.appendChild(rootSection);
        }
    }

    async submitCreateProject() {
        const btn = document.getElementById('btn-submit-create');
        
        const projSelect = document.getElementById('create-project-select').value;
        const newName = document.getElementById('create-name').value;
        const project_name = projSelect === 'new' ? newName : (projSelect.split(/[\\\/]/).pop() || projSelect);
        
        const type = this.appState.inputType;
        const importMode = document.getElementById('create-import-mode').value;
        const date = document.getElementById('create-date').value;
        const parentDirPath = document.getElementById('create-dir-path').value;
        
        const folderSelect = document.getElementById('create-folder-select');
        let folder = folderSelect ? folderSelect.value : '';
        
        if (folder === 'create-new-folder') {
            const newNameInput = document.getElementById('create-folder-new-name');
            const newName = newNameInput ? newNameInput.value.trim() : '';
            if (!newName) return alert("Please specify a name for the new folder.");
            const resFold = await window.electronAPI.createFolder(newName);
            if (!resFold.success) {
                return alert("Error creating folder: " + resFold.error);
            }
            folder = newName;
        }
        this.sceneState.pendingFolder = folder || null;

        if (projSelect === 'new' && !project_name) return alert("Project Name is required.");
        if (!parentDirPath || !type) return alert("Directory and Type are required.");
        if (!date) return alert("Scan Date is required.");

        // Resolve absolute project directory (subdirectory for new, direct folder for existing)
        const projectDirPath = projSelect === 'new' 
            ? `${parentDirPath}/${project_name}`.replace(/\\/g, '/')
            : projSelect.replace(/\\/g, '/');

        // Redesigned validation checks per walkthrough-only requirements
        if (type === 'Structured E57') {
            if (!this.appState.files.e57) return alert("E57 file selection is required.");
        } else if (type === 'E57 + Panos Folder') {
            if (!this.appState.files.e57) return alert("E57 file selection is required.");
            if (!this.appState.files.panos) return alert("Panoramas directory selection is required.");
        } else if (type === 'E57 + Panos + CSV') {
            if (!this.appState.files.e57) return alert("E57 file selection is required.");
            if (!this.appState.files.panos) return alert("Panoramas directory selection is required.");
            if (!this.appState.files.csv) return alert("Pose CSV override file selection is required.");
        }

        btn.innerText = "Starting...";
        btn.disabled = true;

        try {
            const floorThreshold = parseFloat(document.getElementById('create-floor-threshold').value) || 0.25;
            const floorHeightsRaw = document.getElementById('create-floor-heights').value.trim();

            const payload = {
                project_dir: projectDirPath,
                project_name: project_name,
                scan_date: date,
                type: type,
                import_mode: importMode,
                e57_path: this.appState.files.e57,
                panos_path: this.appState.files.panos,
                csv_path: this.appState.files.csv,
                slam_path: this.appState.files.slam,
                floor_threshold: floorThreshold,
                floor_heights: floorHeightsRaw
            };

            const res = await window.electronAPI.apiRequest('api/ingest', payload);
            
            if (res.success && res.data.status === 'started') {
                document.getElementById('create-modal').style.display = 'none';
                document.getElementById('home-screen').style.display = 'none';
                this.pollStatus(projectDirPath);
            } else {
                alert("Error starting ingestion: " + (res.data ? res.data.error : res.error));
                btn.innerText = "Process";
                btn.disabled = false;
            }
        } catch (err) {
            console.error("Ingestion dispatch failed:", err);
            alert("Fatal Error starting process: " + err.message);
            btn.innerText = "Process";
            btn.disabled = false;
        }
    }

    pollStatus(dirPath) {
        document.getElementById('progress-container').style.display = 'block';
        document.getElementById('progress-fill').style.width = '0%';
        document.getElementById('splash-screen').style.display = 'block';
        
        let failCount = 0;
        const maxFails = 10;
        
        const interval = setInterval(async () => {
            const res = await window.electronAPI.apiRequest('api/status', {});
            if (res.success && res.data) {
                failCount = 0;
                const state = res.data;
                if (state.message) document.getElementById('splash-text').innerText = state.message;
                document.getElementById('progress-fill').style.width = `${state.progress}%`;

                if (state.status === 'success') {
                    clearInterval(interval);
                    document.getElementById('progress-container').style.display = 'none';
                    document.getElementById('btn-submit-create').innerText = "Process";
                    document.getElementById('btn-submit-create').disabled = false;
                    this.loadProject(dirPath);
                } else if (state.status === 'failed') {
                    clearInterval(interval);
                    document.getElementById('progress-fill').style.background = 'red';
                    document.getElementById('btn-submit-create').innerText = "Process";
                    document.getElementById('btn-submit-create').disabled = false;
                    setTimeout(() => {
                        this.showHome();
                        alert("Processing Failed:\n" + state.message);
                    }, 1000);
                }
            } else {
                failCount++;
                console.warn(`Ingestion status poll failed (${failCount}/${maxFails}) - Backend might be busy downsampling.`);
                if (failCount >= maxFails) {
                    clearInterval(interval);
                    document.getElementById('splash-text').innerText = "Backend Ingest disconnected.";
                    document.getElementById('progress-fill').style.background = 'red';
                    document.getElementById('btn-submit-create').innerText = "Process";
                    document.getElementById('btn-submit-create').disabled = false;
                    setTimeout(() => {
                        this.showHome();
                        alert("Processing Failed:\nThe backend ingestion engine terminated unexpectedly.");
                    }, 2000);
                }
            }
        }, 2000);
    }

    async reclusterCurrentProject() {
        if (!this.sceneState.projectPath) return;
        const btn = document.getElementById('btn-recluster-floors');
        if (btn) {
            btn.innerText = "Updating...";
            btn.disabled = true;
        }
        try {
            const res = await window.electronAPI.apiRequest('api/recluster', {
                project_dir: this.sceneState.projectPath,
                floor_threshold: 0.25
            });
            if (res.success && res.data && res.data.status === 'success') {
                await this.loadProject(this.sceneState.projectPath);
            } else {
                alert("Could not recalculate floor levels: " + (res.data ? res.data.error : res.error));
            }
        } catch (err) {
            console.error("Recluster failed:", err);
        } finally {
            if (btn) {
                btn.innerText = "Auto-Levels";
                btn.disabled = false;
            }
        }
    }

    async loadProject(dirPath) {
        let res = await this.projectManager.loadProject(dirPath);
        if (res.success) {
            // Automatically upgrade legacy multi-level projects that have multiple floors but lack cross-floor stair links
            const scans = res.data.scans || [];
            const needsMultiLevelUpgrade = scans.some(sc => {
                const floors = sc.floors || [];
                if (floors.length < 2) return false;
                const panos = sc.panos || [];
                if (panos.length < 4) return false;
                const panoById = new Map(panos.map(p => [p.id, p]));
                const hasCrossFloorLink = panos.some(p =>
                    (p.neighbors || []).some(nid => {
                        const nb = panoById.get(nid);
                        return nb && nb.floor_id !== p.floor_id;
                    })
                );
                return !hasCrossFloorLink;
            });

            if (needsMultiLevelUpgrade) {
                const reclusterRes = await window.electronAPI.apiRequest('api/recluster', {
                    project_dir: dirPath,
                    floor_threshold: 0.25
                });
                if (reclusterRes.success) {
                    res = await this.projectManager.loadProject(dirPath);
                }
            }

            this.sceneState.projectData = res.data;
            this.sceneState.projectPath = dirPath;
            
            document.getElementById('project-name').innerText = this.sceneState.projectData.name || "Untitled Project";
            
            const select = document.getElementById('scan-date-selector');
            select.innerHTML = '<option value="">Select Scan Date</option>';
            this.sceneState.projectData.scans.forEach(scan => {
                const opt = document.createElement('option');
                opt.value = scan.scan_date;
                opt.innerText = scan.scan_date;
                select.appendChild(opt);
            });
            
            this.updateBookmarksSelector();
            
            if (this.sceneState.projectData.scans.length > 0) {
                const defaultScan = this.sceneState.projectData.scans[0].scan_date;
                select.value = defaultScan;
                await this.loadScan(defaultScan);
            }
            
            const existingProj = this.recentProjects.find(p => p.path === dirPath);
            const folderName = existingProj ? existingProj.folder : (this.sceneState.pendingFolder || null);
            this.sceneState.pendingFolder = null; // clear it
            
            await window.electronAPI.addRecentProject({
                name: this.sceneState.projectData.name || "Untitled",
                path: dirPath,
                folder: folderName
            });
            this.loadRecentProjects();
            this.showViewer();
        } else {
            console.error("Project Load Error:", res.error);
            alert("Failed to load project: " + (res.error || "Unknown error"));
            this.showHome();
        }
    }

    async validateScanRuntime(scan, projectPath) {
        const errors = [];
        
        // 1. Check panorama count > 0
        if (!scan.panos || scan.panos.length === 0) {
            errors.push("No panoramas defined in scan database.");
            return { valid: false, errors };
        }
        
        // 2. Check position, rotation, and file existence for each panorama
        for (const p of scan.panos) {
            if (!p.position || p.position.length !== 3 || p.position.some(isNaN)) {
                errors.push(`Pano ${p.id} has invalid or missing position vector.`);
            }
            if (!p.rotation || p.rotation.length !== 4 || p.rotation.some(isNaN)) {
                errors.push(`Pano ${p.id} has invalid or missing rotation quaternion.`);
            }
            
            // Check if image file exists
            const imgPath = `${projectPath}/Scans/${scan.scan_date}/${p.image_path}`.replace(/\\/g, '/');
            const existsRes = await window.electronAPI.fileExists(imgPath);
            if (!existsRes.success || !existsRes.exists) {
                errors.push(`Pano ${p.id} referenced image file does not exist: ${p.image_path}`);
            }
        }
        
        // 3. Check neighbors (navigation graph contains valid neighbors)
        const panoIds = new Set(scan.panos.map(p => p.id));
        for (const p of scan.panos) {
            if (p.neighbors) {
                for (const nid of p.neighbors) {
                    if (!panoIds.has(nid)) {
                        errors.push(`Pano ${p.id} references invalid neighbor node ID: ${nid}`);
                    }
                }
            }
        }
        
        // 4. Check point cloud cache file if referenced
        if (scan.point_cloud_cache) {
            const cachePath = `${projectPath}/${scan.point_cloud_cache}`.replace(/\\/g, '/');
            const existsRes = await window.electronAPI.fileExists(cachePath);
            if (!existsRes.success || !existsRes.exists) {
                errors.push(`Point cloud cache is referenced but file does not exist: ${scan.point_cloud_cache}`);
            }
        }
        
        return {
            valid: errors.length === 0,
            errors
        };
    }

    renderFloorLevelBar() {
        const bar = document.getElementById('floor-level-bar');
        if (!bar) return;
        bar.innerHTML = '';
        if (!this.sceneState.currentScan || !this.sceneState.currentScan.floors) return;

        // Sort floors highest-to-lowest vertically (Matterport / NavVis IVION elevator style)
        const sortedFloors = [...this.sceneState.currentScan.floors].sort((a, b) => b.id - a.id);
        sortedFloors.forEach(f => {
            const btn = document.createElement('button');
            btn.className = `floor-level-btn${this.sceneState.currentFloorId === f.id ? ' active' : ''}`;
            btn.dataset.floorId = f.id;
            btn.innerText = `F${f.id}`;
            const zInfo = f.mean_z !== undefined ? `${f.mean_z.toFixed(1)}m` : (f.z_height !== undefined ? `${f.z_height.toFixed(1)}m` : '');
            btn.title = `${f.name ? `Floor ${f.id} (${f.name})` : ('Floor ' + f.id)}${zInfo ? ` — ${zInfo}` : ''}`;
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.setFloor(f.id);
            });
            bar.appendChild(btn);
        });
    }

    syncFloorControlsUI(floorId) {
        const fSelect = document.getElementById('floor-selector');
        if (fSelect && String(fSelect.value) !== String(floorId)) {
            fSelect.value = floorId;
        }
        const bar = document.getElementById('floor-level-bar');
        if (bar) {
            bar.querySelectorAll('.floor-level-btn').forEach(btn => {
                if (parseInt(btn.dataset.floorId) === floorId) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });
        }
    }

    async loadScan(date) {
        const prevDate = this.sceneState.currentScanDate;
        
        let oldYawDeg = 0;
        if (this.sceneState.currentPano) {
            const oldPano = this.sceneState.currentPano;
            const q = new THREE.Quaternion(oldPano.rotation[0], oldPano.rotation[2], -oldPano.rotation[1], oldPano.rotation[3]);
            const euler = new THREE.Euler().setFromQuaternion(q, 'YXZ');
            oldYawDeg = THREE.MathUtils.radToDeg(euler.y);
        }
        
        // Query target scan metadata first
        const targetScan = this.sceneState.projectData.scans.find(s => s.scan_date === date);
        if (!targetScan) return;

        // Run Phase 4 - Runtime Validation
        const validation = await this.validateScanRuntime(targetScan, this.sceneState.projectPath);
        if (!validation.valid) {
            this.showHome();
            alert(`RUNTIME VALIDATION FAILURE:\n\n${validation.errors.join('\n')}`);
            return;
        }

        let targetPano = null;
        if (targetScan.panos.length > 0) {
            targetPano = targetScan.panos[0];
            
            // Auto-Stack comparisons if transit is from an existing panorama
            if (this.sceneState.currentPano) {
                const maxDist = this.sceneState.projectData.settings.max_autostack_distance || 10.0;
                const nearest = AutoStackManager.findNearestPano(
                    this.sceneState.currentPano,
                    targetScan.panos,
                    maxDist
                );
                
                if (nearest) {
                    targetPano = nearest;
                } else {
                    // Abort Transit Fallback: revert select element in UI and exit
                    alert(`No matching viewpoint coverage on this date within ${maxDist}m. Switch canceled.`);
                    const dateSelect = document.getElementById('scan-date-selector');
                    if (dateSelect) dateSelect.value = prevDate || '';
                    return;
                }
            }
        }

        // Apply new scan state only after verification succeeds
        this.sceneState.currentScanDate = date;
        this.sceneState.currentScan = targetScan;
        
        const fSelect = document.getElementById('floor-selector');
        fSelect.innerHTML = '<option value="">Select Floor</option>';
        this.sceneState.currentScan.floors.forEach(f => {
            const opt = document.createElement('option');
            opt.value = f.id;
            opt.innerText = f.name ? `Floor ${f.id} (${f.name})` : `Floor ${f.id}`;
            fSelect.appendChild(opt);
        });
        this.renderFloorLevelBar();

        // Point cloud loader delegation
        this.renderer.unloadPointCloud();
        this.sceneState.pointCloudData = null;
        
        if (this.sceneState.currentScan.point_cloud_cache) {
            const cachePath = `${this.sceneState.projectPath}/${this.sceneState.currentScan.point_cloud_cache}`.replace(/\\/g, '/');
            const points = await DataLoader.loadPointCloudBin(cachePath);
            if (points) {
                this.sceneState.pointCloudData = points;
                this.renderer.updatePointCloud(points.positions, points.colors);
            }
        }
        
        if (targetPano) {
            this.sceneState.currentFloorId = targetPano.floor_id;
            this.syncFloorControlsUI(targetPano.floor_id);
            
            // Adjust cameraLon by the scanner yaw difference to align orientations
            if (prevDate && this.sceneState.currentPano) {
                const q = new THREE.Quaternion(targetPano.rotation[0], targetPano.rotation[2], -targetPano.rotation[1], targetPano.rotation[3]);
                const euler = new THREE.Euler().setFromQuaternion(q, 'YXZ');
                const newYawDeg = THREE.MathUtils.radToDeg(euler.y);
                
                const deltaYaw = newYawDeg - oldYawDeg;
                this.sceneState.cameraLon += deltaYaw;
            }
            
            this.goToPano(targetPano.id);
        }
    }

    setFloor(floorId) {
        this.sceneState.currentFloorId = floorId;
        this.syncFloorControlsUI(floorId);
        this.renderKeyplan();
        
        if (this.sceneState.currentPano && this.sceneState.currentPano.floor_id !== floorId) {
            const floorPanos = this.sceneState.currentScan.panos.filter(p => p.floor_id === floorId);
            if (floorPanos.length > 0) {
                const ref = this.sceneState.currentPano;
                // Teleport directly above/below the current (X, Y) position on the selected floor
                const closest = AutoStackManager.findNearestHorizontalPano(ref, floorPanos);
                if (closest) this.goToPano(closest.id);
            }
        }
    }

    async goToPano(panoId) {
        const pano = this.sceneState.currentScan.panos.find(p => p.id === panoId);
        if (!pano) return;
        
        this.sceneState.currentPano = pano;

        // Automatically switch active floor when walking up/down stairs across the midpoint
        if (pano.floor_id && pano.floor_id !== this.sceneState.currentFloorId) {
            this.sceneState.currentFloorId = pano.floor_id;
            this.syncFloorControlsUI(pano.floor_id);
        }
        
        // Update point cloud translation relative to camera centered at (0,0,0)
        this.renderer.alignPointCloud(pano.position);
        
        // Align panorama sphere and nav markers rotation to match scanner pose coordinates
        this.renderer.alignPanoSphere(pano.rotation);
        
        const imgPath = `${this.sceneState.projectPath}/Scans/${this.sceneState.currentScanDate}/${pano.image_path}`.replace(/\\/g, '/');
        const res = await window.electronAPI.readFileBin(imgPath);
        if (res.success && res.data) {
            const blob = new Blob([res.data], { type: 'image/jpeg' });
            const blobUrl = URL.createObjectURL(blob);
            this.renderer.updatePanoTexture(blobUrl);
        } else {
            console.error("Failed to load panorama image natively:", imgPath, res.error);
        }

        // Update nav rings and keyplan active node markers
        this.navigation.updateNavMarkers(this.sceneState.currentPano, this.sceneState.currentScan.panos);
        this.renderKeyplan();
        
        // Preserve camera viewing direction orientation
        this.renderer.updateCamera(this.sceneState.cameraLat, this.sceneState.cameraLon);
    }

    renderKeyplan() {
        if (!this.sceneState.currentScan || !this.sceneState.currentFloorId) return;
        const canvas = document.getElementById('keyplan-canvas');
        const floorPanos = this.sceneState.currentScan.panos.filter(p => p.floor_id === this.sceneState.currentFloorId);
        
        const fpImg = this.floorplans[this.sceneState.currentFloorId];
        const floor = this.sceneState.currentScan.floors.find(f => f.id === this.sceneState.currentFloorId);
        const off = floor ? floor.fpOffset : null;
        const sc = floor ? floor.fpScale : null;

        this.navigation.renderKeyplan(canvas, this.sceneState.currentPano, floorPanos, fpImg, off, sc, this.sceneState.cameraLon);
    }

    updateBookmarksSelector() {
        const select = document.getElementById('bookmark-selector');
        if (!select) return;
        select.innerHTML = '<option value="">Select Bookmark</option>';
        if (this.sceneState.projectData && this.sceneState.projectData.bookmarks) {
            this.sceneState.projectData.bookmarks.forEach(b => {
                const opt = document.createElement('option');
                opt.value = b.name;
                opt.textContent = b.name;
                select.appendChild(opt);
            });
        }
    }

    async selectBookmark(name) {
        if (!name || !this.sceneState.projectData) return;
        const b = this.sceneState.projectData.bookmarks.find(x => x.name === name);
        if (!b) return;

        this.sceneState.activeBookmark = name;
        
        const dateSelect = document.getElementById('scan-date-selector');
        if (dateSelect) dateSelect.value = b.scan_date;
        
        await this.loadScan(b.scan_date);
        
        const closest = AutoStackManager.findNearestPano(
            { position: b.position, floor_id: b.floor_id },
            this.sceneState.currentScan.panos,
            99999.0
        );
        
        if (closest) {
            const fSelect = document.getElementById('floor-selector');
            if (fSelect) fSelect.value = closest.floor_id;
            this.setFloor(closest.floor_id);
            this.goToPano(closest.id);
        }
        
        this.sceneState.cameraLon = b.rotation[0];
        this.sceneState.cameraLat = b.rotation[1];
        this.renderer.updateCamera(this.sceneState.cameraLat, this.sceneState.cameraLon);
        this.renderKeyplan();
    }

    addNewBookmark() {
        if (!this.sceneState.currentPano) return alert("Open a viewpoint first to create a bookmark.");
        const name = prompt("Enter a unique name for this spatial bookmark:");
        if (!name || name.trim() === "") return;

        this.projectManager.addBookmark(
            name.trim(),
            this.sceneState.currentScanDate,
            this.sceneState.currentPano.position,
            [this.sceneState.cameraLon, this.sceneState.cameraLat],
            this.sceneState.currentFloorId
        );

        this.updateBookmarksSelector();
        this.projectManager.saveProject();
    }

    onMouseDown(event) {
        this.controls.isDragging = false;
        this.controls.mouseDownTime = Date.now();
        this.controls.previousMousePosition = { x: event.clientX, y: event.clientY };
    }

    onMouseMove(event) {
        if (event.buttons === 1) {
            this.controls.isDragging = true;
            const deltaMove = {
                x: event.clientX - this.controls.previousMousePosition.x,
                y: event.clientY - this.controls.previousMousePosition.y
            };

            this.sceneState.cameraLon -= deltaMove.x * 0.15;
            this.sceneState.cameraLat += deltaMove.y * 0.15;
            this.sceneState.cameraLat = Math.max(-85, Math.min(85, this.sceneState.cameraLat));

            this.controls.previousMousePosition = { x: event.clientX, y: event.clientY };
            this.renderer.updateCamera(this.sceneState.cameraLat, this.sceneState.cameraLon);
            this.renderKeyplan();
        }
    }

    onMouseUp(event) {
        if (Date.now() - this.controls.mouseDownTime < 200) {
            this.controls.isDragging = false;
        }
    }

    onMouseWheel(event) {
        const fov = this.renderer.camera.fov + event.deltaY * 0.05;
        this.renderer.camera.fov = THREE.MathUtils.clamp(fov, 30, 100);
        this.renderer.camera.updateProjectionMatrix();
    }

    onClick(event) {
        if (this.controls.isDragging) return;
        
        this.mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
        this.mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

        this.raycaster.setFromCamera(this.mouse, this.renderer.camera);

        const intersects = this.raycaster.intersectObjects(this.renderer.navMarkersGroup.children);
        if (intersects.length > 0) {
            const nid = intersects[0].object.userData.panoId;
            gsap.to(this.renderer.camera, { 
                duration: 0.4, 
                fov: 30, 
                onUpdate: () => this.renderer.camera.updateProjectionMatrix(), 
                onComplete: () => {
                    this.goToPano(nid);
                    this.renderer.camera.fov = 75;
                    this.renderer.camera.updateProjectionMatrix();
                }
            });
        }
    }

    onDblClick(event) {
        if (!this.sceneState.currentPano || !this.sceneState.currentScan) return;
        
        // Calculate mouse coordinates in normalized device space
        this.mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
        this.mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;
        
        this.raycaster.setFromCamera(this.mouse, this.renderer.camera);
        const clickDir = this.raycaster.ray.direction.clone();
        
        const currentThreePos = CoordsUtility.pythonToThree(this.sceneState.currentPano.position, THREE);
        const allPanos = this.sceneState.currentScan.panos;
        
        let bestNeighbor = null;
        let maxScore = -Infinity;
        
        this.sceneState.currentPano.neighbors.forEach(nid => {
            const neighbor = allPanos.find(p => p.id === nid);
            if (!neighbor) return;
            
            const neighborPos = CoordsUtility.pythonToThree(neighbor.position, THREE);
            const relPos = neighborPos.clone().sub(currentThreePos);
            const distance = relPos.length();
            
            const relDir = relPos.clone().normalize();
            const dot = relDir.dot(clickDir);
            
            // Check if neighbor is within a 50-degree cone of click direction
            if (dot > 0.64) {
                // Score based on angular alignment and proximity
                const score = dot / (distance + 0.1);
                if (score > maxScore) {
                    maxScore = score;
                    bestNeighbor = nid;
                }
            }
        });
        
        if (bestNeighbor) {
            gsap.to(this.renderer.camera, { 
                duration: 0.4, 
                fov: 30, 
                onUpdate: () => this.renderer.camera.updateProjectionMatrix(), 
                onComplete: () => {
                    this.goToPano(bestNeighbor);
                    this.renderer.camera.fov = 75;
                    this.renderer.camera.updateProjectionMatrix();
                }
            });
        }
    }

    onWindowResize() {
        this.renderer.resize();
        this.renderKeyplan();
    }
}

function startApp() {
    window.app = new WalkthroughApp();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startApp);
} else {
    startApp();
}
