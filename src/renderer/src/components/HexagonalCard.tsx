import { type LucideIcon } from 'lucide-react'
import { motion } from 'framer-motion'

interface HexagonalCardProps {
  icon: LucideIcon
  label: string
  accent?: 'cyan' | 'electric' | 'white' | 'navy' | 'light'
  delay?: number
  onClick?: () => void
  onHover?: (label: string) => void
  onLeave?: () => void
}

const accentConfig = {
  cyan: {
    border: 'border-[#00E5FF]/20 group-hover:border-[#00E5FF]/40',
    glow: 'group-hover:shadow-glow-cyan',
    icon: 'text-[#00E5FF]/80 group-hover:text-[#00E5FF]',
    label: 'group-hover:text-[#00E5FF]',
    shine: 'from-[#00E5FF]/0 via-[#00E5FF]/5 to-[#00E5FF]/0',
    pulseColor: 'rgba(0, 229, 255, 0.2)',
  },
  electric: {
    border: 'border-[#00B4D8]/20 group-hover:border-[#00B4D8]/40',
    glow: 'group-hover:shadow-glow-cyan-sm',
    icon: 'text-[#00B4D8]/80 group-hover:text-[#00B4D8]',
    label: 'group-hover:text-[#00B4D8]',
    shine: 'from-[#00B4D8]/0 via-[#00B4D8]/5 to-[#00B4D8]/0',
    pulseColor: 'rgba(0, 180, 216, 0.2)',
  },
  white: {
    border: 'border-[#FFFFFF]/20 group-hover:border-[#FFFFFF]/40',
    glow: 'group-hover:shadow-glow-white',
    icon: 'text-[#FFFFFF]/80 group-hover:text-[#FFFFFF]',
    label: 'group-hover:text-[#FFFFFF]',
    shine: 'from-[#FFFFFF]/0 via-[#FFFFFF]/5 to-[#FFFFFF]/0',
    pulseColor: 'rgba(255, 255, 255, 0.15)',
  },
  navy: {
    border: 'border-[#1A237E]/20 group-hover:border-[#1A237E]/40',
    glow: 'group-hover:shadow-glow-navy',
    icon: 'text-[#1A237E]/80 group-hover:text-[#1A237E]',
    label: 'group-hover:text-[#1A237E]',
    shine: 'from-[#1A237E]/0 via-[#1A237E]/5 to-[#1A237E]/0',
    pulseColor: 'rgba(26, 35, 78, 0.2)',
  },
  light: {
    border: 'border-[#E2E8F0]/20 group-hover:border-[#E2E8F0]/40',
    glow: 'group-hover:shadow-glow-white',
    icon: 'text-[#E2E8F0]/80 group-hover:text-[#E2E8F0]',
    label: 'group-hover:text-[#E2E8F0]',
    shine: 'from-[#E2E8F0]/0 via-[#E2E8F0]/5 to-[#E2E8F0]/0',
    pulseColor: 'rgba(226, 232, 240, 0.15)',
  },
}

export function HexagonalCard({
  icon: Icon,
  label,
  accent = 'cyan',
  delay = 0,
  onClick,
  onHover,
  onLeave,
}: HexagonalCardProps): JSX.Element {
  const cfg = accentConfig[accent]

  return (
    <motion.div
      animate={{ y: [0, -3, 0] }}
      transition={{
        duration: 3,
        repeat: Infinity,
        ease: 'easeInOut',
        delay: delay * 0.5,
      }}
      className="flex flex-col items-center"
    >
      <motion.button
        initial={{ opacity: 0, y: 12, scale: 0.92 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.4, delay, ease: [0.25, 0.1, 0.25, 1] }}
        whileHover={{ scale: 1.04, transition: { duration: 0.2 } }}
        whileTap={{ scale: 0.96 }}
        onClick={onClick}
        onMouseEnter={() => onHover?.(label)}
        onMouseLeave={() => onLeave?.()}
        className="group relative flex flex-col items-center justify-center outline-none"
      >
      {/* Outer glow aura (subtle, only on hover) */}
      <div
        className="absolute inset-0 -m-2 rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-700 pointer-events-none"
        style={{
          background: `radial-gradient(circle at center, ${cfg.pulseColor} 0%, transparent 70%)`,
        }}
      />

      {/* Hexagonal clip container — dark luxury glass */}
      <div
        className={`relative w-[84px] h-[98px] flex flex-col items-center justify-center gap-1
          bg-[#0D0D15]/90 backdrop-blur-3xl border ${cfg.border} ${cfg.glow}
          transition-all duration-400 cursor-pointer
          [clip-path:polygon(25%_0%,75%_0%,100%_50%,75%_100%,25%_100%,0%_50%)]
        `}
      >
        {/* Subtle shine sweep on hover */}
        <div
          className={`absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none
            bg-gradient-to-br ${cfg.shine}
          `}
        />

        {/* Inner border glow on hover */}
        <div
          className="absolute inset-[1.5px] pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-400
            [clip-path:polygon(25%_0%,75%_0%,100%_50%,75%_100%,25%_100%,0%_50%)]"
          style={{
            boxShadow: `inset 0 0 10px rgba(0, 229, 255, 0.06)`,
          }}
        />

        {/* Icon */}
        <div className={`relative z-10 transition-all duration-400 ${cfg.icon}`}>
          <Icon className="w-[18px] h-[18px]" />
        </div>

        {/* Label */}
        <span
          className={`relative z-10 text-[8px] font-rajdhani font-semibold text-[#E2E8F0]/40 ${cfg.label} transition-colors duration-400 tracking-[0.15em] uppercase`}
        >
          {label}
        </span>

        {/* Bottom accent line */}
        <div className="absolute bottom-1 left-1/2 -translate-x-1/2 w-5 h-px bg-gradient-to-r from-transparent via-current to-transparent opacity-0 group-hover:opacity-50 transition-opacity duration-400 text-[#00E5FF]" />
      </div>
    </motion.button>
    </motion.div>
  )
}
