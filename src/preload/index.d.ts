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
  }
  jobs: {
    scan: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    matches: () => Promise<{ success: boolean; data?: unknown; error?: string }>
    approve: (jobId: string) => Promise<{ success: boolean; data?: unknown; error?: string }>
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
