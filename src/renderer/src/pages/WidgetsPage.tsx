import { useState, useCallback } from 'react'
import { Clock, TrendingUp, Calculator, Code, Wand2, Globe, CheckCircle } from 'lucide-react'
import { motion } from 'framer-motion'
import { api } from '../utils/api'

const widgetDefs = [
  { icon: Clock, accent: 'text-neural', title: 'Floating Timer', desc: 'Countdown / stopwatch widget', action: 'timer' },
  { icon: TrendingUp, accent: 'text-cyan-300', title: 'Stock Ticker', desc: 'Real-time stock prices', action: 'stocks' },
  { icon: Calculator, accent: 'text-plasma', title: 'Calculator', desc: 'Desktop calculator widget', action: 'calculator' },
  { icon: Globe, accent: 'text-holographic', title: 'Weather', desc: 'Current conditions widget', action: 'weather' },
]

export function WidgetsPage(): JSX.Element {
  const [spawnStatus, setSpawnStatus] = useState('')
  const [spawning, setSpawning] = useState(false)

  const spawnWidget = useCallback(async (action: string, title: string) => {
    setSpawning(true)
    setSpawnStatus(`Spawning ${title}...`)
    try {
      await api('/desktop/protocols/create', {
        name: `widget_${action}`,
        steps: [{ action: 'open_url', target: `http://127.0.0.1:8970/docs` }],
        trigger_phrase: `spawn ${action} widget`,
      })
      setSpawnStatus(`${title} spawned`)
    } catch {
      setSpawnStatus(`Failed to spawn ${title}`)
    }
    setSpawning(false)
  }, [])

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">WIDGETS & UI</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">Floating widgets, live coding, and desktop customization</p>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {widgetDefs.map((w, i) => {
          const Icon = w.icon
          return (
            <motion.div key={w.title} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="glass-card-hover text-center">
              <Icon className={`w-8 h-8 ${w.accent} mx-auto mb-2`} />
              <h3 className="text-sm font-rajdhani font-semibold text-ghost">{w.title}</h3>
              <p className="text-xs font-exo text-dim-400 mt-1">{w.desc}</p>
              <button onClick={() => spawnWidget(w.action, w.title)} disabled={spawning} className="btn-ghost-cyan text-xs mt-3">Spawn</button>
            </motion.div>
          )
        })}
      </div>

      {spawnStatus && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center gap-2 text-xs font-exo">
          <CheckCircle className="w-3 h-3 text-neural" />
          <span className="text-dim-400">{spawnStatus}</span>
        </motion.div>
      )}

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass-card">
        <div className="flex items-center gap-2 mb-4">
          <Wand2 className="w-5 h-5 text-cyan-300" />
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Widget Forge</h3>
        </div>
        <p className="text-sm font-exo text-dim-400 mb-4">Design and spawn custom floating widgets</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-void-700/50 rounded-lg p-4 border border-cyan-500/5">
            <p className="text-hud font-share-tech text-dim-400 mb-2 uppercase tracking-wider">Widget code (JSX)</p>
            <textarea
              className="w-full bg-void-900/80 text-ghost/80 text-xs font-jetbrains p-3 rounded-lg min-h-[120px] resize-none border border-cyan-500/10 focus:outline-none focus:border-cyan-500/30 transition-colors"
              placeholder="// Custom widget JSX..."
            />
          </div>
          <div className="bg-void-700/50 rounded-lg p-4 flex items-center justify-center border border-cyan-500/5">
            <div className="text-center">
              <Code className="w-8 h-8 text-dim-500 mx-auto mb-2" />
              <p className="text-xs text-dim-400 font-exo">Preview will appear here</p>
            </div>
          </div>
        </div>
        <button className="btn-cyan text-sm mt-4">Spawn Widget</button>
      </motion.div>
    </div>
  )
}
