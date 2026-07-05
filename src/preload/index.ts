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
    command: (text: string) => ipcRenderer.invoke('voice:command', text),
    setSensitivity: (level: string) => ipcRenderer.invoke('voice:sensitivity', level),
    setTtsVoice: (voice: string) => ipcRenderer.invoke('voice:set-tts-voice', voice),
    history: (limit?: number) => ipcRenderer.invoke('voice:history', limit || 50)
  },

  // Job search
  jobs: {
    scan: () => ipcRenderer.invoke('jobs:scan'),
    matches: () => ipcRenderer.invoke('jobs:matches'),
    approve: (jobId: string) => ipcRenderer.invoke('jobs:approve', jobId),
    responseAnalytics: () => ipcRenderer.invoke('jobs:response-analytics'),
    recordResponse: (data: unknown) => ipcRenderer.invoke('jobs:record-response', data),
    followupCandidates: () => ipcRenderer.invoke('jobs:followup-candidates'),
    scheduleFollowups: () => ipcRenderer.invoke('jobs:schedule-followups'),
    sendFollowup: (data: unknown) => ipcRenderer.invoke('jobs:send-followup', data),
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

  // Memory & Knowledge
  memory: {
    get: () => ipcRenderer.invoke('memory:get'),
    store: (key: string, value: string, category?: string) =>
      ipcRenderer.invoke('memory:store', key, value, category || 'general'),
    forget: (key: string) => ipcRenderer.invoke('memory:forget', key),
    search: (query: string) => ipcRenderer.invoke('memory:search', query)
  },

  // Notes
  notes: {
    get: () => ipcRenderer.invoke('notes:get'),
    create: (title: string, content: string, tags?: string[]) =>
      ipcRenderer.invoke('notes:create', title, content, tags || []),
    delete: (id: number) => ipcRenderer.invoke('notes:delete', id)
  },

  // Documents
  documents: {
    powerpoint: (data: unknown) => ipcRenderer.invoke('documents:powerpoint', data),
    excel: (data: unknown) => ipcRenderer.invoke('documents:excel', data),
    pdf: (data: unknown) => ipcRenderer.invoke('documents:pdf', data)
  },

  // System
  system: {
    status: () => ipcRenderer.invoke('system:status'),
    launchApp: (appName: string) => ipcRenderer.invoke('system:launch-app', appName),
    closeApp: (appName: string) => ipcRenderer.invoke('system:close-app', appName),
    dropZone: {
      listRules: () => ipcRenderer.invoke('system:drop-zone:rules:list'),
      createRule: (rule: unknown) => ipcRenderer.invoke('system:drop-zone:rules:create', rule),
      deleteRule: (ruleIndex: number) => ipcRenderer.invoke('system:drop-zone:rules:delete', ruleIndex),
      evaluate: (data: unknown) => ipcRenderer.invoke('system:drop-zone:evaluate', data),
    },
    sort: {
      preview: (data: unknown) => ipcRenderer.invoke('system:sort:preview', data),
      execute: (data: unknown) => ipcRenderer.invoke('system:sort:execute', data),
      undo: (undoId: string) => ipcRenderer.invoke('system:sort:undo', undoId),
    },
    git: (data: unknown) => ipcRenderer.invoke('system:git', data),
    packageManager: (data: unknown) => ipcRenderer.invoke('system:package-manager', data),
    monitors: () => ipcRenderer.invoke('system:monitors'),
  },

  // Desktop
  desktop: {
    ocr: (region?: number[]) => ipcRenderer.invoke('desktop:ocr', region),
    wallpaper: (description: string, source?: string) =>
      ipcRenderer.invoke('desktop:wallpaper', description, source || 'auto')
  },

  // Web & Media
  web: {
    browse: (data: unknown) => ipcRenderer.invoke('web:browse', data),
    stocks: (ticker: string, period?: string) =>
      ipcRenderer.invoke('web:stocks', ticker, period || '1d'),
    weather: (city: string) => ipcRenderer.invoke('web:weather', city),
    generateImage: (prompt: string, style?: string) =>
      ipcRenderer.invoke('web:generate-image', prompt, style || 'auto')
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
