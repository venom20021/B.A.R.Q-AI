import { app, Menu, Tray, BrowserWindow, nativeImage } from 'electron'
import { join } from 'path'

let tray: Tray | null = null

export function createTray(mainWindow: BrowserWindow): void {
  // Create a simple 16x16 tray icon
  const icon = nativeImage.createFromDataURL(
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAAAbwAAAG8B8aLcQwAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAAEoSURBVDiNpZMxTsNAEEX/rNeOAwUlHVdA4gJcAokLUNDRcAQkLkCBaOgouQIVHZyAgoKSK0QiJI5jr3cohuxarJOU/NJo5s+b2dEuqcpJUZQ3AL4BzNXsJ4DjGOP7KiOZK5IDAHcAdk3bOwCHJIMAHHY6nQsAOyaYmw+ZTqf3TdveA7giOQfgm8k3InkG4IbkbRzjuCRmZmOMNya4AzAnOQrTNL0mOQIwJzkKInIH4InkOIiIHIE3khOSOwBPJMcA3pZ50zQHJL8AjEn2Aaikkn0ADySHAB6b4G4Akg8kDwB8kBwC+ATwaZqDJJ8BPJLsknwC8AzgxwR3kyQ5APBqgjuSvwC+TPBXkv0Y4+s6UWY2JNkDMAPwH2ZmY4z3/2JmH4D/A1Rq7nmOQat7AAAAAElFTkSuQmCC'
  )

  tray = new Tray(icon)
  tray.setToolTip('BARQ - Voice Assistant')

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Open BARQ',
      click: () => {
        mainWindow.show()
        mainWindow.focus()
      }
    },
    {
      label: 'Voice Control',
      click: () => {
        mainWindow.webContents.send('toggle-voice')
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
      label: 'Quit',
      click: () => {
        app.isQuitting = true
        app.quit()
      }
    }
  ])

  tray.setContextMenu(contextMenu)

  tray.on('double-click', () => {
    mainWindow.show()
    mainWindow.focus()
  })
}
