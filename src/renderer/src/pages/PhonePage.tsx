import { Smartphone, Camera, Battery, FileUp, FileDown, Clipboard, ToggleLeft, Package } from 'lucide-react'
import { motion } from 'framer-motion'

export function PhonePage(): JSX.Element {
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">MOBILE CONTROL</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">Control your Android device via ADB — all by voice</p>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0 }}
          className="glass-card flex flex-col items-center text-center"
        >
          <div className="w-16 h-16 rounded-full bg-void-700/80 flex items-center justify-center mb-3 border border-cyan-500/10">
            <Smartphone className="w-8 h-8 text-dim-400" />
          </div>
          <h3 className="text-sm font-rajdhani font-semibold text-ghost">No device connected</h3>
          <p className="text-xs font-exo text-dim-400 mt-1">Connect via USB or Wi-Fi ADB</p>
          <button className="btn-cyan text-sm mt-4">Scan for Devices</button>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="glass-card"
        >
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-3">Quick Actions</h3>
          <div className="space-y-2">
            <button className="btn-ghost-cyan w-full text-left text-sm flex items-center gap-2">
              <Camera className="w-4 h-4" /> Take Photo
            </button>
            <button className="btn-ghost-cyan w-full text-left text-sm flex items-center gap-2">
              <Battery className="w-4 h-4" /> Battery Level
            </button>
            <button className="btn-ghost-cyan w-full text-left text-sm flex items-center gap-2">
              <ToggleLeft className="w-4 h-4" /> Toggle Flashlight
            </button>
            <button className="btn-ghost-cyan w-full text-left text-sm flex items-center gap-2">
              <Package className="w-4 h-4" /> Open Slack
            </button>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-card"
        >
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-3">File Transfer</h3>
          <div className="space-y-2">
            <button className="btn-ghost-cyan w-full text-left text-sm flex items-center gap-2">
              <FileUp className="w-4 h-4" /> Push to Phone
            </button>
            <button className="btn-ghost-cyan w-full text-left text-sm flex items-center gap-2">
              <FileDown className="w-4 h-4" /> Pull from Phone
            </button>
            <button className="btn-ghost-cyan w-full text-left text-sm flex items-center gap-2">
              <Clipboard className="w-4 h-4" /> Sync Clipboard
            </button>
          </div>
        </motion.div>
      </div>
    </div>
  )
}
