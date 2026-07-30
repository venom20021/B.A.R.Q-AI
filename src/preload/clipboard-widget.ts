import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('clipboardWidget', {
  // Receive clipboard text from main process
  onClipboardText: (callback: (data: { text: string }) => void) => {
    ipcRenderer.on('clipboard:text', (_event, data) => callback(data))
  },

  // Trigger an AI action on the clipboard text
  runAction: async (action: string, text: string): Promise<{ success: boolean; result: string }> => {
    const result = await ipcRenderer.invoke('clipboard:action', action, text)
    return result as { success: boolean; result: string }
  },

  // Close the widget
  close: () => ipcRenderer.send('clipboard:close'),

  // Copy text to clipboard
  copy: (text: string) => ipcRenderer.send('clipboard:copy', text),

  // Remove all listeners
  removeAllListeners: (channel: string) => {
    ipcRenderer.removeAllListeners(channel)
  },
})
