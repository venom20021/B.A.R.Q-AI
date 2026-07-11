import { Suspense, useState, useEffect, useRef, useCallback, lazy, useMemo } from 'react'
import type { MutableRefObject } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Cloud, Mic, MicOff, Bot, User, ArrowLeft, Send, Loader2,
} from 'lucide-react'
import { Vector3 } from 'three'

import { LiveCaptions } from '../components/LiveCaptions'

// ─── User Name ─────────────────────────────────────────────────────────

const USER_NAME_KEY = 'barq_user_name'
const DEFAULT_USER_NAME = ''

function getStoredUserName(): string {
  try { return localStorage.getItem(USER_NAME_KEY) || DEFAULT_USER_NAME } catch { return DEFAULT_USER_NAME }
}

// ─── Lazy-loaded Agent Node Network ────────────────────────────────────

const ParticleSphere3D = lazy(() =>
  import('../components/ParticleSphere3D').then(mod => ({ default: mod.ParticleSphere3D }))
)

// ─── Real Weather Data ─────────────────────────────────────────────────

interface WeatherData { city: string; temperature_c: number; feels_like_c: number; humidity: number; description: string }

const DEFAULT_WEATHER_CITY = 'London'
const WEATHER_RETRY_MS = [1000, 3000, 8000] // backoff intervals

async function fetchWeatherFromBridge(city: string): Promise<WeatherData | null> {
  const resp = await window.barq?.python.request(
    `/web/weather?city=${encodeURIComponent(city)}`,
  )
  if (!resp || typeof resp !== 'object') return null

  const w = resp as Record<string, unknown>

  // Backend unavailable responses
  if (w.status === 'unconfigured' || w.status === 'unavailable') {
    console.warn('[Weather] Backend unavailable:', w.status, w.message || '')
    return null
  }

  // Validate required field
  if (w.temperature_c == null) {
    console.warn('[Weather] Missing temperature_c in response', w)
    return null
  }

  return {
    city: (w.city as string) ?? city,
    temperature_c: w.temperature_c as number,
    feels_like_c: (w.feels_like_c as number) ?? 0,
    humidity: (w.humidity as number) ?? 0,
    description: (w.description as string) ?? '',
  }
}

function useWeatherData(): WeatherData | null {
  const [data, setData] = useState<WeatherData | null>(null)
  const cityRef = useRef<string>(DEFAULT_WEATHER_CITY)

  useEffect(() => {
    let mounted = true
    let retryCount = 0
    let retryTimer: ReturnType<typeof setTimeout> | null = null

    const attemptFetch = async () => {
      try {
        // 1. Resolve city from voice status (fallback to DEFAULT)
        let city = DEFAULT_WEATHER_CITY
        try {
          const statusResp = await window.barq?.python.request('/voice/status')
          if (statusResp && typeof statusResp === 'object') {
            const s = statusResp as { weather_city?: string }
            if (s.weather_city) city = s.weather_city
          }
        } catch (err) {
          console.warn('[Weather] Failed to get city from voice status, using default:', DEFAULT_WEATHER_CITY, err)
        }

        cityRef.current = city // store for interval refresh

        // 2. Fetch weather data
        const weatherData = await fetchWeatherFromBridge(city)
        if (!mounted) return

        if (weatherData) {
          setData(weatherData)
          retryCount = 0 // success — reset retries
          console.log('[Weather] Loaded:', weatherData.city, weatherData.temperature_c + '°C', weatherData.description)
        } else {
          // No data — schedule retry if we haven't exhausted attempts
          if (retryCount < WEATHER_RETRY_MS.length) {
            const delay = WEATHER_RETRY_MS[retryCount]
            retryCount++
            console.warn(`[Weather] Fetch returned no data, retry ${retryCount}/${WEATHER_RETRY_MS.length} in ${delay}ms`)
            retryTimer = setTimeout(attemptFetch, delay)
          } else {
            console.warn('[Weather] All retries exhausted — weather unavailable')
          }
        }
      } catch (err) {
        console.error('[Weather] Fetch error:', err)
        if (retryCount < WEATHER_RETRY_MS.length && mounted) {
          const delay = WEATHER_RETRY_MS[retryCount]
          retryCount++
          retryTimer = setTimeout(attemptFetch, delay)
        }
      }
    }

    attemptFetch()

    // Periodic refresh every 5 minutes — uses cityRef to avoid stale closure
    const interval = setInterval(async () => {
      try {
        const city = cityRef.current
        const weatherData = await fetchWeatherFromBridge(city)
        if (mounted && weatherData) {
          setData(weatherData)
        }
      } catch {
        // silent on interval — retry next cycle
      }
    }, 300_000)

    return () => {
      mounted = false
      clearInterval(interval)
      if (retryTimer) clearTimeout(retryTimer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return data
}

// ─── Greeting Helpers ─────────────────────────────────────────────────

function getGreeting(name: string): string {
  const hour = new Date().getHours()
  const timeGreeting = hour < 12 ? 'GOOD MORNING' : hour < 17 ? 'GOOD AFTERNOON' : 'GOOD EVENING'
  return name ? `${timeGreeting}, ${name.toUpperCase()}` : timeGreeting
}
function getGreetingForDisplay(sttText: string, responseText: string, aiState: string, userName: string): string {
  if (sttText) return 'LISTENING'
  if (responseText) return 'RESPONDING'
  if (aiState === 'thinking') return 'THINKING'
  return getGreeting(userName)
}
function getSubGreeting(sttText: string, responseText: string, aiState: string, weather: WeatherData | null): string {
  if (sttText) return `"${sttText}"`
  if (responseText) return responseText.length > 50 ? responseText.slice(0, 50) + '…' : responseText
  if (aiState === 'thinking') return 'Processing your request…'
  if (weather) return `${weather.city} · ${weather.description}`
  return 'BARQ is ready'
}

// ─── Types ─────────────────────────────────────────────────────────────

interface AgentChatMessage { role: 'user' | 'assistant'; content: string }

// ─── CSS Audio Waveform ────────────────────────────────────────────────

function AudioWaveformBars({ isActive }: { isActive: boolean }): JSX.Element {
  return (
    <div className="flex items-center gap-[3px] h-5">
      {[1, 2, 3, 4, 5, 4, 3, 2, 1].map((h, i) => (
        <motion.span key={i} className={`w-[3px] rounded-full ${isActive ? 'bg-cyan-400' : 'bg-white/20'}`}
          animate={isActive ? { height: [4, 4 + h * 4, 4], opacity: [0.3, 1, 0.3] } : { height: 4, opacity: 0.2 }}
          transition={{ duration: 0.8 + i * 0.05, repeat: Infinity, ease: 'easeInOut', delay: i * 0.06 }}
        />
      ))}
    </div>
  )
}

// ─── Main Dashboard Page ───────────────────────────────────────────────

export function DashboardPage(): JSX.Element {
  const [voiceListening, setVoiceListening] = useState(false)
  const [detectorRunning, setDetectorRunning] = useState(false)
  const [wsConnected, setWsConnected] = useState(false)
  const [aiState, setAiState] = useState<'idle' | 'listening' | 'thinking' | 'responding'>('idle')
  const [sttText, setSttText] = useState('')
  const [responseText, setResponseText] = useState('')
  const [userName, setUserName] = useState(getStoredUserName)

  // ── Clickable agent node state ───────────────────────────────────
  const [activeAgent, setActiveAgent] = useState<string | null>(null)
  const focusTargetRef = useRef<Vector3 | null>(null) as MutableRefObject<Vector3 | null>

  const AGENT_COLORS: Record<string, string> = {
    Strategist: '#00E5FF', Researcher: '#A855F7', 'Chief of Staff': '#FBBF24',
    Finance: '#34D399', Memory: '#F472B6', Vision: '#60A5FA', Analytics: '#FB923C', Coding: '#2DD4BF',
  }
  const activeAgentColor = useMemo(
    () => (activeAgent ? AGENT_COLORS[activeAgent] : '#00E5FF') ?? '#00E5FF', [activeAgent],
  )

  const onSelectAgent = useCallback((label: string) => { setActiveAgent(label) }, [])
  const onReturnToCore = useCallback(() => {
    setActiveAgent(null)
    setActiveRadialMenu(null)
    focusTargetRef.current = null
  }, [])

  // ── Agent chat state ─────────────────────────────────────────────
  const [agentHistory, setAgentHistory] = useState<Record<string, AgentChatMessage[]>>({})
  const currentMessages: AgentChatMessage[] = activeAgent ? (agentHistory[activeAgent] ?? []) : []
  const [agentInput, setAgentInput] = useState('')
  const [agentLoading, setAgentLoading] = useState(false)
  const agentInputRef = useRef<HTMLTextAreaElement>(null!)
  const agentInputRefValue = useRef('')
  const messagesEndRef = useRef<HTMLDivElement>(null!)

  useEffect(() => { agentInputRefValue.current = agentInput }, [agentInput])
  useEffect(() => { if (activeAgent) { const timer = setTimeout(() => agentInputRef.current?.focus(), 350); return () => clearTimeout(timer) } }, [activeAgent])
  useEffect(() => { if (messagesEndRef.current) messagesEndRef.current.scrollTop = messagesEndRef.current.scrollHeight }, [currentMessages, agentLoading])

  const sendAgentMessage = useCallback(async () => {
    const text = agentInputRefValue.current.trim()
    if (!text || !activeAgent || agentLoading) return
    setAgentInput('')
    setAgentHistory(prev => ({ ...prev, [activeAgent]: [...(prev[activeAgent] ?? []), { role: 'user' as const, content: text }] }))
    setAgentLoading(true)
    try {
      const resp = await window.barq?.python.request('/agent/execute', { goal: `[${activeAgent}] ${text}` })
      const result = resp && typeof resp === 'object' ? (resp as Record<string, unknown>).result ?? (resp as Record<string, unknown>).detail ?? 'No response' : String(resp ?? 'No response')
      setAgentHistory(prev => ({ ...prev, [activeAgent]: [...(prev[activeAgent] ?? []), { role: 'assistant' as const, content: String(result) }] }))
    } catch {
      setAgentHistory(prev => ({ ...prev, [activeAgent]: [...(prev[activeAgent] ?? []), { role: 'assistant' as const, content: 'Failed to reach agent. Is the backend running?' }] }))
    } finally { setAgentLoading(false) }
  }, [activeAgent, agentLoading])

  const weather = useWeatherData()

  // ── Listen for profile updates ───────────────────────────────────
  useEffect(() => {
    const handler = (): void => { setUserName(getStoredUserName()) }
    window.addEventListener('barq:profile-updated', handler)
    return () => window.removeEventListener('barq:profile-updated', handler)
  }, [])

  // ── Greeting ─────────────────────────────────────────────────────
  const greeting = getGreetingForDisplay(sttText, responseText, aiState, userName)
  const subGreeting = getSubGreeting(sttText, responseText, aiState, weather)

  // ── Voice detector ───────────────────────────────────────────────
  const toggleDetector = useCallback(async () => {
    const wasRunning = detectorRunning
    setDetectorRunning(!detectorRunning)
    try {
      if (wasRunning) await window.barq?.python.request('/voice/stop', { method: 'POST' })
      else await window.barq?.python.request('/voice/start', { method: 'POST' })
    } catch { setDetectorRunning(wasRunning) }
  }, [detectorRunning])

  // ── WebSocket ────────────────────────────────────────────────────
  useEffect(() => {
    const WS_URL = 'ws://127.0.0.1:8970/voice/ws/status'
    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let httpPollTimer: ReturnType<typeof setTimeout> | null = null
    let wsFailedAt: number | null = null
    let mounted = true

    const applyStatus = (data: Record<string, unknown>) => {
      setVoiceListening(Boolean(data.conversation_active))
      setDetectorRunning(Boolean(data.is_listening))
      setSttText((data.stt_text as string) ?? '')
      setResponseText((data.response_text as string) ?? '')
      if (data.is_speaking) setAiState('responding')
      else if (data.is_processing) setAiState('thinking')
      else if (data.conversation_active) setAiState('listening')
      else setAiState('idle')
      window.dispatchEvent(new CustomEvent('barq:voice-status', { detail: { conversation_active: Boolean(data.conversation_active), is_listening: Boolean(data.is_listening), is_speaking: Boolean(data.is_speaking), is_processing: Boolean(data.is_processing), language: data.language ?? 'en', tts_voice: data.tts_voice ?? 'en-US-JennyNeural' } }))
    }

    const startHttpPoll = () => {
      if (httpPollTimer) return
      const poll = async () => {
        if (!mounted) return
        try { const resp = await window.barq?.python.request('/voice/status'); if (resp && typeof resp === 'object' && !mounted) return; if (resp && typeof resp === 'object') applyStatus(resp as Record<string, unknown>) } catch { /* */ }
        if (mounted) httpPollTimer = setTimeout(poll, 2000)
      }
      poll()
    }

    const connect = () => {
      try { ws = new WebSocket(WS_URL); wsFailedAt = null } catch {
        if (!wsFailedAt) wsFailedAt = Date.now()
        if (wsFailedAt && Date.now() - wsFailedAt > 5000) startHttpPoll()
        reconnectTimer = setTimeout(connect, 2000); return
      }
      ws.onopen = () => { setWsConnected(true); wsFailedAt = null; if (httpPollTimer) { clearTimeout(httpPollTimer); httpPollTimer = null } }
      ws.onmessage = (event) => { if (!mounted) return; try { const data = JSON.parse(event.data); if (data.type === 'voice_status') applyStatus(data) } catch { /* */ } }
      ws.onclose = () => { setWsConnected(false); if (!mounted) return; if (!wsFailedAt) wsFailedAt = Date.now(); if (Date.now() - wsFailedAt > 5000) startHttpPoll(); reconnectTimer = setTimeout(connect, 2000) }
      ws.onerror = () => { ws?.close() }
    }

    connect()
    return () => { mounted = false; if (ws) { ws.onclose = null; ws.close() }; if (reconnectTimer) clearTimeout(reconnectTimer); if (httpPollTimer) clearTimeout(httpPollTimer) }
  }, [])

  // ═══════════════════════════════════════════════════════════════════
  //  GLOBAL STATE: systemLoad, drag-drop, radial menu, transfers
  // ═══════════════════════════════════════════════════════════════════

  const [systemLoad, setSystemLoad] = useState(35)
  const [isDraggingFile, setIsDraggingFile] = useState(false)
  const [activeRadialMenu, setActiveRadialMenu] = useState<string | null>(null)
  const [activeTransfers, setActiveTransfers] = useState<{ id: string; from: [number, number, number]; to: [number, number, number]; color: string; progress: number }[]>([])

  // ── Simulate system load oscillation ──────────────────────────────
  useEffect(() => {
    const interval = setInterval(() => {
      setSystemLoad(prev => {
        const delta = (Math.random() - 0.5) * 20
        return Math.max(5, Math.min(95, prev + delta))
      })
    }, 3000)
    return () => clearInterval(interval)
  }, [])

  // ── Simulate periodic data transfer sparks ───────────────────────
  useEffect(() => {
    const interval = setInterval(() => {
      const randomNode = AGENT_COLORS_KEYS[Math.floor(Math.random() * AGENT_COLORS_KEYS.length)]
      const nodeData = AGENT_NODES_LIST.find(n => n.label === randomNode)
      if (!nodeData) return
      const sparkId = `spark-${Date.now()}`
      const color = nodeData.color
      setActiveTransfers(prev => [...prev, { id: sparkId, from: [0, 0, 0], to: nodeData.position, color, progress: 0 }])
      // Animate progress to 1 over 1.5s
      const startTime = performance.now()
      const animFrame = () => {
        const elapsed = performance.now() - startTime
        const progress = Math.min(elapsed / 1500, 1)
        setActiveTransfers(prev => prev.map(s => s.id === sparkId ? { ...s, progress } : s))
        if (progress < 1) requestAnimationFrame(animFrame)
        else {
          // Remove spark after completion
          setActiveTransfers(prev => prev.filter(s => s.id !== sparkId))
        }
      }
      requestAnimationFrame(animFrame)
    }, 4000)
    return () => clearInterval(interval)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── Radial menu handlers ─────────────────────────────────────────
  const onContextMenu = useCallback((label: string) => {
    setActiveRadialMenu(label)
  }, [])
  const onCloseRadialMenu = useCallback(() => {
    setActiveRadialMenu(null)
  }, [])

  // ── Radial action handlers ────────────────────────────────────────
  const QUICK_PROMPTS: Record<string, string> = {
    Strategist: 'Scan the current environment and provide a strategic overview',
    Researcher: 'Summarize the latest developments in our active research areas',
    'Chief of Staff': 'Check the status of all active workflows and flag any blockers',
    Finance: 'Provide a quick budget health check and spending summary',
    Memory: 'Summarize recent context and important facts from memory',
    Vision: 'Analyze the current screen content and describe what you see',
    Analytics: 'Pull the latest metrics and highlight any anomalies',
    Coding: 'Review the current codebase state and suggest improvements',
  }

  const handleRadialAction = useCallback(async (label: string, action: 'quick-execute' | 'view-details' | 'share-link') => {
    onCloseRadialMenu()

    if (action === 'quick-execute') {
      const prompt = QUICK_PROMPTS[label] ?? `Quick action for ${label}`
      try {
        const resp = await window.barq?.python.request('/agent/execute', { goal: `[${label}] ${prompt}` })
        const result = resp && typeof resp === 'object'
          ? ((resp as Record<string, unknown>).result ?? JSON.stringify(resp))
          : String(resp ?? 'No response')
        console.log(`⚡ ${label} result:`, String(result).slice(0, 200))
      } catch {
        console.warn(`⚡ ${label} execution failed — backend unreachable`)
      }
    }

    if (action === 'view-details') {
      try {
        const resp = await window.barq?.python.request('/agent/plan', { goal: `Show capabilities and context for agent ${label}`, context: `${label} agent` })
        if (resp && typeof resp === 'object') {
          const plan = (resp as Record<string, unknown>).plan ?? (resp as Record<string, unknown>).steps ?? JSON.stringify(resp)
          console.log(`📄 ${label}:`, String(plan).slice(0, 200))
        }
      } catch {
        console.warn(`📄 Could not retrieve ${label} details from backend`)
      }
    }

    if (action === 'share-link') {
      const shareText = `🤖 BARQ Agent: ${label}\nContext: Active agent in BARQ v2.0 Spatial Node Network\nColor: ${AGENT_COLORS[label] ?? '#00E5FF'}`
      try {
        await navigator.clipboard.writeText(shareText)
        console.log(`🔗 Copied ${label} profile to clipboard`)
      } catch {
        console.warn(`🔗 Could not copy ${label} profile`)
      }
    }
  }, [onCloseRadialMenu])

  // ── Drag-and-drop handlers ───────────────────────────────────────
  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setIsDraggingFile(true)
  }, [])
  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation()
    // Only hide if leaving the overlay, not entering a child
    if (e.currentTarget === e.target || !e.currentTarget.contains(e.relatedTarget as Node)) {
      setIsDraggingFile(false)
    }
  }, [])
  const handleDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation() }, [])
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setIsDraggingFile(false)
  }, [])

  // ── Render ────────────────────────────────────────────────────────────
  const isVoiceActive = voiceListening && detectorRunning

  return (
    <div
      className="fixed inset-0 w-screen h-screen overflow-hidden bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-blue-900 via-slate-900 to-black"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {/* ── 3D Agent Network Canvas ───────────────────────────────── */}
      <div className="absolute inset-0">
        <Suspense fallback={
          <div className="w-full h-full flex items-center justify-center">
            <div className="relative flex items-center justify-center">
              <div className="w-16 h-16 border-2 border-cyan-400/20 border-t-cyan-400 rounded-full animate-spin" />
              <div className="absolute w-24 h-24 border border-cyan-400/10 rounded-full animate-ping" style={{ animationDuration: '2s' }} />
            </div>
          </div>
        }>
          <ParticleSphere3D
            activeAgent={activeAgent}
            onSelectAgent={onSelectAgent}
            focusTargetRef={focusTargetRef}
            onReturnToCore={onReturnToCore}
            systemLoad={systemLoad}
            activeTransfers={activeTransfers}
            onContextMenu={onContextMenu}
            activeRadialMenu={activeRadialMenu}
            onCloseRadialMenu={onCloseRadialMenu}
            onRadialAction={handleRadialAction}
          />
        </Suspense>
      </div>

      {/* ── Subtle vignette overlay ───────────────────────────────── */}
      <div className="absolute inset-0 pointer-events-none" style={{ background: 'radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.4) 100%)' }} />

      {/* ═══ WORKSPACE SIDE-PANEL ═══ */}
      <AnimatePresence>
        {activeAgent && (
          <motion.div
            initial={{ opacity: 0, x: 80 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 80 }}
            transition={{ duration: 0.35, ease: 'easeOut' }}
            className="absolute right-0 top-0 h-full w-[380px] z-20 flex flex-col"
            style={{ borderLeft: `3px solid ${activeAgentColor}`, boxShadow: `-4px 0 24px ${activeAgentColor}15` }}
          >
            <div className="absolute inset-0 backdrop-blur-md bg-slate-900/40" />
            <div className="relative z-10 flex flex-col h-full p-8">
              {/* Header */}
              <div className="flex items-start justify-between mb-8">
                <div>
                  <p className="text-[10px] font-sans text-white/30 tracking-[0.2em] uppercase font-medium mb-1">Agent Workspace</p>
                  <h2 className="text-2xl font-sans font-bold text-white/90 tracking-tight">{activeAgent.toUpperCase()}</h2>
                </div>
                <div className="w-2.5 h-2.5 rounded-full shrink-0 mt-2" style={{ backgroundColor: activeAgentColor, boxShadow: `0 0 12px ${activeAgentColor}60` }} />
              </div>

              {/* Chat */}
              <div className="flex-1 rounded-xl bg-white/[0.03] border border-white/[0.06] flex flex-col overflow-hidden">
                <div className="flex-1 overflow-y-auto p-4 space-y-3 scrollbar-thin" ref={messagesEndRef}>
                  {currentMessages.length === 0 ? (
                    <div className="flex items-center justify-center h-full">
                      <p className="text-sm font-sans text-white/20 italic text-center max-w-[200px]">Ask {activeAgent} anything to get started</p>
                    </div>
                  ) : (
                    currentMessages.map((msg, i) => (
                      <motion.div key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex items-start gap-2.5">
                        {msg.role === 'assistant' ? (
                          <Bot className="w-4 h-4 mt-0.5 shrink-0" style={{ color: activeAgentColor, filter: `drop-shadow(0 0 4px ${activeAgentColor}60)` }} />
                        ) : (
                          <User className="w-4 h-4 mt-0.5 shrink-0 text-white/40" />
                        )}
                        <p className="text-sm font-sans text-white/70 leading-relaxed">{msg.content}</p>
                      </motion.div>
                    ))
                  )}
                  {agentLoading && (
                    <div className="flex items-center gap-2.5">
                      <Bot className="w-4 h-4 shrink-0" style={{ color: activeAgentColor, filter: `drop-shadow(0 0 4px ${activeAgentColor}60)` }} />
                      <div className="flex gap-1">
                        <span className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ backgroundColor: activeAgentColor, opacity: 0.6, animationDelay: '0ms' }} />
                        <span className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ backgroundColor: activeAgentColor, opacity: 0.6, animationDelay: '150ms' }} />
                        <span className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ backgroundColor: activeAgentColor, opacity: 0.6, animationDelay: '300ms' }} />
                      </div>
                    </div>
                  )}
                </div>

                {/* Chat input */}
                <div className="p-3 border-t border-white/[0.06]">
                  <div className="flex items-start gap-2">
                    <textarea ref={agentInputRef} value={agentInput}
                      onChange={(e) => { setAgentInput(e.target.value); e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px' }}
                      onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAgentMessage(); e.currentTarget.style.height = 'auto' } }}
                      placeholder={`Ask ${activeAgent} anything...`}
                      className="flex-1 bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2.5 text-sm font-sans text-white/70 placeholder:text-white/20 outline-none focus:border-cyan-500/30 focus:bg-white/[0.06] transition-all duration-200 resize-none min-h-[36px] max-h-[120px] leading-relaxed overflow-y-auto"
                      disabled={agentLoading} rows={1}
                    />
                    <button onClick={sendAgentMessage} disabled={!agentInput.trim() || agentLoading}
                      className="flex items-center justify-center w-9 h-9 rounded-lg bg-cyan-500/20 border border-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200 shrink-0 mt-0.5"
                    >
                      {agentLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              </div>

              {/* Return button */}
              <button onClick={onReturnToCore} className="mt-6 flex items-center gap-2 px-4 py-2.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 hover:border-white/20 text-white/50 hover:text-white/80 transition-all duration-200 group">
                <ArrowLeft className="w-4 h-4 transition-transform duration-200 group-hover:-translate-x-0.5" />
                <span className="text-xs font-sans font-medium tracking-wide">Return to Core</span>
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ═══ TOP-LEFT: Weather + Greeting ═══ */}
      <div className="absolute top-8 left-24 z-10">
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease: 'easeOut' }} className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <Cloud className="w-4 h-4 text-cyan-300/60" />
            {weather ? (
              <span className="text-lg font-sans font-light text-white/80 tracking-wide tabular-nums">{Math.round(weather.temperature_c)}°<span className="text-white/40 text-sm">C</span></span>
            ) : (
              <span className="text-lg font-sans font-light text-white/40">--°</span>
            )}
            <span className="w-px h-4 bg-white/10" />
            <span className="text-[10px] font-sans text-white/40 uppercase tracking-[0.15em] font-medium">{weather?.city ?? 'Loading...'}</span>
          </div>
          <div className="mt-2">
            <h1 className="text-4xl font-sans font-bold text-white/90 tracking-tight leading-none">{greeting}</h1>
            <p className="text-sm font-sans text-white/40 mt-1.5 font-light tracking-wide max-w-[300px] line-clamp-1">{subGreeting}</p>
          </div>
          <AnimatePresence mode="wait">
            {sttText && (
              <motion.div key="stt" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.2 }} className="mt-3 flex items-start gap-2">
                <span className="flex items-center gap-1 shrink-0 mt-0.5">
                  <User className="w-3 h-3 text-cyan-300/60" />
                  <span className="relative flex w-1.5 h-1.5"><span className="animate-ping absolute inset-0 rounded-full bg-cyan-400 opacity-50" /><span className="relative rounded-full w-1.5 h-1.5 bg-cyan-400" /></span>
                </span>
                <span className="text-sm font-sans text-cyan-200/80 italic leading-relaxed">&ldquo;{sttText}&rdquo;</span>
              </motion.div>
            )}
            {!sttText && responseText && (
              <motion.div key="response" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.2 }} className="mt-3 flex items-start gap-2">
                <span className="flex items-center gap-1 shrink-0 mt-0.5">
                  <Bot className="w-3 h-3 text-emerald-300/60" />
                  <span className="relative flex w-1.5 h-1.5"><span className="animate-ping absolute inset-0 rounded-full bg-emerald-400 opacity-40" /><span className="relative rounded-full w-1.5 h-1.5 bg-emerald-400" /></span>
                </span>
                <span className="text-sm font-sans text-emerald-200/80 leading-relaxed max-w-[320px]">
                  {responseText}
                  {(aiState === 'responding' || aiState === 'thinking') && <span className="inline-block w-1 h-4 ml-0.5 bg-emerald-400/60 animate-pulse align-text-bottom" />}
                </span>
              </motion.div>
            )}
          </AnimatePresence>
          <div className="flex items-center gap-3 mt-4">
            {['CORE', 'VISION', 'AUDIO', 'NET'].map((mod, i) => (
              <div key={mod} className="flex items-center gap-1.5">
                <span className={`w-1.5 h-1.5 rounded-full ${i !== 2 ? 'bg-cyan-400/60 shadow-[0_0_5px_rgba(34,211,238,0.3)]' : 'bg-white/10'}`} />
                <span className={`text-[9px] font-sans font-medium tracking-wider ${i !== 2 ? 'text-cyan-300/50' : 'text-white/20'}`}>{mod}</span>
              </div>
            ))}
            <span className={`w-1.5 h-1.5 rounded-full transition-all duration-300 ${wsConnected ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]' : 'bg-amber-500/50'}`} title={wsConnected ? 'Connected' : 'Reconnecting...'} />
          </div>
        </motion.div>
      </div>

      {/* ═══ LIVE CAPTIONS OVERLAY ═══ */}
      <LiveCaptions
        sttText={sttText}
        responseText={responseText}
        isSpeaking={aiState === 'responding'}
        isProcessing={aiState === 'thinking'}
        conversationActive={voiceListening && detectorRunning}
        isListening={detectorRunning}
      />

      {/* ═══ BOTTOM-CENTER: Voice Pill ═══ */}
      <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-10">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.2, ease: 'easeOut' }}
          className="flex items-center gap-4 px-5 py-3 rounded-2xl backdrop-blur-md bg-white/5 border border-white/10 shadow-xl"
        >
          <button onClick={toggleDetector}
            className={`flex items-center justify-center w-8 h-8 rounded-full transition-all duration-300 ${!detectorRunning ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30' : isVoiceActive ? 'bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30' : 'bg-white/5 text-white/40 hover:bg-white/10 hover:text-white/60'}`}
            title={detectorRunning ? 'Mute microphone' : 'Unmute microphone'}
          >{detectorRunning ? <Mic className="w-4 h-4" /> : <MicOff className="w-4 h-4" />}</button>
          <div className="w-px h-6 bg-white/10" />
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <span className={`text-xs font-sans font-bold tracking-[0.15em] uppercase transition-all duration-300 ${!detectorRunning ? 'text-red-400' : isVoiceActive ? 'text-cyan-300' : 'text-white/40'}`}>
                {!detectorRunning ? 'MUTED' : isVoiceActive ? 'ON AIR' : 'STANDBY'}
              </span>
              {(isVoiceActive || aiState === 'thinking' || aiState === 'responding') && (
                <span className="relative flex w-2 h-2">
                  <span className={`animate-ping absolute inset-0 rounded-full ${aiState === 'responding' ? 'bg-emerald-400' : aiState === 'thinking' ? 'bg-amber-400' : 'bg-cyan-400'} opacity-50`} />
                  <span className={`relative rounded-full w-2 h-2 ${aiState === 'responding' ? 'bg-emerald-400' : aiState === 'thinking' ? 'bg-amber-400' : 'bg-cyan-400'}`} />
                </span>
              )}
            </div>
            <span className="text-[10px] font-sans text-white/25 tracking-wide">
              {aiState === 'responding' ? 'BARQ is speaking' : aiState === 'thinking' ? 'Processing...' : isVoiceActive ? 'Listening for commands' : detectorRunning ? 'Waiting for wake word' : 'Microphone disabled'}
            </span>
          </div>
          <div className="w-px h-6 bg-white/10" />
          <AudioWaveformBars isActive={isVoiceActive || aiState === 'responding'} />
        </motion.div>
      </div>

      {/* ── Bottom-left branding ──────────────────────────────────── */}
      <div className="absolute bottom-8 left-8 z-10">
        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6, delay: 0.4 }}
          className="text-[10px] font-sans text-white/15 tracking-[0.2em] uppercase font-medium">B.A.R.Q · Agent Network</motion.p>
      </div>

      {/* ═══ SYSTEM LOAD INDICATOR (mini) ═══ */}
      <div className="absolute bottom-8 right-8 z-10 flex items-center gap-2">
        <div className="w-16 h-1 rounded-full bg-white/5 overflow-hidden">
          <motion.div
            className="h-full rounded-full"
            style={{ backgroundColor: systemLoad > 70 ? '#FBBF24' : '#4FC3F7' }}
            animate={{ width: `${systemLoad}%` }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
          />
        </div>
        <span className="text-[9px] font-mono text-white/30 tabular-nums">{Math.round(systemLoad)}%</span>
      </div>

      {/* ═══ CONTEXT DROP ZONE (full-screen overlay) ═══ */}
      <AnimatePresence>
        {isDraggingFile && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-50 flex items-center justify-center backdrop-blur-xl bg-slate-950/60"
            onDragEnter={handleDragEnter}
            onDragLeave={handleDragLeave}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
          >
            <div className="relative flex items-center justify-center w-80 h-80">
              {/* Outer dashed ring */}
              <div className="absolute inset-0 rounded-full border-2 border-dashed border-cyan-400/40 animate-[spin_8s_linear_infinite]" />
              {/* Inner pulsing ring */}
              <div className="absolute inset-4 rounded-full border border-cyan-400/20 animate-ping" style={{ animationDuration: '3s' }} />
              {/* Center text */}
              <div className="text-center">
                <p className="text-lg font-sans font-bold text-white/80 tracking-[0.2em] uppercase">DROP TO</p>
                <p className="text-lg font-sans font-bold text-cyan-300/90 tracking-[0.2em] uppercase">INGEST INTO</p>
                <p className="text-lg font-sans font-bold text-white/80 tracking-[0.2em] uppercase">MEMORY</p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ─── Module-level helpers (used by the component) ──────────────────────

interface TLHelper { id: string; label: string; color: string; position: [number, number, number]; description: string }

const AGENT_COLORS_KEYS = Object.keys({ Strategist: '#00E5FF', Researcher: '#A855F7', 'Chief of Staff': '#FBBF24', Finance: '#34D399', Memory: '#F472B6', Vision: '#60A5FA', Analytics: '#FB923C', Coding: '#2DD4BF' })

const AGENT_NODES_LIST: TLHelper[] = [
  { id: 'strategist', label: 'Strategist', color: '#00E5FF', position: [5.0, 1.8, 1.0], description: 'Planning & Strategy' },
  { id: 'researcher', label: 'Researcher', color: '#A855F7', position: [2.0, 4.5, 2.0], description: 'Deep Research' },
  { id: 'chief-of-staff', label: 'Chief of Staff', color: '#FBBF24', position: [-3.5, 4.0, 1.5], description: 'Coordination' },
  { id: 'finance', label: 'Finance', color: '#34D399', position: [-5.5, 0.0, -1.0], description: 'Budget & Tracking' },
  { id: 'memory', label: 'Memory', color: '#F472B6', position: [-3.0, -3.8, 2.0], description: 'Context & Recall' },
  { id: 'vision', label: 'Vision', color: '#60A5FA', position: [3.5, -3.5, 2.5], description: 'Computer Vision' },
  { id: 'analytics', label: 'Analytics', color: '#FB923C', position: [0.5, -5.5, -1.5], description: 'Data Insights' },
  { id: 'coding', label: 'Coding', color: '#2DD4BF', position: [1.5, 5.0, -2.0], description: 'Code Generation' },
]
