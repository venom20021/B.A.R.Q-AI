import { type LucideIcon } from 'lucide-react'
import { motion } from 'framer-motion'

interface StatCardProps {
  title: string
  value: string | number
  description?: string
  icon: LucideIcon
  trend?: { value: number; isPositive: boolean }
  accent?: 'cyan' | 'purple' | 'green' | 'plasma' | 'blue'
  delay?: number
}

const accentConfig = {
  cyan: {
    border: 'border-cyan-500/20 hover:border-cyan-500/40',
    glow: 'shadow-glow-cyan-sm',
    iconBg: 'bg-cyan-500/10',
    iconColor: 'text-cyan-300',
    valueColor: 'text-cyan-200',
    gradient: 'from-cyan-400 to-cyan-600',
  },
  purple: {
    border: 'border-holographic/20 hover:border-holographic/40',
    glow: 'shadow-glow-purple',
    iconBg: 'bg-holographic/10',
    iconColor: 'text-holographic',
    valueColor: 'text-holographic',
    gradient: 'from-holographic to-purple-600',
  },
  green: {
    border: 'border-neural/20 hover:border-neural/40',
    glow: 'shadow-glow-green',
    iconBg: 'bg-neural/10',
    iconColor: 'text-neural',
    valueColor: 'text-neural',
    gradient: 'from-neural to-neural-500',
  },
  plasma: {
    border: 'border-plasma/20 hover:border-plasma/40',
    glow: 'shadow-glow-plasma',
    iconBg: 'bg-plasma/10',
    iconColor: 'text-plasma',
    valueColor: 'text-plasma',
    gradient: 'from-plasma to-orange-500',
  },
  blue: {
    border: 'border-cyan-400/20 hover:border-cyan-400/40',
    glow: 'shadow-glow-cyan-sm',
    iconBg: 'bg-cyan-400/10',
    iconColor: 'text-cyan-400',
    valueColor: 'text-cyan-300',
    gradient: 'from-cyan-400 to-cyan-600',
  },
}

export function StatCard({
  title,
  value,
  description,
  icon: Icon,
  trend,
  accent = 'cyan',
  delay = 0,
}: StatCardProps): JSX.Element {
  const cfg = accentConfig[accent]

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay }}
      className={`relative overflow-hidden rounded-xl bg-void-700/50 backdrop-blur-lg border ${cfg.border} ${cfg.glow} p-5 transition-all duration-300 hover:-translate-y-0.5 group`}
    >
      {/* Holographic shimmer top border */}
      <div className={`absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r ${cfg.gradient} opacity-50 group-hover:opacity-80 transition-opacity`} />

      {/* Scanline overlay */}
      <div className="absolute inset-0 pointer-events-none opacity-[0.02]"
        style={{
          backgroundImage: 'repeating-linear-gradient(transparent 0px, transparent 2px, rgba(0,240,255,0.03) 2px, rgba(0,240,255,0.03) 4px)',
        }}
      />

      <div className="relative z-10">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <p className="text-hud font-share-tech text-dim-400 uppercase tracking-wider">{title}</p>
            <p className={`text-2xl font-orbitron font-bold tracking-tight ${cfg.valueColor} text-glow-cyan`}>
              {value}
            </p>
            {description && (
              <p className="text-xs font-exo text-dim-400">{description}</p>
            )}
            {trend && (
              <div className="flex items-center gap-1.5 mt-1">
                <span
                  className={`text-hud-lg font-share-tech ${
                    trend.isPositive ? 'text-neural' : 'text-plasma'
                  }`}
                >
                  {trend.isPositive ? '+' : ''}
                  {trend.value}%
                </span>
                <span className="text-hud font-share-tech text-dim-500">vs last month</span>
              </div>
            )}
          </div>
          <div className={`p-3 rounded-lg ${cfg.iconBg} ${cfg.iconColor} group-hover:scale-110 transition-transform duration-200`}>
            <Icon className="w-5 h-5" />
          </div>
        </div>

        {/* Mini sparkline placeholder */}
        <div className="mt-4 h-8 flex items-end gap-[2px] opacity-30">
          {[30, 45, 25, 60, 40, 55, 35, 70, 50, 65, 45, 80, 55, 75, 60].map((h, i) => (
            <div
              key={i}
              className={`flex-1 rounded-t-sm bg-gradient-to-t ${cfg.gradient} transition-all duration-300`}
              style={{ height: `${h}%`, opacity: 0.3 + (h / 100) * 0.4 }}
            />
          ))}
        </div>
      </div>
    </motion.div>
  )
}
