import { BrainCircuit, Bookmark, Search, FileText, Globe, Plus } from 'lucide-react'
import { motion } from 'framer-motion'

export function MemoryPage(): JSX.Element {
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">MEMORY & KNOWLEDGE</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">Core memory, vector search, notes, and RAG knowledge base</p>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="lg:col-span-2 glass-card"
        >
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-4">Core Memory</h3>
          <div className="space-y-3">
            {[
              { key: 'My API key', value: 'sk-... stored in keychain' },
              { key: 'Project setup', value: 'BARQ: Electron + React + Python' },
              { key: 'Email', value: 'user@example.com' },
            ].map((item) => (
              <div key={item.key} className="flex items-center justify-between py-2 border-b border-cyan-500/10 last:border-0">
                <div>
                  <p className="text-sm font-rajdhani font-semibold text-ghost">{item.key}</p>
                  <p className="text-xs font-exo text-dim-400">{item.value}</p>
                </div>
                <button className="text-xs font-exo text-dim-500 hover:text-cyan-300 transition-colors">Edit</button>
              </div>
            ))}
          </div>
          <button className="btn-ghost-cyan text-sm mt-4 flex items-center gap-2">
            <Plus className="w-4 h-4" /> Add Memory
          </button>
        </motion.div>

        <div className="space-y-4">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="glass-card"
          >
            <div className="flex items-center gap-2 mb-3">
              <Search className="w-5 h-5 text-cyan-300" />
              <h3 className="text-sm font-rajdhani font-semibold text-ghost">Vector Search</h3>
            </div>
            <input type="text" placeholder="Search your codebase..." className="input-cyan w-full text-sm" />
            <p className="text-xs font-exo text-dim-400 mt-2">Say: &quot;Find files about user auth&quot;</p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="glass-card"
          >
            <div className="flex items-center gap-2 mb-3">
              <FileText className="w-5 h-5 text-neural" />
              <h3 className="text-sm font-rajdhani font-semibold text-ghost">System Notes</h3>
            </div>
            <div className="space-y-2">
              <div className="bg-void-700/50 rounded-lg p-3 border border-cyan-500/5">
                <p className="text-xs font-exo text-ghost/80">Project architecture overview...</p>
                <p className="text-hud font-share-tech text-dim-500 mt-1">2 hours ago</p>
              </div>
            </div>
            <button className="btn-ghost-cyan text-xs mt-2 w-full text-left">Create Note</button>
          </motion.div>
        </div>
      </div>
    </div>
  )
}
