import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Mic, Send, Loader2, MessageSquare, X, Volume2, VolumeX } from 'lucide-react'
import { AudioWaveform } from './AudioWaveform'
import { useMicrophoneAnalyser } from '../hooks/useMicrophoneAnalyser'

interface Message {
  id: string
  role: 'user' | 'ai'
  text: string
  timestamp: number
}

interface AiChatPanelProps {
  isMuted?: boolean
  onMuteToggle?: () => void
}

export function AiChatPanel({ isMuted = false, onMuteToggle }: AiChatPanelProps): JSX.Element {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'ai',
      text: 'System online. Awaiting your command.',
      timestamp: Date.now(),
    },
  ])
  const [input, setInput] = useState('')
  const [isListening, setIsListening] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [transcript, setTranscript] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const recognitionRef = useRef<SpeechRecognition | null>(null)
  const [speechSupported, setSpeechSupported] = useState(false)
  const micAnalyser = useMicrophoneAnalyser()

  // Check browser speech recognition support
  useEffect(() => {
    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition
    setSpeechSupported(!!SpeechRecognitionAPI)
  }, [])

  // Keep a ref to the audio element for playing TTS responses
  const audioRef = useRef<HTMLAudioElement | null>(null)

  // Speak AI response via backend audio (Edge-TTS, same voice as wake greeting)
  const speakAudio = useCallback((audioBase64: string): void => {
    if (isMuted || !audioBase64) return
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
  }, [isMuted])

  // Cancel audio when muted
  useEffect(() => {
    if (isMuted && audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }
  }, [isMuted])

  // Cleanup audio ref on unmount
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
      }
    }
  }, [])

  interface ChatResponse {
    text: string
    audio_base64?: string
  }

  // Send message to AI backend and get text + audio
  const sendToAI = useCallback(async (text: string): Promise<ChatResponse> => {
    try {
      const resp = await window.barq?.python.request('/voice/chat', {
        method: 'POST',
        body: JSON.stringify({ message: text, language: 'en' }),
        headers: { 'Content-Type': 'application/json' },
      })
      if (resp && typeof resp === 'object') {
        const d = resp as ChatResponse
        return {
          text: d.text || 'Command processed.',
          audio_base64: d.audio_base64,
        }
      }
      return { text: 'Command processed.' }
    } catch {
      return { text: 'Error connecting to AI backend.' }
    }
  }, [])

  // Start speech recognition on open
  useEffect(() => {
    if (!isOpen) {
      setIsListening(false)
      setTranscript('')
      micAnalyser.stop()
      // Stop speech recognition
      if (recognitionRef.current) {
        recognitionRef.current.stop()
        recognitionRef.current = null
      }
      return
    }

    // Start mic analyser for waveform visualization
    micAnalyser.start().then(() => setIsListening(true))
    inputRef.current?.focus()

    // Start speech recognition if supported
    if (speechSupported) {
      const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition
      const recognition = new SpeechRecognitionAPI()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = 'en-US'

      const handleResult = (event: SpeechRecognitionEvent): void => {
        let finalTranscript = ''
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i]
          if (result.isFinal) {
            finalTranscript += result[0].transcript
          }
        }
        if (finalTranscript) {
          const trimmed = finalTranscript.trim()
          if (trimmed.length > 1) {
            setTranscript(trimmed)
            const userMsg: Message = { id: `user-${Date.now()}`, role: 'user', text: trimmed, timestamp: Date.now() }
            setMessages((prev) => [...prev, userMsg])
            setIsProcessing(true)
            sendToAI(trimmed).then((res) => {
              setMessages((prev) => [...prev, { id: `ai-${Date.now()}`, role: 'ai', text: res.text, timestamp: Date.now() }])
              setIsProcessing(false)
              if (res.audio_base64) speakAudio(res.audio_base64)
            })
          }
        }
      }

      recognition.onresult = handleResult
      recognition.onerror = () => { /* Speech recognition error — user can still type */ }

      try {
        recognition.start()
        recognitionRef.current = recognition
      } catch {
        // Recognition already started
      }
    }

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop()
        recognitionRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, speechSupported])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(async (): Promise<void> => {
    const text = input.trim()
    if (!text || isProcessing) return
    const userMsg: Message = { id: `user-${Date.now()}`, role: 'user', text, timestamp: Date.now() }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setIsProcessing(true)
    const res = await sendToAI(text)
    const aiMsg: Message = { id: `ai-${Date.now()}`, role: 'ai', text: res.text, timestamp: Date.now() }
    setMessages((prev) => [...prev, aiMsg])
    setIsProcessing(false)
    if (res.audio_base64) speakAudio(res.audio_base64)
  }, [input, isProcessing, sendToAI, speakAudio])

  return (
    <>
      {/* Toggle button — always visible on right edge */}
      <motion.button
        onClick={() => setIsOpen((p) => !p)}
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        className="fixed bottom-6 right-6 z-50 flex items-center justify-center w-12 h-12 rounded-full bg-[#00E5FF] text-black shadow-[0_0_20px_rgba(0,229,255,0.3)] hover:shadow-[0_0_30px_rgba(0,229,255,0.5)] transition-shadow duration-300"
      >
        {isOpen ? <X className="w-5 h-5" /> : <MessageSquare className="w-5 h-5" />}
      </motion.button>

      {/* Chat popup */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="fixed bottom-24 right-6 z-40 w-[380px] h-[520px] luxury-glass rounded-2xl flex flex-col overflow-hidden border border-[#00E5FF]/20 shadow-2xl"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-[#00E5FF]/10">
              <div className="flex items-center gap-2.5">
                <div className="w-2 h-2 rounded-full bg-[#00E5FF] shadow-[0_0_8px_rgba(0,229,255,0.6)] animate-pulse" />
                <span className="text-xs font-rajdhani font-semibold text-[#E2E8F0]/80 tracking-wider uppercase">AI Interface</span>
              </div>
              <div className="flex items-center gap-1.5">
                {/* Mute button for TTS responses */}
                <button
                  onClick={onMuteToggle}
                  className={`flex items-center gap-1 px-2 py-1 rounded-lg text-[9px] font-share-tech tracking-wider uppercase transition-all ${
                    isMuted
                      ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                      : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                  }`}
                  title={isMuted ? 'Unmute voice responses' : 'Mute voice responses'}
                >
                  {isMuted ? <VolumeX className="w-3 h-3" /> : <Volume2 className="w-3 h-3" />}
                  <span>{isMuted ? 'Muted' : 'Voice'}</span>
                </button>
                <button onClick={() => setIsOpen(false)} className="p-1 rounded-lg hover:bg-[#00E5FF]/10 transition-colors">
                  <X className="w-3.5 h-3.5 text-[#E2E8F0]/30" />
                </button>
              </div>
            </div>

            {/* Audio waveform */}
            <div className="relative flex items-center justify-center py-2 border-b border-[#00E5FF]/5 bg-[#00E5FF]/2">
              {micAnalyser.error && (
                <div className="absolute inset-0 flex items-center justify-center bg-[#0A0A0F]/80 backdrop-blur-sm z-10">
                  <span className="text-[10px] font-share-tech text-[#00E5FF]/60 uppercase tracking-wider">
                    {micAnalyser.error}
                  </span>
                </div>
              )}
              <AudioWaveform
                isActive={isListening}
                analyser={{
                  analyserRef: micAnalyser.analyserRef,
                  dataArrayRef: micAnalyser.dataArrayRef,
                }}
              />
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto scroll-cyan p-3 space-y-2">
              <AnimatePresence initial={false}>
                {messages.map((msg) => (
                  <motion.div
                    key={msg.id}
                    initial={{ opacity: 0, y: 8, scale: 0.97 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    transition={{ duration: 0.2, ease: 'easeOut' }}
                    className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div className={`max-w-[85%] px-3 py-2 rounded-xl text-xs font-rajdhani leading-relaxed ${
                      msg.role === 'user'
                        ? 'bg-[#00E5FF]/15 text-[#E2E8F0]/90 border border-[#00E5FF]/20'
                        : 'bg-[#0D0D15]/60 text-[#E2E8F0]/70 border border-[#00E5FF]/8'
                    }`}>
                      {msg.text}
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
              {isProcessing && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
                  <div className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-[#0D0D15]/60 border border-[#DC2626]/8">
                    <Loader2 className="w-3 h-3 text-[#00E5FF]/60 animate-spin" />
                    <span className="text-[10px] font-rajdhani text-[#E2E8F0]/40">Processing...</span>
                  </div>
                </motion.div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input area */}
            <div className="p-3 border-t border-[#00E5FF]/10">
              <div className="flex items-center gap-2">
                {/* Mic indicator — active when panel is open */}
                <div className={`relative flex items-center justify-center w-9 h-9 rounded-lg transition-all ${
                  transcript
                    ? 'bg-emerald-500/20 text-emerald-400 shadow-[0_0_12px_rgba(16,185,129,0.2)]'
                    : 'bg-[#00E5FF]/15 text-[#00E5FF] shadow-[0_0_12px_rgba(0,229,255,0.15)]'
                }`}>
                  <Mic className="w-4 h-4" />
                  {!transcript && (
                    <span className="absolute inset-0 rounded-lg animate-ping bg-[#00E5FF]/10" />
                  )}
                </div>
                <input
                  ref={inputRef}
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && void handleSend()}
                  placeholder="Type command or speak..."
                  className="flex-1 bg-[#0D0D15]/60 border border-[#00E5FF]/10 rounded-lg px-3 py-2 text-xs font-rajdhani text-[#E2E8F0]/70 placeholder-[#E2E8F0]/20 outline-none focus:border-[#00E5FF]/30 transition-all duration-200"
                />
                <motion.button
                  onClick={() => void handleSend()}
                  whileTap={{ scale: 0.9 }}
                  disabled={!input.trim() || isProcessing}
                  className="flex items-center justify-center w-9 h-9 rounded-lg bg-[#00E5FF]/20 text-[#00E5FF] hover:bg-[#00E5FF]/30 disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200"
                >
                  <Send className="w-4 h-4" />
                </motion.button>
              </div>
              {/* Status line — transcript + mute state */}
              <div className="flex items-center gap-2 mt-2">
                <div className={`w-1.5 h-1.5 rounded-full transition-all duration-300 ${
                  isListening
                    ? 'bg-emerald-400 shadow-[0_0_6px_rgba(16,185,129,0.6)]'
                    : 'bg-zinc-600'
                }`} />
                <span className="text-[8px] font-share-tech text-[#E2E8F0]/25 tracking-wider uppercase">
                  {isListening ? 'LISTENING' : 'MIC OFFLINE'}
                </span>
                {transcript && (
                  <span className="ml-auto text-[8px] font-rajdhani text-emerald-400/60 truncate max-w-[160px]">
                    &quot;{transcript}&quot;
                  </span>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
