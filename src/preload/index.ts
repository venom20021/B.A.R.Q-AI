import { contextBridge, ipcRenderer } from 'electron'

// Expose a safe API to the renderer process
contextBridge.exposeInMainWorld('barq', {
  // Python sidecar communication
  python: {
    request: (endpoint: string, data?: unknown) =>
      ipcRenderer.invoke('python:request', endpoint, data),
    health: () => ipcRenderer.invoke('python:health')
  },

  // Voice control
  voice: {
    start: () => ipcRenderer.invoke('voice:start'),
    stop: () => ipcRenderer.invoke('voice:stop'),
    command: (text: string) => ipcRenderer.invoke('voice:command', text)
  },

  // Job search
  jobs: {
    scan: () => ipcRenderer.invoke('jobs:scan'),
    matches: () => ipcRenderer.invoke('jobs:matches'),
    approve: (jobId: string) => ipcRenderer.invoke('jobs:approve', jobId)
  },

  // Social media
  social: {
    trends: () => ipcRenderer.invoke('social:trends'),
    generateScript: (topic: string, format: string) =>
      ipcRenderer.invoke('social:generate-script', topic, format),
    renderVideo: (scriptId: string) => ipcRenderer.invoke('social:render-video', scriptId),
    post: (videoId: string, platforms: string[]) =>
      ipcRenderer.invoke('social:post', videoId, platforms)
  },

  // Analytics
  analytics: {
    career: () => ipcRenderer.invoke('analytics:career'),
    social: () => ipcRenderer.invoke('analytics:social'),
    revenue: () => ipcRenderer.invoke('analytics:revenue')
  },

  // Notifications
  notification: {
    show: (title: string, body: string) =>
      ipcRenderer.send('notification:show', title, body),
    poll: () => ipcRenderer.invoke('notifications:poll'),
    markRead: (id: number) => ipcRenderer.invoke('notifications:mark-read', id),
    send: (title: string, body: string, priority?: string, category?: string) =>
      ipcRenderer.invoke('notifications:send', title, body, priority, category),
    status: () => ipcRenderer.invoke('notifications:status'),
    test: (channel: string) => ipcRenderer.invoke('notifications:test', channel),
    startPolling: () => ipcRenderer.send('notifications:start-polling'),
    stopPolling: () => ipcRenderer.send('notifications:stop-polling')
  },

  // Navigation listener
  onNavigate: (callback: (route: string) => void) => {
    ipcRenderer.on('navigate', (_event, route) => callback(route))
  },

  // Voice toggle listener
  onVoiceToggle: (callback: () => void) => {
    ipcRenderer.on('toggle-voice', () => callback())
  },

  // Notification update listener (from polling)
  onNotificationsUpdate: (callback: (data: unknown) => void) => {
    ipcRenderer.on('notifications:update', (_event, data) => callback(data))
  },

  // Quick Overlay listener (triggered by Ctrl+Shift+I global shortcut)
  onQuickOverlay: (callback: (position: { x: number; y: number }) => void) => {
    ipcRenderer.on('quick-overlay:show', (_event, position) => callback(position))
  },

  // Window management
  window: {
    toggle: () => ipcRenderer.send('window:toggle'),
    minimize: () => ipcRenderer.send('window:minimize'),
    close: () => ipcRenderer.send('window:close')
  }
})
