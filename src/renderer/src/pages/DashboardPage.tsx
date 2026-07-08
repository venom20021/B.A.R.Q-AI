import { lazy, Suspense, useState, useEffect, useRef, useCallback } from 'react'
import { motion } from 'framer-motion'
import {
  Activity, Clock, Terminal, CheckCircle2, FileText, Radio,
  Cloud, MessageCircle, Mic, Plus, X,
} from 'lucide-react'
import { useTheme } from '../contexts/ThemeContext'
import { useStreamingChat } from '../hooks/useStreamingChat'

// ─── Glowing Digital Clock (purple) ────────────────────────────────────

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
        <Clock className="w-3.5 h-3.5 text-purple-400/80" />
        <span className="font-mono text-2xl font-bold tracking-[0.15em] tabular-nums" style={{ color: 'var(--a200)', filter: 'drop-shadow(0 0 12px rgba(var(--a400-rgb), 0.2))' }}>
          <span>{hh}</span>
          <motion.span
            animate={{ opacity: [1, 0, 1] }}
            transition={{ duration: 1, repeat: Infinity, ease: 'steps(1)' as unknown as undefined }}
            className="text-purple-500 mx-0.5"
          >:</motion.span>
          <span>{mm}</span>
          <motion.span
            animate={{ opacity: [1, 0, 1] }}
            transition={{ duration: 1, repeat: Infinity, ease: 'steps(1)' as unknown as undefined, delay: 0.5 }}
            className="text-purple-500 mx-0.5"
          >:</motion.span>
          <span>{ss}</span>
        </span>
      </div>
      <p className="text-[11px] font-mono text-purple-400/50 tracking-[0.2em] mt-0.5">
        {day} &middot; {date}
      </p>
    </div>
  )
}

// ─── Sparkline Chart (canvas) ──────────────────────────────────────────

interface SparklineProps {
  data: number[]
  color?: string
  height?: number
}

function SparklineChart({ data, color = '#A855F7', height = 32 }: SparklineProps): JSX.Element {
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

    const lastX = padding + chartW
    const lastY = padding + chartH - ((data[data.length - 1] - min) / range) * chartH
    ctx.beginPath()
    ctx.arc(lastX, lastY, 2.5, 0, Math.PI * 2)
    ctx.fillStyle = color
    ctx.shadowColor = color
    ctx.shadowBlur = 10
    ctx.fill()
  }, [data, color, height])

  return <canvas ref={canvasRef} style={{ width: '100%', height }} className="rounded" />
}

// ─── Real System Data (polls /system/status) ────────────────────────────

interface SystemData {
  cpuPercent: number
  memPercent: number
  diskPercent: number
  memUsedGB: number
  memTotalGB: number
  cpus: number
  cpuHistory: number[]
  memHistory: number[]
  diskHistory: number[]
  responseTimeMs: number
  isConnected: boolean
}

function useRealSystemData(): SystemData {
  const [data, setData] = useState<SystemData>(() => ({
    cpuPercent: 0,
    memPercent: 0,
    diskPercent: 0,
    memUsedGB: 0,
    memTotalGB: 0,
    cpus: 0,
    cpuHistory: Array.from({ length: 30 }, () => 20 + Math.random() * 20),
    memHistory: Array.from({ length: 30 }, () => 40 + Math.random() * 15),
    diskHistory: Array.from({ length: 30 }, () => 30 + Math.random() * 20),
    responseTimeMs: 0,
    isConnected: false,
  }))

  useEffect(() => {
    let mounted = true

    const fetchData = async () => {
      const start = performance.now()
      try {
        const resp = await window.barq?.python.request('/system/status')
        if (!mounted) return
        const elapsed = performance.now() - start

        if (resp && typeof resp === 'object') {
          const status = resp as Record<string, unknown>
          const mem = status.memory as Record<string, number> | undefined
          const disk = status.disk as Record<string, number> | undefined

          const cpu = (status.cpu_percent as number) ?? 0
          const memPct = mem?.percent ?? 0
          const diskPct = disk?.percent ?? 0
          const memUsed = mem?.used_gb ?? 0
          const memTotal = mem?.total_gb ?? 0
          const cpus = (status.cpus as number) ?? 0

          setData(prev => ({
            cpuPercent: cpu,
            memPercent: memPct,
            diskPercent: diskPct,
            memUsedGB: memUsed,
            memTotalGB: memTotal,
            cpus,
            cpuHistory: [...prev.cpuHistory.slice(1), cpu],
            memHistory: [...prev.memHistory.slice(1), memPct],
            diskHistory: [...prev.diskHistory.slice(1), diskPct],
            responseTimeMs: elapsed,
            isConnected: true,
          }))
        }
      } catch {
        // Backend unavailable — keep previous values
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 2000)
    return () => { mounted = false; clearInterval(interval) }
  }, [])

  return data
}

// ─── Metric Tile (large number + sparkline) ────────────────────────────

interface MetricTileProps {
  label: string
  value: string
  sparklineData: number[]
}

function MetricTile({ label, value, sparklineData }: MetricTileProps): JSX.Element {
  return (
    <div className="group">
      <span className="text-[10px] font-mono text-zinc-300 uppercase tracking-[0.15em]">{label}</span>
      <div className="flex items-baseline gap-1.5 mt-0.5">
        <span className="text-3xl font-orbitron font-bold text-zinc-100 tabular-nums" style={{ filter: 'drop-shadow(0 0 8px rgba(var(--a400-rgb), 0.08))' }}>
          {value}
        </span>
      </div>
      <div className="mt-1.5">
        <SparklineChart data={sparklineData} color="#3f3f46" height={24} />
      </div>
    </div>
  )
}

// ─── Documents Checklist ───────────────────────────────────────────────

const DOCUMENTS = [
  'System_Arch_v2.4.pdf',
  'API_Spec_Neural_Inference.docx',
  'Security_Audit_Report_2026.pdf',
  'Model_Training_Logs_Q2.xlsx',
  'Deployment_Playbook_RC3.md',
  'Network_Topology_Map.svg',
]

function DocumentsChecklist(): JSX.Element {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2.5">
        <FileText className="w-3 h-3 text-purple-400/60" />
        <span className="text-[9px] font-mono text-purple-400/50 uppercase tracking-[0.2em] font-semibold">
          Documents
        </span>
      </div>
      <div className="space-y-1.5">
        {DOCUMENTS.map((doc, i) => (
          <div key={i} className="flex items-center gap-2 group">
            <div className="w-3.5 h-3.5 rounded border border-zinc-600 flex items-center justify-center group-hover:border-purple-500/50 transition-colors">
              <CheckCircle2 className="w-2.5 h-2.5 text-purple-500/50" />
            </div>
            <span className="text-[10px] font-mono text-zinc-400 group-hover:text-zinc-300 transition-colors truncate">
              {doc}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Activity Feed Types ────────────────────────────────────────────────

type ActivityType = 'weather' | 'chat' | 'voice' | 'system'

interface ActivityEntry {
  id: number
  timestamp: string
  type: ActivityType
  label: string
  message: string
  detail?: string
}

const WEATHER_FALLBACKS = [
  { temp: 22, condition: 'Partly Cloudy', city: 'London', humidity: 58 },
  { temp: 18, condition: 'Light Rain', city: 'New York', humidity: 72 },
  { temp: 28, condition: 'Sunny', city: 'Tokyo', humidity: 45 },
  { temp: 15, condition: 'Overcast', city: 'Berlin', humidity: 65 },
  { temp: 32, condition: 'Clear', city: 'Dubai', humidity: 20 },
]

// ─── Voice Waveform (uses parent's audioAmplitude from WebSocket) ──

function VoiceWaveform({ isListening, amplitude }: { isListening: boolean; amplitude: number }): JSX.Element {
  const BAR_WEIGHTS = [0.3, 0.55, 0.8, 1.0, 0.8, 0.55, 0.3]

  return (
    <div className="flex items-center gap-[2px] h-3">
      {BAR_WEIGHTS.map((w, i) => {
        const h = Math.max(2, amplitude * 14 * w)
        return (
          <motion.span
            key={i}
            layout
            transition={{ type: 'spring', stiffness: 400, damping: 25 }}
            className="w-[2px] rounded-full"
            style={{
              height: `${h}px`,
              backgroundColor: isListening ? 'rgb(52,211,153)' : 'rgb(113,113,122)',
            }}
          />
        )
      })}
    </div>
  )
}

// ─── Real Weather Data (polls /web/weather) ─────────────────────────

interface WeatherData {
  city: string
  country: string
  temperature_c: number
  feels_like_c: number
  humidity: number
  description: string
  wind_speed: number
  visibility: number
}

function useWeatherData(): WeatherData | null {
  const [data, setData] = useState<WeatherData | null>(null)

  useEffect(() => {
    let mounted = true

    const fetchWeather = async () => {
      try {
        // Try to get the default city from voice status, fallback to London
        let city = 'London'
        try {
          const statusResp = await window.barq?.python.request('/voice/status')
          if (statusResp && typeof statusResp === 'object') {
            const s = statusResp as { weather_city?: string }
            if (s.weather_city) city = s.weather_city
          }
        } catch { /* use default */ }

        const resp = await window.barq?.python.request(`/web/weather?city=${encodeURIComponent(city)}`)
        if (!mounted) return

        if (resp && typeof resp === 'object') {
            const w = resp as WeatherData & { status?: string }
            if (w.temperature_c != null && w.status !== 'unconfigured' && w.status !== 'unavailable') {
              setData({
              city: w.city ?? city,
              country: w.country ?? '',
              temperature_c: w.temperature_c,
              feels_like_c: w.feels_like_c,
              humidity: w.humidity,
              description: w.description,
              wind_speed: w.wind_speed,
              visibility: w.visibility,
            })
          }
        }
      } catch { /* backend unavailable */ }
    }

    fetchWeather()
    const interval = setInterval(fetchWeather, 300_000) // 5 min
    return () => { mounted = false; clearInterval(interval) }
  }, [])

  return data
}

// ─── Multi-City Weather (polls /web/weather for tracked cities) ──────

interface CityWeather {
  city: string
  country: string
  temperature_c: number
  feels_like_c: number
  humidity: number
  description: string
  wind_speed: number
  visibility: number
}

const WEATHER_CITIES_KEY = 'barq_weather_cities'
const DEFAULT_WEATHER_CITIES = ['London']

function useMultiCityWeather(): {
  cities: string[]
  weatherMap: Map<string, CityWeather>
  selectedCity: string
  setSelectedCity: (c: string) => void
  addCity: (c: string) => void
  removeCity: (c: string) => void
  loading: boolean
} {
  const [cities, setCities] = useState<string[]>(() => {
    try {
      const stored = localStorage.getItem(WEATHER_CITIES_KEY)
      if (stored) {
        const parsed = JSON.parse(stored)
        if (Array.isArray(parsed) && parsed.length > 0) return parsed
      }
    } catch { /* ignore */ }
    return DEFAULT_WEATHER_CITIES
  })
  const [weatherMap, setWeatherMap] = useState<Map<string, CityWeather>>(new Map())
  const [selectedCity, setSelectedCity] = useState<string>(cities[0])
  const [loading, setLoading] = useState(true)

  // Persist cities
  useEffect(() => {
    localStorage.setItem(WEATHER_CITIES_KEY, JSON.stringify(cities))
  }, [cities])

  // Poll weather for all cities
  useEffect(() => {
    let mounted = true
    let isFirstFetch = true

    const fetchAll = async () => {
      if (isFirstFetch) setLoading(true)
      const results = await Promise.allSettled(
        cities.map(async (city) => {
          const resp = await window.barq?.python.request(`/web/weather?city=${encodeURIComponent(city)}`)
          if (resp && typeof resp === 'object') {
            const w = resp as CityWeather & { status?: string }
            if (w.temperature_c != null && w.status !== 'unconfigured' && w.status !== 'unavailable') {
            return { city, data: w }
            }
          }
          return null
        })
      )
      if (!mounted) return

      // Use functional update to avoid stale closure
      setWeatherMap(prev => {
        const m = new Map(prev)
        for (const r of results) {
          if (r.status === 'fulfilled' && r.value) {
            m.set(r.value.city, r.value.data)
          }
        }
        return m
      })
      isFirstFetch = false
      setLoading(false)
    }

    fetchAll()
    const interval = setInterval(fetchAll, 300_000)
    return () => { mounted = false; clearInterval(interval) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cities])

  const addCity = useCallback((city: string) => {
    const n = city.trim()
    if (!n || cities.includes(n)) return
    setCities(prev => [...prev, n])
    setSelectedCity(n)
  }, [cities])

  const removeCity = useCallback((city: string) => {
    if (cities.length <= 1) return
    setCities(prev => prev.filter(c => c !== city))
    setSelectedCity(prev => prev === city ? cities.filter(c => c !== city)[0] : prev)
  }, [cities])

  return { cities, weatherMap, selectedCity, setSelectedCity, addCity, removeCity, loading }
}

// ─── Real Activity Feed (polls backend endpoints) ─────────────────────

interface BackendActivity {
  id: number
  type: string
  action: string
  description: string
  severity: string
  created_at: string
}

interface VoiceHistoryEntry {
  id: number
  transcript: string
  action: string
  success: boolean
  confidence: number
  created_at: string
}

function useRealActivityFeed(weather: WeatherData | null): { activities: ActivityEntry[]; liveCount: number; latestVoice: { transcript: string; action: string } | null } {
  const [entries, setEntries] = useState<ActivityEntry[]>([])
  const idRef = useRef(0)
  const [liveCount, setLiveCount] = useState(0)
  const [backendSeed, setBackendSeed] = useState<ActivityEntry[]>([])
  const [latestVoice, setLatestVoice] = useState<{ transcript: string; action: string } | null>(null)
  const seedDone = useRef(false)
  const weatherRef = useRef(weather)
  weatherRef.current = weather

  // Seed with initial backend data
  useEffect(() => {
    if (seedDone.current) return
    seedDone.current = true

    const seed = async () => {
      try {
        const resp = await window.barq?.python.request('/analytics/activity?limit=35')
        if (resp && typeof resp === 'object') {
          const data = resp as { activities?: BackendActivity[] }
          const items = (data.activities ?? []).map(a => ({
            id: idRef.current++,
            timestamp: _formatTs(a.created_at),
            type: _activityTypeToEntry(a.type) as ActivityType,
            label: a.action,
            message: a.description || a.action,
            detail: `${a.severity}`,
          } as ActivityEntry))
          setBackendSeed(items)
        }
      } catch { /* fallback to mock seed below */ }
    }
    seed()
  }, [])

  // Build initial display from backend seed + weather fill
  useEffect(() => {
    const initial: ActivityEntry[] = []

    // Copy backend seed items (newest first from DB)
    backendSeed.forEach(item => initial.push(item))

    // Fill remaining slots with weather entries (real data if available, fallback otherwise)
    const needed = Math.max(20 - initial.length, 0)
    for (let i = 0; i < needed; i++) {
      const ts = new Date()
      const t = `${ts.getHours().toString().padStart(2, '0')}:${ts.getMinutes().toString().padStart(2, '0')}:${ts.getSeconds().toString().padStart(2, '0')}`
      const w = weatherRef.current
      if (w) {
        initial.push({
          id: idRef.current++,
          timestamp: t, type: 'weather',
          label: w.city,
          message: `${Math.round(w.temperature_c)}°C — ${w.description}`,
          detail: `Humidity: ${w.humidity}% · Feels like ${Math.round(w.feels_like_c)}°C`,
        })
      } else {
        const fb = WEATHER_FALLBACKS[i % WEATHER_FALLBACKS.length]
        initial.push({
          id: idRef.current++,
          timestamp: t, type: 'weather',
          label: fb.city,
          message: `${fb.temp}°C — ${fb.condition}`,
          detail: `Humidity: ${fb.humidity}%`,
        })
      }
    }

    setEntries(initial.slice(-50))

    // ── Polling loop ────────────────────────────────────────────
    let mounted = true
    let latestActivityTs = ''
    let latestVoiceTs = ''
    let latestSystemTs = ''

    const poll = async () => {
      try {
        const [actResp, voiceResp, sysResp] = await Promise.all([
          window.barq?.python.request('/analytics/activity?limit=10'),
          window.barq?.python.request('/voice/history?limit=5'),
          window.barq?.python.request('/system/events?limit=5'),
        ])
        if (!mounted) return

        const newEntries: ActivityEntry[] = []

        // Process activity log
        if (actResp && typeof actResp === 'object') {
          const data = actResp as { activities?: BackendActivity[] }
          for (const a of data.activities ?? []) {
            if (a.created_at <= latestActivityTs) break
            if (!latestActivityTs) { latestActivityTs = a.created_at; break }
            newEntries.push({
              id: idRef.current++,
              timestamp: _formatTs(a.created_at),
              type: _activityTypeToEntry(a.type) as ActivityType,
              label: a.action,
              message: a.description || a.action,
              detail: _severityTag(a.severity),
            })
            if (a.created_at > latestActivityTs) latestActivityTs = a.created_at
          }
          const acts = data.activities ?? []
          if (acts.length > 0 && !latestActivityTs) {
            latestActivityTs = acts[0].created_at
          }
        }

        // Process voice history
        if (voiceResp && typeof voiceResp === 'object') {
          const data = voiceResp as { commands?: VoiceHistoryEntry[] }
          for (const c of data.commands ?? []) {
            if (c.created_at <= latestVoiceTs) break
            if (!latestVoiceTs) { latestVoiceTs = c.created_at; break }
            // Set latest voice transcript for the header indicator
            setLatestVoice({ transcript: c.transcript, action: c.action })
            newEntries.push({
              id: idRef.current++,
              timestamp: _formatTs(c.created_at),
              type: 'voice',
              label: c.success ? 'Voice' : 'Voice (failed)',
              message: c.transcript,
              detail: `${c.action} (${Math.round(c.confidence * 100)}%)`,
            })
            if (c.created_at > latestVoiceTs) latestVoiceTs = c.created_at
          }
          const cmds = data.commands ?? []
          if (cmds.length > 0 && !latestVoiceTs) {
            latestVoiceTs = cmds[0].created_at
          }
        }

        // Process system events
        if (sysResp && typeof sysResp === 'object') {
          const data = sysResp as { events?: BackendActivity[] }
          for (const e of data.events ?? []) {
            if (e.created_at <= latestSystemTs) break
            if (!latestSystemTs) { latestSystemTs = e.created_at; break }
            const sev = e.severity === 'error' ? '⚠️ ' : e.severity === 'warn' ? '⚠ ' : ''
            newEntries.push({
              id: idRef.current++,
              timestamp: _formatTs(e.created_at),
              type: 'system' as ActivityType,
              label: e.action,
              message: `${sev}${e.description || e.action}`,
              detail: e.severity !== 'info' ? e.severity : 'system',
            })
            if (e.created_at > latestSystemTs) latestSystemTs = e.created_at
          }
          const events = data.events ?? []
          if (events.length > 0 && !latestSystemTs) {
            latestSystemTs = events[0].created_at
          }
        }

        if (newEntries.length > 0) {
          setLiveCount(prev => prev + newEntries.length)
          setEntries(prev => [...prev, ...newEntries].slice(-50))
        }
      } catch {
        // Backend unavailable — inject weather entry so feed stays alive
        if (!mounted) return
        const ts = new Date()
        const t = `${ts.getHours().toString().padStart(2, '0')}:${ts.getMinutes().toString().padStart(2, '0')}:${ts.getSeconds().toString().padStart(2, '0')}`
        const w = weatherRef.current
        if (w) {
          setEntries(prev => [...prev.slice(-49), {
            id: idRef.current++,
            timestamp: t, type: 'weather' as ActivityType,
            label: w.city,
            message: `${Math.round(w.temperature_c)}°C — ${w.description}`,
            detail: `Humidity: ${w.humidity}% · Wind: ${w.wind_speed}m/s`,
          }].slice(-50))
        } else {
          const fb = WEATHER_FALLBACKS[Math.floor(Math.random() * WEATHER_FALLBACKS.length)]
          setEntries(prev => [...prev.slice(-49), {
            id: idRef.current++,
            timestamp: t, type: 'weather' as ActivityType,
            label: fb.city,
            message: `${fb.temp}°C — ${fb.condition}`,
            detail: `Humidity: ${fb.humidity}% — offline mode`,
          }].slice(-50))
        }
      }
    }

    const interval = setInterval(poll, 3000)
    return () => { mounted = false; clearInterval(interval) }
  }, [backendSeed])

  return { activities: entries, liveCount, latestVoice }
}

function _formatTs(iso: string): string {
  try {
    const d = new Date(iso)
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`
  } catch {
    return '--:--:--'
  }
}

const ACTIVITY_TYPE_MAP: Record<string, string> = {
  voice: 'voice',
  memory: 'chat',
  job: 'chat',
  notification: 'chat',
  social: 'chat',
  analytics: 'chat',
  system: 'system',
}

function _activityTypeToEntry(dbType: string): string {
  return ACTIVITY_TYPE_MAP[dbType] ?? 'chat'
}

function _severityTag(severity: string): string {
  switch (severity) {
    case 'error': return '⚠ error'
    case 'warn': return '! warning'
    default: return ''
  }
}

// ─── Lazy-loaded 3D Particle Sphere ────────────────────────────────────

const ParticleSphere3D = lazy(() =>
  import('../components/ParticleSphere3D').then(mod => ({
    default: mod.ParticleSphere3D
  }))
)

// ─── System Status Threads (dynamic polling) ────────────────────────────

const THREAD_DEFS = [
  { name: 'inference.worker', pid: '0x2A1F' },
  { name: 'audio.capture', pid: '0x3B7E' },
  { name: 'network.poll', pid: '0x4C9D' },
  { name: 'memory.compactor', pid: '0x5D3B' },
  { name: 'vision.processor', pid: '0x6E8F' },
  { name: 'scheduler.daemon', pid: '0x7F1A' },
  { name: 'token.manager', pid: '0x8A2C' },
  { name: 'index.builder', pid: '0x9B4E' },
]

type ThreadStatus = 'RUNNING' | 'IDLE' | 'SLEEP'

interface ThreadState {
  name: string
  pid: string
  status: ThreadStatus
}

function useThreadStatuses(): ThreadState[] {
  const [threads, setThreads] = useState<ThreadState[]>(
    THREAD_DEFS.map(t => ({ ...t, status: 'RUNNING' as ThreadStatus }))
  )

  useEffect(() => {
    const interval = setInterval(() => {
      setThreads(prev => prev.map(t => {
        const roll = Math.random()
        const status: ThreadStatus =
          roll < 0.6 ? 'RUNNING' :
          roll < 0.85 ? 'IDLE' :
          'SLEEP'
        return { ...t, status }
      }))
    }, 3000)
    return () => clearInterval(interval)
  }, [])

  return threads
}

// ─── Main Dashboard Page ───────────────────────────────────────────────

export function DashboardPage(): JSX.Element {
  const sys = useRealSystemData()
  const threads = useThreadStatuses()
  const [displayExecTime, setDisplayExecTime] = useState('0.42')
  const [voiceListening, setVoiceListening] = useState(false)
  const [detectorRunning, setDetectorRunning] = useState(false)
  const [wsConnected, setWsConnected] = useState(false)
  const [aiState, setAiState] = useState<'idle' | 'listening' | 'thinking' | 'responding'>('idle')
  const [audioAmplitude, setAudioAmplitude] = useState(0)
  const [sttText, setSttText] = useState('')  // live interim transcription from STT
  const [sttConfidence, setSttConfidence] = useState(0)  // confidence score 0.0-1.0 from STT
  const [activityFilter, setActivityFilter] = useState<'all' | 'weather' | 'chat' | 'voice' | 'system'>('all')

  // ── Streaming response text (token-by-token for reduced latency) ──
  const [streamingResponse, setStreamingResponse] = useState('')
  const lastSttSentRef = useRef('')

  // Audio element for TTS playback (same pattern as AiChatPanel)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const speakAudio = useCallback((audioBase64: string): void => {
    if (!audioBase64) return
    try {
      // Stop any current playback and revoke old URL to prevent memory leak
      if (audioRef.current) {
        const oldSrc = audioRef.current.src
        audioRef.current.pause()
        if (oldSrc?.startsWith('blob:')) URL.revokeObjectURL(oldSrc)
        audioRef.current = null
      }
      const binaryStr = atob(audioBase64)
      const bytes = new Uint8Array(binaryStr.length)
      for (let i = 0; i < binaryStr.length; i++) {
        bytes[i] = binaryStr.charCodeAt(i)
      }
      const blob = new Blob([bytes], { type: 'audio/mpeg' })
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audio.onended = () => URL.revokeObjectURL(url)
      audioRef.current = audio
      void audio.play()
    } catch {
      // Audio playback unavailable — silently skip
    }
  }, [])

  // Ref for stable callback access inside streaming handlers
  const speakAudioRef = useRef(speakAudio)
  speakAudioRef.current = speakAudio

  const stream = useStreamingChat({
    onToken: (token: string) => {
      setStreamingResponse(prev => prev + token)
    },
    onAudio: (audioBase64: string) => {
      // Play TTS audio as soon as it arrives in the stream
      speakAudioRef.current(audioBase64)
    },
    onComplete: (fullText: string) => {
      // Keep final text visible for a few seconds
      setTimeout(() => setStreamingResponse(''), 6_000)
    },
    onError: () => {
      setStreamingResponse('')
    },
  })

  // Ref for stable access inside effect (avoids re-firing on every render)
  const sendRef = useRef(stream.send)
  sendRef.current = stream.send

  // Cancel stream on unmount
  useEffect(() => {
    return () => { stream.cancel() }
  }, [stream.cancel])

  // Cleanup audio element on unmount (prevents memory leak from blob URLs)
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        const src = audioRef.current.src
        audioRef.current.pause()
        if (src?.startsWith('blob:')) URL.revokeObjectURL(src)
        audioRef.current = null
      }
    }
  }, [])

  // Auto-trigger streaming when user finishes speaking and AI starts processing
  useEffect(() => {
    // When state transitions to 'thinking' and we have NEW STT text from the user
    if (aiState === 'thinking' && sttText && sttText !== lastSttSentRef.current) {
      lastSttSentRef.current = sttText
      setStreamingResponse('')
      sendRef.current(sttText)
    }
    // Clear response when idle
    if (aiState === 'idle') {
      setStreamingResponse('')
    }
  }, [aiState, sttText])

  const weather = useWeatherData()
  const { activities, liveCount, latestVoice } = useRealActivityFeed(weather)
  const {
    cities, weatherMap, selectedCity, setSelectedCity,
    addCity, removeCity, loading: weatherLoading,
  } = useMultiCityWeather()
  const [expandedBlock, setExpandedBlock] = useState<'weather' | 'chat' | 'voice' | 'system' | null>(null)
  const [addingCity, setAddingCity] = useState(false)
  const [newCityInput, setNewCityInput] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const handleAddCity = () => {
    addCity(newCityInput)
    setNewCityInput('')
    setAddingCity(false)
  }
  const { accent } = useTheme()

  // Toggle wake word detector on/off (mute/unmute)
  // Optimistically toggles local state so the UI responds immediately,
  // regardless of WebSocket timing. The next WS message will reconcile
  // if the backend state doesn't match.
  const toggleDetector = useCallback(async () => {
    const wasRunning = detectorRunning
    // Optimistic toggle — instant UI response
    setDetectorRunning(!detectorRunning)
    try {
      if (wasRunning) {
        await window.barq?.python.request('/voice/stop', { method: 'POST' })
      } else {
        await window.barq?.python.request('/voice/start', { method: 'POST' })
      }
    } catch (err) {
      console.error('[Voice] Failed to toggle detector:', err)
      // Revert on failure
      setDetectorRunning(wasRunning)
    }
  }, [detectorRunning])

  // Update execution time
  useEffect(() => {
    if (sys.responseTimeMs > 0) {
      setDisplayExecTime((sys.responseTimeMs / 1000).toFixed(2))
    }
  }, [sys.responseTimeMs])

  // Transient voice transcript display (auto-dismiss 6s)
  const [displayTranscript, setDisplayTranscript] = useState<{ transcript: string; action: string } | null>(null)
  const transcriptTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (latestVoice) {
      setDisplayTranscript(latestVoice)
      if (transcriptTimer.current) clearTimeout(transcriptTimer.current)
      transcriptTimer.current = setTimeout(() => setDisplayTranscript(null), 6_000)
    }
    return () => { if (transcriptTimer.current) clearTimeout(transcriptTimer.current) }
  }, [latestVoice])

  // WebSocket for real-time voice status + mic level (replaces HTTP polling)
  useEffect(() => {
    const WS_URL = 'ws://127.0.0.1:8956/voice/ws/status'
    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let mounted = true

    const connect = () => {
      try {
        ws = new WebSocket(WS_URL)
      } catch (err) {
        console.error('[Voice] WebSocket creation failed:', err)
        reconnectTimer = setTimeout(connect, 2000)
        return
      }

      ws.onopen = () => {
        setWsConnected(true)
        console.log('[Voice] WebSocket connected')
      }

      ws.onmessage = (event) => {
        if (!mounted) return
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'voice_status') {
            setVoiceListening(data.conversation_active ?? false)
            setDetectorRunning(data.is_listening ?? false)
            setAudioAmplitude(data.mic_level ?? 0)
            setSttText(data.stt_text ?? '')
            setSttConfidence(data.stt_confidence ?? 0)

            // Derive AI state from backend status (order matters: most specific first)
            if (data.is_speaking) {
              setAiState('responding')
            } else if (data.is_processing) {
              setAiState('thinking')
            } else if (data.conversation_active) {
              setAiState('listening')
            } else {
              setAiState('idle')
            }
          }
        } catch (err) {
          console.error('[Voice] WebSocket parse error:', err)
        }
      }

      ws.onclose = () => {
        setWsConnected(false)
        if (!mounted) return
        console.log('[Voice] WebSocket disconnected, reconnecting in 2s...')
        reconnectTimer = setTimeout(connect, 2000)
      }

      ws.onerror = () => {
        ws?.close()
      }
    }

    connect()

    return () => {
      mounted = false
      if (ws) {
        ws.onclose = null  // prevent reconnect logic on unmount
        ws.close()
      }
      if (reconnectTimer) clearTimeout(reconnectTimer)
    }
  }, [])

  // Recent (last 2) get highlight
  const latestIds = new Set(activities.slice(-2).map(a => a.id))

  return (
    <div className="h-full w-full bg-black text-zinc-200 overflow-hidden relative font-mono">
      {/* ── Grid floor background ────────────────────────────────── */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(var(--a500-rgb), 0.12) 1px, transparent 1px),
            linear-gradient(90deg, rgba(var(--a500-rgb), 0.12) 1px, transparent 1px)
          `,
          backgroundSize: '48px 48px',
          maskImage: 'linear-gradient(to top, black 10%, transparent 75%)',
          WebkitMaskImage: 'linear-gradient(to top, black 10%, transparent 75%)',
        }}
      />

      {/* ── Grid floor bottom highlight ───────────────────────────── */}
      <div
        className="absolute bottom-0 left-0 right-0 h-1/3 pointer-events-none"
        style={{
          background: `linear-gradient(to top, rgba(var(--a500-rgb), 0.03) 0%, transparent 100%)`,
        }}
      />

      {/* ── HUD corner brackets ───────────────────────────────────── */}
      <div className="absolute top-3 left-3 w-5 h-5 border-l-[1.5px] border-t-[1.5px] pointer-events-none" style={{ borderColor: 'rgba(var(--a500-rgb), 0.15)' }} />
      <div className="absolute top-3 right-3 w-5 h-5 border-r-[1.5px] border-t-[1.5px] pointer-events-none" style={{ borderColor: 'rgba(var(--a500-rgb), 0.15)' }} />
      <div className="absolute bottom-3 left-3 w-5 h-5 border-l-[1.5px] border-b-[1.5px] pointer-events-none" style={{ borderColor: 'rgba(var(--a500-rgb), 0.15)' }} />
      <div className="absolute bottom-3 right-3 w-5 h-5 border-r-[1.5px] border-b-[1.5px] pointer-events-none" style={{ borderColor: 'rgba(var(--a500-rgb), 0.15)' }} />

      <div className="relative z-10 h-full flex flex-col p-4 gap-3">
        {/* ═══ HEADER ═══ */}
        <div className="flex items-center justify-between px-1 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-[26px] h-[26px] rounded-md bg-purple-500/15 flex items-center justify-center border border-purple-500/20">
              <Activity className="w-3.5 h-3.5 text-purple-400" />
            </div>
            <div>
              <h1 className="text-[12px] font-orbitron font-bold tracking-[0.25em] uppercase" style={{ color: 'var(--a200)', filter: 'drop-shadow(0 0 6px rgba(var(--a400-rgb), 0.12))' }}>
                B.A.R.Q AI v2.0
              </h1>
              <p className="text-[9px] font-mono text-zinc-300 tracking-[0.15em]">
                Neural Command Center
              </p>
            </div>
          </div>

          {/* ── Voice Activity Indicator (click to mute/unmute) ── */}
          <button
            onClick={toggleDetector}
            className="flex items-center gap-2 px-3 py-1 rounded-lg bg-zinc-950/60 border border-zinc-800 hover:border-zinc-600 transition-colors cursor-pointer"
            title={detectorRunning ? 'Click to mute microphone' : 'Click to unmute microphone'}
          >
            <div className="relative flex items-center gap-1.5">
              <div className={`relative w-2 h-2 rounded-full transition-all duration-300 ${
                !detectorRunning
                  ? 'bg-red-500/60'
                  : voiceListening
                    ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.7)]'
                    : 'bg-zinc-500'
              }`}>
                {detectorRunning && voiceListening && (
                  <motion.span
                    className="absolute inset-0 rounded-full bg-emerald-400"
                    animate={{ opacity: [0.4, 0.1, 0.4], scale: [1, 1.8, 1] }}
                    transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
                  />
                )}
              </div>
              <div className="flex flex-col">
                <span className={`text-[9px] font-mono tracking-wider uppercase transition-all duration-300 ${
                  !detectorRunning
                    ? 'text-red-400 font-bold'
                    : voiceListening
                      ? 'text-emerald-400 font-bold'
                      : 'text-zinc-300'
                }`}>
                  {!detectorRunning ? 'MUTED' : voiceListening ? 'ON AIR' : 'STANDBY'}
                </span>
                {/* Live interim STT transcript (while user is speaking) */}
                {sttText && (
                  <motion.span
                    key="stt-interim"
                    initial={{ opacity: 0, y: 2 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="text-[8px] font-mono text-cyan-300/90 truncate max-w-[160px] leading-tight mt-0.5"
                    title={sttText}
                  >
                    &ldquo;{sttText}&rdquo;
                  </motion.span>
                )}
                {/* Completed command transcript toast */}
                {!sttText && displayTranscript && (
                  <motion.span
                    key="voice-transcript"
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="text-[8px] font-mono text-pink-300/80 truncate max-w-[140px] leading-tight mt-0.5"
                    title={displayTranscript.transcript}
                  >
                    &ldquo;{displayTranscript.transcript}&rdquo;
                  </motion.span>
                )}
              </div>
            </div>
            <VoiceWaveform isListening={voiceListening} amplitude={audioAmplitude} />
            {/* WebSocket connection indicator */}
            <span
              className={`w-1 h-1 rounded-full transition-all duration-300 ${
                wsConnected
                  ? 'bg-green-500 shadow-[0_0_4px_rgba(34,197,94,0.5)]'
                  : 'bg-red-500/40'
              }`}
              title={wsConnected ? 'WebSocket connected' : 'WebSocket disconnected'}
            />
          </button>

          <DigitalClock />
        </div>

        {/* ═══ 4-COLUMN GRID ═══ */}
        <div className="flex-1 grid grid-cols-4 gap-3 min-h-0">
          {/* ─── LEFT PANEL (1/4): System Vitals ───────────────────── */}
          <div className="flex flex-col gap-3 min-h-0 overflow-y-auto overflow-x-hidden">
            <div className="space-y-3">
              <MetricTile label="CPU Load" value={`${Math.round(sys.cpuPercent)}%`} sparklineData={sys.cpuHistory} />
              <div className="h-px bg-gradient-to-r from-transparent via-purple-500/8 to-transparent" />
              <MetricTile label="Memory" value={`${Math.round(sys.memPercent)}%`} sparklineData={sys.memHistory} />
              <div className="h-px bg-gradient-to-r from-transparent via-purple-500/8 to-transparent" />
              <MetricTile label="Disk" value={`${Math.round(sys.diskPercent)}%`} sparklineData={sys.diskHistory} />
              <div className="h-px bg-gradient-to-r from-transparent via-purple-500/8 to-transparent" />
              <MetricTile label="Memory Used" value={`${sys.memUsedGB.toFixed(1)}GB`} sparklineData={sys.memHistory} />
            </div>

            <div className="mt-auto pt-2 border-t border-purple-500/8">
              <DocumentsChecklist />
            </div>
          </div>

          {/* ─── CENTER PANEL (2/4): AI Core ──────────────────────── */}
          <div className="col-span-2 flex flex-col items-center justify-center min-h-0 relative">
        {/* Ambient glow behind sphere — boosted for brighter core */}
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[540px] h-[540px] rounded-full pointer-events-none"
          style={{
            background: `radial-gradient(circle at center, rgba(var(--a500-rgb),0.07) 0%, rgba(var(--a500-rgb),0.035) 30%, transparent 70%)`,
            maskImage: 'radial-gradient(circle at center, black 80%, transparent 100%)',
            WebkitMaskImage: 'radial-gradient(circle at center, black 80%, transparent 100%)',
          }}
        />

            {/* 3D Sphere + Perspective Grid */}
            <div className="relative flex items-center justify-center">
              <motion.div
                className="absolute w-[420px] h-[420px] rounded-full border-0"
                style={{
                  boxShadow: '0 0 0 0.5px rgba(var(--a500-rgb), 0.2)',
                }}
                animate={{ rotate: 360 }}
                transition={{ duration: 60, repeat: Infinity, ease: 'linear' }}
              />
              <motion.div
                className="absolute w-[400px] h-[400px] rounded-full border-0"
                style={{
                  boxShadow: '0 0 0 0.5px rgba(var(--a500-rgb), 0.12), 0 0 18px rgba(var(--a500-rgb), 0.04)',
                }}
                animate={{ rotate: -360 }}
                transition={{ duration: 45, repeat: Infinity, ease: 'linear' }}
              />

              <Suspense fallback={
                <div className="w-[420px] h-[420px] flex items-center justify-center">
                  <div className="w-8 h-8 border-2 border-purple-500/30 border-t-purple-400 rounded-full animate-spin" />
                </div>
              }>
                <ParticleSphere3D activeTheme={accent} aiState={aiState} audioAmplitude={audioAmplitude} micMuted={!detectorRunning} showGrid sttText={sttText} />
              </Suspense>
            </div>

            {/* ── Live STT Transcript Caption (near the sphere) ──── */}
            {sttText && !streamingResponse && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="text-center mt-1.5 mb-1"
              >
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-500/8 border border-cyan-500/15">
                  <span className="relative flex w-1.5 h-1.5">
                    <span className="animate-ping absolute inset-0 rounded-full bg-cyan-400 opacity-40" />
                    <span className="relative rounded-full w-1.5 h-1.5 bg-cyan-400" />
                  </span>
                  <span className="text-[11px] font-mono text-cyan-300/80 italic max-w-[240px] truncate" title={sttText}>
                    &ldquo;{sttText}&rdquo;
                  </span>
                  {/* Confidence badge */}
                  <span
                    className={`text-[9px] font-mono font-bold tabular-nums ${
                      sttConfidence >= 0.8
                        ? 'text-emerald-400'
                        : sttConfidence >= 0.5
                        ? 'text-amber-400'
                        : 'text-red-400'
                    }`}
                    title={`STT confidence: ${(sttConfidence * 100).toFixed(0)}%`}
                  >
                    {(sttConfidence * 100).toFixed(0)}%
                  </span>
                </div>
              </motion.div>
            )}

            {/* ── Streaming AI Response Text (token-by-token) ────── */}
            {streamingResponse && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="text-center mt-1.5 mb-1 max-w-md mx-auto"
              >
                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-500/8 border border-emerald-500/15">
                  <span className="relative flex w-1.5 h-1.5">
                    <span className="animate-ping absolute inset-0 rounded-full bg-emerald-400 opacity-40" />
                    <span className="relative rounded-full w-1.5 h-1.5 bg-emerald-400" />
                  </span>
                  <span className="text-[11px] font-mono text-emerald-300/90 max-w-[320px] leading-relaxed">
                    {streamingResponse}
                    <span className="inline-block w-1 h-3.5 ml-0.5 bg-emerald-400/70 animate-pulse align-text-bottom" />
                  </span>
                </div>
              </motion.div>
            )}

            {/* ── Task Completion Readout ──────────────────────────── */}
            <div className={`text-center ${sttText ? 'mt-0.5' : 'mt-2'}`}>
              <div className="flex items-center justify-center gap-1.5 mb-1">
                <CheckCircle2 className="w-3 h-3 text-purple-400/70" />
                <span className="text-[10px] font-mono text-purple-400/50 uppercase tracking-[0.2em]">
                  Task Completed
                </span>
              </div>
              <p className="text-sm font-orbitron font-bold text-zinc-100 tracking-wide" style={{ filter: 'drop-shadow(0 0 4px rgba(var(--a400-rgb), 0.08))' }}>
                Compiled local execution environment
              </p>
              <div className="flex items-center justify-center gap-3 mt-1.5">
                <span className="text-[10px] font-mono text-zinc-300 tracking-[0.1em]">
                  EXECUTION TIME: <span className="text-purple-300/80">{displayExecTime}s</span>
                </span>
                <span className="text-zinc-500">|</span>
                <span className="text-[10px] font-mono text-zinc-300 tracking-[0.1em]">
                  MEM: <span className="text-purple-300/80">24MB</span>
                </span>
                <span className="text-zinc-500">|</span>
                <span className="text-[10px] font-mono text-zinc-300 tracking-[0.1em]">
                  EXIT: <span className="text-emerald-400/70">0x00</span>
                </span>
              </div>
            </div>

            {/* ── Module indicator dots ────────────────────────────── */}
            <div className="flex items-center justify-center gap-4 mt-2.5">
              {[
                { name: 'CORE', active: true },
                { name: 'VISION', active: true },
                { name: 'AUDIO', active: false },
                { name: 'SCHED', active: true },
              ].map(mod => (
                <div key={mod.name} className="flex items-center gap-1.5">
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${mod.active ? 'bg-purple-400/70 shadow-[0_0_5px_rgba(168,85,247,0.4)]' : 'bg-zinc-600'}`}
                  />
                  <span className={`text-[8px] font-mono tracking-wider ${mod.active ? 'text-purple-400/50' : 'text-zinc-400'}`}>
                    {mod.name}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* ─── RIGHT PANEL (1/4): Square Activity Blocks ────────── */}
          <div className="flex flex-col gap-2 min-h-0">
            {/* ── Header with filter buttons ── */}
            <div className="flex items-center justify-between shrink-0">
              <div className="flex items-center gap-1.5">
                <Terminal className="w-3 h-3 text-purple-400/70" />
                <div className="flex items-center gap-0.5 bg-zinc-950/60 border border-zinc-800 rounded-md p-0.5">
                  {(['all', 'weather', 'chat', 'voice', 'system'] as const).map(f => (
                    <button
                      key={f}
                      onClick={() => setActivityFilter(f)}
                      className={`px-1.5 py-0.5 text-[7px] font-mono uppercase tracking-wider rounded transition-all duration-150 ${
                        activityFilter === f
                          ? 'bg-purple-500/15 text-purple-300 border border-purple-500/20'
                          : 'text-zinc-300 hover:text-zinc-100 border border-transparent'
                      }`}
                    >
                      {f === 'all' ? 'All' : f}
                    </button>
                  ))}
                </div>
              </div>
              <span className="text-[8px] font-mono text-zinc-300 tabular-nums">{liveCount > 0 ? `${liveCount} new` : ''}</span>
            </div>

            {/* ── Filtered Square Activity Blocks ── */}
            <div className={`flex-1 grid gap-1.5 min-h-0 ${activityFilter === 'all' ? 'grid-rows-4' : 'grid-rows-1'}`}>
              {/* ═══ WEATHER BLOCK ═══ */}
              {(activityFilter === 'all' || activityFilter === 'weather') && (
                <motion.div
                  layout
                  whileHover={{ scale: 1.008, borderColor: 'rgba(6,182,212,0.18)', boxShadow: '0 0 14px rgba(6,182,212,0.03)' }}
                  onClick={() => setExpandedBlock(expandedBlock === 'weather' ? null : 'weather')}
                  className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-2.5 overflow-hidden flex flex-col min-h-0 cursor-pointer transition-colors"
                >
                  {/* Header */}
                  <div className="flex items-center justify-between mb-1.5 shrink-0">
                    <div className="flex items-center gap-1.5">
                      <Cloud className="w-3 h-3 text-cyan-400/70" />
                      <span className="text-[8px] font-mono text-cyan-400/50 uppercase tracking-wider font-semibold">Weather</span>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); setAddingCity(true); setTimeout(() => inputRef.current?.focus(), 50) }}
                      className="flex items-center gap-0.5 px-1.5 py-0.5 text-[7px] font-mono uppercase tracking-wider rounded
                        text-cyan-400/60 hover:text-cyan-300 border border-cyan-500/10 hover:border-cyan-500/30 transition-all"
                    >
                      <Plus className="w-2.5 h-2.5" /> Add
                    </button>
                  </div>

                  {/* City chips */}
                  <div className="flex items-center gap-1 overflow-x-auto shrink-0 pb-1 scrollbar-none">
                    {cities.map(city => (
                      <div key={city} className="flex items-center gap-0.5 shrink-0">
                        <button
                          onClick={(e) => { e.stopPropagation(); setSelectedCity(city) }}
                          className={`px-1.5 py-0.5 text-[7px] font-mono uppercase tracking-wider rounded transition-all ${
                            selectedCity === city
                              ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/20'
                              : 'text-zinc-300 hover:text-zinc-100 border border-transparent'
                          }`}
                        >
                          {city}
                        </button>
                        {cities.length > 1 && (
                          <button
                            onClick={(e) => { e.stopPropagation(); removeCity(city) }}
                            className="p-0.5 rounded text-zinc-400 hover:text-red-400 hover:bg-red-500/10 transition-all"
                          >
                            <X className="w-2 h-2" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Add city input */}
                  {addingCity && (
                    <div onClick={(e) => e.stopPropagation()} className="flex items-center gap-1 mb-1 shrink-0">
                      <input
                        ref={inputRef}
                        type="text"
                        value={newCityInput}
                        onChange={e => setNewCityInput(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter' && newCityInput.trim()) handleAddCity(); if (e.key === 'Escape') { setAddingCity(false); setNewCityInput('') } }}
                        placeholder="City name..."
                        className="flex-1 px-1.5 py-0.5 text-[8px] font-mono bg-zinc-900 border border-zinc-700 rounded
                          text-zinc-300 placeholder-zinc-600 outline-none focus:border-cyan-500/40 transition-colors"
                      />
                      <button
                        onClick={(e) => { e.stopPropagation(); handleAddCity() }}
                        disabled={!newCityInput.trim()}
                        className="px-1.5 py-0.5 text-[7px] font-mono bg-cyan-500/20 text-cyan-300 rounded
                          border border-cyan-500/20 hover:bg-cyan-500/30 transition-all disabled:opacity-30"
                      >
                        Add
                      </button>
                    </div>
                  )}

                  {/* Detail view */}
                  <div className="flex-1 flex flex-col justify-center min-h-0">
                    {(() => {
                      const w = weatherMap.get(selectedCity)
                      if (w) {
                        return (
                          <>
                            <div className="flex items-baseline gap-1.5">
                              <span className="text-2xl font-orbitron font-bold text-zinc-100 tabular-nums">
                                {Math.round(w.temperature_c)}°
                              </span>
                              <span className="text-[9px] font-mono text-zinc-300 uppercase">{w.city}</span>
                            </div>
                            <p className="text-[10px] font-mono text-zinc-400 mt-0.5 capitalize">{w.description}</p>
                            <div className="flex items-center gap-2 mt-1 text-[8px] font-mono text-zinc-300">
                              <span>Humidity: {w.humidity}%</span>
                              <span className="text-zinc-500">|</span>
                              <span>Feels {Math.round(w.feels_like_c)}°</span>
                              <span className="text-zinc-500">|</span>
                              <span>Wind: {w.wind_speed}m/s</span>
                            </div>
                            {/* Expanded extras */}
                            {expandedBlock === 'weather' && (
                              <motion.div
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                transition={{ duration: 0.2 }}
                                className="mt-1.5 pt-1.5 border-t border-zinc-800/60 space-y-0.5"
                              >
                                <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[7px] font-mono">
                                  <span className="text-zinc-400">Visibility</span>
                                  <span className="text-zinc-400 text-right">{w.visibility >= 1000 ? `${(w.visibility / 1000).toFixed(1)} km` : `${w.visibility} m`}</span>
                                  <span className="text-zinc-400">Country</span>
                                  <span className="text-zinc-400 text-right">{w.country || '—'}</span>
                                  <span className="text-zinc-400">Wind</span>
                                  <span className="text-zinc-400 text-right">{w.wind_speed} m/s</span>
                                  <span className="text-zinc-400">Feels like</span>
                                  <span className="text-zinc-400 text-right">{Math.round(w.feels_like_c)}°C</span>
                                </div>
                                <p className="text-[6px] text-zinc-500 text-center mt-1">Click to collapse</p>
                              </motion.div>
                            )}
                          </>
                        )
                      }
                      if (weatherLoading) {
                        return (
                          <div className="flex-1 flex items-center justify-center">
                            <div className="w-3 h-3 border border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin" />
                          </div>
                        )
                      }
                      // Fallback to activity feed weather
                      const latestFeed = activities.filter(a => a.type === 'weather').slice(-1)[0]
                      if (latestFeed) {
                        return (
                          <>
                            <div className="flex items-baseline gap-1.5">
                              <span className="text-2xl font-orbitron font-bold text-zinc-100 tabular-nums">
                                {latestFeed.message.split(' — ')[0]}
                              </span>
                              <span className="text-[9px] font-mono text-zinc-300 uppercase">{latestFeed.label}</span>
                            </div>
                            <p className="text-[10px] font-mono text-zinc-400 mt-0.5 capitalize">
                              {latestFeed.message.includes('—') ? latestFeed.message.split('—')[1]?.trim() : latestFeed.message}
                            </p>
                            <p className="text-[8px] font-mono text-zinc-300 mt-1 truncate">{latestFeed.detail}</p>
                          </>
                        )
                      }
                      return (
                        <div className="flex-1 flex items-center justify-center">
                          <span className="text-[9px] text-zinc-400">No data</span>
                        </div>
                      )
                    })()}
                  </div>
                </motion.div>
              )}

              {/* ═══ CHAT BLOCK ═══ */}
              {(activityFilter === 'all' || activityFilter === 'chat') && (
                <motion.div
                  layout
                  whileHover={{ scale: 1.008, borderColor: 'rgba(168,85,247,0.18)', boxShadow: '0 0 14px rgba(168,85,247,0.03)' }}
                  onClick={() => setExpandedBlock(expandedBlock === 'chat' ? null : 'chat')}
                  className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-2.5 overflow-hidden flex flex-col min-h-0 cursor-pointer"
                >
                  <div className="flex items-center gap-1.5 mb-1.5 shrink-0">
                    <MessageCircle className="w-3 h-3 text-purple-400/70" />
                    <span className="text-[8px] font-mono text-purple-400/50 uppercase tracking-wider font-semibold">Chat</span>
                  </div>
                  <div className="flex-1 overflow-y-auto space-y-1 min-h-0">
                    {(() => {
                      const chatItems = activities.filter(a => a.type === 'chat')
                      const count = expandedBlock === 'chat' ? 20 : 5
                      const items = chatItems.slice(-count).reverse()
                      return items.map(entry => (
                        <div key={entry.id} className="text-[7px] font-mono leading-[1.3]">
                          <div className="flex items-center gap-1">
                            <span className="text-zinc-400 shrink-0 tabular-nums">{entry.timestamp}</span>
                            <span className="font-semibold text-zinc-400 truncate">{entry.label}</span>
                          </div>
                          <p className={expandedBlock === 'chat' ? 'text-zinc-300' : 'text-zinc-300 truncate'}>{entry.message}</p>
                          {entry.detail && <p className="text-zinc-400 truncate">{entry.detail}</p>}
                        </div>
                      ))
                    })()}
                    {activities.filter(a => a.type === 'chat').length === 0 && (
                      <div className="flex items-center justify-center h-full">
                        <span className="text-[9px] text-zinc-400">No messages</span>
                      </div>
                    )}
                    {/* Expand indicator */}
                    {expandedBlock === 'chat' && activities.filter(a => a.type === 'chat').length > 5 && (
                      <p className="text-[6px] text-zinc-500 text-center pt-1">Click to collapse</p>
                    )}
                    {expandedBlock !== 'chat' && activities.filter(a => a.type === 'chat').length > 5 && (
                      <p className="text-[6px] text-zinc-500 text-center pt-0.5">+{activities.filter(a => a.type === 'chat').length - 5} more &middot; Click to expand</p>
                    )}
                  </div>
                </motion.div>
              )}

              {/* ═══ VOICE BLOCK ═══ */}
              {(activityFilter === 'all' || activityFilter === 'voice') && (
                <motion.div
                  layout
                  whileHover={{ scale: 1.008, borderColor: 'rgba(244,114,182,0.18)', boxShadow: '0 0 14px rgba(244,114,182,0.03)' }}
                  onClick={() => setExpandedBlock(expandedBlock === 'voice' ? null : 'voice')}
                  className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-2.5 overflow-hidden flex flex-col min-h-0 cursor-pointer"
                >
                  <div className="flex items-center gap-1.5 mb-1.5 shrink-0">
                    <Mic className="w-3 h-3 text-pink-400/70" />
                    <span className="text-[8px] font-mono text-pink-400/50 uppercase tracking-wider font-semibold">Voice</span>
                  </div>
                  <div className="flex-1 overflow-y-auto space-y-1 min-h-0">
                    {(() => {
                      const voiceItems = activities.filter(a => a.type === 'voice')
                      const count = expandedBlock === 'voice' ? 20 : 5
                      const items = voiceItems.slice(-count).reverse()
                      return items.map(entry => {
                        const isLatest = latestIds.has(entry.id)
                        return (
                          <div key={entry.id} className={`text-[7px] font-mono leading-[1.3]`}>
                            <div className="flex items-center gap-1">
                              <span className={`w-1 h-1 rounded-full shrink-0 ${isLatest ? 'bg-pink-400/60 shadow-[0_0_4px_rgba(244,114,182,0.4)]' : 'bg-zinc-700'}`} />
                              <span className="text-zinc-400 shrink-0 tabular-nums">{entry.timestamp}</span>
                              <span className={`font-semibold truncate ${isLatest ? 'text-pink-300' : 'text-zinc-400'}`}>{entry.label}</span>
                            </div>
                            <p className={expandedBlock === 'voice' && isLatest ? 'text-zinc-300' : expandedBlock === 'voice' ? 'text-zinc-300' : 'text-zinc-300 truncate'}>{entry.message}</p>
                            {entry.detail && <p className="text-zinc-400 truncate">{entry.detail}</p>}
                          </div>
                        )
                      })
                    })()}
                    {activities.filter(a => a.type === 'voice').length === 0 && (
                      <div className="flex items-center justify-center h-full">
                        <span className="text-[9px] text-zinc-400">No commands</span>
                      </div>
                    )}
                    {expandedBlock === 'voice' && activities.filter(a => a.type === 'voice').length > 5 && (
                      <p className="text-[6px] text-zinc-500 text-center pt-1">Click to collapse</p>
                    )}
                    {expandedBlock !== 'voice' && activities.filter(a => a.type === 'voice').length > 5 && (
                      <p className="text-[6px] text-zinc-500 text-center pt-0.5">+{activities.filter(a => a.type === 'voice').length - 5} more &middot; Click to expand</p>
                    )}
                  </div>
                </motion.div>
              )}

              {/* ═══ SYSTEM BLOCK ═══ */}
              {(activityFilter === 'all' || activityFilter === 'system') && (
                <motion.div
                  layout
                  whileHover={{ scale: 1.008, borderColor: 'rgba(245,158,11,0.18)', boxShadow: '0 0 14px rgba(245,158,11,0.03)' }}
                  onClick={() => setExpandedBlock(expandedBlock === 'system' ? null : 'system')}
                  className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-2.5 overflow-hidden flex flex-col min-h-0 cursor-pointer"
                >
                  <div className="flex items-center gap-1.5 mb-1.5 shrink-0">
                    <Radio className="w-3 h-3 text-amber-400/70" />
                    <span className="text-[8px] font-mono text-amber-400/50 uppercase tracking-wider font-semibold">System</span>
                  </div>
                  <div className="flex-1 overflow-y-auto space-y-1 min-h-0">
                    {(() => {
                      const sysItems = activities.filter(a => a.type === 'system')
                      const count = expandedBlock === 'system' ? 20 : 5
                      const items = sysItems.slice(-count).reverse()
                      return items.map(entry => (
                        <div key={entry.id} className="text-[7px] font-mono leading-[1.3]">
                          <div className="flex items-center gap-1">
                            <span className="text-zinc-400 shrink-0 tabular-nums">{entry.timestamp}</span>
                            <span className="font-semibold text-zinc-400 truncate">{entry.label}</span>
                          </div>
                          <p className={expandedBlock === 'system' ? 'text-zinc-300' : 'text-zinc-300 truncate'}>{entry.message}</p>
                          {entry.detail && <p className="text-zinc-400 truncate">{entry.detail}</p>}
                        </div>
                      ))
                    })()}
                    {activities.filter(a => a.type === 'system').length === 0 && (
                      <div className="flex items-center justify-center h-full">
                        <span className="text-[9px] text-zinc-400">No events</span>
                      </div>
                    )}
                    {expandedBlock === 'system' && activities.filter(a => a.type === 'system').length > 5 && (
                      <p className="text-[6px] text-zinc-500 text-center pt-1">Click to collapse</p>
                    )}
                    {expandedBlock !== 'system' && activities.filter(a => a.type === 'system').length > 5 && (
                      <p className="text-[6px] text-zinc-500 text-center pt-0.5">+{activities.filter(a => a.type === 'system').length - 5} more &middot; Click to expand</p>
                    )}
                  </div>
                </motion.div>
              )}
            </div>

            {/* System Status Grid */}
            <div className="shrink-0 border-t border-purple-500/8 pt-1.5 mt-0.5">
              <div className="flex items-center gap-2 mb-1">
                <Radio className="w-2.5 h-2.5 text-purple-400/50" />
                <span className="text-[7px] font-mono text-purple-400/50 uppercase tracking-[0.2em] font-semibold">
                  Threads
                </span>
              </div>
              <div className="grid grid-cols-2 gap-x-2 gap-y-0.5">
                {threads.map((thread) => (
                  <div key={thread.name} className="flex items-center gap-1 group">
                    <span
                      className={`w-1 h-1 rounded-full shrink-0 ${
                        thread.status === 'RUNNING'
                          ? 'bg-purple-400/60 shadow-[0_0_3px_rgba(168,85,247,0.25)]'
                          : thread.status === 'IDLE'
                          ? 'bg-zinc-500'
                          : 'bg-zinc-600'
                      }`}
                    />
                    <span className="text-[7px] font-mono text-zinc-300 truncate group-hover:text-zinc-100 transition-colors">
                      {thread.name}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Mock AI State Control Panel ────────────────────────── */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-4 py-2 rounded-lg bg-zinc-950/80 border border-zinc-800 backdrop-blur-sm">
        <div className="flex items-center gap-1">
          {(['idle', 'listening', 'thinking', 'responding'] as const).map(s => (
            <button
              key={s}
              onClick={() => setAiState(s)}
              className={`px-2 py-1 text-[9px] font-mono uppercase tracking-wider rounded transition-all duration-150 ${
                aiState === s
                  ? s === 'idle' ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                  : s === 'listening' ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                  : s === 'thinking' ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                  : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                : 'text-zinc-300 hover:text-zinc-100 border border-transparent'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        <div className="w-px h-6 bg-zinc-800" />
        <div className="flex items-center gap-2">
          <span className="text-[8px] font-mono text-zinc-300 uppercase tracking-wider">Amp</span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={audioAmplitude}
            onChange={e => setAudioAmplitude(parseFloat(e.target.value))}
            className="w-20 h-1 accent-cyan-400 cursor-pointer"
          />
          <span className="text-[9px] font-mono text-zinc-400 tabular-nums w-8 text-right">
            {audioAmplitude.toFixed(2)}
          </span>
        </div>
      </div>
    </div>
  )
}
