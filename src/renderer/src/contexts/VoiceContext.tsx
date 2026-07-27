import { createContext, useContext, useState, useCallback, useEffect, useRef, type ReactNode } from 'react'
import { api } from '../utils/api'
import { getBackendConfig } from '../utils/backendConfig'

// ─── Types ──────────────────────────────────────────────────────────────────

type AIState = 'idle' | 'listening' | 'thinking' | 'responding'

interface VoiceContextValue {
  voiceListening: boolean
  detectorRunning: boolean
  wsConnected: boolean
  aiState: AIState
  sttText: string
  responseText: string
  isRemote: boolean
  /** Toggle the backend voice detector on/off */
  toggleDetector: () => Promise<void>
  /** Start the backend voice detector */
  startDetector: () => Promise<void>
  /** Stop the backend voice detector */
  stopDetector: () => Promise<void>
}

// ─── Context ─────────────────────────────────────────────────────────────────

const VoiceContext = createContext<VoiceContextValue>({
  voiceListening: false,
  detectorRunning: false,
  wsConnected: false,
  aiState: 'idle',
  sttText: '',
  responseText: '',
  isRemote: false,
  toggleDetector: async () => {},
  startDetector: async () => {},
  stopDetector: async () => {},
})

export function useVoice(): VoiceContextValue {
  return useContext(VoiceContext)
}

// ─── Provider ────────────────────────────────────────────────────────────────

/** Voice WS always connects to localhost.
 * Microphone/speakers are physically on this machine,
 * so the voice pipeline MUST run locally regardless of
 * whether non-voice endpoints are in remote mode.
 */
const LOCAL_VOICE_WS_URL = 'ws://127.0.0.1:8956/voice/ws/status'

let _voiceWsUrl: string | null = null
let _isRemote: boolean | null = null
async function getVoiceWsUrl(): Promise<string> {
  if (!_voiceWsUrl) {
    try {
      const config = await getBackendConfig()
      _isRemote = config.isRemote
    } catch {
      _isRemote = false
    }
    _voiceWsUrl = LOCAL_VOICE_WS_URL
  }
  return _voiceWsUrl
}

export function VoiceProvider({ children }: { children: ReactNode }): JSX.Element {
  const [voiceListening, setVoiceListening] = useState(false)
  const [detectorRunning, setDetectorRunning] = useState(false)
  const [wsConnected, setWsConnected] = useState(false)
  const [aiState, setAiState] = useState<AIState>('idle')
  const [sttText, setSttText] = useState('')
  const [responseText, setResponseText] = useState('')
  const [isRemote, setIsRemote] = useState(false)

  // Track current generation for stale caption filtering
  const currentGenerationRef = useRef(0)

  // ── Detect mode on mount ──────────────────────────────────────────
  useEffect(() => {
    getBackendConfig().then((config) => {
      setIsRemote(config.isRemote)
    })
  }, [])

  // ── Apply status from backend snapshot ────────────────────────────
  const applyStatus = useCallback((data: Record<string, unknown>) => {
    setVoiceListening(Boolean(data.conversation_active))
    setDetectorRunning(Boolean(data.is_listening))
    setSttText((data.stt_text as string) ?? '')
    setResponseText((data.response_text as string) ?? '')
    if (data.is_speaking) setAiState('responding')
    else if (data.is_processing) setAiState('thinking')
    else if (data.conversation_active) setAiState('listening')
    else setAiState('idle')

    window.dispatchEvent(
      new CustomEvent('barq:voice-status', {
        detail: {
          conversation_active: Boolean(data.conversation_active),
          is_listening: Boolean(data.is_listening),
          is_speaking: Boolean(data.is_speaking),
          is_processing: Boolean(data.is_processing),
          language: data.language ?? 'en',
          tts_voice: data.tts_voice ?? 'en-US-JennyNeural',
        },
      }),
    )
  }, [])

  // ── Toggle detector ───────────────────────────────────────────────
  const toggleDetector = useCallback(async () => {
    const wasRunning = detectorRunning
    setDetectorRunning(!detectorRunning)
    try {
      if (wasRunning) await api('/voice/stop', {})
      else await api('/voice/start', {})
    } catch {
      setDetectorRunning(wasRunning)
    }
  }, [detectorRunning])

  const startDetector = useCallback(async () => {
    try {
      await api('/voice/start', {})
      setDetectorRunning(true)
    } catch {
      // silent
    }
  }, [])

  const stopDetector = useCallback(async () => {
    try {
      await api('/voice/stop', {})
      setDetectorRunning(false)
    } catch {
      // silent
    }
  }, [])

  // ── WebSocket + HTTP polling (always connects to LOCAL voice pipeline) ──
  useEffect(() => {
    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let httpPollTimer: ReturnType<typeof setTimeout> | null = null
    let syncPollTimer: ReturnType<typeof setTimeout> | null = null
    let wsFailedAt: number | null = null
    let wsRetryCount = 0
    let mounted = true

    /** Exponential backoff: 1s, 2s, 4s, 8s… capped at 30s */
    const getReconnectDelay = (): number => {
      const delay = Math.min(1000 * Math.pow(2, wsRetryCount), 30_000)
      wsRetryCount++
      return delay
    }

    /** Fetch /voice/status and apply to local state (syncs detectorRunning, etc.) */
    const fetchStatus = async (): Promise<void> => {
      if (!mounted) return
      try {
        const d = await api('/voice/status')
        if (d && typeof d === 'object' && mounted) {
          applyStatus(d as Record<string, unknown>)
        }
      } catch {
        // silent
      }
    }

    const startHttpPoll = () => {
      if (httpPollTimer) return
      const poll = async () => {
        if (!mounted) return
        await fetchStatus()
        if (mounted) httpPollTimer = setTimeout(poll, 2000)
      }
      poll()
    }

    /** Periodic status sync poll (every 5s, even when WS is connected).
     * Catches state desyncs where the backend detector starts/stops
     * but the WebSocket misses the state_change message.
     */
    const startSyncPoll = () => {
      if (syncPollTimer) clearTimeout(syncPollTimer)
      const poll = async () => {
        if (!mounted) return
        await fetchStatus()
        if (mounted) syncPollTimer = setTimeout(poll, 5000)
      }
      poll()
    }

    const connect = async (): Promise<void> => {
      try {
        const url = await getVoiceWsUrl()
        ws = new WebSocket(url)
        wsFailedAt = null
      } catch {
        if (!wsFailedAt) wsFailedAt = Date.now()
        if (wsFailedAt && Date.now() - wsFailedAt > 5000) startHttpPoll()
        const delay = getReconnectDelay()
        console.debug(`[Voice WS] Connect failed, retrying in ${delay}ms (attempt ${wsRetryCount})`)
        reconnectTimer = setTimeout(() => void connect(), delay)
        return
      }

      ws.onopen = () => {
        setWsConnected(true)
        wsFailedAt = null
        wsRetryCount = 0
        if (httpPollTimer) {
          clearTimeout(httpPollTimer)
          httpPollTimer = null
        }
        // On reconnect, sync state from backend immediately
        void fetchStatus()
        startSyncPoll()
      }

      ws.onmessage = (event) => {
        if (!mounted) return
        try {
          const data = JSON.parse(event.data)
          const gen = currentGenerationRef.current

          switch (data.type) {
            case 'state_change':
              if (data.status === 'listening') {
                setAiState('listening')
                setVoiceListening(true)
                setDetectorRunning(true)
                currentGenerationRef.current++
                setResponseText('')
                setSttText('')
              } else if (data.status === 'processing') {
                setAiState('thinking')
                currentGenerationRef.current++
              } else if (data.status === 'speaking') {
                setAiState((prev) => (prev !== 'responding' ? 'responding' : prev))
              } else if (data.status === 'idle') {
                setAiState('idle')
                setVoiceListening(false)
                setDetectorRunning(false)
              }
              break

            case 'caption_user':
              setSttText(data.text)
              if (data.isFinal) {
                setVoiceListening(true)
                setDetectorRunning(true)
                setAiState('listening')
                currentGenerationRef.current++
                setResponseText('')
              }
              break

            case 'caption_barq': {
              const capturedGen = gen
              setResponseText((prev) => {
                if (capturedGen !== currentGenerationRef.current) return prev
                return prev + data.text
              })
              setAiState((prev) => (prev !== 'responding' ? 'responding' : prev))
              break
            }

            case 'voice_status':
              applyStatus(data)
              break
          }
        } catch {
          // ignore malformed messages
        }
      }

      ws.onclose = () => {
        setWsConnected(false)
        if (syncPollTimer) {
          clearTimeout(syncPollTimer)
          syncPollTimer = null
        }
        if (!mounted) return
        if (!wsFailedAt) wsFailedAt = Date.now()
        if (Date.now() - wsFailedAt > 5000) startHttpPoll()
        const delay = getReconnectDelay()
        console.debug(`[Voice WS] Disconnected, retrying in ${delay}ms (attempt ${wsRetryCount})`)
        reconnectTimer = setTimeout(connect, delay)
      }

      ws.onerror = () => {
        ws?.close()
      }
    }

    connect()

    // ── Initial HTTP fetch to avoid false "disabled" flash ──────────
    void fetchStatus()

    return () => {
      mounted = false
      if (ws) {
        ws.onclose = null
        ws.close()
      }
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (httpPollTimer) clearTimeout(httpPollTimer)
      if (syncPollTimer) clearTimeout(syncPollTimer)
    }
  }, [applyStatus])

  return (
    <VoiceContext.Provider
      value={{
        voiceListening,
        detectorRunning,
        wsConnected,
        aiState,
        sttText,
        responseText,
        isRemote,
        toggleDetector,
        startDetector,
        stopDetector,
      }}
    >
      {children}
    </VoiceContext.Provider>
  )
}
