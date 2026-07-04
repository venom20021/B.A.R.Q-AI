import { app, BrowserWindow, shell, globalShortcut } from 'electron'
import { join } from 'path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import { createTray } from './tray'
import { registerIpcHandlers } from './ipc'
import { PythonSidecar } from './python-bridge'

let mainWindow: BrowserWindow | null = null
let pythonSidecar: PythonSidecar | null = null

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
    if (!app.isQuitting) {
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

  // Start Python sidecar
  pythonSidecar = new PythonSidecar()
  await pythonSidecar.start()

  // Create the main window
  createWindow()

  // Create system tray
  createTray(mainWindow!)

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('will-quit', () => {
  // Unregister all shortcuts
  globalShortcut.unregisterAll()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', async () => {
  app.isQuitting = true
  // Cleanup Python sidecar
  if (pythonSidecar) {
    await pythonSidecar.stop()
  }
})

// Global flag to track quit intent
declare module 'electron' {
  interface App {
    isQuitting?: boolean
  }
}
app.isQuitting = false
