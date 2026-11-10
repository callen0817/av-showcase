const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    readFile: (path) => ipcRenderer.invoke('read-file', { path }),
    fileExists: (path) => ipcRenderer.invoke('file-exists', { path }),
    readFileBin: (path) => ipcRenderer.invoke('read-file-bin', { path }),
    writeFile: (path, content) => ipcRenderer.invoke('write-file', { path, content }),
    apiRequest: (endpoint, payload) => ipcRenderer.invoke('api-request', { endpoint, payload }),
    selectDirectory: () => ipcRenderer.invoke('select-directory'),
    selectFile: (filters) => ipcRenderer.invoke('select-file', filters),
    getRecentProjects: () => ipcRenderer.invoke('get-recent-projects'),
    addRecentProject: (project) => ipcRenderer.invoke('add-recent-project', project),
    deleteProject: (path, deleteDisk) => ipcRenderer.invoke('delete-project', { path, deleteDisk }),
    createFolder: (name) => ipcRenderer.invoke('create-folder', name),
    deleteFolder: (name) => ipcRenderer.invoke('delete-folder', name)
});
