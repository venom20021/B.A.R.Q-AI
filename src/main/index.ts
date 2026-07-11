import { app, BrowserWindow, shell, globalShortcut } from 'electron'
import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import { createTray, setAppIsQuitting } from './tray'
import { registerIpcHandlers } from './ipc'
import { PythonSidecar } from './python-bridge'
import { initOverlayManager, destroyOverlayManager } from './overlay-manager'

let mainWindow: BrowserWindow | null = null
let pythonSidecar: PythonSidecar | null = null
let isQuitting = false

// ═══════════════════════════════════════════════════════════════════════════════
// Wake Receiver — Lightweight HTTP server for Python wake word detection
// Listens on port 8112 for POST /wake to restore and focus the window
// ═══════════════════════════════════════════════════════════════════════════════

import * as http from 'http'

const WAKE_PORT = 8112
let wakeServer: http.Server | null = null

function startWakeReceiver(): void {
  wakeServer = http.createServer((req, res) => {
    // CORS headers for local Python requests
    res.setHeader('Access-Control-Allow-Origin', '*')
    res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS')
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type')

    if (req.method === 'OPTIONS') {
      res.writeHead(204)
      res.end()
      return
    }

    if (req.method === 'POST' && req.url === '/wake') {
      const chunks: string[] = []
      req.on('data', (chunk: string) => { chunks.push(chunk) })
      req.on('end', () => {
        try {
          const win = BrowserWindow.getAllWindows()[0]
          if (win) {
            if (win.isMinimized()) win.restore()
            if (!win.isVisible()) win.show()
            win.focus()
            console.log('[WakeReceiver] Window restored and focused via /wake')
          }

          res.writeHead(200, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ status: 'ok', message: 'BARQ window focused' }))
        } catch (err) {
          console.error('[WakeReceiver] Error handling /wake:', err)
          res.writeHead(500)
          res.end(JSON.stringify({ status: 'error', message: String(err) }))
        }
      })
    } else {
      res.writeHead(404)
      res.end('Not found')
    }
  })

  wakeServer.listen(WAKE_PORT, '127.0.0.1', () => {
    console.log(`[WakeReceiver] Listening for wake word on http://127.0.0.1:${WAKE_PORT}/wake`)
  })

  wakeServer.on('error', (err: NodeJS.ErrnoException) => {
    if (err.code === 'EADDRINUSE') {
      console.warn(`[WakeReceiver] Port ${WAKE_PORT} in use — wake listener unavailable`)
    } else {
      console.error('[WakeReceiver] Server error:', err)
    }
  })
}

function stopWakeReceiver(): void {
  if (wakeServer) {
    wakeServer.close()
    wakeServer = null
    console.log('[WakeReceiver] Stopped')
  }
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    show: false,
    title: 'BARQ',
    icon: join(__dirname, '../../resources/icon.png'),
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      nodeIntegration: false,
      contextIsolation: true
    }
  })

  // Hide menu bar for cleaner look
  mainWindow.setMenuBarVisibility(false)

  mainWindow.on('ready-to-show', () => {
    mainWindow?.show()
  })

  mainWindow.on('close', (event) => {
    // Hide to tray instead of closing
    if (!isQuitting) {
      event.preventDefault()
      mainWindow?.hide()
    }
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // In development, load from vite dev server
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

app.whenReady().then(async () => {
  // Set app user model id for Windows
  electronApp.setAppUserModelId('com.barq.desktop')

  // Default open or close DevTools by F12 in development
  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  // ─── Auto-start on OS login ────────────────────────────────────────
  app.setLoginItemSettings({
    openAtLogin: true,
    path: app.getPath('exe'),
  })

  // ─── Start wake receiver HTTP server ───────────────────────────────
  startWakeReceiver()

  // Register global shortcut: Ctrl+Shift+I — Quick Overlay
  globalShortcut.register('CommandOrControl+Shift+I', () => {
    const win = BrowserWindow.getAllWindows()[0]
    if (win) {
      const bounds = win.getBounds()
      win.webContents.send('quick-overlay:show', {
        x: Math.round(bounds.width / 2),
        y: Math.round(bounds.height / 3)
      })
    }
  })

  // Register IPC handlers
  registerIpcHandlers()

  // Initialize desktop overlay manager
  initOverlayManager()

  // Start Python sidecar
  pythonSidecar = new PythonSidecar()
  await pythonSidecar.start()

  // Auto-start wake word detection in Python sidecar
  try {
    await pythonSidecar.request('/voice/start', {}, 5000)
    console.log('[Main] Wake word detection auto-started on Python sidecar')
  } catch (err) {
    console.warn('[Main] Could not auto-start wake detection:', err)
  }

  // Create the main window (starts hidden if closed previously)
  createWindow()

  // Create system tray
  createTray(mainWindow!)

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('will-quit', () => {
  // Cleanup overlay manager
  destroyOverlayManager()
  // Unregister all shortcuts
  globalShortcut.unregisterAll()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', async () => {
  isQuitting = true
  setAppIsQuitting(true)
  // Stop wake receiver
  stopWakeReceiver()
  // Cleanup Python sidecar
  if (pythonSidecar) {
    await pythonSidecar.stop()
  }
})
