import { motion } from 'framer-motion'
import { Cpu, MemoryStick, BrainCircuit, Activity, Wifi, HardDrive } from 'lucide-react'

interface InfoRowProps {
  icon: typeof Cpu
  label: string
  value: string
  status?: 'online' | 'busy' | 'offline'
}

function InfoRow({ icon: Icon, label, value, status }: InfoRowProps): JSX.Element {
  return (      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#00E5FF]/8 last:border-b-0">
      <div className="flex items-center gap-2.5">
        <Icon className="w-3.5 h-3.5 text-[#00E5FF]/60" />
        <span className="text-[10px] font-share-tech text-[#E2E8F0]/40 uppercase tracking-wider">
          {label}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs font-rajdhani font-semibold text-[#E2E8F0]/80">
          {value}
        </span>
        {status && (
          <div className={`w-1.5 h-1.5 rounded-full ${
            status === 'online' ? 'bg-[#00E5FF] shadow-[0_0_6px_rgba(0,229,255,0.5)]' :
            status === 'busy' ? 'bg-[#00B4D8]' : 'bg-[#E2E8F0]/10'
          }`} />
        )}
      </div>
    </div>
  )
}

export function SystemInfo(): JSX.Element {
  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: 0.3, duration: 0.5, ease: 'easeOut' }}
      className="luxury-glass rounded-xl overflow-hidden border border-[#00E5FF]/15"
    >
      {/* Header */}
      <div className="px-4 py-2.5 bg-[#00E5FF]/5 border-b border-[#00E5FF]/10">
        <div className="flex items-center gap-2">
          <Activity className="w-3.5 h-3.5 text-[#00E5FF]/80" />
          <span className="text-[10px] font-share-tech font-semibold text-[#E2E8F0]/60 uppercase tracking-[0.15em]">
            System Metrics
          </span>
        </div>
      </div>

      {/* Info rows */}
      <InfoRow icon={Cpu} label="CPU" value="23%" status="online" />
      <InfoRow icon={MemoryStick} label="RAM" value="1.8 / 8.0 GB" status="online" />
      <InfoRow icon={HardDrive} label="Disk" value="64 / 256 GB" status="online" />
      <InfoRow icon={BrainCircuit} label="Ollama" value="Connected" status="online" />
      <InfoRow icon={Wifi} label="Network" value="Stable" status="online" />
      <InfoRow icon={Activity} label="Uptime" value="12h 34m" status="busy" />
    </motion.div>
  )
}
