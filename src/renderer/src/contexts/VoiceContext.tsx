import { createContext, useContext, useState, useCallback, useEffect, useRef, type ReactNode } from 'react'
import { api } from '../utils/api'

// ─── Types ──────────────────────────────────────────────────────────────────

type AIState = 'idle' | 'listening' | 'thinking' | 'responding'

interface VoiceContextValue {
  voiceListening: boolean
  detectorRunning: boolean
  wsConnected: boolean
  aiState: AIState
  sttText: string
  responseText: string
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
  toggleDetector: async () => {},
  startDetector: async () => {},
  stopDetector: async () => {},
})

export function useVoice(): VoiceContextValue {
  return useContext(VoiceContext)
}

// ─── Provider ────────────────────────────────────────────────────────────────

const WS_URL = 'ws://127.0.0.1:8970/voice/ws/status'

export function VoiceProvider({ children }: { children: ReactNode }): JSX.Element {
  const [voiceListening, setVoiceListening] = useState(false)
  const [detectorRunning, setDetectorRunning] = useState(false)
  const [wsConnected, setWsConnected] = useState(false)
  const [aiState, setAiState] = useState<AIState>('idle')
  const [sttText, setSttText] = useState('')
  const [responseText, setResponseText] = useState('')

  // Track current generation for stale caption filtering
  const currentGenerationRef = useRef(0)

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

  // ── WebSocket + HTTP polling ───────────────────────────────────────
  useEffect(() => {
    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let httpPollTimer: ReturnType<typeof setTimeout> | null = null
    let wsFailedAt: number | null = null
    let mounted = true

    const startHttpPoll = () => {
      if (httpPollTimer) return
      const poll = async () => {
        if (!mounted) return
        try {
          const d = await api('/voice/status')
          if (d && typeof d === 'object' && mounted) {
            applyStatus(d as Record<string, unknown>)
          }
        } catch {
          // silent
        }
        if (mounted) httpPollTimer = setTimeout(poll, 2000)
      }
      poll()
    }

    const connect = () => {
      try {
        ws = new WebSocket(WS_URL)
        wsFailedAt = null
      } catch {
        if (!wsFailedAt) wsFailedAt = Date.now()
        if (wsFailedAt && Date.now() - wsFailedAt > 5000) startHttpPoll()
        reconnectTimer = setTimeout(connect, 2000)
        return
      }

      ws.onopen = () => {
        setWsConnected(true)
        wsFailedAt = null
        if (httpPollTimer) {
          clearTimeout(httpPollTimer)
          httpPollTimer = null
        }
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
        if (!mounted) return
        if (!wsFailedAt) wsFailedAt = Date.now()
        if (Date.now() - wsFailedAt > 5000) startHttpPoll()
        reconnectTimer = setTimeout(connect, 2000)
      }

      ws.onerror = () => {
        ws?.close()
      }
    }

    connect()

    // ── Initial HTTP fetch to avoid false "disabled" flash ──────────
    ;(async () => {
      if (!mounted) return
      try {
        const initial = await api('/voice/status')
        if (initial && typeof initial === 'object' && mounted) {
          applyStatus(initial as Record<string, unknown>)
        }
      } catch {
        // backend unreachable — WS will retry
      }
    })()

    return () => {
      mounted = false
      if (ws) {
        ws.onclose = null
        ws.close()
      }
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (httpPollTimer) clearTimeout(httpPollTimer)
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
        toggleDetector,
        startDetector,
        stopDetector,
      }}
    >
      {children}
    </VoiceContext.Provider>
  )
}
