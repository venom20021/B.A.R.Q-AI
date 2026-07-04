import { Monitor, Maximize, Minimize, Grid3x3, Image, Workflow } from 'lucide-react'
import { motion } from 'framer-motion'

export function SystemPage(): JSX.Element {
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">SYSTEM CONTROL</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">Window management, wallpaper, and custom protocols</p>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card"
        >
          <div className="flex items-center gap-2 mb-4">
            <Monitor className="w-5 h-5 text-cyan-300" />
            <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Window Management</h3>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button className="btn-ghost-cyan text-sm flex items-center gap-2"><Maximize className="w-4 h-4" /> Maximize</button>
            <button className="btn-ghost-cyan text-sm flex items-center gap-2"><Minimize className="w-4 h-4" /> Minimize</button>
            <button className="btn-ghost-cyan text-sm flex items-center gap-2"><Grid3x3 className="w-4 h-4" /> Snap Left</button>
            <button className="btn-ghost-cyan text-sm flex items-center gap-2"><Grid3x3 className="w-4 h-4" /> Snap Right</button>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="glass-card"
        >
          <div className="flex items-center gap-2 mb-4">
            <Image className="w-5 h-5 text-holographic" />
            <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">AI Wallpaper</h3>
          </div>
          <div className="flex gap-2">
            <input type="text" placeholder='e.g., "cyberpunk city"' className="input-cyan flex-1 text-sm" />
            <button className="btn-cyan text-sm">Set</button>
          </div>
          <p className="text-xs font-exo text-dim-400 mt-2">Say: &quot;Change wallpaper to mountain sunset&quot;</p>
        </motion.div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="glass-card"
      >
        <div className="flex items-center gap-2 mb-4">
          <Workflow className="w-5 h-5 text-neural" />
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Custom Protocols</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {[
            { name: 'Job Hunt Mode', desc: 'Open job boards, update resume, start scanning' },
            { name: 'Deep Work Mode', desc: 'Kill distractions, set focus wallpaper, start timer' },
            { name: 'Gaming Mode', desc: 'Close background apps, free up RAM' },
          ].map((p) => (
            <div key={p.name} className="bg-void-700/50 rounded-lg p-4 cursor-pointer hover:bg-void-600/50 transition-colors border border-cyan-500/5 hover:border-cyan-500/15">
              <p className="text-sm font-rajdhani font-semibold text-ghost">{p.name}</p>
              <p className="text-xs font-exo text-dim-400 mt-1">{p.desc}</p>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  )
}
