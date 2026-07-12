import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Cpu, HardDrive, Monitor, Activity, X } from 'lucide-react'
import { api } from '../utils/api'

interface DiagnosticsData {
  cpu_percent: number
  memory: { used_gb: number; total_gb: number; percent: number }
  disk: { used_gb: number; total_gb: number; percent: number }
  hostname: string
  platform: string
  uptime: string
}

export function TransientDiagnostics(): JSX.Element {
  const [data, setData] = useState<DiagnosticsData | null>(null)
  const [visible, setVisible] = useState(false)

  // Listen for silent-diagnostics events
  useEffect(() => {
    const handler = (_e: CustomEvent<DiagnosticsData>): void => {
      setData(_e.detail)
      setVisible(true)
      // Auto-dismiss after 12 seconds
      setTimeout(() => setVisible(false), 12000)
    }
    window.addEventListener('barq:show-diagnostics', handler as EventListener)
    return () => window.removeEventListener('barq:show-diagnostics', handler as EventListener)
  }, [])

  const fetchAndShow = useCallback(async () => {
    try {
      const data = await api<DiagnosticsData>('/system/status')
      if (data) {
        setData(data)
        setVisible(true)
        setTimeout(() => setVisible(false), 12000)
      }
    } catch { /* ignore */ }
  }, [])

  // Also listen for the custom event from voice commands
  useEffect(() => {
    const cmdHandler = (e: CustomEvent<{ action: string }>): void => {
      if (e.detail?.action === 'show_diagnostics') void fetchAndShow()
    }
    window.addEventListener('barq:voice-command', cmdHandler as EventListener)
    return () => window.removeEventListener('barq:voice-command', cmdHandler as EventListener)
  }, [fetchAndShow])

  if (!data) return <></>

  return (
    <AnimatePresence>
      {visible && data && (
        <motion.div
          initial={{ opacity: 0, y: 30, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 20, scale: 0.95 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}          className="fixed bottom-6 left-6 z-40 w-72 overflow-hidden rounded-xl bg-void-900/80 backdrop-blur-2xl border border-white/[0.06] shadow-2xl"
        >
          {/* Header bar with glow */}
          <div className="h-1 bg-gradient-to-r from-cyan-400 via-cyan-500 to-cyan-400 shadow-glow-cyan-sm" />

          <div className="p-4 space-y-3">
            {/* Title */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-cyan-300" />
                <span className="text-xs font-share-tech text-ghost/60 uppercase tracking-wider">System Diagnostics</span>
              </div>
              <button
                onClick={() => setVisible(false)}
                className="p-1 rounded hover:bg-cyan-500/10 transition-colors"
              >
                <X className="w-3 h-3 text-dim-400" />
              </button>
            </div>

            {/* Hostname */}
            <p className="text-[10px] font-exo text-dim-500">{data.hostname} · {data.platform}</p>

            {/* Metrics */}
            <div className="space-y-2">
              {/* CPU */}
              <div>
                <div className="flex items-center justify-between text-xs font-rajdhani mb-1">
                  <div className="flex items-center gap-1.5">
                    <Cpu className="w-3 h-3 text-dim-400" />
                    <span className="text-dim-300">CPU</span>
                  </div>
                  <span className={`font-semibold ${data.cpu_percent > 80 ? 'text-red-400' : data.cpu_percent > 50 ? 'text-amber-400' : 'text-emerald-400'}`}>
                    {data.cpu_percent}%
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-void-700/60 overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(data.cpu_percent, 100)}%` }}
                    transition={{ duration: 0.5, ease: 'easeOut' }}
                    className={`h-full rounded-full ${
                      data.cpu_percent > 80 ? 'bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.4)]' :
                      data.cpu_percent > 50 ? 'bg-amber-500 shadow-[0_0_6px_rgba(245,158,11,0.3)]' :
                      'bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.3)]'
                    }`}
                  />
                </div>
              </div>

              {/* Memory */}
              <div>
                <div className="flex items-center justify-between text-xs font-rajdhani mb-1">
                  <div className="flex items-center gap-1.5">
                    <HardDrive className="w-3 h-3 text-dim-400" />
                    <span className="text-dim-300">RAM</span>
                  </div>
                  <span className="text-dim-400">
                    {data.memory?.used_gb.toFixed(1)} / {data.memory?.total_gb.toFixed(1)} GB
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-void-700/60 overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(data.memory?.percent || 0, 100)}%` }}
                    transition={{ duration: 0.5, ease: 'easeOut', delay: 0.1 }}
                    className={`h-full rounded-full ${
                      (data.memory?.percent || 0) > 85 ? 'bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.4)]' :
                      (data.memory?.percent || 0) > 70 ? 'bg-amber-500 shadow-[0_0_6px_rgba(245,158,11,0.3)]' :
                      'bg-cyan-500 shadow-[0_0_6px_rgba(6,182,212,0.3)]'
                    }`}
                  />
                </div>
              </div>

              {/* Disk */}
              {data.disk && (
                <div>
                  <div className="flex items-center justify-between text-xs font-rajdhani mb-1">
                    <div className="flex items-center gap-1.5">
                      <Monitor className="w-3 h-3 text-dim-400" />
                      <span className="text-dim-300">Disk</span>
                    </div>
                    <span className="text-dim-400">
                      {data.disk.used_gb.toFixed(1)} / {data.disk.total_gb.toFixed(1)} GB
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-void-700/60 overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.min(data.disk.percent, 100)}%` }}
                      transition={{ duration: 0.5, ease: 'easeOut', delay: 0.2 }}
                      className={`h-full rounded-full ${
                        data.disk.percent > 90 ? 'bg-red-500 shadow-[0_0_6px_rgba(239,68,68,0.4)]' :
                        data.disk.percent > 75 ? 'bg-amber-500 shadow-[0_0_6px_rgba(245,158,11,0.3)]' :
                        'bg-cyan-500 shadow-[0_0_6px_rgba(6,182,212,0.3)]'
                      }`}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
