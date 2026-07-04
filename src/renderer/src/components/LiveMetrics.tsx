import { motion } from 'framer-motion'
import { Activity, Zap } from 'lucide-react'

export function LiveMetrics(): JSX.Element {
  return (
    <motion.div
      initial={{ opacity: 0, y: -5 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center justify-between px-6 py-2 border-b border-[#00E5FF]/8"
    >
      <div className="flex items-center gap-3">
        <div className="w-2 h-2 rounded-full bg-[#00E5FF] shadow-[0_0_6px_rgba(0,229,255,0.5)] animate-pulse" />
        <span className="text-xs font-orbitron font-bold text-[#E2E8F0]/80 tracking-wider">BARQ</span>
        <span className="text-[8px] font-share-tech text-[#00E5FF]/50 bg-[#00E5FF]/8 px-1.5 py-0.5 rounded uppercase">v2</span>
      </div>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <Zap className="w-3 h-3 text-[#00E5FF]/50" />
          <span className="text-[9px] font-share-tech text-[#E2E8F0]/30 tracking-wider uppercase">All Systems Nominal</span>
        </div>
      </div>
    </motion.div>
  )
}
