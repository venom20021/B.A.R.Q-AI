import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'

/* ─── Mock Data Generators ──────────────────────────────────────────── */

const SUBSYSTEMS_LEFT = [
  { label: 'PLASMA CORE', unit: 'MW', warn: 40, crit: 20 },
  { label: 'COOLANT FLOW', unit: 'L/s', warn: 50, crit: 25 },
  { label: 'MAGNETIC FIELD', unit: 'T', warn: 35, crit: 15 },
  { label: 'ENERGY OUTPUT', unit: 'GW', warn: 30, crit: 10 },
]

const SUBSYSTEMS_RIGHT = [
  { label: 'NEURAL LINK', unit: '%', warn: 45, crit: 20 },
  { label: 'VOICE SYNC', unit: 'ms', warn: 60, crit: 30 },
  { label: 'DATA STREAM', unit: 'Gbps', warn: 35, crit: 15 },
  { label: 'SECURITY GRID', unit: '%', warn: 40, crit: 20 },
]

function useFakeSensor(seed: number, min: number, max: number, volatility: number): number {
  const [value, setValue] = useState(min + (max - min) * 0.7)
  const phaseRef = useRef(seed * 10)

  useEffect(() => {
    const interval = setInterval(() => {
      phaseRef.current += 0.3 + Math.random() * 0.5
      const noise = Math.sin(phaseRef.current) * volatility
      const drift = (Math.random() - 0.5) * volatility * 0.3
      setValue((prev) => {
        const next = prev + noise * 0.05 + drift
        return Math.max(min, Math.min(max, next))
      })
    }, 200)
    return () => clearInterval(interval)
  }, [seed, min, max, volatility])

  return value
}

/* ─── Mini Sparkline Graph ──────────────────────────────────────────── */

function MiniGraph({ value, max, warn, crit }: { value: number; max: number; warn: number; crit: number }): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const pointsRef = useRef<number[]>([])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    pointsRef.current.push(value)
    if (pointsRef.current.length > 40) pointsRef.current.shift()

    ctx.clearRect(0, 0, 60, 20)

    const color = value <= crit ? '#FF3333' : value <= warn ? '#FFAA00' : '#00E5FF'

    ctx.beginPath()
    pointsRef.current.forEach((p, i) => {
      const x = (i / 39) * 58
      const y = 18 - (p / max) * 16
      if (i === 0) ctx.moveTo(x + 1, y)
      else ctx.lineTo(x + 1, y)
    })
    ctx.strokeStyle = color
    ctx.lineWidth = 1.2
    ctx.stroke()

    // Fill below
    const last = pointsRef.current.length
    if (last > 1) {
      ctx.lineTo((last - 1) / 39 * 58 + 1, 18)
      ctx.lineTo(1, 18)
      ctx.closePath()
      ctx.fillStyle = `rgba(${color === '#FF3333' ? '255,51,51' : color === '#FFAA00' ? '255,170,0' : '0,229,255'}, 0.08)`
      ctx.fill()
    }
  }, [value, max, warn, crit])

  return (
    <canvas
      ref={canvasRef}
      width={60}
      height={20}
      style={{ width: 60, height: 20, flexShrink: 0 }}
    />
  )
}

/* ─── Individual Monitor Row ────────────────────────────────────────── */

function MonitorRow({
  label,
  value,
  unit,
  max,
  warn,
  crit,
}: {
  label: string
  value: number
  unit: string
  max: number
  warn: number
  crit: number
}): JSX.Element {
  const pct = (value / max) * 100
  const color = pct <= crit ? '#FF3333' : pct <= warn ? '#FFAA00' : '#00E5FF'

  return (
    <div className="w-full">
      {/* Label row */}
      <div className="flex items-center justify-between mb-0.5">
        <span className="text-[7px] font-share-tech tracking-[0.15em] text-[#00E5FF]/50">
          {label}
        </span>
        <span className="text-[8px] font-share-tech tabular-nums" style={{ color }}>
          {value.toFixed(1)}
          <span className="text-[6px] text-[#00E5FF]/30 ml-0.5">{unit}</span>
        </span>
      </div>

      {/* Bar + mini graph row */}
      <div className="flex items-center gap-1.5">
        {/* Status bar */}
        <div className="flex-1 h-1.5 bg-[#0A1A2A] rounded-full overflow-hidden relative">
          <div
            className="h-full rounded-full transition-all duration-300 ease-out"
            style={{
              width: `${Math.min(100, pct)}%`,
              backgroundColor: color,
              boxShadow: `0 0 4px ${color}`,
            }}
          />
        </div>

        {/* Sparkline */}
        <MiniGraph value={value} max={max} warn={warn} crit={crit} />
      </div>
    </div>
  )
}

/* ─── Panel Component ───────────────────────────────────────────────── */

interface QuickAction {
  label: string
  value: string
  subtitle: string
  /** Optional scan-progress data — renders a mini progress bar instead of the plain value */
  progress?: { pct: number; phase: string }
  /** Optional status indicator — renders a colored dot with status label */
  status?: { active: boolean; label: string }
  /** Optional action callback — renders a trigger button when idle */
  onAction?: () => void
}

interface ArcMonitorPanelProps {
  side: 'left' | 'right'
  quickActions?: QuickAction[]
  weather?: {
    temp: number
    feels: number
    description: string
    emoji: string
  } | null
}

export function ArcMonitorPanel({ side, quickActions, weather }: ArcMonitorPanelProps): JSX.Element {
  const subsystems = side === 'left' ? SUBSYSTEMS_LEFT : SUBSYSTEMS_RIGHT

  // Hooks must be called unconditionally
  const leftValues = SUBSYSTEMS_LEFT.map((_, i) => useFakeSensor(i, 10, 100, 15))
  const rightValues = SUBSYSTEMS_RIGHT.map((_, i) => useFakeSensor(i + 10, 5, 100, 12))
  const allValues = [...leftValues, ...rightValues]

  // ── Status line ──
  const allOk = allValues.every((v, i) => {
    const s = [...SUBSYSTEMS_LEFT, ...SUBSYSTEMS_RIGHT][i]
    return (v / 100) * 100 > (s?.crit ?? 20)
  })
  const statusText = allOk ? 'ALL SYSTEMS NOMINAL' : 'ANOMALY DETECTED'
  const statusColor = allOk ? '#00E5FF' : '#FF3333'

  const panelLabel = side === 'left' ? 'REACTOR MONITOR' : 'SUBSYSTEM STATUS'
  const staggerDelay = side === 'left' ? 0 : 0.15

  return (
    <motion.div
      initial={{ opacity: 0, x: side === 'left' ? -10 : 10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.6, delay: staggerDelay, ease: 'easeOut' }}
      className={`
        w-[260px] flex-shrink-0 flex flex-col gap-2
        ${side === 'left' ? 'ml-4' : 'mr-4'}
      `}
    >
      {/* Main monitor panel */}
      <div className="border border-[#00E5FF]/10 rounded bg-[#050D15]/80 backdrop-blur-sm p-3">
        {/* Header */}
        <div className="flex items-center justify-between mb-2.5 pb-1.5 border-b border-[#00E5FF]/8">
          <span className="text-[8px] font-share-tech tracking-[0.2em] text-[#00E5FF]/40">
            {panelLabel}
          </span>
          <span className="flex items-center gap-1">
            <span
              className="w-1.5 h-1.5 rounded-full animate-pulse"
              style={{ backgroundColor: statusColor, boxShadow: `0 0 4px ${statusColor}` }}
            />
            <span className="text-[6px] font-share-tech tracking-wider" style={{ color: statusColor }}>
              {statusText}
            </span>
          </span>
        </div>

        {/* Subsystem rows */}
        <div className="flex flex-col gap-2.5">
          {subsystems.map((sub, i) => {
            const idx = side === 'left' ? i : i + SUBSYSTEMS_LEFT.length
            return (
              <MonitorRow
                key={sub.label}
                label={sub.label}
                value={allValues[idx]}
                unit={sub.unit}
                max={100}
                warn={sub.warn}
                crit={sub.crit}
              />
            )
          })}
        </div>

        {/* Footer: pulsing indicator line */}
        <div className="mt-2.5 pt-1.5 border-t border-[#00E5FF]/8 flex items-center justify-between">
          <span className="text-[6px] font-share-tech tracking-[0.15em] text-[#00E5FF]/25">
            UPLINK · STABLE
          </span>
          <span className="flex gap-0.5">
            {[0, 1, 2, 3].map((i) => (
              <motion.span
                key={i}
                className="w-1 h-2 rounded-sm"
                style={{ backgroundColor: '#00E5FF' }}
                animate={{ opacity: [0.2, 0.8, 0.2] }}
                transition={{ duration: 1.2, delay: i * 0.2, repeat: Infinity }}
              />
            ))}
          </span>
        </div>
      </div>

      {/* Quick-action stats section */}
      {quickActions && quickActions.length > 0 && (
        <div className="border border-[#00E5FF]/10 rounded bg-[#050D15]/80 backdrop-blur-sm p-2.5">
          <div className="text-[7px] font-share-tech tracking-[0.2em] text-[#00E5FF]/30 uppercase mb-2">
            {side === 'left' ? 'SYSTEM STATS' : 'TASK STATS'}
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            {quickActions.map((action) => (
              <div
                key={action.label}
                className="border border-[#00E5FF]/10 rounded bg-[#00E5FF]/[0.02] px-2 py-1.5"
              >
                <div className="text-[6px] font-share-tech tracking-[0.15em] text-[#00E5FF]/35 uppercase mb-0.5">
                  {action.label}
                </div>

                {/* Status indicator variant */}
                {action.status ? (
                  <div className="space-y-1">
                    {/* Top row: value + status dot */}
                    <div className="flex items-center justify-between">
                      <div
                        className="text-sm font-orbitron font-bold tracking-wider"
                        style={{ color: '#00E5FF', textShadow: '0 0 8px rgba(0,229,255,0.3)' }}
                      >
                        {action.value}
                      </div>
                      {/* Status dot */}
                      <div className="flex items-center gap-1">
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${action.status.active ? 'animate-pulse' : ''}`}
                          style={{
                            backgroundColor: action.status.active ? '#00FF88' : '#4A5568',
                            boxShadow: action.status.active ? '0 0 6px rgba(0,255,136,0.5)' : 'none',
                          }}
                        />
                        <span
                          className="text-[7px] font-share-tech tracking-wider uppercase"
                          style={{ color: action.status.active ? '#00FF88' : '#4A5568' }}
                        >
                          {action.status.label}
                        </span>
                      </div>
                    </div>
                    <div className="text-[6px] font-share-tech text-[#00E5FF]/20">
                      {action.subtitle}
                    </div>
                  </div>
                ) : /* Progress bar variant */
                action.progress ? (
                  <div className="space-y-1">
                    <div
                      className="text-sm font-orbitron font-bold tracking-wider"
                      style={{ color: '#00E5FF', textShadow: '0 0 8px rgba(0,229,255,0.3)' }}
                    >
                      {action.value}
                    </div>
                    {/* Mini progress bar */}
                    <div className="w-full h-1 bg-[#0A1A2A] rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-500 ease-out"
                        style={{
                          width: `${Math.min(100, action.progress.pct)}%`,
                          background: 'linear-gradient(90deg, #00E5FF, #6366F1, #A855F7)',
                          boxShadow: '0 0 6px rgba(0,229,255,0.4)',
                        }}
                      />
                    </div>
                    <div className="text-[6px] font-share-tech text-[#00E5FF]/25 truncate">
                      {action.progress.phase}
                    </div>
                  </div>
                ) : (
                  /* Default static value */
                  <>
                    <div className="flex items-center justify-between">
                      <div
                        className="text-sm font-orbitron font-bold tracking-wider"
                        style={{ color: '#00E5FF', textShadow: '0 0 8px rgba(0,229,255,0.3)' }}
                      >
                        {action.value}
                      </div>
                      {/* Action button */}
                      {action.onAction && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            action.onAction!()
                          }}
                          className="text-[6px] font-share-tech tracking-wider uppercase px-1.5 py-0.5 rounded
                            border border-[#00E5FF]/25 text-[#00E5FF]/60
                            hover:bg-[#00E5FF]/10 hover:text-[#00E5FF] hover:border-[#00E5FF]/40
                            transition-all duration-200"
                        >
                          SCAN NOW
                        </button>
                      )}
                    </div>
                    <div className="text-[6px] font-share-tech text-[#00E5FF]/20 mt-0.5">
                      {action.subtitle}
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Weather section (right panel only) */}
      {side === 'right' && weather && (
        <div className="border border-[#00E5FF]/10 rounded bg-[#050D15]/80 backdrop-blur-sm p-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[7px] font-share-tech tracking-[0.2em] text-[#00E5FF]/30 uppercase">
              WEATHER
            </span>
            <span className="text-[7px] font-share-tech tabular-nums text-[#00E5FF]/40">
              London
            </span>
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-lg">{weather.emoji}</span>
            <div>
              <div className="text-sm font-orbitron font-bold text-[#E2E8F0]/80 tracking-wider">
                {weather.temp}°C
              </div>
              <div className="text-[6px] font-share-tech text-[#00E5FF]/30 capitalize">
                {weather.description}
              </div>
            </div>
            <div className="ml-auto text-right">
              <div className="text-[6px] font-share-tech text-[#00E5FF]/25">
                Feels
              </div>
              <div className="text-[8px] font-share-tech tabular-nums text-[#E2E8F0]/50">
                {weather.feels}°
              </div>
            </div>
          </div>
        </div>
      )}
    </motion.div>
  )
}
