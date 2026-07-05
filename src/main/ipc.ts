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

  // ─── Memory & Knowledge IPC handlers ──────────────────────────────

  ipcMain.handle('memory:get', async () => {
    try {
      const result = await pythonBridge.request('/memory/memory')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('memory:store', async (_event, key: string, value: string, category: string) => {
    try {
      const result = await pythonBridge.request('/memory/memory', { key, value, category })
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('memory:forget', async (_event, key: string) => {
    try {
      const result = await pythonBridge.request(`/memory/memory/${encodeURIComponent(key)}`, {}, 5000)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('memory:search', async (_event, query: string) => {
    try {
      const result = await pythonBridge.request(`/memory/memory/search?query=${encodeURIComponent(query)}`)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // ─── Notes IPC handlers ───────────────────────────────────────────

  ipcMain.handle('notes:get', async () => {
    try {
      const result = await pythonBridge.request('/memory/notes')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('notes:create', async (_event, title: string, content: string, tags: string[]) => {
    try {
      const result = await pythonBridge.request('/memory/notes', { title, content, tags })
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('notes:delete', async (_event, noteId: number) => {
    try {
      const result = await pythonBridge.request(`/memory/notes/${noteId}`, {}, 5000)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // ─── Documents IPC handlers ───────────────────────────────────────

  ipcMain.handle('documents:powerpoint', async (_event, data: unknown) => {
    try {
      const result = await pythonBridge.request('/documents/powerpoint', data)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('documents:excel', async (_event, data: unknown) => {
    try {
      const result = await pythonBridge.request('/documents/excel', data)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('documents:pdf', async (_event, data: unknown) => {
    try {
      const result = await pythonBridge.request('/documents/pdf', data)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // ─── System Control IPC handlers ──────────────────────────────────

  ipcMain.handle('system:status', async () => {
    try {
      const result = await pythonBridge.request('/system/status')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('system:launch-app', async (_event, appName: string) => {
    try {
      const result = await pythonBridge.request('/system/launch-app', { app_name: appName })
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // ─── Desktop Automation IPC handlers ──────────────────────────────

  ipcMain.handle('desktop:ocr', async (_event, region?: number[]) => {
    try {
      const result = await pythonBridge.request('/desktop/ocr/capture', { region })
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('desktop:wallpaper', async (_event, description: string, source: string) => {
    try {
      const result = await pythonBridge.request('/desktop/wallpaper/set', { description, source })
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // ─── Web & Media IPC handlers ─────────────────────────────────────

  ipcMain.handle('web:browse', async (_event, data: unknown) => {
    try {
      const result = await pythonBridge.request('/web/browse', data)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('web:stocks', async (_event, ticker: string, period: string) => {
    try {
      const result = await pythonBridge.request(`/web/stocks/${encodeURIComponent(ticker)}?period=${period}`)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('web:weather', async (_event, city: string) => {
    try {
      const result = await pythonBridge.request(`/web/weather?city=${encodeURIComponent(city)}`)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('web:generate-image', async (_event, prompt: string, style: string) => {
    try {
      const result = await pythonBridge.request('/web/images/generate', { prompt, style })
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // ─── Voice Settings IPC handlers ──────────────────────────────────

  ipcMain.handle('voice:sensitivity', async (_event, level: string) => {
    try {
      const result = await pythonBridge.request('/voice/sensitivity', { level })
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('voice:set-tts-voice', async (_event, voice: string) => {
    try {
      const result = await pythonBridge.request('/voice/set-tts-voice', { voice })
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('voice:history', async (_event, limit: number) => {
    try {
      const result = await pythonBridge.request(`/voice/history?limit=${limit}`)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // ─── Phase 3: Job Analytics & Follow-ups ──────────────────────────

  ipcMain.handle('jobs:response-analytics', async () => {
    try {
      const result = await pythonBridge.request('/jobs/analytics/responses')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('jobs:record-response', async (_event, data: unknown) => {
    try {
      const result = await pythonBridge.request('/jobs/responses/record', data)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('jobs:followup-candidates', async () => {
    try {
      const result = await pythonBridge.request('/jobs/followups/candidates')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('jobs:schedule-followups', async () => {
    try {
      const result = await pythonBridge.request('/jobs/followups/schedule')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('jobs:send-followup', async (_event, data: unknown) => {
    try {
      const result = await pythonBridge.request('/jobs/followups/send', data)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // ─── Phase 2: Smart Drop Zones ────────────────────────────────────

  // Close app
  ipcMain.handle('system:close-app', async (_event, appName: string) => {
    try {
      const result = await pythonBridge.request('/system/close-app', { app_name: appName })
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Smart Drop Zones
  ipcMain.handle('system:drop-zone:rules:list', async () => {
    try {
      const result = await pythonBridge.request('/system/drop-zone/rules')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('system:drop-zone:rules:create', async (_event, rule: unknown) => {
    try {
      const result = await pythonBridge.request('/system/drop-zone/rules', rule)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('system:drop-zone:rules:delete', async (_event, ruleIndex: number) => {
    try {
      const result = await pythonBridge.request(`/system/drop-zone/rules/${ruleIndex}`, {}, 5000)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('system:drop-zone:evaluate', async (_event, data: unknown) => {
    try {
      const result = await pythonBridge.request('/system/drop-zone/evaluate', data)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // ─── Phase 2: File Sort Wizard ────────────────────────────────────

  ipcMain.handle('system:sort:preview', async (_event, data: unknown) => {
    try {
      const result = await pythonBridge.request('/system/file/sort/preview', data)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('system:sort:execute', async (_event, data: unknown) => {
    try {
      const result = await pythonBridge.request('/system/file/sort/execute', data)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('system:sort:undo', async (_event, undoId: string) => {
    try {
      const result = await pythonBridge.request(`/system/file/sort/undo/${encodeURIComponent(undoId)}`, {}, 10000)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // ─── Phase 2: Git Operations ──────────────────────────────────────

  ipcMain.handle('system:git', async (_event, data: unknown) => {
    try {
      const result = await pythonBridge.request('/system/git', data)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // ─── Phase 2: Package Manager ─────────────────────────────────────

  ipcMain.handle('system:package-manager', async (_event, data: unknown) => {
    try {
      const result = await pythonBridge.request('/system/package-manager', data)
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // ─── Phase 2: Multi-Monitor ───────────────────────────────────────

  ipcMain.handle('system:monitors', async () => {
    try {
      const result = await pythonBridge.request('/system/monitors')
      return { success: true, data: result }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })
}
