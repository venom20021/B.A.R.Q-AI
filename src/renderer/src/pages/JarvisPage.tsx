import { useState, useEffect, useRef, startTransition, useLayoutEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Cpu, Activity, Mic, Camera, Shield,
  Clock, Terminal, Zap, Radio, Wifi, Server,
  ToggleLeft, ToggleRight, Lock,
} from 'lucide-react'

// ─── Glowing Digital Clock ──────────────────────────────────────────────

function DigitalClock(): JSX.Element {
  const [time, setTime] = useState(new Date())

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  const hh = time.getHours().toString().padStart(2, '0')
  const mm = time.getMinutes().toString().padStart(2, '0')
  const ss = time.getSeconds().toString().padStart(2, '0')
  const day = time.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase()
  const date = time.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' }).toUpperCase()

  return (
    <div className="text-right">
      <div className="flex items-center justify-end gap-2">
        <Clock className="w-3 h-3 text-violet-400/60" />
        <span className="font-mono text-2xl font-bold tracking-[0.15em] text-violet-300 tabular-nums">
          <span>{hh}</span>
          <motion.span
            animate={{ opacity: [1, 0, 1] }}
            transition={{ duration: 1, repeat: Infinity, ease: 'steps(1)' as unknown as undefined }}
            className="text-violet-500 mx-0.5"
          >:</motion.span>
          <span>{mm}</span>
          <motion.span
            animate={{ opacity: [1, 0, 1] }}
            transition={{ duration: 1, repeat: Infinity, ease: 'steps(1)' as unknown as undefined, delay: 0.5 }}
            className="text-violet-500 mx-0.5"
          >:</motion.span>
          <span>{ss}</span>
        </span>
      </div>
      <p className="text-[10px] font-mono text-violet-400/40 tracking-[0.2em] mt-0.5">
        {day} · {date}
      </p>
    </div>
  )
}

// ─── Sparkline Chart (canvas) ──────────────────────────────────────────

interface SparklineProps {
  data: number[]
  color?: string
  height?: number
  label?: string
  value?: string
  unit?: string
}

function SparklineChart({ data, color = '#A855F7', height = 32, label, value, unit }: SparklineProps): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || data.length < 2) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    const w = canvas.clientWidth
    const h = height
    canvas.width = w * dpr
    canvas.height = h * dpr
    ctx.scale(dpr, dpr)

    const padding = 2
    const chartW = w - padding * 2
    const chartH = h - padding * 2
    const min = Math.min(...data)
    const max = Math.max(...data)
    const range = max - min || 1

    ctx.clearRect(0, 0, w, h)

    // Gradient fill under the line
    const gradient = ctx.createLinearGradient(0, 0, 0, h)
    gradient.addColorStop(0, `${color}40`)
    gradient.addColorStop(1, `${color}05`)

    ctx.beginPath()
    data.forEach((d, i) => {
      const x = padding + (i / (data.length - 1)) * chartW
      const y = padding + chartH - ((d - min) / range) * chartH
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.lineTo(padding + chartW, padding + chartH)
    ctx.lineTo(padding, padding + chartH)
    ctx.closePath()
    ctx.fillStyle = gradient
    ctx.fill()

    // Line
    ctx.beginPath()
    data.forEach((d, i) => {
      const x = padding + (i / (data.length - 1)) * chartW
      const y = padding + chartH - ((d - min) / range) * chartH
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.strokeStyle = color
    ctx.lineWidth = 1.5
    ctx.shadowColor = color
    ctx.shadowBlur = 6
    ctx.stroke()
    ctx.shadowBlur = 0

    // End dot
    const lastX = padding + chartW
    const lastY = padding + chartH - ((data[data.length - 1] - min) / range) * chartH
    ctx.beginPath()
    ctx.arc(lastX, lastY, 2.5, 0, Math.PI * 2)
    ctx.fillStyle = color
    ctx.shadowColor = color
    ctx.shadowBlur = 10
    ctx.fill()
  }, [data, color, height])

  return (
    <div className="space-y-1">
      {(label || value) && (
        <div className="flex items-center justify-between">
          {label && <span className="text-[9px] font-mono text-violet-400/50 uppercase tracking-[0.15em]">{label}</span>}
          {value && (
            <span className="text-xs font-mono font-bold text-violet-200 tabular-nums">
              {value}<span className="text-[9px] text-violet-400/60">{unit}</span>
            </span>
          )}
        </div>
      )}
      <canvas ref={canvasRef} style={{ width: '100%', height }} className="rounded" />
    </div>
  )
}

// ─── Mock Data Generator ───────────────────────────────────────────────

function useMockSparklines() {
  const [cpuData, setCpuData] = useState<number[]>(() =>
    Array.from({ length: 30 }, () => 20 + Math.random() * 60)
  )
  const [memData, setMemData] = useState<number[]>(() =>
    Array.from({ length: 30 }, () => 40 + Math.random() * 30)
  )
  const [diskData, setDiskData] = useState<number[]>(() =>
    Array.from({ length: 30 }, () => 30 + Math.random() * 20)
  )
  const [tokens, setTokens] = useState(847_291)

  useEffect(() => {
    const interval = setInterval(() => {
      setCpuData(prev => [...prev.slice(1), 15 + Math.random() * 65])
      setMemData(prev => [...prev.slice(1), 45 + Math.random() * 25])
      setDiskData(prev => [...prev.slice(1), 30 + Math.random() * 18])
      setTokens(prev => prev + Math.floor(Math.random() * 150))
    }, 2000)
    return () => clearInterval(interval)
  }, [])

  return { cpuData, memData, diskData, tokens }
}

// ─── Hardware Permission Toggle ────────────────────────────────────────

function ToggleSwitch({
  icon: Icon,
  label,
  description,
  enabled,
  onToggle,
  locked,
}: {
  icon: typeof Mic
  label: string
  description: string
  enabled: boolean
  onToggle: () => void
  locked?: boolean
}): JSX.Element {
  return (
    <div className="flex items-center justify-between p-3 rounded-xl bg-black/40 border border-violet-500/10 hover:border-violet-500/20 transition-all group">
      <div className="flex items-center gap-3">
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center transition-all ${
          enabled
            ? 'bg-violet-500/15 text-violet-400 shadow-[0_0_12px_rgba(168,85,247,0.15)]'
            : 'bg-zinc-900/60 text-zinc-600'
        }`}>
          <Icon className="w-4 h-4" />
        </div>
        <div>
          <p className="text-xs font-mono font-semibold text-zinc-200">{label}</p>
          <p className="text-[9px] font-mono text-zinc-500">{description}</p>
        </div>
      </div>
      <button
        onClick={locked ? undefined : onToggle}
        className={`relative flex items-center transition-all ${
          locked ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'
        }`}
        title={locked ? 'Locked by system policy' : enabled ? 'Active — click to disable' : 'Inactive — click to enable'}
      >
        {locked ? (
          <Lock className="w-4 h-4 text-zinc-600" />
        ) : enabled ? (
          <ToggleRight className="w-6 h-6 text-violet-400 drop-shadow-[0_0_6px_rgba(168,85,247,0.4)]" />
        ) : (
          <ToggleLeft className="w-6 h-6 text-zinc-600" />
        )}
        {enabled && !locked && (
          <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-violet-400 animate-ping" />
        )}
      </button>
    </div>
  )
}

// ─── Command Log Types ─────────────────────────────────────────────────

interface LogEntry {
  id: number
  timestamp: string
  level: 'info' | 'warn' | 'error' | 'debug'
  source: string
  message: string
}

const LOG_SOURCES = [
  'CORE.INFERENCE', 'NETWORK.POLL', 'BACKEND.API', 'AUDIO.STREAM',
  'VISION.PROC', 'SCHEDULER', 'MEMORY.INDEX', 'TOKEN.MANAGER',
]

const LOG_MESSAGES = {
  info: [
    'Neural inference completed in 142ms',
    'Vector index refreshed — 12,847 embeddings',
    'Health check OK — all subsystems nominal',
    'Audio stream buffer flushed — 256 frames',
    'Token bucket refilled — 1,024 tokens granted',
    'Network poll: 3 peers reachable, latency 4.2ms',
    'Model checkpoint loaded — v2.4.1-rc3',
    'Memory compaction complete — freed 24MB',
    'Scheduler tick — 7 tasks queued',
    'Cache hit ratio: 94.2% across 2,104 requests',
  ],
  warn: [
    'Token bucket at 15% capacity — throttling suggested',
    'Audio input level below threshold — check microphone',
    'Memory pressure: 78% — consider garbage collection',
    'Network latency spike: 342ms from peer 0x7F',
    'Stale embeddings detected — re-index recommended',
  ],
  error: [
    'Backend timeout after 30s — retry scheduled',
    'Invalid response schema from inference server',
    'Microphone buffer underrun — 3 frames dropped',
    'Failed to acquire lock on memory segment 0x4A',
  ],
  debug: [
    'dbg: tensor shape [1, 512, 768] — pass OK',
    'dbg: attention mask computed in 0.03ms',
    'dbg: gradient norm: 0.042 — stable',
    'dbg: layer 7 activations: min=0.01, max=3.24',
  ],
}

function generateLogEntry(id: number): LogEntry {
  const levels: LogEntry['level'][] = ['info', 'info', 'info', 'info', 'warn', 'error', 'debug', 'debug']
  const level = levels[Math.floor(Math.random() * levels.length)]
  const source = LOG_SOURCES[Math.floor(Math.random() * LOG_SOURCES.length)]
  const messages = LOG_MESSAGES[level]
  const message = messages[Math.floor(Math.random() * messages.length)]
  const now = new Date()
  const timestamp = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}.${Math.floor(Math.random() * 999).toString().padStart(3, '0')}`
  return { id, timestamp, level, source, message }
}

// ─── Center Particle Sphere ────────────────────────────────────────────

function ParticleSphere(): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    let w = 280
    let h = 280
    canvas.width = w * dpr
    canvas.height = h * dpr
    canvas.style.width = `${w}px`
    canvas.style.height = `${h}px`
    ctx.scale(dpr, dpr)

    const cx = w / 2
    const cy = h / 2
    const radius = 90

    // Generate 3D point cloud
    const points: { x: number; y: number; z: number; size: number; speed: number; phase: number }[] = []
    for (let i = 0; i < 180; i++) {
      const theta = Math.random() * Math.PI * 2
      const phi = Math.acos(2 * Math.random() - 1)
      const r = radius * (0.7 + Math.random() * 0.3)
      points.push({
        x: r * Math.sin(phi) * Math.cos(theta),
        y: r * Math.sin(phi) * Math.sin(theta),
        z: r * Math.cos(phi),
        size: 0.8 + Math.random() * 1.5,
        speed: 0.2 + Math.random() * 0.4,
        phase: Math.random() * Math.PI * 2,
      })
    }

    // Connection lines: pre-compute pairs within distance threshold
    const connections: [number, number, number][] = []
    for (let i = 0; i < points.length; i++) {
      for (let j = i + 1; j < points.length; j++) {
        const dx = points[i].x - points[j].x
        const dy = points[i].y - points[j].y
        const dz = points[i].z - points[j].z
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz)
        if (dist < radius * 0.7) {
          connections.push([i, j, 1 - dist / (radius * 0.7)])
        }
      }
    }

    let angle = 0
    const animate = () => {
      angle += 0.005
      ctx.clearRect(0, 0, w, h)

      // Rotate points
      const cosA = Math.cos(angle)
      const sinA = Math.sin(angle)
      const rotated = points.map(p => {
        // Rotate around Y axis
        const x1 = p.x * cosA - p.z * sinA
        const z1 = p.x * sinA + p.z * cosA
        // Slight rotation around X axis
        const y1 = p.y * Math.cos(angle * 0.3) - z1 * Math.sin(angle * 0.3)
        const z2 = p.y * Math.sin(angle * 0.3) + z1 * Math.cos(angle * 0.3)
        return { x: x1, y: y1, z: z2, size: p.size, speed: p.speed, phase: p.phase }
      })

      // Sort by Z for depth
      const sorted = rotated.map((p, i) => ({ ...p, idx: i })).sort((a, b) => b.z - a.z)

      // Draw connections first (behind)
      for (const [i, j, intensity] of connections) {
        const p1 = rotated[i]
        const p2 = rotated[j]
        // Depth fade
        const avgZ = (p1.z + p2.z) / 2
        const depthFactor = (avgZ + radius) / (radius * 2)
        const alpha = intensity * 0.15 * depthFactor

        ctx.beginPath()
        ctx.moveTo(p1.x + cx, p1.y + cy)
        ctx.lineTo(p2.x + cx, p2.y + cy)
        ctx.strokeStyle = `rgba(168, 85, 247, ${alpha})`
        ctx.lineWidth = 0.5
        ctx.stroke()
      }

      // Draw points
      for (const p of sorted) {
        const zFactor = (p.z + radius) / (radius * 2)
        const alpha = 0.3 + zFactor * 0.7
        const size = p.size * (0.5 + zFactor * 0.5)

        // Glow
        const glowRadius = size * 4
        const glow = ctx.createRadialGradient(p.x + cx, p.y + cy, 0, p.x + cx, p.y + cy, glowRadius)
        glow.addColorStop(0, `rgba(168, 85, 247, ${alpha * 0.4})`)
        glow.addColorStop(0.5, `rgba(168, 85, 247, ${alpha * 0.1})`)
        glow.addColorStop(1, 'rgba(168, 85, 247, 0)')
        ctx.beginPath()
        ctx.arc(p.x + cx, p.y + cy, glowRadius, 0, Math.PI * 2)
        ctx.fillStyle = glow
        ctx.fill()

        // Core dot
        ctx.beginPath()
        ctx.arc(p.x + cx, p.y + cy, size, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(168, 85, 247, ${alpha})`
        ctx.fill()

        // Bright center
        if (zFactor > 0.6) {
          ctx.beginPath()
          ctx.arc(p.x + cx, p.y + cy, size * 0.4, 0, Math.PI * 2)
          ctx.fillStyle = `rgba(255, 255, 255, ${alpha * 0.3})`
          ctx.fill()
        }
      }

      animRef.current = requestAnimationFrame(animate)
    }

    const animRef = { current: requestAnimationFrame(animate) }
    return () => cancelAnimationFrame(animRef.current)
  }, [])

  return (
    <canvas
      ref={canvasRef}
      style={{ width: 280, height: 280 }}
      className="pointer-events-none"
    />
  )
}

// ─── Main Jarvis Page ──────────────────────────────────────────────────

export default function JarvisPage(): JSX.Element {
  const { cpuData, memData, diskData, tokens } = useMockSparklines()
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [micEnabled, setMicEnabled] = useState(true)
  const [cameraEnabled, setCameraEnabled] = useState(false)
  const [cameraLocked] = useState(false)
  const logContainerRef = useRef<HTMLDivElement>(null)
  const logIdRef = useRef(0)
  const [aiStatus, setAiStatus] = useState<'ONLINE' | 'PROCESSING' | 'STANDBY'>('ONLINE')

  // Uptime tracker
  const startTimeRef = useRef(0)
  useLayoutEffect(() => { startTimeRef.current = Date.now() }, [])
  const [uptime, setUptime] = useState('00:14:32')

  // Seed initial logs and add new ones periodically
  useEffect(() => {
    const initial: LogEntry[] = []
    for (let i = 0; i < 12; i++) {
      initial.push(generateLogEntry(logIdRef.current++))
    }
    startTransition(() => setLogs(initial))

    const interval = setInterval(() => {
      startTransition(() => setLogs(prev => [...prev.slice(-80), generateLogEntry(logIdRef.current++)]))
      // Occasionally toggle AI status
      if (Math.random() < 0.05) {
        startTransition(() => setAiStatus('PROCESSING'))
        setTimeout(() => startTransition(() => setAiStatus('ONLINE')), 800)
      }
    }, 1500 + Math.random() * 1500)

    return () => clearInterval(interval)
  }, [])

  // Update uptime every second from fixed start reference
  useEffect(() => {
    const timer = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTimeRef.current) / 1000)
      const h = Math.floor(elapsed / 3600).toString().padStart(2, '0')
      const m = Math.floor((elapsed % 3600) / 60).toString().padStart(2, '0')
      const s = (elapsed % 60).toString().padStart(2, '0')
      setUptime(`${h}:${m}:${s}`)
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  // Auto-scroll logs
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logs])

  const levelColors: Record<LogEntry['level'], string> = {
    info: 'text-violet-300/70',
    warn: 'text-amber-400/80',
    error: 'text-red-400/80',
    debug: 'text-zinc-500/60',
  }

  const levelTags: Record<LogEntry['level'], string> = {
    info: 'INFO',
    warn: 'WARN',
    error: 'ERR!',
    debug: 'DEBUG',
  }

  const statusColor = aiStatus === 'ONLINE' ? '#A855F7' : aiStatus === 'PROCESSING' ? '#FBBF24' : '#71717A'

  return (
    <div className="h-full w-full bg-black text-zinc-100 font-mono overflow-hidden relative">
      {/* Subtle grid background */}
      <div
        className="absolute inset-0 opacity-[0.03] pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(168, 85, 247, 0.08) 1px, transparent 1px),
            linear-gradient(90deg, rgba(168, 85, 247, 0.08) 1px, transparent 1px)
          `,
          backgroundSize: '48px 48px',
        }}
      />

      {/* Top-left corner bracket */}
      <div className="absolute top-3 left-3 w-6 h-6 border-l-2 border-t-2 border-violet-500/20 pointer-events-none" />
      <div className="absolute top-3 right-3 w-6 h-6 border-r-2 border-t-2 border-violet-500/20 pointer-events-none" />
      <div className="absolute bottom-3 left-3 w-6 h-6 border-l-2 border-b-2 border-violet-500/20 pointer-events-none" />
      <div className="absolute bottom-3 right-3 w-6 h-6 border-r-2 border-b-2 border-violet-500/20 pointer-events-none" />

      <div className="relative z-10 h-full flex flex-col p-4 gap-4">
        {/* ── Header ────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-1">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-violet-500/15 flex items-center justify-center border border-violet-500/20 shadow-[0_0_16px_rgba(168,85,247,0.15)]">
              <Activity className="w-4 h-4 text-violet-400" />
            </div>
            <div>
              <h1 className="text-sm font-mono font-bold text-violet-200 tracking-[0.2em] uppercase">J.A.R.V.I.S</h1>
              <p className="text-[9px] font-mono text-violet-400/40 tracking-[0.15em]">Neural AI Command Center</p>
            </div>
          </div>
          <DigitalClock />
        </div>

        {/* ─── 3-Column Grid ─────────────────────────────────────────── */}
        <div className="flex-1 grid grid-cols-[280px_1fr_320px] gap-4 min-h-0">
          {/* ═══ LEFT: System Vitals ═══ */}
          <div className="flex flex-col gap-3 min-h-0">
            {/* Status Card */}
            <div className="rounded-xl bg-black/50 border border-violet-500/10 p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[9px] font-mono text-violet-400/50 uppercase tracking-[0.15em]">AI Status</span>
                <div className="flex items-center gap-1.5">
                  <span
                    className="w-1.5 h-1.5 rounded-full"
                    style={{
                      backgroundColor: statusColor,
                      boxShadow: `0 0 6px ${statusColor}`,
                    }}
                  />
                  <motion.span
                    key={aiStatus}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="text-[10px] font-mono font-bold tracking-wider"
                    style={{ color: statusColor }}
                  >
                    {aiStatus}
                  </motion.span>
                </div>
              </div>
              <div className="flex items-center justify-between text-[10px] font-mono text-zinc-500">
                <span>Uptime</span>
                <span className="text-violet-300/70 tabular-nums">{uptime}</span>
              </div>
            </div>

            {/* Sparklines */}
            <div className="flex-1 rounded-xl bg-black/50 border border-violet-500/10 p-3 space-y-3 overflow-y-auto">
              <SparklineChart
                data={cpuData}
                color="#A855F7"
                label="CPU Load"
                value={`${Math.round(cpuData[cpuData.length - 1])}`}
                unit="%"
              />
              <div className="h-px bg-gradient-to-r from-transparent via-violet-500/10 to-transparent" />
              <SparklineChart
                data={memData}
                color="#8B5CF6"
                label="Memory"
                value={`${Math.round(memData[memData.length - 1])}`}
                unit="%"
              />
              <div className="h-px bg-gradient-to-r from-transparent via-violet-500/10 to-transparent" />
              <SparklineChart
                data={diskData}
                color="#6D28D9"
                label="Disk I/O"
                value={`${Math.round(diskData[diskData.length - 1])}`}
                unit="%"
              />
            </div>

            {/* Hardware Toggles */}
            <div className="space-y-2">
              <div className="flex items-center gap-2 px-1">
                <Shield className="w-3 h-3 text-violet-400/50" />
                <span className="text-[8px] font-mono text-violet-400/30 uppercase tracking-[0.2em]">Hardware Permissions</span>
              </div>
              <ToggleSwitch
                icon={Mic}
                label="Local Mic Access"
                description={micEnabled ? 'Active — voice capture enabled' : 'Disabled — microphone offline'}
                enabled={micEnabled}
                onToggle={() => setMicEnabled(prev => !prev)}
              />
              <ToggleSwitch
                icon={Camera}
                label="Camera Privacy"
                description={cameraLocked ? 'Locked by system policy' : cameraEnabled ? 'Active — camera online' : 'Disabled — privacy mode'}
                enabled={cameraEnabled}
                onToggle={() => setCameraEnabled(prev => !prev)}
                locked={cameraLocked}
              />
            </div>
          </div>

          {/* ═══ CENTER: Particle Sphere + Counter ═══ */}
          <div className="flex flex-col items-center justify-center gap-4">
            {/* Outer ring glow */}
            <div className="relative flex items-center justify-center">
              {/* Ambient glow rings */}
              <div className="absolute w-[320px] h-[320px] rounded-full bg-violet-500/3 blur-3xl animate-pulse" style={{ animationDuration: '4s' }} />
              <div className="absolute w-[300px] h-[300px] rounded-full border border-violet-500/10" />
              <div className="absolute w-[280px] h-[280px] rounded-full border border-violet-500/5" />

              {/* Spinning ring segments */}
              <motion.div
                className="absolute w-[310px] h-[310px] rounded-full border border-violet-500/20 border-dashed"
                animate={{ rotate: 360 }}
                transition={{ duration: 60, repeat: Infinity, ease: 'linear' }}
              />
              <motion.div
                className="absolute w-[290px] h-[290px] rounded-full border border-violet-500/10 border-dashed"
                animate={{ rotate: -360 }}
                transition={{ duration: 45, repeat: Infinity, ease: 'linear' }}
              />

              {/* The particle sphere */}
              <ParticleSphere />
            </div>

            {/* Token Counter */}
            <div className="text-center">
              <div className="flex items-center justify-center gap-2 mb-1">
                <Zap className="w-3.5 h-3.5 text-violet-400/60" />
                <span className="text-[9px] font-mono text-violet-400/40 uppercase tracking-[0.2em]">Tokens Processed</span>
              </div>
              <motion.div
                key={tokens}
                initial={{ scale: 1.05, opacity: 0.6 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ duration: 0.3 }}
                className="text-3xl font-mono font-bold tracking-[0.08em] text-violet-200 tabular-nums"
              >
                {tokens.toLocaleString()}
              </motion.div>
              <div className="flex items-center justify-center gap-3 mt-2">
                {['CORE', 'VISION', 'AUDIO'].map(mod => (
                  <div key={mod} className="flex items-center gap-1">
                    <span className="w-1 h-1 rounded-full bg-violet-400/40" />
                    <span className="text-[8px] font-mono text-violet-400/30 tracking-wider">{mod}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Quick Stats Row */}
            <div className="grid grid-cols-3 gap-3 w-full max-w-[360px]">
              {[
                { label: 'INFERENCE', value: '142ms', icon: Cpu },
                { label: 'MODELS', value: '7 / 12', icon: Server },
                { label: 'PEERS', value: '3', icon: Wifi },
              ].map(stat => (
                <div key={stat.label} className="rounded-lg bg-black/40 border border-violet-500/8 p-2.5 text-center">
                  <stat.icon className="w-3 h-3 text-violet-400/40 mx-auto mb-1" />
                  <p className="text-[10px] font-mono font-bold text-violet-200 tabular-nums">{stat.value}</p>
                  <p className="text-[7px] font-mono text-violet-400/30 uppercase tracking-[0.15em] mt-0.5">{stat.label}</p>
                </div>
              ))}
            </div>
          </div>

          {/* ═══ RIGHT: Command Logs ═══ */}
          <div className="flex flex-col gap-3 min-h-0">
            {/* Terminal Header */}
            <div className="flex items-center justify-between px-3 py-2 rounded-t-xl bg-black/60 border border-violet-500/10 border-b-0">
              <div className="flex items-center gap-2">
                <Terminal className="w-3.5 h-3.5 text-violet-400/60" />
                <span className="text-[9px] font-mono text-violet-400/50 uppercase tracking-[0.15em]">Command Log</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-violet-400/60 animate-pulse" />
                <span className="text-[8px] font-mono text-zinc-600 tabular-nums">{logs.length} entries</span>
              </div>
            </div>

            {/* Scrollable Log View */}
            <div
              ref={logContainerRef}
              className="flex-1 rounded-b-xl bg-black/60 border border-violet-500/10 p-2 overflow-y-auto font-mono text-[10px] leading-relaxed space-y-0.5"
            >
              <AnimatePresence initial={false}>
                {logs.map((log) => (
                  <motion.div
                    key={log.id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.15 }}
                    className="flex items-start gap-2 hover:bg-violet-500/3 px-1 py-0.5 rounded transition-colors"
                  >
                    <span className="text-zinc-600 shrink-0 w-[72px] tabular-nums">{log.timestamp}</span>
                    <span className={`shrink-0 w-10 text-[8px] font-bold tracking-wider ${levelColors[log.level]}`}>
                      [{levelTags[log.level]}]
                    </span>
                    <span className="text-violet-400/50 shrink-0 hidden 2xl:inline">{log.source}</span>
                    <span className="text-zinc-400 truncate">{log.message}</span>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>

            {/* Bottom Status Bar */}
            <div className="flex items-center justify-between px-2 py-1.5 rounded-lg bg-black/30 border border-violet-500/8">
              <div className="flex items-center gap-2">
                <Radio className="w-3 h-3 text-violet-400/40" />
                <span className="text-[8px] font-mono text-zinc-600">SYS.READY</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="flex -space-x-1">
                  {[0, 1, 2].map(i => (
                    <motion.div
                      key={i}
                      className="w-2 h-2 rounded-full border border-black"
                      style={{
                        backgroundColor: `rgba(168, 85, 247, ${0.3 + i * 0.2})`,
                      }}
                      animate={{ opacity: [0.5, 1, 0.5] }}
                      transition={{ duration: 2, delay: i * 0.3, repeat: Infinity }}
                    />
                  ))}
                </div>
                <span className="text-[8px] font-mono text-violet-400/30 ml-1">LIVE</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
