import { app, Menu, Tray, BrowserWindow, nativeImage } from 'electron'
import { toggleOverlay, isOverlayVisible } from './overlay-manager'

let tray: Tray | null = null

// Import isQuitting from a shared location, or define it here
// We use a module-level variable that must be set before quit
let _isQuitting = false
export function setAppIsQuitting(val: boolean): void { _isQuitting = val }
export function getAppIsQuitting(): boolean { return _isQuitting }

function buildMenu(mainWindow: BrowserWindow): Electron.Menu {
  return Menu.buildFromTemplate([
    {
      label: 'Open BARQ',
      click: () => {
        mainWindow.show()
        mainWindow.focus()
      }
    },
    {
      label: 'Voice Control',
      submenu: [
        {
          label: 'Toggle Listening',
          click: () => {
            mainWindow.webContents.send('toggle-voice')
          }
        },
        {
          label: 'Always-On (Background)',
          type: 'checkbox',
          checked: true,
          enabled: false,
        }
      ]
    },
    { type: 'separator' },
    {
      label: 'Desktop Overlay',
      type: 'checkbox',
      checked: isOverlayVisible(),
      click: () => {
        toggleOverlay()
        // Rebuild menu on next tick to sync checkbox state
        setImmediate(() => {
          if (tray && !tray.isDestroyed()) {
            tray.setContextMenu(buildMenu(mainWindow))
          }
        })
      }
    },
    { type: 'separator' },
    {
      label: 'Dashboard',
      click: () => {
        mainWindow.webContents.send('navigate', '/dashboard')
        mainWindow.show()
        mainWindow.focus()
      }
    },
    {
      label: 'Job Search',
      click: () => {
        mainWindow.webContents.send('navigate', '/jobs')
        mainWindow.show()
        mainWindow.focus()
      }
    },
    {
      label: 'Content Studio',
      click: () => {
        mainWindow.webContents.send('navigate', '/content')
        mainWindow.show()
        mainWindow.focus()
      }
    },
    { type: 'separator' },
    {
      label: 'Quit BARQ',
      click: () => {
        _isQuitting = true
        app.quit()
      }
    }
  ])
}

export function createTray(mainWindow: BrowserWindow): void {
  // Create a simple 16x16 tray icon
  const icon = nativeImage.createFromDataURL(
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAAbwAAAG8B8aLcQwAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAAEoSURBVDiNpZMxTsNAEEX/rNeOAwUlHVdA4gJcAokLUNDRcAQkLkCBaOgouQIVHZyAgoKSK0QiJI5jr3cohuxarJOU/NJo5s+b2dEuqcpJUZQ3AL4BzNXsJ4DjGOP7KiOZK5IDAHcAdk3bOwCHJIMAHHY6nQsAOyaYmw+ZTqf3TdveA7giOQfgm8k3InkG4IbkbRzjuCRmZmOMNya4AzAnOQrTNL0mOQIwJzkKInIH4InkOIiIHIE3khOSOwBPJMcA3pZ50zQHJL8AjEn2Aaikkn0ADySHAB6b4G4Akg8kDwB8kBwC+ATwaZqDJJ8BPJLsknwC8AzgxwR3kyQ5APBqgjuSvwC+TPBXkv0Y4+s6UWY2JNkDMAPwH2ZmY4z3/2JmH4D/A1Rq7nmOQat7AAAAAElFTkSuQmCC'
  )

  tray = new Tray(icon)
  tray.setToolTip('BARQ - Voice Assistant')

  // Set initial menu
  tray.setContextMenu(buildMenu(mainWindow))

  tray.on('double-click', () => {
    mainWindow.show()
    mainWindow.focus()
  })
}
