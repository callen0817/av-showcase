export class ProjectManager {
    constructor() {
        this.projectData = null;
        this.projectPath = null;
        this.autosaveInterval = null;
        this.isModified = false;
    }

    /**
     * Loads project metadata from project.avproj.
     * @param {string} dirPath - Folder path containing project.avproj
     * @returns {Promise<{ success: boolean, data?: Object, error?: string }>}
     */
    async loadProject(dirPath) {
        this.stopAutosaveLoop();
        this.projectPath = dirPath;

        const avprojPath = `${dirPath}/project.avproj`.replace(/\\/g, '/');
        const res = await window.electronAPI.readFile(avprojPath);
        if (res.success) {
            try {
                this.projectData = JSON.parse(res.data);
                this.isModified = false;
                
                // Initialize default arrays if missing
                if (!this.projectData.bookmarks) {
                    this.projectData.bookmarks = [];
                }
                if (!this.projectData.scans) {
                    this.projectData.scans = [];
                }
                if (!this.projectData.settings) {
                    this.projectData.settings = {
                        max_autostack_distance: 10.0,
                        default_unit: "metric"
                    };
                }

                this.startAutosaveLoop();
                this.logAutosave("Project loaded successfully.");
                return { success: true, data: this.projectData };
            } catch (err) {
                return { success: false, error: "Failed to parse project.avproj: " + err.message };
            }
        }
        return { success: false, error: res.error };
    }

    /**
     * Saves the current project state back to project.avproj.
     * @returns {Promise<{ success: boolean, error?: string }>}
     */
    async saveProject() {
        if (!this.projectData || !this.projectPath) {
            return { success: false, error: "No active project." };
        }

        const avprojPath = `${this.projectPath}/project.avproj`.replace(/\\/g, '/');
        const content = JSON.stringify(this.projectData, null, 2);
        const res = await window.electronAPI.writeFile(avprojPath, content);
        
        if (res.success) {
            this.isModified = false;
            this.logAutosave("Project saved successfully.");
            return { success: true };
        }
        
        this.logAutosave("Autosave Failed: " + res.error);
        return { success: false, error: res.error };
    }

    startAutosaveLoop() {
        this.stopAutosaveLoop();
        // Autosave every 60 seconds if changes have occurred
        this.autosaveInterval = setInterval(() => {
            if (this.isModified) {
                this.saveProject();
            }
        }, 60000);
    }

    stopAutosaveLoop() {
        if (this.autosaveInterval) {
            clearInterval(this.autosaveInterval);
            this.autosaveInterval = null;
        }
    }

    /**
     * Registers a new spatial viewpoint bookmark.
     * @param {string} name - Name of the bookmark (e.g. "Kitchen")
     * @param {string} scanDate - Deterministic scan date target
     * @param {number[]} position - Python coordinate [x, y, z]
     * @param {number[]} rotation - Camera yaw/pitch angles [lon, lat]
     * @param {number} floorId - Associated floor index
     */
    addBookmark(name, scanDate, position, rotation, floorId) {
        if (!this.projectData) return;

        // Strip existing bookmark with same name if exists
        this.projectData.bookmarks = this.projectData.bookmarks.filter(b => b.name.toLowerCase() !== name.toLowerCase());

        const bookmark = {
            name,
            scan_date: scanDate,
            position: [...position],
            rotation: [...rotation],
            floor_id: floorId
        };

        this.projectData.bookmarks.push(bookmark);
        this.isModified = true;
        this.logAutosave(`Added bookmark: "${name}"`);
    }

    removeBookmark(name) {
        if (!this.projectData) return;
        this.projectData.bookmarks = this.projectData.bookmarks.filter(b => b.name.toLowerCase() !== name.toLowerCase());
        this.isModified = true;
        this.logAutosave(`Removed bookmark: "${name}"`);
    }

    /**
     * Writes an audit log statement to logs/autosave.log inside the project directory.
     * @param {string} message - Logging message
     */
    async logAutosave(message) {
        if (!this.projectPath) return;
        const logPath = `${this.projectPath}/logs/autosave.log`.replace(/\\/g, '/');
        const timestamp = new Date().toISOString();
        const logLine = `[${timestamp}] ${message}\n`;
        // Append log line
        const readRes = await window.electronAPI.readFile(logPath);
        const existing = readRes.success ? readRes.data : "";
        await window.electronAPI.writeFile(logPath, existing + logLine);
    }
}
