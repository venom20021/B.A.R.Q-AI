import { useState, useCallback, useRef, useEffect } from 'react'
import { MessageSquare, Mic, Send, Loader2 } from 'lucide-react'
import { motion } from 'framer-motion'

interface ChatMessage {
  role: 'user' | 'barq'
  text: string
}

export function ChatPage(): JSX.Element {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [voiceStatus, setVoiceStatus] = useState<{ is_listening?: boolean; recent_commands?: { transcript: string; created_at: string }[] } | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const fetchVoiceStatus = useCallback(async () => {
    try {
      const resp = await window.barq?.python.request('/voice/status')
      if (resp && typeof resp === 'object') setVoiceStatus(resp as typeof voiceStatus)
    } catch { /* ignore */ }
  }, [])

  const sendMessage = useCallback(async () => {
    if (!input.trim()) return
    const text = input.trim()
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', text }])
    setSending(true)

    try {
      // Friendly response mapping for known command actions
      const FRIENDLY_RESPONSES: Record<string, string> = {
        show_diagnostics: 'Showing system diagnostics',
        scan_jobs: 'Scanning for new job listings',
        navigate: 'Navigating to the requested page',
        toggle_mute: 'Toggling microphone',
        weather: 'Fetching weather data',
        help: 'Here are the available commands',
      }

      // Try AI chat first for natural conversation
      const resp = await window.barq?.python.request('/voice/chat/text', {
        method: 'POST',
        body: JSON.stringify({ message: text, language: 'en' }),
        headers: { 'Content-Type': 'application/json' },
      })
      if (resp && typeof resp === 'object') {
        const data = resp as { text?: string; action?: string }
        const friendlyText = data.action ? FRIENDLY_RESPONSES[data.action] : undefined
        const responseText = data.text || friendlyText || 'Command processed.'

        // Dispatch custom event for known command actions
        if (data.action && data.action !== 'conversation') {
          window.dispatchEvent(
            new CustomEvent('barq:voice-command', { detail: { action: data.action } })
          )
        }

        setMessages((prev) => [...prev, { role: 'barq', text: responseText }])
      } else {
        setMessages((prev) => [...prev, { role: 'barq', text: 'Command processed.' }])
      }
    } catch {
      setMessages((prev) => [...prev, { role: 'barq', text: 'Failed to process command.' }])
    }
    setSending(false)
  }, [input])

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">CHAT</h1>
          <p className="text-sm font-rajdhani text-dim-400 mt-1">Conversation with BARQ AI</p>
        </div>
        <button onClick={fetchVoiceStatus} className="btn-glass text-xs">
          {voiceStatus?.is_listening ? '🎤 Active' : '🎤 Check Status'}
        </button>
      </motion.div>

      <div className="flex flex-col h-[calc(100vh-12rem)]">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="flex-1 glass-card overflow-y-auto mb-4 scroll-cyan p-4">
          {messages.length === 0 ? (
            <div className="text-center py-12">
              <MessageSquare className="w-12 h-12 text-dim-500 mx-auto mb-3" />
              <p className="text-dim-400 text-sm font-exo">Start a conversation with BARQ</p>
              <p className="text-dim-500 text-xs mt-1 font-exo">Type a command or say it naturally</p>
              {voiceStatus?.recent_commands && voiceStatus.recent_commands.length > 0 && (
                <div className="mt-4 space-y-1">
                  <p className="text-hud font-share-tech text-dim-500 mb-1">Recent voice commands:</p>
                  {voiceStatus.recent_commands.slice(0, 3).map((c, i) => (
                    <p key={i} className="text-xs font-exo text-dim-400">"{c.transcript}"</p>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[80%] rounded-lg px-4 py-2 ${
                    msg.role === 'user'
                      ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20'
                      : 'bg-void-700/60 text-ghost border border-cyan-500/8'
                  }`}>
                    <p className="text-sm font-exo">{msg.text}</p>
                  </div>
                </div>
              ))}
              {sending && (
                <div className="flex justify-start">
                  <div className="bg-void-700/60 rounded-lg px-4 py-2 border border-cyan-500/8">
                    <Loader2 className="w-4 h-4 text-cyan-300 animate-spin" />
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
          )}
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-2">
          <button className="p-3 rounded-lg bg-void-700/80 hover:bg-void-600/80 text-dim-400 hover:text-cyan-300 transition-colors border border-cyan-500/10">
            <Mic className="w-5 h-5" />
          </button>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
            placeholder="Type a command or ask a question..."
            className="input-cyan flex-1"
          />
          <button onClick={sendMessage} disabled={sending || !input.trim()} className="btn-cyan p-3">
            {sending ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
          </button>
        </motion.div>
      </div>
    </div>
  )
}
