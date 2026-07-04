import { FolderOpen, Search, Upload, Download, SortAsc } from 'lucide-react'
import { motion } from 'framer-motion'

export function FilesPage(): JSX.Element {
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">FILES</h1>
          <p className="text-sm font-rajdhani text-dim-400 mt-1">
            Browse, search, and organize your files with voice
          </p>
        </div>
        <button className="btn-cyan flex items-center gap-2">
          <Upload className="w-4 h-4" />
          Upload
        </button>
      </motion.div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dim-400" />
          <input
            type="text"
            placeholder="Search files by name or content..."
            className="input-cyan w-full pl-10"
          />
        </div>
        <button className="btn-glass flex items-center gap-2">
          <SortAsc className="w-4 h-4" />
          Sort
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="glass-card-hover cursor-pointer col-span-2 min-h-[300px] flex items-center justify-center">
          <div className="text-center">
            <FolderOpen className="w-12 h-12 text-dim-500 mx-auto mb-3" />
            <p className="text-dim-400 text-sm">File browser will appear here</p>
            <p className="text-dim-500 text-xs mt-1">Use voice commands like &quot;Show my downloads&quot; or &quot;Find files about React&quot;</p>
          </div>
        </div>
        <div className="glass-card space-y-4">
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Quick Actions</h3>
          <div className="space-y-2">
            <button className="w-full text-left btn-ghost-cyan text-sm flex items-center gap-2">
              <Download className="w-4 h-4" /> Downloads
            </button>
            <button className="w-full text-left btn-ghost-cyan text-sm flex items-center gap-2">
              <FolderOpen className="w-4 h-4" /> Documents
            </button>
            <button className="w-full text-left btn-ghost-cyan text-sm flex items-center gap-2">
              <FolderOpen className="w-4 h-4" /> Desktop
            </button>
          </div>
          <div className="pt-3 border-t border-cyan-500/8">
            <h4 className="text-hud font-share-tech text-dim-500 font-medium mb-2 tracking-wider uppercase">Drop Zones</h4>
            <div className="space-y-1.5">
              <div className="text-xs font-exo text-dim-400 bg-void-700/50 px-3 py-2 rounded-lg border border-cyan-500/5">
                PDFs → Documents/PDFs
              </div>
              <div className="text-xs font-exo text-dim-400 bg-void-700/50 px-3 py-2 rounded-lg border border-cyan-500/5">
                Images → Pictures
              </div>
              <div className="text-xs font-exo text-dim-400 bg-void-700/50 px-3 py-2 rounded-lg border border-cyan-500/5">
                Downloads &gt;7d → Archive
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
