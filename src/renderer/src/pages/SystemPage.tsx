import { useState, useCallback } from 'react'
import { Monitor, Maximize, Minimize, Grid3x3, Image, Workflow, Loader2, CheckCircle, ExternalLink } from 'lucide-react'
import { motion } from 'framer-motion'

export function SystemPage(): JSX.Element {
  const [wallpaperPrompt, setWallpaperPrompt] = useState('')
  const [wallpaperStatus, setWallpaperStatus] = useState('')
  const [wallpaperUrl, setWallpaperUrl] = useState('')
  const [applying, setApplying] = useState(false)

  const windowAction = useCallback(async (action: string) => {
    try {
      await window.barq?.python.request('/system/window/control', {
        method: 'POST',
        body: JSON.stringify({ action }),
        headers: { 'Content-Type': 'application/json' },
      })
    } catch { /* ignore */ }
  }, [])

  const setWallpaper = useCallback(async () => {
    if (!wallpaperPrompt.trim()) return
    setApplying(true)
    setWallpaperStatus('Generating...')
    try {
      const resp = await window.barq?.python.request('/desktop/wallpaper/set', {
        method: 'POST',
        body: JSON.stringify({ description: wallpaperPrompt, source: 'auto' }),
        headers: { 'Content-Type': 'application/json' },
      })
      if (resp && typeof resp === 'object') {
        const data = resp as { status?: string; image_url?: string }
        setWallpaperStatus(data.status || 'Applied')
        if (data.image_url) setWallpaperUrl(data.image_url)
      }
    } catch {
      setWallpaperStatus('Failed')
    }
    setApplying(false)
  }, [wallpaperPrompt])

  const activateProtocol = useCallback(async (name: string) => {
    try {
      await window.barq?.python.request(`/desktop/protocols/activate/${encodeURIComponent(name)}`, { method: 'POST' })
    } catch { /* ignore */ }
  }, [])

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">SYSTEM CONTROL</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">Window management, wallpaper, and custom protocols</p>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card">
          <div className="flex items-center gap-2 mb-4">
            <Monitor className="w-5 h-5 text-cyan-300" />
            <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Window Management</h3>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button onClick={() => windowAction('maximize')} className="btn-ghost-cyan text-sm flex items-center gap-2"><Maximize className="w-4 h-4" /> Maximize</button>
            <button onClick={() => windowAction('minimize')} className="btn-ghost-cyan text-sm flex items-center gap-2"><Minimize className="w-4 h-4" /> Minimize</button>
            <button onClick={() => windowAction('snap_left')} className="btn-ghost-cyan text-sm flex items-center gap-2"><Grid3x3 className="w-4 h-4" /> Snap Left</button>
            <button onClick={() => windowAction('snap_right')} className="btn-ghost-cyan text-sm flex items-center gap-2"><Grid3x3 className="w-4 h-4" /> Snap Right</button>
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="glass-card">
          <div className="flex items-center gap-2 mb-4">
            <Image className="w-5 h-5 text-holographic" />
            <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">AI Wallpaper</h3>
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={wallpaperPrompt}
              onChange={(e) => setWallpaperPrompt(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && setWallpaper()}
              placeholder='e.g., "cyberpunk city"'
              className="input-cyan flex-1 text-sm"
            />
            <button onClick={setWallpaper} disabled={applying} className="btn-cyan text-sm">
              {applying ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Set'}
            </button>
          </div>
          {wallpaperStatus && (
            <div className="mt-2 flex items-center gap-2 text-xs font-exo">
              <CheckCircle className={`w-3 h-3 ${wallpaperStatus === 'Failed' ? 'text-red-400' : 'text-neural'}`} />
              <span className={wallpaperStatus === 'Failed' ? 'text-red-400' : 'text-neural'}>{wallpaperStatus}</span>
              {wallpaperUrl && <ExternalLink className="w-3 h-3 text-dim-400" />}
            </div>
          )}
        </motion.div>
      </div>

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass-card">
        <div className="flex items-center gap-2 mb-4">
          <Workflow className="w-5 h-5 text-neural" />
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Custom Protocols</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {[
            { name: 'Job Hunt Mode', desc: 'Open job boards, update resume, start scanning', action: 'job_hunt_mode' },
            { name: 'Deep Work Mode', desc: 'Kill distractions, set focus wallpaper, start timer', action: 'deep_work_mode' },
            { name: 'Gaming Mode', desc: 'Close background apps, free up RAM', action: 'gaming_mode' },
          ].map((p) => (
            <button
              key={p.name}
              onClick={() => activateProtocol(p.action)}
              className="bg-void-700/50 rounded-lg p-4 cursor-pointer hover:bg-void-600/50 transition-colors border border-cyan-500/5 hover:border-cyan-500/15 text-left"
            >
              <p className="text-sm font-rajdhani font-semibold text-ghost">{p.name}</p>
              <p className="text-xs font-exo text-dim-400 mt-1">{p.desc}</p>
            </button>
          ))}
        </div>
      </motion.div>
    </div>
  )
}
