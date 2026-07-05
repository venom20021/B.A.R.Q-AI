import { ElectronAPI } from '@electron-toolkit/preload'

interface BarqAPI {
  python: {
    request: (endpoint: string, data?: unknown) => Promise<{ success: boolean; data?: unknown; error?: string }>
    health: () => Promise<{ success: boolean; data?: unknown; error?: string }>
  }
  voice: {
    start: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    stop: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    command: (text: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
    setSensitivity: (level: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
    setTtsVoice: (voice: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
    history: (limit?: number) => Promise<{ success: boolean; data?: unknown; error?: string }>
  }
  jobs: {
    scan: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    matches: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    approve: (jobId: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
    responseAnalytics: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    recordResponse: (data: unknown) => Promise<{ success: boolean; data?: unknown; error?: string }>
    followupCandidates: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    scheduleFollowups: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    sendFollowup: (data: unknown) => Promise<{ success: boolean; data?: unknown; error?: string }>
  }
  social: {
    trends: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    generateScript: (topic: string, format: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
    renderVideo: (scriptId: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
    post: (videoId: string, platforms: string[]) => Promise<{ success: boolean; data?: unknown; error?: string }>
  }
  analytics: {
    career: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    social: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    revenue: () => Promise<{ success: boolean; data?: unknown; error?: string }>
  }
  notification: {
    show: (title: string, body: string) => void
    poll: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    markRead: (id: number) => Promise<{ success: boolean; data?: unknown; error?: string }>
    send: (title: string, body: string, priority?: string, category?: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
    status: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    test: (channel: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
    startPolling: () => void
    stopPolling: () => void
  }
  memory: {
    get: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    store: (key: string, value: string, category?: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
    forget: (key: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
    search: (query: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
  }
  notes: {
    get: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    create: (title: string, content: string, tags?: string[]) => Promise<{ success: boolean; data?: unknown; error?: string }>
    delete: (id: number) => Promise<{ success: boolean; data?: unknown; error?: string }>
  }
  documents: {
    powerpoint: (data: unknown) => Promise<{ success: boolean; data?: unknown; error?: string }>
    excel: (data: unknown) => Promise<{ success: boolean; data?: unknown; error?: string }>
    pdf: (data: unknown) => Promise<{ success: boolean; data?: unknown; error?: string }>
  }
  system: {
    status: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    launchApp: (appName: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
    closeApp: (appName: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
    dropZone: {
      listRules: () => Promise<{ success: boolean; data?: unknown; error?: string }>
      createRule: (rule: unknown) => Promise<{ success: boolean; data?: unknown; error?: string }>
      deleteRule: (ruleIndex: number) => Promise<{ success: boolean; data?: unknown; error?: string }>
      evaluate: (data: unknown) => Promise<{ success: boolean; data?: unknown; error?: string }>
    }
    sort: {
      preview: (data: unknown) => Promise<{ success: boolean; data?: unknown; error?: string }>
      execute: (data: unknown) => Promise<{ success: boolean; data?: unknown; error?: string }>
      undo: (undoId: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
    }
    git: (data: unknown) => Promise<{ success: boolean; data?: unknown; error?: string }>
    packageManager: (data: unknown) => Promise<{ success: boolean; data?: unknown; error?: string }>
    monitors: () => Promise<{ success: boolean; data?: unknown; error?: string }>
  }
  desktop: {
    ocr: (region?: number[]) => Promise<{ success: boolean; data?: unknown; error?: string }>
    wallpaper: (description: string, source?: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
  }
  web: {
    browse: (data: unknown) => Promise<{ success: boolean; data?: unknown; error?: string }>
    stocks: (ticker: string, period?: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
    weather: (city: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
    generateImage: (prompt: string, style?: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
  }
  onNavigate: (callback: (route: string) => void) => void
  onVoiceToggle: (callback: () => void) => void
  onNotificationsUpdate: (callback: (data: unknown) => void) => void
  onQuickOverlay: (callback: (position: { x: number; y: number }) => void) => void
  window: {
    toggle: () => void
    minimize: () => void
    close: () => void
  }
}

declare global {
  interface Window {
    electron: ElectronAPI
    barq: BarqAPI
  }
}
