import { type ReactNode, type CSSProperties } from 'react'
import { motion, type TargetAndTransition, type VariantLabels, type Transition } from 'framer-motion'

/**
 * Shared glassmorphism wrapper — consistent with navbar, dock, and all panels.
 *
 * Renders a `<div>` (or `<motion.div>` when animation props are provided) with
 * the standard glass style: `bg-void-900/80 backdrop-blur-2xl border border-white/[0.06] rounded-xl`.
 *
 * @example
 *   <GlassPanel>Basic card</GlassPanel>
 *
 *   <GlassPanel className="p-6 space-y-4">
 *     <h2>Custom padding</h2>
 *   </GlassPanel>
 *
 *   <GlassPanel hover className="p-4">
 *     Hoverable card with lift + glow
 *   </GlassPanel>
 *
 *   <GlassPanel
 *     initial={{ opacity: 0, y: 10 }}
 *     animate={{ opacity: 1, y: 0 }}
 *     className="p-4"
 *   >
 *     Animated entrance
 *   </GlassPanel>
 */

const GLASS_BASE = 'bg-void-900/80 backdrop-blur-2xl border border-white/[0.06] rounded-xl shadow-lg'
const GLASS_HOVER = 'hover:border-cyan-500/20 hover:shadow-glow-cyan-sm hover:-translate-y-0.5 transition-all duration-300'

interface GlassPanelProps {
  children: ReactNode
  className?: string
  /** Enable hover lift + glow effect (like the old glass-card-hover) */
  hover?: boolean
  /** Pass as a ref to motion.div for programmatic control */
  layoutId?: string
  /** Framer-motion initial state (renders as motion.div when provided) */
  initial?: boolean | TargetAndTransition | VariantLabels
  /** Framer-motion animate state */
  animate?: boolean | TargetAndTransition | VariantLabels
  /** Framer-motion exit state */
  exit?: TargetAndTransition | VariantLabels
  /** Framer-motion transition config */
  transition?: Transition
  /** Inline styles */
  style?: CSSProperties
  /** Click handler */
  onClick?: () => void
  /** On mouse enter */
  onMouseEnter?: () => void
}

export function GlassPanel({
  children,
  className = '',
  hover = false,
  layoutId,
  initial,
  animate,
  exit,
  transition,
  style,
  onClick,
  onMouseEnter,
}: GlassPanelProps): JSX.Element {
  const cls = [GLASS_BASE, hover && GLASS_HOVER, className].filter(Boolean).join(' ')

  // If any animation props are provided, render as motion.div
  if (initial || animate || exit) {
    return (
      <motion.div
        layoutId={layoutId}
        initial={initial}
        animate={animate}
        exit={exit}
        transition={transition ?? { duration: 0.2, ease: 'easeOut' }}
        className={cls}
        style={style}
        onClick={onClick}
        onMouseEnter={onMouseEnter}
      >
        {children}
      </motion.div>
    )
  }

  return (
    <div className={cls} style={style} onClick={onClick} onMouseEnter={onMouseEnter}>
      {children}
    </div>
  )
}

/**
 * Convenience alias for hover-enabled glass cards.
 */
export function GlassCard({ className = '', ...props }: GlassPanelProps): JSX.Element {
  return <GlassPanel hover className={className} {...props} />
}
