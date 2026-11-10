const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

let mainWindow;
let pythonProcess = null;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1280,
        height: 720,
        icon: path.join(__dirname, 'assets', 'av-walkthrough-logo.png'),
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true,
            webSecurity: false
        },
        autoHideMenuBar: true
    });

    // In production we would load from Vite build dir
    // During dev we load from localhost or standard Vite build.
    mainWindow.loadFile(path.join(__dirname, 'index.html'));

    mainWindow.webContents.on('console-message', (event, level, message, line, sourceId) => {
        console.log(`[Renderer] ${message} (Source: ${sourceId}, Line: ${line})`);
    });
    
    // Open devtools to force the renderer to load properly or display errors
    mainWindow.webContents.openDevTools();
}

function startPythonBackend() {
    const pythonScript = path.join(__dirname, 'backend', 'app.py');
    const localAppData = process.env.LOCALAPPDATA || path.join(process.env.USERPROFILE || '', 'AppData', 'Local');
    const candidatePythons = [
        path.join(localAppData, 'Programs', 'Python', 'Python311', 'python.exe'),
        path.join(localAppData, 'Programs', 'Python', 'Python312', 'python.exe'),
        path.join(localAppData, 'Programs', 'Python', 'Python310', 'python.exe')
    ];
    let pythonExe = 'python';
    for (const candidate of candidatePythons) {
        if (fs.existsSync(candidate)) {
            pythonExe = candidate;
            break;
        }
    }
    logApp(`Starting Python backend script: ${pythonScript} using ${pythonExe}`);
    pythonProcess = spawn(pythonExe, ['-u', pythonScript]);

    pythonProcess.stdout.on('data', (data) => {
        logApp(`[Python]: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        logApp(`[Python Error]: ${data}`);
    });

    pythonProcess.on('close', (code) => {
        logApp(`Python backend exited with code ${code}`);
    });
}


function checkLicense() {
    const licensePath = path.join(app.getPath('userData'), 'license.key');
    if (!fs.existsSync(licensePath)) {
        // In a real app we would open a custom dialog window. For the stub, we simulate the prompt and save a trial key.
        console.log("No license found. Automatically generating trial stub.");
        fs.writeFileSync(licensePath, "TRIAL_LICENSE_1234");
    } else {
        console.log("License found:", fs.readFileSync(licensePath, 'utf-8'));
    }
}

// Allow loading ES modules from local file system without a custom protocol
app.commandLine.appendSwitch('disable-web-security');
app.commandLine.appendSwitch('allow-file-access-from-files');

app.whenReady().then(() => {
    checkLicense();
    startPythonBackend();
    createWindow();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('quit', () => {
    if (pythonProcess) {
        pythonProcess.kill();
    }
});

// Logging utility for commercial stability
let LOGS_FILE = null;
function logApp(msg) {
    if (!LOGS_FILE) {
        try {
            LOGS_FILE = path.join(app.getPath('userData'), 'app.log');
        } catch (e) {
            console.log(`[Early Log] ${msg}`);
            return;
        }
    }
    const timestamp = new Date().toISOString();
    const line = `[${timestamp}] ${msg}\n`;
    try {
        fs.appendFileSync(LOGS_FILE, line);
    } catch (e) {}
    console.log(line.trim());
}

// IPC Logic
ipcMain.handle('read-file', async (event, { path: filePath }) => {
    try {
        const data = fs.readFileSync(filePath, 'utf-8');
        return { success: true, data };
    } catch (error) {
        logApp(`File Read Error on ${filePath}: ${error.message}`);
        return { success: false, error: error.message };
    }
});

ipcMain.handle('file-exists', async (event, { path: filePath }) => {
    try {
        const exists = fs.existsSync(filePath);
        return { success: true, exists };
    } catch (error) {
        return { success: false, exists: false, error: error.message };
    }
});

ipcMain.handle('write-file', async (event, { path: filePath, content }) => {
    try {
        fs.writeFileSync(filePath, content, 'utf-8');
        return { success: true };
    } catch (error) {
        logApp(`File Write Error on ${filePath}: ${error.message}`);
        return { success: false, error: error.message };
    }
});

ipcMain.handle('read-file-bin', async (event, { path: filePath }) => {
    try {
        const data = fs.readFileSync(filePath);
        return { success: true, data };
    } catch (error) {
        logApp(`Binary File Read Error on ${filePath}: ${error.message}`);
        return { success: false, error: error.message };
    }
});

ipcMain.handle('api-request', async (event, { endpoint, payload }) => {
    // In a real app we might use standard http requests to localhost from Main or Renderer
    // This provides a secure way to do it via IPC if we strictly don't want Renderer accessing network
    try {
        const { net } = require('electron');
        const response = await net.fetch(`http://localhost:8000/${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        return { success: true, data };
    } catch (error) {
        console.error("API Request Error:", error);
        return { success: false, error: error.message };
    }
});

ipcMain.handle('select-directory', async () => {
    const { dialog } = require('electron');
    const result = await dialog.showOpenDialog(mainWindow, {
        properties: ['openDirectory']
    });
    return result.filePaths;
});

ipcMain.handle('select-file', async (event, filters) => {
    const { dialog } = require('electron');
    const result = await dialog.showOpenDialog(mainWindow, {
        properties: ['openFile'],
        filters: filters || []
    });
    return result.filePaths;
});

function getProjectsFile() {
    return path.join(app.getPath('userData'), 'recent_projects.json');
}

ipcMain.handle('get-recent-projects', async () => {
    try {
        const projectsFile = getProjectsFile();
        if (!fs.existsSync(projectsFile)) return { projects: [], folders: [] };
        const data = fs.readFileSync(projectsFile, 'utf-8');
        const parsed = JSON.parse(data);
        if (Array.isArray(parsed)) {
            return { projects: parsed, folders: [] };
        }
        if (!parsed.projects) parsed.projects = [];
        if (!parsed.folders) parsed.folders = [];
        return parsed;
    } catch (e) {
        return { projects: [], folders: [] };
    }
});

ipcMain.handle('add-recent-project', async (event, project) => {
    try {
        const projectsFile = getProjectsFile();
        let registry = { projects: [], folders: [] };
        if (fs.existsSync(projectsFile)) {
            const parsed = JSON.parse(fs.readFileSync(projectsFile, 'utf-8'));
            if (Array.isArray(parsed)) {
                registry.projects = parsed;
            } else {
                registry = parsed;
            }
        }
        if (!registry.projects) registry.projects = [];
        if (!registry.folders) registry.folders = [];
        
        registry.projects = registry.projects.filter(p => p.path !== project.path);
        registry.projects.unshift(project);
        registry.projects = registry.projects.slice(0, 100);
        fs.writeFileSync(projectsFile, JSON.stringify(registry));
        return { success: true };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

ipcMain.handle('delete-project', async (event, { path: projectPath, deleteDisk }) => {
    try {
        const projectsFile = getProjectsFile();
        let registry = { projects: [], folders: [] };
        if (fs.existsSync(projectsFile)) {
            const parsed = JSON.parse(fs.readFileSync(projectsFile, 'utf-8'));
            if (Array.isArray(parsed)) {
                registry.projects = parsed;
            } else {
                registry = parsed;
            }
        }
        if (!registry.projects) registry.projects = [];
        
        registry.projects = registry.projects.filter(p => p.path !== projectPath);
        fs.writeFileSync(projectsFile, JSON.stringify(registry));
        
        let diskDeleted = false;
        let diskError = null;
        
        // Clean up project files on disk ONLY if requested
        if (deleteDisk && fs.existsSync(projectPath)) {
            const pathLower = projectPath.toLowerCase().replace(/\\/g, '/');
            const isSystemDir = pathLower.endsWith('/downloads') || 
                                pathLower.endsWith('/desktop') || 
                                pathLower.endsWith('/documents') ||
                                pathLower.endsWith('/onedrive') ||
                                pathLower === 'c:' || 
                                pathLower === 'c:/';
                                
            if (isSystemDir) {
                diskError = "Deletion of system folders (Downloads/Desktop/Documents) is blocked to protect your files.";
            } else {
                try {
                    const { shell } = require('electron');
                    await shell.trashItem(projectPath);
                    diskDeleted = true;
                } catch (err) {
                    diskDeleted = false;
                    diskError = err.message;
                }
            }
        }
        return { success: true, diskDeleted, diskError };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

ipcMain.handle('create-folder', async (event, folderName) => {
    try {
        const projectsFile = getProjectsFile();
        let registry = { projects: [], folders: [] };
        if (fs.existsSync(projectsFile)) {
            const parsed = JSON.parse(fs.readFileSync(projectsFile, 'utf-8'));
            if (Array.isArray(parsed)) {
                registry.projects = parsed;
            } else {
                registry = parsed;
            }
        }
        if (!registry.projects) registry.projects = [];
        if (!registry.folders) registry.folders = [];
        
        if (!registry.folders.includes(folderName)) {
            registry.folders.push(folderName);
            registry.folders.sort();
        }
        fs.writeFileSync(projectsFile, JSON.stringify(registry));
        return { success: true };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

ipcMain.handle('delete-folder', async (event, folderName) => {
    try {
        const projectsFile = getProjectsFile();
        let registry = { projects: [], folders: [] };
        if (fs.existsSync(projectsFile)) {
            const parsed = JSON.parse(fs.readFileSync(projectsFile, 'utf-8'));
            if (Array.isArray(parsed)) {
                registry.projects = parsed;
            } else {
                registry = parsed;
            }
        }
        if (!registry.projects) registry.projects = [];
        if (!registry.folders) registry.folders = [];
        
        registry.folders = registry.folders.filter(f => f !== folderName);
        
        // Remove folder references from associated projects
        registry.projects.forEach(p => {
            if (p.folder === folderName) {
                p.folder = null;
            }
        });
        
        fs.writeFileSync(projectsFile, JSON.stringify(registry));
        return { success: true };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

app.on('will-quit', () => {
    if (pythonProcess) {
        pythonProcess.kill();
    }
});
