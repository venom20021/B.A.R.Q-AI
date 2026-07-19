import { useState, useCallback, useRef, useEffect, startTransition } from 'react'
import { MessageSquare, Mic, MicOff, Send, Loader2, Trash2, User, Bot, Volume2, StopCircle } from 'lucide-react'
import { motion } from 'framer-motion'
import { api } from '../utils/api'

// ─── Types ─────────────────────────────────────────────────────────────────

interface ChatMessage {
  role: 'user' | 'barq'
  text: string
  timestamp: number
}

// ─── LocalStorage persistence ──────────────────────────────────────────────

const CHAT_HISTORY_KEY = 'barq_chat_history'

function loadChatHistory(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(CHAT_HISTORY_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as ChatMessage[]
      if (Array.isArray(parsed)) return parsed
    }
  } catch { /* ignore */ }
  return []
}

function saveChatHistory(messages: ChatMessage[]): void {
  try {
    // Keep only last 100 messages
    const trimmed = messages.length > 100 ? messages.slice(-100) : messages
    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(trimmed))
  } catch { /* ignore */ }
}

// ─── Web Speech API hook ──────────────────────────────────────────────────

function useSpeechRecognition(): {
  isListening: boolean
  transcript: string
  startListening: () => void
  stopListening: () => void
  supported: boolean
  interimTranscript: string
} {
  const [isListening, setIsListening] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [interimTranscript, setInterimTranscript] = useState('')
  const recognitionRef = useRef<SpeechRecognition | null>(null)
  const isListeningRef = useRef(false)
  const supported = typeof window !== 'undefined' &&
    ('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)

  // Keep ref in sync with state
  useEffect(() => {
    isListeningRef.current = isListening
  }, [isListening])

  useEffect(() => {
    if (!supported) return
    const SpeechRecognitionCls = (window as Record<string, unknown>).SpeechRecognition || (window as Record<string, unknown>).webkitSpeechRecognition
    const recognition = new (SpeechRecognitionCls as new () => SpeechRecognition)()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-US'

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let final = ''
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        if (result.isFinal) {
          final += result[0].transcript
        } else {
          interim += result[0].transcript
        }
      }
      if (final) setTranscript(prev => (prev + ' ' + final).trim())
      setInterimTranscript(interim)
    }

    recognition.onerror = () => { setIsListening(false) }
    recognition.onend = () => {
      // Use ref to avoid stale closure over isListening state
      if (isListeningRef.current) recognition.start()
    }

    recognitionRef.current = recognition
    return () => { recognition.abort() }
  }, [supported])

  const startListening = useCallback(() => {
    if (recognitionRef.current) {
      setTranscript('')
      setInterimTranscript('')
      recognitionRef.current.start()
      setIsListening(true)
    }
  }, [])

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop()
      setIsListening(false)
    }
  }, [])

  return { isListening, transcript, startListening, stopListening, supported, interimTranscript }
}

// ─── Text-to-Speech ───────────────────────────────────────────────────────

function useTextToSpeech() {
  const [speaking, setSpeaking] = useState(false)
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null)

  const speak = useCallback((text: string) => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel()
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.rate = 1.1
      utterance.pitch = 1.0
      utterance.voice = window.speechSynthesis.getVoices().find(v => v.lang.startsWith('en')) ?? null
      utterance.onend = () => setSpeaking(false)
      utterance.onerror = () => setSpeaking(false)
      utteranceRef.current = utterance
      setSpeaking(true)
      window.speechSynthesis.speak(utterance)
    }
  }, [])

  const stop = useCallback(() => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel()
      setSpeaking(false)
    }
  }, [])

  return { speak, stop, speaking }
}

// ─── Main Chat Page ───────────────────────────────────────────────────────

export function ChatPage(): JSX.Element {
  const [messages, setMessages] = useState<ChatMessage[]>(loadChatHistory)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [voiceStatus, setVoiceStatus] = useState<{ is_listening?: boolean; recent_commands?: { transcript: string; created_at: string }[] } | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const { isListening, transcript, interimTranscript, startListening, stopListening, supported: voiceSupported } = useSpeechRecognition()
  const { speak, stop: stopTts, speaking: ttsSpeaking } = useTextToSpeech()

  // Persist messages
  useEffect(() => { saveChatHistory(messages) }, [messages])

  // Auto-scroll
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, sending])

  // Focus input on mount
  useEffect(() => { inputRef.current?.focus() }, [])

  // Consume speech transcript when it arrives
  useEffect(() => {
    if (transcript) {
      startTransition(() => {
        setInput(transcript)
      })
    }
  }, [transcript])

  // Fetch voice backend status
  const fetchVoiceStatus = useCallback(async () => {
    const data = await api('/voice/status')
    if (data && typeof data === 'object') setVoiceStatus(data as typeof voiceStatus)
  }, [])

  useEffect(() => {
    startTransition(() => {
      void fetchVoiceStatus()
    })
  }, [fetchVoiceStatus])

  // Send message
  const sendMessage = useCallback(async (text?: string) => {
    const msg = (text || input).trim()
    if (!msg) return
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', text: msg, timestamp: Date.now() }])
    setSending(true)

    try {
      const data = await api<{ text?: string; action?: string }>('/voice/chat/text', { message: msg, language: 'en' })

      if (data) {
        const responseText = data.text || 'Command processed.'
        setMessages((prev) => [...prev, { role: 'barq', text: responseText, timestamp: Date.now() }])

        // Dispatch command event for known actions
        if (data.action && data.action !== 'conversation') {
          window.dispatchEvent(new CustomEvent('barq:voice-command', { detail: { action: data.action } }))
        }

        // Auto-speak the response
        speak(responseText)
      } else {
        setMessages((prev) => [...prev, { role: 'barq', text: 'I received your message but could not process a response. Please check the backend connection.', timestamp: Date.now() }])
      }
    } catch {
      setMessages((prev) => [...prev, { role: 'barq', text: 'Failed to reach the AI backend. Is the Python sidecar running?', timestamp: Date.now() }])
    }
    setSending(false)
  }, [input, speak])

  // Clear history
  const clearHistory = useCallback(() => {
    setMessages([])
    localStorage.removeItem(CHAT_HISTORY_KEY)
  }, [])

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 h-full flex flex-col">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-cyan-500/10 flex items-center justify-center border border-cyan-500/20">
              <MessageSquare className="w-5 h-5 text-cyan-400" />
            </div>
            <div>
              <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">CHAT</h1>
              <p className="text-sm font-rajdhani text-dim-400 mt-0.5">Conversation with BARQ AI</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Voice status badge */}
            {voiceStatus?.is_listening && (
              <span className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] font-rajdhani font-semibold">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                Voice Active
              </span>
            )}
            <button onClick={fetchVoiceStatus}
              className="px-3 py-1.5 rounded-lg bg-zinc-800/60 text-zinc-400 border border-zinc-700/50 text-[10px] font-rajdhani font-semibold hover:bg-zinc-700/60 transition-all"
            >
              {voiceStatus?.is_listening ? '🎤 Live' : '🎤 Check'}
            </button>
            <button onClick={clearHistory} disabled={messages.length === 0}
              className="p-1.5 rounded-lg text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
              title="Clear chat history"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </motion.div>

      {/* ── Chat Messages ───────────────────────────────────────────────── */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
        className="flex-1 bg-zinc-900/40 backdrop-blur-sm rounded-xl border border-zinc-800/60 overflow-hidden flex flex-col min-h-0"
      >
        <div className="flex-1 overflow-y-auto p-4 space-y-3 scrollbar-thin">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full py-16">
              <MessageSquare className="w-12 h-12 text-zinc-700 mb-3" />
              <p className="text-sm font-exo text-zinc-500">Start a conversation with BARQ</p>
              <p className="text-xs font-exo text-zinc-600 mt-1">Type a message or use the microphone</p>
              {voiceStatus?.recent_commands && voiceStatus.recent_commands.length > 0 && (
                <div className="mt-6 space-y-1.5">
                  <p className="text-[10px] font-mono text-zinc-600 uppercase tracking-wider text-center mb-2">Recent voice commands</p>
                  {voiceStatus.recent_commands.slice(0, 3).map((c, i) => (
                    <button key={i} onClick={() => sendMessage(c.transcript)}
                      className="block text-xs font-exo text-zinc-500 hover:text-zinc-300 bg-zinc-800/30 hover:bg-zinc-800/50 px-3 py-1.5 rounded-lg transition-all"
                    >
                      &ldquo;{c.transcript}&rdquo;
                    </button>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <>
              {messages.map((msg, i) => (
                <motion.div key={i}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div className={`flex items-start gap-2.5 max-w-[80%] ${
                    msg.role === 'user' ? 'flex-row-reverse' : ''
                  }`}>
                    <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${
                      msg.role === 'user'
                        ? 'bg-cyan-500/15 border border-cyan-500/25'
                        : 'bg-violet-500/15 border border-violet-500/25'
                    }`}>
                      {msg.role === 'user'
                        ? <User className="w-3.5 h-3.5 text-cyan-300" />
                        : <Bot className="w-3.5 h-3.5 text-violet-300" />
                      }
                    </div>
                    <div className={`rounded-xl px-4 py-2.5 ${
                      msg.role === 'user'
                        ? 'bg-cyan-500/8 border border-cyan-500/15'
                        : 'bg-zinc-800/40 border border-zinc-800/60'
                    }`}>
                      <p className="text-sm font-exo text-zinc-200 leading-relaxed">{msg.text}</p>
                      <p className="text-[9px] font-mono text-zinc-600 mt-1">
                        {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                    {/* Speak button for assistant messages */}
                    {msg.role === 'barq' && (
                      <button onClick={() => speak(msg.text)}
                        className="p-1 rounded text-zinc-600 hover:text-cyan-400 hover:bg-zinc-800/40 transition-all opacity-0 group-hover:opacity-100"
                        title="Speak this response"
                      >
                        <Volume2 className="w-3 h-3" />
                      </button>
                    )}
                  </div>
                </motion.div>
              ))}
              {/* Typing indicator */}
              {sending && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
                  <div className="flex items-center gap-2.5">
                    <div className="w-7 h-7 rounded-full bg-violet-500/15 border border-violet-500/25 flex items-center justify-center">
                      <Bot className="w-3.5 h-3.5 text-violet-300" />
                    </div>
                    <div className="bg-zinc-800/40 rounded-xl px-4 py-3 border border-zinc-800/60">
                      <div className="flex gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-violet-400/60 animate-bounce" style={{ animationDelay: '0ms' }} />
                        <span className="w-1.5 h-1.5 rounded-full bg-violet-400/60 animate-bounce" style={{ animationDelay: '150ms' }} />
                        <span className="w-1.5 h-1.5 rounded-full bg-violet-400/60 animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}
              <div ref={chatEndRef} />
            </>
          )}
        </div>

        {/* ── Input Area ─────────────────────────────────────────────────── */}
        <div className="border-t border-zinc-800/40 p-4">
          {/* Interim transcript display */}
          {interimTranscript && (
            <div className="mb-2 px-3 py-1.5 rounded-lg bg-cyan-500/5 border border-cyan-500/10">
              <p className="text-xs font-exo text-cyan-300/60 italic">&ldquo;{interimTranscript}&rdquo;</p>
            </div>
          )}
          <div className="flex items-center gap-2">
            {/* Mic button */}
            <button
              onClick={isListening ? stopListening : startListening}
              disabled={!voiceSupported}
              className={`flex items-center justify-center w-10 h-10 rounded-lg transition-all duration-200 ${
                isListening
                  ? 'bg-red-500/20 text-red-400 border border-red-500/30 animate-pulse shadow-[0_0_12px_rgba(239,68,68,0.2)]'
                  : 'bg-zinc-800/60 text-zinc-400 border border-zinc-700/50 hover:bg-zinc-700/60 hover:text-cyan-300'
              } ${!voiceSupported ? 'opacity-30 cursor-not-allowed' : ''}`}
              title={!voiceSupported ? 'Speech recognition not supported in this browser' : isListening ? 'Stop listening' : 'Start voice input'}
            >
              {isListening ? <MicOff className="w-4 h-4" /> : <Mic className="w-4 h-4" />}
            </button>

            {/* Text input */}
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  sendMessage()
                }
              }}
              placeholder="Type a message or click the mic..."
              className="flex-1 bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-4 py-2.5 text-sm font-exo text-zinc-200 outline-none focus:border-cyan-500/40 focus:shadow-[0_0_12px_rgba(34,211,238,0.06)] transition-all placeholder:text-zinc-600"
            />

            {/* Send / Stop TTS button */}
            {ttsSpeaking ? (
              <button onClick={stopTts}
                className="flex items-center justify-center w-10 h-10 rounded-lg bg-amber-500/15 text-amber-400 border border-amber-500/25 hover:bg-amber-500/25 transition-all"
                title="Stop speaking"
              >
                <StopCircle className="w-4 h-4" />
              </button>
            ) : (
              <button onClick={() => sendMessage()} disabled={sending || !input.trim()}
                className="flex items-center justify-center w-10 h-10 rounded-lg bg-cyan-500/15 text-cyan-400 border border-cyan-500/25 hover:bg-cyan-500/25 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
              >
                {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              </button>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  )
}
