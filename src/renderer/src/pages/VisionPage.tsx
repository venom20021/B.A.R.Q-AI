import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Eye, Monitor, Camera, Play, Square, Loader2, CheckCircle, XCircle,
  AlertTriangle, History, Settings2, Volume2,
  ChevronDown, ChevronUp, Trash2, Clock, Wifi, WifiOff,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '../utils/api'

// ─── Types ────────────────────────────────────────────────────────────

interface Capabilities {
  screen_capture: boolean
  webcam: boolean
  gemini_api: boolean
  gemini_live: boolean
}

interface AnalysisEntry {
  id: number
  source: 'screen' | 'camera'
  prompt: string
  result: string
  timestamp: string
  error?: string
}

interface VisionResponse {
  status?: string
  text?: string
  description?: string
  source?: string
  message?: string
  image_size_bytes?: number
  mime_type?: string
  image_base64?: string
  audio_pcm_base64?: string
  sample_rate?: number
}

// WebSocket message types
interface WsStatusMsg {
  type: 'status'
  gemini_available: boolean
  api_key_configured: boolean
  ready: boolean
}

interface WsTokenMsg {
  type: 'token'
  text: string
}

interface WsDoneMsg {
  type: 'done'
  text: string
  duration_ms: number
}

interface WsAudioMsg {
  type: 'audio'
  audio_base64: string
  sample_rate: number
}

interface WsErrorMsg {
  type: 'error'
  message: string
  component?: string
}

type WsMessage = WsStatusMsg | WsTokenMsg | WsDoneMsg | WsAudioMsg | WsErrorMsg

// ─── WebSocket URL ────────────────────────────────────────────────────
// Matches the backend config (default: 127.0.0.1:8956)
const WS_BASE = `ws://${location.hostname || '127.0.0.1'}:8956`

// ─── Capability definitions ───────────────────────────────────────────

const CAP_DEFS: { key: keyof Capabilities; label: string; icon: typeof Monitor }[] = [
  { key: 'screen_capture', label: 'Screen Capture', icon: Monitor },
  { key: 'webcam',        label: 'Webcam',        icon: Camera },
  { key: 'gemini_api',    label: 'Gemini Vision',  icon: Eye },
  { key: 'gemini_live',   label: 'Gemini Live Audio', icon: Volume2 },
]

// ═══════════════════════════════════════════════════════════════════════
// VisionPage
// ═══════════════════════════════════════════════════════════════════════

export function VisionPage(): JSX.Element {
  const [prompt, setPrompt] = useState("What's on my screen? Be concise.")
  const [result, setResult] = useState<VisionResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [setupRequired, setSetupRequired] = useState(false)
  const [source, setSource] = useState<'screen' | 'camera'>('screen')
  const [cameraIndex, setCameraIndex] = useState(0)
  const [caps, setCaps] = useState<Capabilities | null>(null)
  const [history, setHistory] = useState<AnalysisEntry[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const [liveMode, setLiveMode] = useState(false)
  const [liveInterval, setLiveInterval] = useState(5)
  const liveRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const historyIdRef = useRef(0)
  const audioCtxRef = useRef<AudioContext | null>(null)

  // ── WebSocket state ────────────────────────────────────────────────
  const [wsConnected, setWsConnected] = useState(false)
  const [wsReady, setWsReady] = useState(false)        // gemini + api key ready
  const [streamingText, setStreamingText] = useState('') // real-time partial text
  const wsRef = useRef<WebSocket | null>(null)
  const wsReconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const resumeAudioCtx = useCallback(async () => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new AudioContext()
    }
    if (audioCtxRef.current.state === 'suspended') {
      await audioCtxRef.current.resume()
    }
    return audioCtxRef.current
  }, [])

  // ── WebSocket Connection ───────────────────────────────────────────

  // Store self-reference for setTimeout callbacks
  const connectWsRef = useRef<() => void>(() => { /* noop */ })

  const connectWs = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    try {
      const ws = new WebSocket(`${WS_BASE}/vision/ws/vision`)
      wsRef.current = ws

      ws.onopen = () => {
        setWsConnected(true)
        console.log('[Vision WS] Connected')
      }

      ws.onmessage = (event) => {
        try {
          const msg: WsMessage = JSON.parse(event.data)

          switch (msg.type) {
            case 'status':
              setWsReady(msg.ready)
              // Dynamically update capabilities based on WS status
              setCaps((prev) => ({
                screen_capture: prev?.screen_capture ?? false,
                webcam: prev?.webcam ?? false,
                gemini_api: msg.api_key_configured,
                gemini_live: msg.ready, // Live ready when gemini + key ok
              }))
              if (!msg.api_key_configured) {
                setSetupRequired(true)
              }
              break

            case 'token':
              setStreamingText((prev) => prev + msg.text)
              break

            case 'done':
              setStreamingText('')
              setLoading(false)
              setResult((prev) => ({
                ...prev,
                text: msg.text,
                status: 'success',
              }))
              historyIdRef.current += 1
              setHistory((prev) => [
                {
                  id: historyIdRef.current,
                  source,
                  prompt: prompt.trim(),
                  result: msg.text,
                  timestamp: new Date().toLocaleTimeString(),
                },
                ...prev,
              ].slice(0, 50))
              break

            case 'audio':
              // Play received audio via Web Audio API
              if (msg.audio_base64) {
                void (async () => {
                  try {
                    const binaryStr = atob(msg.audio_base64)
                    const bytes = new Uint8Array(binaryStr.length)
                    for (let i = 0; i < binaryStr.length; i++) bytes[i] = binaryStr.charCodeAt(i)
                    const ctx = await resumeAudioCtx()
                    const buffer = ctx.decodeAudioData(bytes.buffer)
                    const sourceNode = ctx.createBufferSource()
                    sourceNode.buffer = await buffer
                    sourceNode.connect(ctx.destination)
                    sourceNode.start()
                  } catch (e) {
                    console.warn('[Vision WS] Audio playback error:', e)
                  }
                })()
              }
              break

            case 'error':
              setError(msg.message)
              setLoading(false)
              setStreamingText('')
              if (msg.component === 'Gemini Vision' || msg.message.includes('API key')) {
                setWsReady(false)
                setSetupRequired(true)
                setCaps((prev) => prev ? { ...prev, gemini_api: false, gemini_live: false } : prev)
              }
              break
          }
        } catch (e) {
          console.warn('[Vision WS] Parse error:', e)
        }
      }

      ws.onclose = () => {
        setWsConnected(false)
        setWsReady(false)
        setStreamingText('')
        wsRef.current = null
        // Auto-reconnect after 3s
        wsReconnectRef.current = setTimeout(() => {
          connectWsRef.current()
        }, 3000)
      }

      ws.onerror = () => {
        // onclose will fire after this
      }
    } catch (e) {
      console.warn('[Vision WS] Connection error:', e)
      setWsConnected(false)
      // Retry after 5s
      wsReconnectRef.current = setTimeout(() => {
        connectWsRef.current()
      }, 5000)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])  // Intentionally stable — no external deps; connect is called once on mount

  // Keep ref in sync so setTimeout callbacks can call connectWs without TDZ issues
  useEffect(() => {
    connectWsRef.current = connectWs
  }, [connectWs])

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connectWs()  // eslint-disable-line react-hooks/set-state-in-effect
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      if (wsReconnectRef.current) {
        clearTimeout(wsReconnectRef.current)
      }
    }
  }, [connectWs])

  // ── Fetch REST capabilities once as fallback ───────────────────────

  useEffect(() => {
    (async () => {
      try {
        const data = await api<{ capabilities?: Capabilities }>('/vision/check')
        if (data?.capabilities) {
          setCaps((prev) => ({
            // WS status takes priority for gemini, REST for screen/camera
            ...data.capabilities,
            gemini_api: prev?.gemini_api ?? data.capabilities.gemini_api,
            gemini_live: prev?.gemini_live ?? data.capabilities.gemini_live,
          }))
        }
      } catch { /* ignore */ }
    })()
  }, [])

  const camAvail = caps?.webcam ?? false

  // ── Live mode cleanup ──────────────────────────────────────────────

  useEffect(() => {
    return () => {
      if (liveRef.current) clearInterval(liveRef.current)
    }
  }, [])

  // ── Capture image as base64 ────────────────────────────────────────

  const captureImageAsBase64 = useCallback(async (): Promise<{ base64: string; mime: string } | null> => {
    try {
      // Use the REST endpoint to capture and get base64 image back
      const endpoint = source === 'screen' ? '/vision/screen' : '/vision/camera'
      const body = source === 'screen'
        ? { prompt: 'capture' }
        : { prompt: 'capture', camera_index: cameraIndex }
      const data = await api<VisionResponse>(endpoint, body)
      if (data?.image_base64) {
        // image_base64 is "data:image/jpeg;base64,..." — strip prefix
        const parts = data.image_base64.split(',')
        return { base64: parts[1] ?? parts[0], mime: data.mime_type || 'image/jpeg' }
      }
      return null
    } catch (e) {
      setError(String(e))
      return null
    }
  }, [source, cameraIndex])

  // ── Send WebSocket analysis request ────────────────────────────────

  const analyzeViaWs = useCallback(async () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setError('Vision WebSocket not connected. Reconnecting...')
      // connectWs() will be called by the auto-reconnect handler
      return
    }

    setLoading(true)
    setError('')
    setResult(null)
    setStreamingText('')
    setSetupRequired(false)

    const trimmedPrompt = prompt.trim() || (source === 'screen'
      ? "What's on my screen? Be concise."
      : "What do you see? Be concise.")

    // Capture image as base64
    const img = await captureImageAsBase64()
    if (!img) {
      setError('Failed to capture image')
      setLoading(false)
      return
    }

    // Send over WebSocket
    wsRef.current.send(JSON.stringify({
      type: 'analyze',
      image_base64: img.base64,
      mime_type: img.mime,
      prompt: trimmedPrompt,
      speak: true, // Request TTS playback
    }))
  }, [prompt, source, captureImageAsBase64])

  // ── Error/response helpers ─────────────────────────────────────────

  const detectApiKeyMissing = useCallback((msg: string) => {
    if (msg.toLowerCase().includes('gemini api key') || msg.toLowerCase().includes('api key')) {
      setSetupRequired(true)
    }
  }, [])

  const addToHistory = useCallback((entry: AnalysisEntry) => {
    setHistory(prev => [entry, ...prev].slice(0, 50))
  }, [])

  // ── Main capture & analyze (legacy REST path as fallback) ──────────

  const captureAndAnalyze = useCallback(async () => {
    // If WebSocket is connected and ready, use streaming path
    if (wsRef.current?.readyState === WebSocket.OPEN && wsReady) {
      await analyzeViaWs()
      return
    }

    // Fallback to legacy REST path
    setLoading(true)
    setError('')
    setResult(null)
    setSetupRequired(false)

    const trimmedPrompt = prompt.trim() || (source === 'screen'
      ? "What's on my screen? Be concise."
      : "What do you see? Be concise.")

    const endpoint = source === 'screen' ? '/vision/screen' : '/vision/camera'
    const body = source === 'screen'
      ? { prompt: trimmedPrompt }
      : { prompt: trimmedPrompt, camera_index: cameraIndex }

    try {
      const data = await api<VisionResponse>(endpoint, body)

      if (data) {
        if (data.status === 'unavailable') {
          const msg = String(data.message || 'Vision service unavailable')
          setError(msg)
          detectApiKeyMissing(msg)
          return
        }

        setResult(data)
        const text = data.text || data.description || ''
        if (text) {
          historyIdRef.current += 1
          addToHistory({
            id: historyIdRef.current,
            source,
            prompt: trimmedPrompt,
            result: text,
            timestamp: new Date().toLocaleTimeString(),
          })
        }
      }
    } catch (e) {
      const msg = String(e)
      setError(msg)
      detectApiKeyMissing(msg)
    }
    setLoading(false)
  }, [prompt, source, cameraIndex, wsReady, analyzeViaWs, detectApiKeyMissing, addToHistory])

  // ── Live mode toggle ───────────────────────────────────────────────

  const toggleLiveMode = useCallback(() => {
    if (liveMode) {
      if (liveRef.current) {
        clearInterval(liveRef.current)
        liveRef.current = null
      }
      setLiveMode(false)
    } else {
      setLiveMode(true)
      void captureAndAnalyze()
      liveRef.current = setInterval(() => {
        void captureAndAnalyze()
      }, liveInterval * 1000)
    }
  }, [liveMode, liveInterval, captureAndAnalyze])

  // ── Voice response via Gemini Live ─────────────────────────────────

  const captureWithVoice = useCallback(async () => {
    setLoading(true)
    setError('')
    setResult(null)
    setSetupRequired(false)

    const trimmedPrompt = prompt.trim() || "What do you see? Be concise."

    try {
      const data = await api<VisionResponse>('/vision/analyze', {
        prompt: trimmedPrompt,
        angle: source,
        camera_index: cameraIndex,
        voice_response: true,
      })

      if (data) {
        if (data.status === 'unavailable') {
          setError(String(data.message || 'Voice vision unavailable'))
          detectApiKeyMissing(String(data.message || ''))
          return
        }
        if (data.audio_pcm_base64) {
          const binaryStr = atob(data.audio_pcm_base64)
          const bytes = new Uint8Array(binaryStr.length)
          for (let i = 0; i < binaryStr.length; i++) bytes[i] = binaryStr.charCodeAt(i)
          const pcm16 = new Int16Array(bytes.buffer)
          const float32 = new Float32Array(pcm16.length)
          for (let i = 0; i < pcm16.length; i++) float32[i] = pcm16[i] / 32768.0
          const ctx = await resumeAudioCtx()
          const buffer = ctx.createBuffer(1, float32.length, data.sample_rate || 24000)
          buffer.getChannelData(0).set(float32)
          const source = ctx.createBufferSource()
          source.buffer = buffer
          source.connect(ctx.destination)
          source.start()
          setResult(data)
        }
      }
    } catch (e) {
      setError(String(e))
      detectApiKeyMissing(String(e))
    }
    setLoading(false)
  }, [prompt, source, cameraIndex, detectApiKeyMissing, resumeAudioCtx])

  // ── Clear history ──────────────────────────────────────────────────

  const clearHistory = useCallback(() => {
    setHistory([])
    historyIdRef.current = 0
  }, [])

  // ── Readiness summary ──────────────────────────────────────────────

  const readyCount = caps ? Object.values(caps).filter(Boolean).length : 0
  const capTotal = caps ? Object.keys(caps).length : 0
  const allReady = caps && readyCount === capTotal

  // ═════════════════════════════════════════════════════════════════════
  // ── Render ─────────────────────────────────────────────────────────
  // ═════════════════════════════════════════════════════════════════════

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider flex items-center gap-3">
              <Eye className="w-6 h-6 text-cyan-400" />
              VISUAL AWARENESS
            </h1>
            <p className="text-sm font-rajdhani text-dim-400 mt-1">
              Real-time screen and webcam analysis via Google Gemini 2.5 Flash
            </p>
          </div>

          {/* Readiness badge */}
          {caps && (
            <div className="flex items-center gap-3">
              {/* WS connection indicator */}
              <div className={`flex items-center gap-1.5 px-2 py-1 rounded border text-[10px] font-share-tech ${
                wsConnected
                  ? 'border-emerald-500/20 text-emerald-400'
                  : 'border-red-500/20 text-red-400'
              }`}>
                {wsConnected
                  ? <><Wifi className="w-3 h-3" /> WS</>
                  : <><WifiOff className="w-3 h-3" /> WS</>
                }
              </div>

              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-rajdhani font-semibold ${
                allReady
                  ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
                  : 'bg-amber-500/10 text-amber-300 border-amber-500/20'
              }`}>
                <span className={`relative w-2 h-2 ${allReady ? '' : 'animate-pulse'}`}>
                  <span className={`absolute inset-0 rounded-full ${allReady ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                </span>
                {allReady ? 'All Systems Ready' : `${readyCount}/${capTotal} Ready`}
              </div>
            </div>
          )}
        </div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* ── Left: Controls ───────────────────────────────────────── */}
        <div className="lg:col-span-2 space-y-4">
          {/* Main Control Card */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card">
            {/* Source Toggle */}
            <div className="flex items-center gap-2 mb-4">
              <div className="flex rounded-lg border border-cyan-500/10 p-0.5">
                <button
                  onClick={() => setSource('screen')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-rajdhani font-semibold transition-all ${
                    source === 'screen'
                      ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-400/30'
                      : 'text-dim-400 hover:text-ghost'
                  }`}
                >
                  <Monitor className="w-3.5 h-3.5" /> Screen
                </button>
                <button
                  onClick={() => setSource('camera')}
                  disabled={!camAvail}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-rajdhani font-semibold transition-all ${
                    !camAvail ? 'text-dim-600 cursor-not-allowed' :
                    source === 'camera'
                      ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-400/30'
                      : 'text-dim-400 hover:text-ghost'
                  }`}
                  title={!camAvail ? 'OpenCV not installed' : 'Use webcam'}
                >
                  <Camera className="w-3.5 h-3.5" /> Camera
                </button>
              </div>

              {/* Live Mode Toggle */}
              <button
                onClick={toggleLiveMode}
                disabled={loading}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-rajdhani font-semibold transition-all ml-auto ${
                  liveMode
                    ? 'bg-red-500/15 text-red-300 border border-red-400/30 animate-pulse'
                    : 'bg-void-700/40 text-dim-400 hover:text-ghost border border-cyan-500/10'
                }`}
              >
                {liveMode ? (
                  <><Square className="w-3 h-3" /> Stop Live</>
                ) : (
                  <><Play className="w-3 h-3" /> Live Mode</>
                )}
              </button>
            </div>

            {/* Camera Selection */}
            <AnimatePresence>
              {source === 'camera' && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden mb-3"
                >
                  <div className="flex items-center gap-2 bg-void-700/30 rounded-lg p-2 border border-cyan-500/5">
                    <Settings2 className="w-3.5 h-3.5 text-dim-400" />
                    <span className="text-xs font-exo text-dim-400">Camera Index:</span>
                    <select
                      value={cameraIndex}
                      onChange={(e) => setCameraIndex(Number(e.target.value))}
                      className="bg-void-700 rounded px-2 py-1 text-xs text-ghost border border-cyan-500/10"
                    >
                      {[0, 1, 2, 3].map(i => (
                        <option key={i} value={i}>Camera {i}</option>
                      ))}
                    </select>
                    {!camAvail && (
                      <span className="text-xs text-amber-400 ml-auto">opencv not installed</span>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Live Interval */}
            <AnimatePresence>
              {liveMode && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden mb-3"
                >
                  <div className="flex items-center gap-2 bg-void-700/30 rounded-lg p-2 border border-cyan-500/5">
                    <Clock className="w-3.5 h-3.5 text-dim-400" />
                    <span className="text-xs font-exo text-dim-400">Interval:</span>
                    <select
                      value={liveInterval}
                      onChange={(e) => {
                        setLiveInterval(Number(e.target.value))
                        if (liveRef.current) {
                          clearInterval(liveRef.current)
                          liveRef.current = setInterval(() => {
                            void captureAndAnalyze()
                          }, Number(e.target.value) * 1000)
                        }
                      }}
                      className="bg-void-700 rounded px-2 py-1 text-xs text-ghost border border-cyan-500/10"
                    >
                      {[2, 5, 10, 15, 30, 60].map(s => (
                        <option key={s} value={s}>{s}s</option>
                      ))}
                    </select>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Prompt Input */}
            <div className="mb-3">
              <input
                type="text"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && !liveMode && captureAndAnalyze()}
                placeholder="Ask about what's on screen..."
                className="input-cyan text-sm w-full"
              />
            </div>

            {/* Action Buttons */}
            <div className="flex gap-2 flex-wrap">
              <button
                onClick={captureAndAnalyze}
                disabled={loading || liveMode}
                className="btn-cyan text-sm flex items-center gap-1.5"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Eye className="w-4 h-4" />}
                {loading ? 'Analyzing...' : source === 'screen' ? 'Analyze Screen' : 'Capture Camera'}
              </button>

              <button
                onClick={captureWithVoice}
                disabled={loading || liveMode}
                className="btn-ghost-cyan text-sm flex items-center gap-1.5"
                title="Get a spoken audio response from Gemini Live"
              >
                <Volume2 className="w-4 h-4" />
                Voice Response
              </button>
            </div>

            <p className="text-hud text-dim-500 mt-2 text-xs">
              {liveMode
                ? `Live mode active — capturing every ${liveInterval}s. Click "Stop Live" to end.`
                : wsConnected && wsReady
                  ? 'Streaming via WebSocket — real-time token display active.'
                  : 'Uses Google Gemini 2.5 Flash. Screen captures are not stored.'}
            </p>
          </motion.div>

          {/* ── Live Mode Indicator ──────────────────────────────── */}
          {liveMode && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="glass-card border-red-500/20"
            >
              <div className="flex items-center gap-2">
                <span className="relative w-2 h-2">
                  <span className="absolute inset-0 rounded-full bg-red-400 animate-ping" />
                  <span className="absolute inset-0 rounded-full bg-red-500" />
                </span>
                <span className="text-xs font-exo text-red-300 font-semibold">Live Capture Active</span>
                <span className="text-xs font-exo text-dim-400 ml-auto">
                  {history.length > 0 ? `${history.length} captures` : 'Waiting...'}
                </span>
              </div>
            </motion.div>
          )}

          {/* ── Streaming Result (WebSocket) ────────────────────── */}
          {loading && streamingText && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card border-cyan-500/20"
            >
              <div className="flex items-center gap-2 mb-2">
                <Loader2 className="w-4 h-4 animate-spin text-cyan-300" />
                <h4 className="text-sm font-rajdhani font-semibold text-ghost">
                  Analyzing with Gemini{' '}
                  <span className="text-dim-400 font-normal">(streaming)</span>
                </h4>
              </div>
              <p className="text-sm font-exo text-dim-200 leading-relaxed whitespace-pre-wrap">
                {streamingText}
                <span className="inline-block w-1.5 h-4 bg-cyan-400/60 ml-0.5 animate-pulse" />
              </p>
            </motion.div>
          )}

          {/* ── Error ───────────────────────────────────────────── */}
          {error && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card border-red-500/20"
            >
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                <p className="text-xs font-exo text-red-400">{error}</p>
              </div>
              {setupRequired && (
                <div className="mt-3 bg-void-800/60 rounded-lg p-3 border border-amber-500/20">
                  <p className="text-xs font-exo text-amber-300 font-semibold">Setup Required</p>
                  <ol className="mt-2 text-xs font-exo text-dim-300 space-y-1 list-decimal list-inside">
                    <li>Get a <a className="text-cyan-400 underline" href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer">Gemini API key</a> (free)</li>
                    <li>Save it to <code className="text-amber-300 bg-void-900/60 px-1 rounded">python/config/api_keys.json</code></li>
                    <li>Or set the <code className="text-amber-300">GEMINI_API_KEY</code> env var</li>
                    <li>Restart the backend server</li>
                  </ol>
                </div>
              )}
            </motion.div>
          )}

          {/* ── Loading (non-streaming fallback) ────────────────── */}
          {loading && !streamingText && (
            <div className="glass-card text-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-cyan-300 mx-auto mb-2" />
              <p className="text-xs font-exo text-dim-400">Analyzing with Gemini...</p>
            </div>
          )}

          {/* ── Result ──────────────────────────────────────────── */}
          {result && !loading && !error && !streamingText && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card"
            >
              <div className="flex items-center gap-2 mb-3">
                <CheckCircle className="w-4 h-4 text-emerald-400" />
                <h4 className="text-sm font-rajdhani font-semibold text-ghost">
                  Analysis Result
                </h4>
                {result.source && (
                  <span className="text-hud text-[10px] text-dim-400 border border-dim-500/20 rounded px-1.5 py-0.5">
                    {result.source}
                  </span>
                )}
                {result.image_size_bytes && (
                  <span className="text-hud text-[10px] text-dim-500">
                    {(result.image_size_bytes / 1024).toFixed(0)} KB
                  </span>
                )}
              </div>

              {/* Image Preview */}
              {result.image_base64 && (
                <div className="mb-4 rounded-lg overflow-hidden border border-cyan-500/10 bg-void-800/50">
                  <img
                    src={result.image_base64}
                    alt="Captured preview"
                    className="w-full max-h-80 object-contain"
                  />
                  <div className="flex items-center gap-2 px-3 py-1.5 border-t border-cyan-500/5">
                    <Camera className="w-3 h-3 text-dim-400" />
                    <span className="text-hud text-[10px] text-dim-500">
                      {result.source === 'screen' ? 'Screen capture' : 'Camera capture'} —{' '}
                      {result.mime_type || 'image'}
                    </span>
                  </div>
                </div>
              )}

              <p className="text-sm font-exo text-dim-200 leading-relaxed whitespace-pre-wrap">
                {result.text || result.description || 'Analysis complete.'}
              </p>
              {result.audio_pcm_base64 && (
                <div className="mt-3 flex items-center gap-2 text-xs font-exo text-cyan-400">
                  <Volume2 className="w-3.5 h-3.5" />
                  Audio response received — playing through speakers
                </div>
              )}
            </motion.div>
          )}
        </div>

        {/* ── Right: Capabilities + History ──────────────────────────── */}
        <div className="space-y-4">
          {/* Capabilities */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card">
            <h3 className="text-sm font-rajdhani font-semibold text-ghost mb-3">Capabilities</h3>
            <div className="space-y-2">
              {CAP_DEFS.map(({ key, label, icon: Icon }) => (
                <CapabilityRow
                  key={key}
                  label={label}
                  icon={Icon}
                  installed={caps ? caps[key] : null}
                />
              ))}
            </div>

            {/* WS Status */}
            <div className="mt-3 pt-3 border-t border-cyan-500/5">
              <div className="flex items-center justify-between py-1">
                <div className="flex items-center gap-1.5">
                  {wsConnected
                    ? <Wifi className="w-3.5 h-3.5 text-emerald-400" />
                    : <WifiOff className="w-3.5 h-3.5 text-dim-500" />
                  }
                  <span className="text-xs font-exo text-dim-300">Vision WebSocket</span>
                </div>
                <span className={`text-[10px] font-share-tech ${wsConnected ? 'text-emerald-400' : 'text-dim-500'}`}>
                  {wsConnected ? (wsReady ? 'Ready' : 'No Key') : 'Disconnected'}
                </span>
              </div>
            </div>
          </motion.div>

          {/* History */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="glass-card"
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <History className="w-4 h-4 text-holographic" />
                <h3 className="text-sm font-rajdhani font-semibold text-ghost">History</h3>
              </div>
              <div className="flex items-center gap-1">
                {history.length > 0 && (
                  <button onClick={clearHistory} className="p-1 rounded text-dim-400 hover:text-red-400 transition-colors" title="Clear history">
                    <Trash2 className="w-3 h-3" />
                  </button>
                )}
                <button
                  onClick={() => setShowHistory(!showHistory)}
                  className="p-1 rounded text-dim-400 hover:text-ghost transition-colors"
                >
                  {showHistory ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                </button>
              </div>
            </div>

            {history.length === 0 ? (
              <p className="text-xs font-exo text-dim-500 text-center py-4">No analyses yet</p>
            ) : (
              <AnimatePresence>
                {showHistory && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="space-y-2 max-h-80 overflow-y-auto scroll-cyan">
                      {history.map((entry) => (
                        <div
                          key={entry.id}
                          className="bg-void-700/30 rounded-lg p-2.5 border border-cyan-500/5 hover:border-cyan-500/15 transition-colors"
                        >
                          <div className="flex items-center gap-1.5 mb-1">
                            {entry.source === 'screen'
                              ? <Monitor className="w-3 h-3 text-cyan-400" />
                              : <Camera className="w-3 h-3 text-amber-400" />
                            }
                            <span className="text-hud text-[10px] text-dim-400">{entry.timestamp}</span>
                            <span className="text-hud text-[10px] text-dim-500 truncate ml-auto">{entry.prompt.slice(0, 30)}</span>
                          </div>
                          <p className="text-hud text-[11px] text-dim-300 line-clamp-2">{entry.result}</p>
                        </div>
                      ))}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            )}

            {!showHistory && history.length > 0 && (
              <p className="text-hud text-[10px] text-dim-500 mt-1">{history.length} analyses — click to expand</p>
            )}
          </motion.div>
        </div>
      </div>
    </div>
  )
}

// ─── Capability Row ───────────────────────────────────────────────────

function CapabilityRow({
  label,
  icon: Icon,
  installed,
}: {
  label: string
  icon: typeof Monitor
  installed: boolean | null
}): JSX.Element {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-cyan-500/5 last:border-0">
      <div className="flex items-center gap-1.5">
        <Icon className={`w-3.5 h-3.5 ${
          installed === true ? 'text-emerald-400' :
          installed === false ? 'text-dim-500' :
          'text-dim-500'
        }`} />
        <span className="text-xs font-exo text-dim-300">{label}</span>
      </div>
      {installed === null ? (
        <Loader2 className="w-3 h-3 text-dim-400 animate-spin" />
      ) : installed ? (
        <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
      ) : (
        <XCircle className="w-3.5 h-3.5 text-dim-500" />
      )}
    </div>
  )
}
