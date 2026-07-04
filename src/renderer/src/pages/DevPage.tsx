import { Terminal as TerminalIcon, GitBranch, Globe, Play, Code, FileCode } from 'lucide-react'
import { motion } from 'framer-motion'

export function DevPage(): JSX.Element {
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">DEVELOPER TOOLS</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">
          Terminal, git, macros, and localhost tunneling
        </p>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card"
        >
          <div className="flex items-center gap-2 mb-4">
            <TerminalIcon className="w-5 h-5 text-neural" />
            <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Terminal</h3>
          </div>
          <div className="bg-void-900/80 rounded-lg p-4 font-jetbrains text-sm text-dim-400 min-h-[200px] border border-cyan-500/5">
            <p className="text-neural">$ BARQ ready</p>
            <p className="text-dim-500 mt-2">Use voice: &quot;Run npm install&quot;</p>
            <p className="text-dim-500">Use voice: &quot;Check git status&quot;</p>
            <p className="text-dim-500">Use voice: &quot;Build the project&quot;</p>
          </div>
        </motion.div>

        <div className="space-y-4">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="glass-card"
          >
            <div className="flex items-center gap-2 mb-3">
              <GitBranch className="w-5 h-5 text-plasma" />
              <h3 className="text-sm font-rajdhani font-semibold text-ghost">Git</h3>
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between py-2 border-b border-cyan-500/8">
                <span className="text-sm font-exo text-dim-400">Current branch</span>
                <span className="text-sm font-jetbrains text-neural">main</span>
              </div>
              <button className="btn-ghost-cyan w-full text-left text-sm">git status</button>
              <button className="btn-ghost-cyan w-full text-left text-sm">git commit</button>
              <button className="btn-ghost-cyan w-full text-left text-sm">git push</button>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="glass-card"
          >
            <div className="flex items-center gap-2 mb-3">
              <Globe className="w-5 h-5 text-cyan-300" />
              <h3 className="text-sm font-rajdhani font-semibold text-ghost">Wormhole Tunnel</h3>
            </div>
            <p className="text-xs font-exo text-dim-400 mb-3">Expose localhost to the internet</p>
            <div className="flex gap-2">
              <input type="text" placeholder="Port (e.g., 3000)" className="input-cyan flex-1 text-sm" />
              <button className="btn-cyan text-sm">Expose</button>
            </div>
          </motion.div>
        </div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="glass-card"
      >
        <div className="flex items-center gap-2 mb-4">
          <Play className="w-5 h-5 text-holographic" />
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Macros</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="bg-void-700/50 rounded-lg p-4 cursor-pointer hover:bg-void-600/50 transition-colors border border-cyan-500/5 hover:border-cyan-500/15">
            <p className="text-sm font-rajdhani font-semibold text-ghost">Start Dev Mode</p>
            <p className="text-xs font-exo text-dim-400 mt-1">npm install → npm run dev → open browser</p>
          </div>
          <div className="bg-void-700/50 rounded-lg p-4 cursor-pointer hover:bg-void-600/50 transition-colors border border-cyan-500/5 hover:border-cyan-500/15">
            <p className="text-sm font-rajdhani font-semibold text-ghost">Deploy</p>
            <p className="text-xs font-exo text-dim-400 mt-1">Build → test → deploy to production</p>
          </div>
          <div className="bg-void-700/50 rounded-lg p-4 border border-dashed border-cyan-500/20 cursor-pointer hover:bg-void-600/50 transition-colors">
            <Code className="w-4 h-4 text-dim-400 mb-1" />
            <p className="text-sm font-rajdhani font-semibold text-dim-400">Create New Macro</p>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
