import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Mic, Send, Loader2, MessageSquare, X } from 'lucide-react'
import { AudioWaveform } from './AudioWaveform'
import { useMicrophoneAnalyser } from '../hooks/useMicrophoneAnalyser'

interface Message {
  id: string
  role: 'user' | 'ai'
  text: string
  timestamp: number
}

export function AiChatPanel(): JSX.Element {
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
  const [wakeWordDetected, setWakeWordDetected] = useState(false)
  const [transcript, setTranscript] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const micAnalyser = useMicrophoneAnalyser()

  useEffect(() => {
    let wakeTimer: ReturnType<typeof setTimeout>
    if (isOpen) {
      // Auto-start microphone for always-on listening
      micAnalyser.start().then(() => {
        setIsListening(true)
      })
      // Focus input immediately, but delay wake word detection so the
      // "LISTENING FOR WAKE WORD..." phase is visible
      const focusTimer = setTimeout(() => {
        inputRef.current?.focus()
      }, 200)
      wakeTimer = setTimeout(() => {
        setWakeWordDetected(true)
      }, 1200)
    } else {
      // Stop mic when panel closes
      micAnalyser.stop()
      setIsListening(false)
      setWakeWordDetected(false)
    }
    return () => {
      if (wakeTimer !== undefined) clearTimeout(wakeTimer)
    }
  }, [isOpen])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = (): void => {
    const text = input.trim()
    if (!text || isProcessing) return
    const userMsg: Message = { id: `user-${Date.now()}`, role: 'user', text, timestamp: Date.now() }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setIsProcessing(true)
    setTimeout(() => {
      const aiMsg: Message = {
        id: `ai-${Date.now()}`,
        role: 'ai',
        text: `Processing: "${text}". Command acknowledged.`,
        timestamp: Date.now(),
      }
      setMessages((prev) => [...prev, aiMsg])
      setIsProcessing(false)
    }, 800 + Math.random() * 600)
  }

  // Always-on: mic runs continuously while panel is open
  // Wake word is simulated — detected shortly after opening
  // In production, this would use a real wake-word engine (Porcupine, Vosk, etc.)

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
            {/* Header */}              <div className="flex items-center justify-between px-4 py-3 border-b border-[#00E5FF]/10">
              <div className="flex items-center gap-2.5">
                <div className="w-2 h-2 rounded-full bg-[#00E5FF] shadow-[0_0_8px_rgba(0,229,255,0.6)] animate-pulse" />
                <span className="text-xs font-rajdhani font-semibold text-[#E2E8F0]/80 tracking-wider uppercase">AI Interface</span>
              </div>
              <div className="flex items-center gap-1.5">
                {wakeWordDetected && (
                  <span className="text-[9px] font-share-tech text-[#00E5FF] bg-[#00E5FF]/10 px-1.5 py-0.5 rounded uppercase tracking-wider">WAKE</span>
                )}
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
                {/* Always-on mic indicator — no toggle, always active when panel is open */}
                <div className="relative flex items-center justify-center w-9 h-9 rounded-lg bg-[#00E5FF]/15 text-[#00E5FF] shadow-[0_0_12px_rgba(0,229,255,0.15)]">
                  <Mic className="w-4 h-4" />
                  <span className="absolute inset-0 rounded-lg animate-ping bg-[#00E5FF]/10" />
                </div>
                <input
                  ref={inputRef}
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                  placeholder="Type command or speak..."
                  className="flex-1 bg-[#0D0D15]/60 border border-[#00E5FF]/10 rounded-lg px-3 py-2 text-xs font-rajdhani text-[#E2E8F0]/70 placeholder-[#E2E8F0]/20 outline-none focus:border-[#00E5FF]/30 transition-all duration-200"
                />
                <motion.button
                  onClick={handleSend}
                  whileTap={{ scale: 0.9 }}
                  disabled={!input.trim() || isProcessing}
                  className="flex items-center justify-center w-9 h-9 rounded-lg bg-[#00E5FF]/20 text-[#00E5FF] hover:bg-[#00E5FF]/30 disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200"
                >
                  <Send className="w-4 h-4" />
                </motion.button>
              </div>
              {/* Status line — always-on mic state */}
              <div className="flex items-center gap-2 mt-2">
                <div className={`w-1.5 h-1.5 rounded-full transition-all duration-300 ${
                  wakeWordDetected
                    ? 'bg-[#00E5FF] shadow-[0_0_6px_rgba(0,229,255,0.6)]'
                    : 'bg-[#00E5FF]/50 animate-pulse'
                }`} />
                <span className="text-[8px] font-share-tech text-[#E2E8F0]/25 tracking-wider uppercase">
                  {wakeWordDetected ? 'WAKE WORD ACTIVE — LISTENING' : 'ALWAYS-ON — LISTENING FOR WAKE WORD...'}
                </span>
                {transcript && (
                  <span className="ml-auto text-[8px] font-rajdhani text-[#E2E8F0]/30 truncate max-w-[120px]">
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
