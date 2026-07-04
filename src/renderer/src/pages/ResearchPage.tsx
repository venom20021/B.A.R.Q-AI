import { Search, BookOpen, Building2, FileText, Globe, BrainCircuit } from 'lucide-react'
import { motion } from 'framer-motion'

export function ResearchPage(): JSX.Element {
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">DEEP RESEARCH</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">
          Autonomous research, RAG knowledge base, and company intelligence
        </p>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0 }}
          className="lg:col-span-2 glass-card"
        >
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-4">Autonomous Research</h3>
          <div className="flex gap-2 mb-4">
            <input
              type="text"
              placeholder='e.g., "Research quantum computing breakthroughs"'
              className="input-cyan flex-1"
            />
            <button className="btn-cyan flex items-center gap-2">
              <Search className="w-4 h-4" />
              Research
            </button>
          </div>
          <div className="bg-void-900/80 rounded-lg p-4 min-h-[200px] border border-cyan-500/5">
            <p className="text-dim-500 text-sm font-exo">Say: &quot;Research quantum computing breakthroughs&quot;</p>
            <p className="text-dim-500 text-sm font-exo mt-1">Results will appear here with citations</p>
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
              <Building2 className="w-5 h-5 text-plasma" />
              <h3 className="text-sm font-rajdhani font-semibold text-ghost">Company Research</h3>
            </div>
            <div className="flex gap-2">
              <input type="text" placeholder="Company name..." className="input-cyan flex-1 text-sm" />
              <button className="btn-glass text-sm">Go</button>
            </div>
            <p className="text-xs font-exo text-dim-400 mt-2">Say: &quot;Research Google&quot;</p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="glass-card"
          >
            <div className="flex items-center gap-2 mb-3">
              <BrainCircuit className="w-5 h-5 text-holographic" />
              <h3 className="text-sm font-rajdhani font-semibold text-ghost">Codebase Oracle (RAG)</h3>
            </div>
            <p className="text-xs font-exo text-dim-400">Ingest repos and ask questions about your code</p>
            <button className="btn-ghost-cyan text-sm mt-2 w-full text-left">Ingest Repository</button>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            className="glass-card"
          >
            <div className="flex items-center gap-2 mb-3">
              <Globe className="w-5 h-5 text-cyan-300" />
              <h3 className="text-sm font-rajdhani font-semibold text-ghost">Knowledge Base</h3>
            </div>
            <p className="text-xs font-exo text-dim-400">Ingest docs, PDFs, web pages</p>
            <div className="mt-2 space-y-1">
              <div className="text-xs font-exo text-dim-400 bg-void-700/50 px-3 py-2 rounded-lg border border-cyan-500/5">
                React docs (ingested)
              </div>
              <div className="text-xs font-exo text-dim-400 bg-void-700/50 px-3 py-2 rounded-lg border border-cyan-500/5">
                Project README (ingested)
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  )
}
