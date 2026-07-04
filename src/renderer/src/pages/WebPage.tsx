import { Globe, Music, TrendingUp, CloudSun, Map, Image as ImageIcon } from 'lucide-react'
import { motion } from 'framer-motion'

export function WebPage(): JSX.Element {
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">WEB & MEDIA</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">
          Browser agent, Spotify, stocks, weather, maps, and image generation
        </p>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0 }}
          className="glass-card-hover"
        >
          <Globe className="w-5 h-5 text-cyan-300 mb-3" />
          <h3 className="text-sm font-rajdhani font-semibold text-ghost mb-1">Web Agent</h3>
          <p className="text-xs font-exo text-dim-400">Browse, click, fill forms, scrape — all by voice</p>
          <div className="mt-3 flex gap-2">
            <input type="text" placeholder="URL or search query..." className="input-cyan flex-1 text-sm" />
            <button className="btn-cyan text-sm">Go</button>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="glass-card-hover"
        >
          <Music className="w-5 h-5 text-neural mb-3" />
          <h3 className="text-sm font-rajdhani font-semibold text-ghost mb-1">Spotify Control</h3>
          <p className="text-xs font-exo text-dim-400">Now playing: Nothing</p>
          <div className="flex gap-2 mt-3">
            <button className="btn-ghost-cyan text-xs">Play</button>
            <button className="btn-ghost-cyan text-xs">Pause</button>
            <button className="btn-ghost-cyan text-xs">Skip</button>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-card-hover"
        >
          <TrendingUp className="w-5 h-5 text-plasma mb-3" />
          <h3 className="text-sm font-rajdhani font-semibold text-ghost mb-1">Stock Market</h3>
          <p className="text-xs font-exo text-dim-400">Say: &quot;Get Apple stock price&quot; or &quot;Compare NVIDIA vs AMD&quot;</p>
          <div className="mt-3 flex gap-2">
            <input type="text" placeholder="Ticker (e.g., AAPL)" className="input-cyan flex-1 text-sm" />
            <button className="btn-glass text-sm">Search</button>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="glass-card-hover"
        >
          <CloudSun className="w-5 h-5 text-cyan-300 mb-3" />
          <h3 className="text-sm font-rajdhani font-semibold text-ghost mb-1">Weather</h3>
          <p className="text-xs font-exo text-dim-400">Say: &quot;What&apos;s the weather in London?&quot;</p>
          <div className="mt-3 flex gap-2">
            <input type="text" placeholder="City name..." className="input-cyan flex-1 text-sm" />
            <button className="btn-glass text-sm">Check</button>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass-card-hover"
        >
          <Map className="w-5 h-5 text-plasma mb-3" />
          <h3 className="text-sm font-rajdhani font-semibold text-ghost mb-1">Maps</h3>
          <p className="text-xs font-exo text-dim-400">Say: &quot;Show map of Tokyo&quot; or &quot;Directions to airport&quot;</p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
          className="glass-card-hover"
        >
          <ImageIcon className="w-5 h-5 text-holographic mb-3" />
          <h3 className="text-sm font-rajdhani font-semibold text-ghost mb-1">Image Generation</h3>
          <p className="text-xs font-exo text-dim-400">Say: &quot;Generate neon forest image&quot; or &quot;Create thumbnail&quot;</p>
          <div className="mt-3 flex gap-2">
            <input type="text" placeholder="Image description..." className="input-cyan flex-1 text-sm" />
            <button className="btn-cyan text-sm">Generate</button>
          </div>
        </motion.div>
      </div>
    </div>
  )
}
