import { ipcMain, BrowserWindow, Notification } from 'electron'
import { pythonBridge } from './python-bridge'

export function registerIpcHandlers(): void {
  // --- Python Sidecar Communication ---

  // Generic request to Python backend
  ipcMain.handle('python:request', async (_event, endpoint: string, data?: unknown) => {
    try {
      const result = await pythonBridge.request(endpoint, data)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Check Python sidecar health
  ipcMain.handle('python:health', async () => {
    try {
      const result = await pythonBridge.request('/health')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // --- Voice Control ---

  // Start voice recognition
  ipcMain.handle('voice:start', async () => {
    try {
      const result = await pythonBridge.request('/voice/start')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Stop voice recognition
  ipcMain.handle('voice:stop', async () => {
    try {
      const result = await pythonBridge.request('/voice/stop')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Send voice command
  ipcMain.handle('voice:command', async (_event, command: string) => {
    try {
      const result = await pythonBridge.request('/voice/command', { command })
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // --- Job Search ---

  // Trigger job scan
  ipcMain.handle('jobs:scan', async () => {
    try {
      const result = await pythonBridge.request('/jobs/scan')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Get job matches
  ipcMain.handle('jobs:matches', async () => {
    try {
      const result = await pythonBridge.request('/jobs/matches')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Approve job application
  ipcMain.handle('jobs:approve', async (_event, jobId: string) => {
    try {
      const result = await pythonBridge.request('/jobs/approve', { job_id: jobId })
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // --- Social Media ---

  // Trigger trend research
  ipcMain.handle('social:trends', async () => {
    try {
      const result = await pythonBridge.request('/social/trends')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Generate content script
  ipcMain.handle('social:generate-script', async (_event, topic: string, format: string) => {
    try {
      const result = await pythonBridge.request('/social/generate-script', { topic, format })
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Render video
  ipcMain.handle('social:render-video', async (_event, scriptId: string) => {
    try {
      const result = await pythonBridge.request('/social/render-video', { script_id: scriptId })
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Post to platforms
  ipcMain.handle('social:post', async (_event, videoId: string, platforms: string[]) => {
    try {
      const result = await pythonBridge.request('/social/post', { video_id: videoId, platforms })
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // --- Analytics ---

  // Get career analytics
  ipcMain.handle('analytics:career', async () => {
    try {
      const result = await pythonBridge.request('/analytics/career')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Get social analytics
  ipcMain.handle('analytics:social', async () => {
    try {
      const result = await pythonBridge.request('/analytics/social')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Get revenue data
  ipcMain.handle('analytics:revenue', async () => {
    try {
      const result = await pythonBridge.request('/analytics/revenue')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // --- Notifications ---

  // Send desktop notification
  ipcMain.on('notification:show', (_event, title: string, body: string) => {
    const notification = new Notification({
      title,
      body,
      silent: false
    })
    notification.show()
  })

  // Poll for pending notifications from Python sidecar
  ipcMain.handle('notifications:poll', async () => {
    try {
      const result = await pythonBridge.request('/notifications/pending')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Mark a notification as read
  ipcMain.handle('notifications:mark-read', async (_event, notificationId: number) => {
    try {
      const result = await pythonBridge.request(`/notifications/${notificationId}/read`, {}, 5000)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Send a notification through the Python sidecar
  ipcMain.handle('notifications:send', async (_event, title: string, body: string, priority?: string, category?: string) => {
    try {
      const result = await pythonBridge.request('/notifications/send', {
        title,
        body,
        priority: priority || 'normal',
        category: category || 'general'
      })
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Get notification channel status
  ipcMain.handle('notifications:status', async () => {
    try {
      const result = await pythonBridge.request('/notifications/status')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Test a notification channel
  ipcMain.handle('notifications:test', async (_event, channel: string) => {
    try {
      const result = await pythonBridge.request(`/notifications/test/${channel}`)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Notification polling with recursive setTimeout (avoids stacking)
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let isPolling = false

  async function pollNotifications(): Promise<void> {
    try {
      const result = await pythonBridge.request('/notifications/pending')
      if (result && typeof result === 'object') {
        const data = result as { notifications?: Array<{ id: number; title: string; body: string }>; counts?: { unread: number } }
        const notifications = data.notifications || []
        const win = BrowserWindow.getAllWindows()[0]
        if (win && notifications.length > 0) {
          win.webContents.send('notifications:update', data)
          // Show native toast and mark as read concurrently
          await Promise.allSettled(
            notifications.map(async (notif) => {
              const notification = new Notification({
                title: notif.title,
                body: notif.body,
                silent: false
              })
              notification.show()
              // Mark as read after showing
              await pythonBridge.request(`/notifications/${notif.id}/read`, {}, 3000)
            })
          )
        }
      }
    } catch {
      // Silently ignore polling errors
    } finally {
      if (isPolling) {
        pollTimer = setTimeout(pollNotifications, 10000)
      }
    }
  }

  ipcMain.on('notifications:start-polling', () => {
    if (isPolling) return
    isPolling = true
    pollNotifications()
  })

  ipcMain.on('notifications:stop-polling', () => {
    isPolling = false
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  })

  // --- Window Management ---

  // Navigate renderer
  ipcMain.on('navigate', (_event, route: string) => {
    const win = BrowserWindow.getAllWindows()[0]
    if (win) {
      win.webContents.send('navigate', route)
    }
  })

  // Toggle window visibility
  ipcMain.on('window:toggle', () => {
    const win = BrowserWindow.getAllWindows()[0]
    if (win) {
      if (win.isVisible()) {
        win.hide()
      } else {
        win.show()
        win.focus()
      }
    }
  })

  // Quick Overlay: alternative trigger via IPC (for tray menu, etc.)
  ipcMain.on('quick-overlay:show', () => {
    const win = BrowserWindow.getAllWindows()[0]
    if (win) {
      const bounds = win.getBounds()
      win.webContents.send('quick-overlay:show', {
        x: Math.round(bounds.width / 2),
        y: Math.round(bounds.height / 3)
      })
    }
  })
}
