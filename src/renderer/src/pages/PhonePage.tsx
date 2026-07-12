import { useState, useCallback } from 'react'
import { api } from '../utils/api'
import { Smartphone, Camera, Battery, FileUp, FileDown, Clipboard, ToggleLeft, Package, ScanLine, Loader2 } from 'lucide-react'
import { motion } from 'framer-motion'

export function PhonePage(): JSX.Element {
  const [scanning, setScanning] = useState(false)
  const [devices, setDevices] = useState<string[]>([])
  const [ocrText, setOcrText] = useState('')
  const [ocrLoading, setOcrLoading] = useState(false)

  const scanDevices = useCallback(async () => {
    setScanning(true)
    try {
      const resp = await api('/system/status')
      if (resp && typeof resp === 'object') {
        const info = resp as { platform?: string; hostname?: string }
        if (info.platform) setDevices([`${info.hostname || 'localhost'} (${info.platform})`])
      }
    } catch {
      setDevices(['No devices found'])
    }
    setScanning(false)
  }, [])

  const captureOcr = useCallback(async () => {
    setOcrLoading(true)
    setOcrText('')
    try {
      const resp = await api('/desktop/ocr/capture', {})
      if (resp && typeof resp === 'object') {
        const data = resp as { text?: string; status?: string }
        setOcrText(data.text || data.status || 'No text found')
      }
    } catch {
      setOcrText('OCR capture failed')
    }
    setOcrLoading(false)
  }, [])

  const sendKey = useCallback(async (action: string, text?: string) => {
    try {
      await api('/desktop/keyboard', { action, text: text || action, key: action === 'press_key' ? text : undefined })
    } catch { /* ignore */ }
  }, [])

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">MOBILE CONTROL</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">Control your Android device via ADB — all by voice</p>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card flex flex-col items-center text-center">
          <div className="w-16 h-16 rounded-full bg-void-700/80 flex items-center justify-center mb-3 border border-cyan-500/10">
            <Smartphone className={`w-8 h-8 ${devices.length > 0 ? 'text-neural' : 'text-dim-400'}`} />
          </div>
          <h3 className="text-sm font-rajdhani font-semibold text-ghost">
            {devices.length > 0 ? 'Device connected' : 'No device connected'}
          </h3>
          <p className="text-xs font-exo text-dim-400 mt-1">Connect via USB or Wi-Fi ADB</p>
          {devices.length > 0 && (
            <div className="mt-2 text-xs font-exo text-neural">{devices[0]}</div>
          )}
          <button onClick={scanDevices} disabled={scanning} className="btn-cyan text-sm mt-4">
            {scanning ? <Loader2 className="w-3 h-3 animate-spin inline" /> : <ScanLine className="w-3 h-3 inline" />}
            {' '}{scanning ? 'Scanning...' : 'Scan for Devices'}
          </button>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="glass-card">
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-3">Quick Actions</h3>
          <div className="space-y-2">
            <button onClick={captureOcr} disabled={ocrLoading} className="btn-ghost-cyan w-full text-left text-sm flex items-center gap-2">
              {ocrLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Camera className="w-4 h-4" />} Screen OCR
            </button>
            <button onClick={() => sendKey('type', 'BATTERY')} className="btn-ghost-cyan w-full text-left text-sm flex items-center gap-2">
              <Battery className="w-4 h-4" /> Battery Level
            </button>
            <button onClick={() => sendKey('hotkey', 'ctrl+l')} className="btn-ghost-cyan w-full text-left text-sm flex items-center gap-2">
              <ToggleLeft className="w-4 h-4" /> Toggle Torch
            </button>
            <button onClick={() => sendKey('hotkey', 'ctrl+space')} className="btn-ghost-cyan w-full text-left text-sm flex items-center gap-2">
              <Package className="w-4 h-4" /> Open App
            </button>
          </div>
          {ocrText && (
            <div className="mt-3 p-2 bg-void-900/60 rounded-lg text-xs font-exo text-dim-400 max-h-24 overflow-y-auto">
              {ocrText}
            </div>
          )}
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass-card">
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-3">File Transfer</h3>
          <div className="space-y-2">
            <button className="btn-ghost-cyan w-full text-left text-sm flex items-center gap-2"><FileUp className="w-4 h-4" /> Push to Phone</button>
            <button className="btn-ghost-cyan w-full text-left text-sm flex items-center gap-2"><FileDown className="w-4 h-4" /> Pull from Phone</button>
            <button onClick={() => sendKey('hotkey', 'ctrl+c')} className="btn-ghost-cyan w-full text-left text-sm flex items-center gap-2"><Clipboard className="w-4 h-4" /> Sync Clipboard</button>
          </div>
        </motion.div>
      </div>
    </div>
  )
}
