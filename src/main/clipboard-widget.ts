/**
 * BARQ Clipboard Intelligence — Floating AI Widget
 *
 * Architecture:
 *   - Global hotkey (Ctrl+Shift+C) triggers clipboard read
 *   - Opens a frameless, transparent BrowserWindow at cursor position
 *   - Passes clipboard text to the widget frontend
 *   - Widget shows AI action buttons: Translate, Summarize, Explain, Fix
 *   - Each action calls Python backend via IPC → pythonBridge
 *   - Widget auto-hides on blur
 *
 * This module is imported and initialized from src/main/index.ts.
 */

import { BrowserWindow, screen, clipboard, globalShortcut, ipcMain } from 'electron'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'
import { pythonBridge } from './python-bridge'

// ─── State ─────────────────────────────────────────────────────────────────

let widgetWindow: BrowserWindow | null = null
let widgetVisible = false

// ─── Window Creation ────────────────────────────────────────────────────────

function getCursorPosition(): { x: number; y: number } {
  const cursor = screen.getCursorScreenPoint()
  return { x: cursor.x, y: cursor.y }
}

export function createClipboardWidget(clipboardText?: string): BrowserWindow {
  // Close existing if any
  if (widgetWindow && !widgetWindow.isDestroyed()) {
    widgetWindow.close()
  }

  const cursor = getCursorPosition()
  const widgetW = 420
  const widgetH = 320

  // Position widget slightly above and to the right of cursor
  let x = cursor.x + 10
  let y = cursor.y - widgetH - 10

  // Clamp to visible display area
  const displays = screen.getAllDisplays()
  const display =
    displays.find((d) => {
      const { x: dx, y: dy, width, height } = d.workArea
      return cursor.x >= dx && cursor.x <= dx + width && cursor.y >= dy && cursor.y <= dy + height
    }) || screen.getPrimaryDisplay()

  const wa = display.workArea
  x = Math.max(wa.x + 5, Math.min(wa.x + wa.width - widgetW - 5, x))
  y = Math.max(wa.y + 5, Math.min(wa.y + wa.height - widgetH - 5, y))

  widgetWindow = new BrowserWindow({
    width: widgetW,
    height: widgetH,
    x,
    y,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    show: false,
    hasShadow: false,
    webPreferences: {
      preload: join(__dirname, '../preload/clipboard-widget.js'),
      sandbox: false,
      nodeIntegration: false,
      contextIsolation: true,
      backgroundThrottling: false,
    },
  })

  // Load widget HTML
  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    widgetWindow.loadURL(
      `${process.env['ELECTRON_RENDERER_URL'].replace('/index.html', '')}/clipboard-widget.html`
    )
  } else {
    widgetWindow.loadFile(join(__dirname, '../renderer/clipboard-widget.html'))
  }

  // Auto-hide on blur
  widgetWindow.on('blur', () => {
    hideClipboardWidget()
  })

  widgetWindow.on('closed', () => {
    widgetWindow = null
    widgetVisible = false
  })

  // Show after ready
  widgetWindow.once('ready-to-show', () => {
    widgetWindow?.show()
    widgetWindow?.focus()
    widgetVisible = true

    // Send clipboard text to widget
    if (clipboardText) {
      widgetWindow?.webContents.send('clipboard:text', { text: clipboardText })
    }
  })

  return widgetWindow
}

function hideClipboardWidget(): void {
  if (widgetWindow && !widgetWindow.isDestroyed()) {
    widgetWindow.close()
  }
  widgetWindow = null
  widgetVisible = false
}

// ─── AI Action Handlers (proxy to Python backend) ──────────────────────────

async function handleAiAction(action: string, text: string): Promise<string> {
  try {
    const result = await pythonBridge.request('/desktop/clipboard/action', {
      action,
      text,
    })
    if (result && typeof result === 'object') {
      const r = result as { status?: string; result?: string; detail?: string }
      if (r.status === 'ok' && r.result) {
        return r.result
      }
      return r.detail || 'No result returned'
    }
    return String(result || 'Done')
  } catch (error) {
    return `Error: ${String(error)}`
  }
}

// ─── Init / Cleanup ────────────────────────────────────────────────────────

export function initClipboardWidget(): void {
  // Register global shortcut: Ctrl+Shift+C (⌘+Shift+C on macOS)
  const registered = globalShortcut.register('CommandOrControl+Shift+C', () => {
    console.log('[ClipboardWidget] Global shortcut triggered: Ctrl+Shift+C')

    try {
      const text = clipboard.readText()
      if (!text || text.trim().length === 0) {
        console.log('[ClipboardWidget] Clipboard is empty — ignoring')
        return
      }

      const cleaned = text.trim().slice(0, 2000)
      console.log(`[ClipboardWidget] Clipboard text (${cleaned.length} chars): ${cleaned.slice(0, 100)}...`)
      createClipboardWidget(cleaned)
    } catch (err) {
      console.error('[ClipboardWidget] Error reading clipboard:', err)
    }
  })

  if (registered) {
    console.log('[ClipboardWidget] Global shortcut Ctrl+Shift+C registered successfully')
  } else {
    console.warn('[ClipboardWidget] Failed to register global shortcut Ctrl+Shift+C')
  }

  // ─── IPC handlers for AI actions ────────────────────────────────────

  ipcMain.handle('clipboard:action', async (_event, action: string, text: string) => {
    console.log(`[ClipboardWidget] AI Action: ${action} (${text.length} chars)`)
    const result = await handleAiAction(action, text)
    return { success: true, result }
  })

  // Widget requests to close itself
  ipcMain.on('clipboard:close', () => {
    hideClipboardWidget()
  })

  // Widget requests to copy result back to clipboard
  ipcMain.on('clipboard:copy', (_event, text: string) => {
    try {
      clipboard.writeText(text)
      console.log('[ClipboardWidget] Copied result to clipboard')
    } catch (err) {
      console.error('[ClipboardWidget] Failed to copy to clipboard:', err)
    }
  })
}

export function destroyClipboardWidget(): void {
  if (widgetWindow && !widgetWindow.isDestroyed()) {
    widgetWindow.close()
  }
  widgetWindow = null
  widgetVisible = false
}
