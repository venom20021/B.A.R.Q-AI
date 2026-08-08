import { app, BrowserWindow, ipcMain } from 'electron'
import { autoUpdater, type UpdateInfo } from 'electron-updater'

/**
 * BARQ auto-updater.
 *
 * Uses electron-updater against the GitHub Releases feed configured in
 * electron-builder.yml (`publish.provider: github`). On startup (packaged
 * builds only) it checks for a newer release, auto-downloads it in the
 * background and notifies the user when it's ready to install.
 *
 * Update state is broadcast to the renderer on the `update:status` channel so
 * the UI can surface a badge/toast (see preload's `barq.updater` API).
 */

type UpdateState =
  | { state: 'dev' }
  | { state: 'idle' }
  | { state: 'checking' }
  | { state: 'available'; version: string }
  | { state: 'not-available'; version?: string }
  | { state: 'downloading'; percent: number }
  | { state: 'downloaded'; version: string }
  | { state: 'error'; message: string }

function broadcast(state: UpdateState): void {
  for (const win of BrowserWindow.getAllWindows()) {
    win.webContents.send('update:status', state)
  }
}

function registerUpdaterIpc(): void {
  // Manual check — lets the renderer/tray trigger an update check on demand.
  // State changes are broadcast by the autoUpdater events themselves.
  ipcMain.handle('app:check-for-updates', async () => {
    if (!app.isPackaged) {
      return { success: true, data: { state: 'dev', message: 'auto-update disabled in dev mode' } }
    }
    try {
      const result = await autoUpdater.checkForUpdates()
      return {
        success: true,
        data: result ? { state: 'available', version: result.updateInfo.version } : { state: 'not-available' }
      }
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) }
    }
  })

  // Restart-to-install — called by the renderer's Restart button once an
  // update has been downloaded. Quits the app and runs the installer.
  ipcMain.handle('app:restart-to-install', () => {
    if (!app.isPackaged) {
      return { success: false, error: 'auto-update disabled in dev mode' }
    }
    try {
      autoUpdater.quitAndInstall(false, true)
      return { success: true }
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) }
    }
  })
}

export function initAutoUpdater(): void {
  registerUpdaterIpc()

  if (!app.isPackaged) {
    broadcast({ state: 'dev' })
    console.log('[Updater] Skipped — running in dev mode (auto-update only works in packaged builds)')
    return
  }

  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true
  autoUpdater.logger = console

  autoUpdater.on('checking-for-update', () => broadcast({ state: 'checking' }))

  autoUpdater.on('update-available', (info: UpdateInfo) => {
    console.log(`[Updater] Update available: ${info.version}`)
    broadcast({ state: 'available', version: info.version })
  })

  autoUpdater.on('update-not-available', (info: UpdateInfo) => {
    console.log(`[Updater] Up to date (${info.version})`)
    broadcast({ state: 'not-available', version: info.version })
  })

  autoUpdater.on('download-progress', (progress) => {
    broadcast({ state: 'downloading', percent: Math.round(progress.percent) })
  })

  autoUpdater.on('update-downloaded', (info: UpdateInfo) => {
    console.log(`[Updater] Downloaded ${info.version} — restart BARQ to install`)
    broadcast({ state: 'downloaded', version: info.version })
  })

  autoUpdater.on('error', (err) => {
    console.error('[Updater] Error:', err?.message ?? err)
    broadcast({ state: 'error', message: err?.message ?? String(err) })
  })

  // Wait a few seconds so the check doesn't compete with app startup.
  setTimeout(() => {
    autoUpdater.checkForUpdatesAndNotify().catch((err) => {
      console.warn('[Updater] Startup check failed:', err instanceof Error ? err.message : String(err))
    })
  }, 10_000)
}
