import { useState, useCallback, useRef } from 'react'
import { api } from '../utils/api'
import { Smartphone, Camera, Battery, FileUp, FileDown, Clipboard, ToggleLeft, ScanLine, Loader2, Monitor, RotateCw, Volume2, Wifi, ChevronRight, CheckCircle, XCircle, AlertTriangle } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

// ─── Types ─────────────────────────────────────────────────────────────────

interface AdbDevice {
  id: string
  model: string
  state: 'device' | 'unauthorized' | 'offline' | 'unknown'
  battery?: number
}

interface FileTransfer {
  id: string
  direction: 'push' | 'pull'
  path: string
  progress: number
  status: 'pending' | 'transferring' | 'done' | 'error'
  error?: string
}

// ─── ADB Device Scanner ────────────────────────────────────────────────────

async function scanAdbDevices(): Promise<AdbDevice[]> {
  try {
    const resp = await api('/desktop/adb/devices')
    if (resp && typeof resp === 'object') {
      const data = resp as { devices?: AdbDevice[] }
      return data.devices ?? []
    }
  } catch { /* backend endpoint may not exist */ }
  return []
}

// ─── Main Page ─────────────────────────────────────────────────────────────

export function PhonePage(): JSX.Element {
  const [devices, setDevices] = useState<AdbDevice[]>([])
  const [scanning, setScanning] = useState(false)
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null)
  const [ocrText, setOcrText] = useState('')
  const [ocrLoading, setOcrLoading] = useState(false)
  const [ocrImage, setOcrImage] = useState<string | null>(null)
  const [transfers, setTransfers] = useState<FileTransfer[]>([])
  const [pushPath, setPushPath] = useState('/sdcard/Download/')
  const [pullPath, setPullPath] = useState('/sdcard/Download/')
  const [batteryInfo, setBatteryInfo] = useState<string | null>(null)
  const [actionFeedback, setActionFeedback] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const feedbackTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showFeedback = useCallback((message: string, type: 'success' | 'error') => {
    setActionFeedback({ message, type })
    if (feedbackTimer.current) clearTimeout(feedbackTimer.current)
    feedbackTimer.current = setTimeout(() => setActionFeedback(null), 3000)
  }, [])

  // ── Scan for devices ──────────────────────────────────────────────────
  const handleScan = useCallback(async () => {
    setScanning(true)
    setDevices([])
    try {
      // Try ADB first, fall back to system info
      const adbDevices = await scanAdbDevices()
      if (adbDevices.length > 0) {
        setDevices(adbDevices)
        showFeedback(`Found ${adbDevices.length} device(s)`, 'success')
      } else {
        // Fallback: show local machine as device
        const resp = await api('/system/status')
        if (resp && typeof resp === 'object') {
          const info = resp as Record<string, unknown>
          setDevices([{
            id: 'local',
            model: `${(info.hostname as string) || 'localhost'} (${(info.platform as string) || 'unknown'})`,
            state: 'device' as const,
          }])
          showFeedback('Local system detected (no ADB devices)', 'success')
        } else {
          showFeedback('No devices found', 'error')
        }
      }
    } catch {
      showFeedback('Device scan failed', 'error')
    }
    setScanning(false)
  }, [showFeedback])

  // ── Screen OCR ────────────────────────────────────────────────────────
  const handleOcr = useCallback(async () => {
    setOcrLoading(true)
    setOcrText('')
    setOcrImage(null)
    try {
      const resp = await api('/desktop/ocr/capture')
      if (resp && typeof resp === 'object') {
        const data = resp as { text?: string; status?: string; image_base64?: string; mime_type?: string }
        setOcrText(data.text || data.status || 'No text found')
        if (data.image_base64) setOcrImage(data.image_base64)
      } else {
        setOcrText('OCR capture returned no data')
      }
    } catch {
      setOcrText('OCR capture failed — backend may be unavailable')
    }
    setOcrLoading(false)
  }, [])

  // ── Battery info ──────────────────────────────────────────────────────
  const handleBattery = useCallback(async () => {
    setBatteryInfo(null)
    try {
      const resp = await api('/system/battery')
      if (resp && typeof resp === 'object') {
        const data = resp as { percent?: number; status?: string; plugged?: boolean }
        const pct = data.percent ?? '?'
        const charging = data.plugged ? ' (charging)' : ''
        setBatteryInfo(`Battery: ${pct}%${charging}`)
        showFeedback(`Battery: ${pct}%${charging}`, 'success')
      } else {
        setBatteryInfo('Battery info unavailable')
      }
    } catch {
      setBatteryInfo('Battery info unavailable')
    }
  }, [showFeedback])

  // ── Quick actions ─────────────────────────────────────────────────────
  const handleQuickAction = useCallback(async (action: string, label: string) => {
    try {
      if (action === 'torch') {
        await api('/desktop/toggle-torch')
        showFeedback('Torch toggled', 'success')
      } else if (action === 'volume_up') {
        await api('/desktop/keyboard', { action: 'press_key', key: 'volumeup' })
        showFeedback('Volume up', 'success')
      } else if (action === 'volume_down') {
        await api('/desktop/keyboard', { action: 'press_key', key: 'volumedown' })
        showFeedback('Volume down', 'success')
      } else if (action === 'screenshot') {
        await api('/vision/analyze', { prompt: 'Capture screen', angle: 'screen' })
        showFeedback('Screenshot captured', 'success')
      } else if (action === 'wifi_status') {
        const resp = await api('/system/status')
        showFeedback(resp ? 'System info retrieved' : 'No data', resp ? 'success' : 'error')
      } else {
        showFeedback(`${label} — backend endpoint pending`, 'error')
      }
    } catch {
      showFeedback(`${label} failed`, 'error')
    }
  }, [showFeedback])

  // ── File transfer ─────────────────────────────────────────────────────
  const handlePush = useCallback(async () => {
    const id = `push-${Date.now()}`
    setTransfers(prev => [...prev, { id, direction: 'push', path: pushPath, progress: 0, status: 'transferring' }])
    try {
      await api('/desktop/file/push', { path: pushPath })
      setTransfers(prev => prev.map(t => t.id === id ? { ...t, status: 'done', progress: 100 } : t))
      showFeedback(`Pushed to ${pushPath}`, 'success')
    } catch {
      setTransfers(prev => prev.map(t => t.id === id ? { ...t, status: 'error', error: 'Push failed' } : t))
      showFeedback('Push failed', 'error')
    }
  }, [pushPath, showFeedback])

  const handlePull = useCallback(async () => {
    const id = `pull-${Date.now()}`
    setTransfers(prev => [...prev, { id, direction: 'pull', path: pullPath, progress: 0, status: 'transferring' }])
    try {
      await api('/desktop/file/pull', { path: pullPath })
      setTransfers(prev => prev.map(t => t.id === id ? { ...t, status: 'done', progress: 100 } : t))
      showFeedback(`Pulled from ${pullPath}`, 'success')
    } catch {
      setTransfers(prev => prev.map(t => t.id === id ? { ...t, status: 'error', error: 'Pull failed' } : t))
      showFeedback('Pull failed', 'error')
    }
  }, [pullPath, showFeedback])

  const handleSyncClipboard = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText()
      await api('/desktop/clipboard/send', { text })
      showFeedback('Clipboard synced', 'success')
    } catch {
      // Fallback: send a test string
      try {
        await api('/desktop/clipboard/send', { text: 'BARQ clipboard sync' })
        showFeedback('Clipboard test sent', 'success')
      } catch {
        showFeedback('Clipboard sync failed', 'error')
      }
    }
  }, [showFeedback])

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-purple-500/10 flex items-center justify-center border border-purple-500/20">
            <Smartphone className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">MOBILE CONTROL</h1>
            <p className="text-sm font-rajdhani text-dim-400 mt-0.5">Control Android devices via ADB, screen capture, and file transfer</p>
          </div>
        </div>
      </motion.div>

      {/* Feedback toast */}
      <AnimatePresence>
        {actionFeedback && (
          <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-exo border ${
              actionFeedback.type === 'success' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'
            }`}
          >
            {actionFeedback.type === 'success' ? <CheckCircle className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
            {actionFeedback.message}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* ── Device Card ───────────────────────────────────────────────── */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="bg-zinc-900/60 backdrop-blur-sm rounded-xl border border-zinc-800/60 p-5 flex flex-col items-center text-center">
          <div className={`w-16 h-16 rounded-full flex items-center justify-center mb-3 border-2 transition-all ${
            devices.length > 0 ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-zinc-800/60 border-zinc-700/50'
          }`}>
            <Smartphone className={`w-8 h-8 ${devices.length > 0 ? 'text-emerald-400' : 'text-zinc-500'}`} />
          </div>
          <h3 className="text-sm font-rajdhani font-semibold text-zinc-200">
            {devices.length > 0 ? `${devices.length} device(s) connected` : 'No device connected'}
          </h3>
          <p className="text-xs font-exo text-zinc-500 mt-1">Connect via USB or Wi-Fi ADB</p>
          {devices.length > 0 && (
            <div className="mt-3 w-full space-y-1.5">
              {devices.map(d => (
                <div key={d.id}
                  onClick={() => setSelectedDevice(d.id)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-mono cursor-pointer transition-colors ${
                    selectedDevice === d.id ? 'bg-purple-500/10 border border-purple-500/20 text-purple-300' : 'bg-zinc-800/40 border border-zinc-800/60 text-zinc-400 hover:bg-zinc-800/60'
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full ${d.state === 'device' ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                  <span className="flex-1 truncate">{d.model || d.id}</span>
                  <ChevronRight className="w-3 h-3 shrink-0" />
                </div>
              ))}
            </div>
          )}
          <button onClick={handleScan} disabled={scanning} className="flex items-center gap-2 px-4 py-2 mt-4 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20 text-xs font-rajdhani font-semibold hover:bg-purple-500/20 transition-all disabled:opacity-40">
            {scanning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ScanLine className="w-3.5 h-3.5" />}
            {scanning ? 'Scanning...' : 'Scan for Devices'}
          </button>
        </motion.div>

        {/* ── Quick Actions ─────────────────────────────────────────────── */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="bg-zinc-900/60 backdrop-blur-sm rounded-xl border border-zinc-800/60 p-5">
          <h3 className="text-sm font-orbitron font-bold text-zinc-200 tracking-wider mb-4">Quick Actions</h3>
          <div className="grid grid-cols-2 gap-2">
            <ActionButton icon={Camera} label="Screen OCR" onClick={handleOcr} loading={ocrLoading} color="text-cyan-400" />
            <ActionButton icon={Battery} label="Battery" onClick={handleBattery} color="text-emerald-400" />
            <ActionButton icon={Monitor} label="Screenshot" onClick={() => handleQuickAction('screenshot', 'Screenshot')} color="text-violet-400" />
            <ActionButton icon={Volume2} label="Volume Up" onClick={() => handleQuickAction('volume_up', 'Volume up')} color="text-amber-400" />
            <ActionButton icon={Volume2} label="Volume Down" onClick={() => handleQuickAction('volume_down', 'Volume down')} color="text-amber-400" />
            <ActionButton icon={Wifi} label="Wi-Fi Status" onClick={() => handleQuickAction('wifi_status', 'Wi-Fi status')} color="text-blue-400" />
            <ActionButton icon={ToggleLeft} label="Torch" onClick={() => handleQuickAction('torch', 'Torch')} color="text-rose-400" />
            <ActionButton icon={RotateCw} label="Rotate" onClick={() => handleQuickAction('rotate', 'Rotate')} color="text-zinc-400" />
          </div>

          {/* Battery info */}
          {batteryInfo && (
            <div className="mt-3 p-2 bg-zinc-800/40 rounded-lg text-xs font-mono text-zinc-400 text-center">{batteryInfo}</div>
          )}

          {/* OCR result */}
          {ocrText && (
            <div className="mt-3 space-y-2">
              <div className="p-3 bg-zinc-950/80 rounded-lg border border-zinc-800/40 max-h-32 overflow-y-auto">
                <p className="text-xs font-mono text-zinc-400 leading-relaxed whitespace-pre-wrap">{ocrText}</p>
              </div>
              {ocrImage && (
                <div className="rounded-lg overflow-hidden border border-zinc-800/40">
                  <img src={ocrImage} alt="Screen capture" className="w-full h-auto max-h-48 object-contain" />
                </div>
              )}
            </div>
          )}
        </motion.div>

        {/* ── File Transfer ─────────────────────────────────────────────── */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="bg-zinc-900/60 backdrop-blur-sm rounded-xl border border-zinc-800/60 p-5">
          <h3 className="text-sm font-orbitron font-bold text-zinc-200 tracking-wider mb-4">File Transfer</h3>
          
          <div className="space-y-3">
            <div className="space-y-1.5">
              <label className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">Push to Phone</label>
              <div className="flex gap-2">
                <input type="text" value={pushPath} onChange={(e) => setPushPath(e.target.value)}
                  placeholder="/sdcard/Download/" className="flex-1 bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs font-mono text-zinc-300 outline-none focus:border-purple-500/40 transition-colors placeholder:text-zinc-600" />
                <button onClick={handlePush} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20 text-xs font-rajdhani font-semibold hover:bg-purple-500/20 transition-colors shrink-0">
                  <FileUp className="w-3.5 h-3.5" /> Push
                </button>
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">Pull from Phone</label>
              <div className="flex gap-2">
                <input type="text" value={pullPath} onChange={(e) => setPullPath(e.target.value)}
                  placeholder="/sdcard/Download/file.txt" className="flex-1 bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs font-mono text-zinc-300 outline-none focus:border-purple-500/40 transition-colors placeholder:text-zinc-600" />
                <button onClick={handlePull} className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20 text-xs font-rajdhani font-semibold hover:bg-purple-500/20 transition-colors shrink-0">
                  <FileDown className="w-3.5 h-3.5" /> Pull
                </button>
              </div>
            </div>

            {/* Sync clipboard */}
            <button onClick={handleSyncClipboard} className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-zinc-800/60 text-zinc-400 border border-zinc-700/50 text-xs font-rajdhani font-semibold hover:bg-zinc-700/60 hover:text-zinc-200 transition-all">
              <Clipboard className="w-3.5 h-3.5" /> Sync Clipboard
            </button>
          </div>

          {/* Transfer log */}
          {transfers.length > 0 && (
            <div className="mt-3 space-y-1">
              {transfers.slice(-3).map(t => (
                <div key={t.id} className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-zinc-800/30">
                  {t.direction === 'push' ? <FileUp className="w-3 h-3 text-cyan-400" /> : <FileDown className="w-3 h-3 text-amber-400" />}
                  <span className="text-[10px] font-mono text-zinc-500 flex-1 truncate">{t.path}</span>
                  {t.status === 'transferring' && <Loader2 className="w-3 h-3 animate-spin text-cyan-400" />}
                  {t.status === 'done' && <CheckCircle className="w-3 h-3 text-emerald-400" />}
                  {t.status === 'error' && <AlertTriangle className="w-3 h-3 text-red-400" />}
                </div>
              ))}
            </div>
          )}
        </motion.div>
      </div>
    </div>
  )
}

// ─── Action Button Component ───────────────────────────────────────────────

function ActionButton({ icon: Icon, label, onClick, loading, color }: {
  icon: typeof Camera; label: string; onClick: () => void; loading?: boolean; color: string
}): JSX.Element {
  return (
    <button onClick={onClick} disabled={loading}
      className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-zinc-800/40 border border-zinc-800/60 hover:bg-zinc-800/60 hover:border-zinc-700/60 transition-all duration-200 disabled:opacity-40 group"
    >
      {loading ? <Loader2 className="w-4 h-4 animate-spin text-cyan-400" /> : <Icon className={`w-4 h-4 ${color} group-hover:drop-shadow-[0_0_4px]`} />}
      <span className="text-xs font-rajdhani font-semibold text-zinc-400 group-hover:text-zinc-200 transition-colors">{label}</span>
    </button>
  )
}
