import { useState, useEffect } from 'react'
import { Mic, LayoutDashboard, StickyNote, ImageIcon, Smartphone, Settings } from 'lucide-react'

export type NavTab = 'DASHBOARD' | 'NOTES' | 'GALLERY' | 'PHONE' | 'SETTINGS'

export type AIState = 'idle' | 'listening' | 'thinking' | 'responding'

const AI_STATE_LABELS: Record<AIState, string> = {
  idle: 'Idle',
  listening: 'Listening',
  thinking: 'Thinking',
  responding: 'Responding',
}

const AI_STATE_DOT_COLORS: Record<AIState, string> = {
  idle: 'bg-purple-400 shadow-[0_0_6px_rgba(168,85,247,0.5)]',
  listening: 'bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.5)]',
  thinking: 'bg-slate-200 shadow-[0_0_6px_rgba(226,232,240,0.3)]',
  responding: 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]',
}

const AI_STATE_BORDER_COLORS: Record<AIState, string> = {
  idle: 'border-purple-500/20',
  listening: 'border-amber-500/20',
  thinking: 'border-slate-400/20',
  responding: 'border-emerald-500/20',
}

interface NavbarProps {
  activeTab: NavTab
  onTabChange: (tab: NavTab) => void
  isConnected: boolean
  isSpeaking: boolean
  isMuted: boolean
  isConversationActive?: boolean
  onMicToggle: () => void
  aiState?: AIState
  language?: string         // 'en' or 'hi' — for language indicator badge
  ttsVoice?: string         // e.g. 'en-US-JennyNeural', 'hi-IN-SwaraNeural'
}

const tabs: { id: NavTab; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'DASHBOARD', label: 'Command', icon: LayoutDashboard },
  { id: 'NOTES', label: 'Notes', icon: StickyNote },
  { id: 'GALLERY', label: 'Gallery', icon: ImageIcon },
  { id: 'PHONE', label: 'Mobile', icon: Smartphone },
  { id: 'SETTINGS', label: 'Settings', icon: Settings },
]

// ── Language indicator helper ───────────────────────────────────────────

function parseVoiceDisplayName(voiceId: string): string {
  const parts = voiceId.split('-')
  const raw = parts.slice(2).join(' ')
  return raw.replace(/Neural$/i, '').trim() || voiceId
}

export function Navbar({ activeTab, onTabChange, isConnected, isSpeaking, isMuted, onMicToggle, aiState = 'idle', language = 'en', ttsVoice = 'en-US-JennyNeural' }: NavbarProps): JSX.Element {
  const [dockVisible, setDockVisible] = useState(true)

  useEffect(() => {
    const handler = (e: Event) => {
      setDockVisible((e as CustomEvent).detail.visible)
    }
    window.addEventListener('barq:dock-visibility', handler)
    return () => window.removeEventListener('barq:dock-visibility', handler)
  }, [])

  return (
    <header className={`h-14 w-full flex items-center justify-between px-5 border-b border-white/[0.06] z-50 flex-shrink-0 transition-all duration-500 ${
      dockVisible
        ? 'bg-white/[0.06] backdrop-blur-md'
        : 'bg-white/[0.02] backdrop-blur-sm'
    }`}>
      {/* Left: Logo */}
      <div className="flex items-center gap-2.5 w-48">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-400 to-cyan-600 flex items-center justify-center shadow-[0_0_12px_rgba(0,229,255,0.15)]">
          <Mic className="w-4 h-4 text-[#0A0A0F]" />
        </div>
        <div className="flex flex-col leading-none">
          <span className="font-orbitron font-bold text-sm text-cyan-300 tracking-wider">BARQ</span>
          <span className="text-[7px] font-share-tech text-zinc-500 uppercase tracking-[0.2em]">Neural OS</span>
        </div>
      </div>

      {/* Center: Tab Navigation — glass pill */}
      <div className="flex items-center gap-1 bg-white/5 p-1 rounded-2xl border border-white/10 backdrop-blur-md shadow-xl">
        {tabs.map((tab) => {
          const Icon = tab.icon
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`cursor-pointer px-3.5 py-1.5 text-[10px] font-bold tracking-widest uppercase rounded-lg transition-all duration-200 flex items-center gap-2 ${
                isActive
                  ? 'bg-cyan-500/12 text-cyan-300 border border-cyan-500/25 shadow-[0_0_12px_rgba(0,229,255,0.1)]'
                  : 'text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.03] border border-transparent'
              }`}
            >
              <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-cyan-300' : 'text-zinc-600'}`} />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* Right: Status indicators */}
      <div className="flex items-center justify-end gap-3 w-72">
        {/* ── Language Indicator Badge ── */}
        <div
          className={`flex items-center gap-1.5 px-2 py-1 rounded-lg border backdrop-blur-md transition-all duration-300 ${
            language === 'hi'
              ? 'border-orange-500/25 bg-orange-500/8'
              : 'border-cyan-500/20 bg-cyan-500/8'
          }`}
          title={`Language: ${language === 'hi' ? 'Hindi' : 'English'} — TTS: ${ttsVoice}`}
        >
          <span className="text-[10px] leading-none">
            {language === 'hi' ? '🇮🇳' : '🇬🇧'}
          </span>
          <span className={`text-[8px] font-mono font-bold tracking-wider ${
            language === 'hi' ? 'text-orange-300' : 'text-cyan-300'
          }`}>
            {language.toUpperCase()}
          </span>
          <span className="text-[7px] font-mono text-zinc-500 leading-none">
            {parseVoiceDisplayName(ttsVoice)}
          </span>
        </div>

        {/* ── AI State Indicator ── */}
        <div
          className={`flex items-center gap-1.5 px-2 py-1 rounded-lg border backdrop-blur-md transition-all duration-300 ${AI_STATE_BORDER_COLORS[aiState]} bg-white/[0.03]`}
          title={`AI State: ${AI_STATE_LABELS[aiState]}`}
        >
          <span className={`relative w-2 h-2 rounded-full ${AI_STATE_DOT_COLORS[aiState]}`}>
            <span className="absolute inset-0 rounded-full animate-ping opacity-30" style={{ backgroundColor: 'inherit' }} />
          </span>
          <span className="text-[8px] font-mono tracking-wider uppercase text-zinc-400">
            {AI_STATE_LABELS[aiState]}
          </span>
        </div>

        {/* ── Mic Status ── */}
        <button
          onClick={onMicToggle}
          className={`relative flex items-center gap-2 px-2.5 py-1.5 rounded-lg border backdrop-blur-md transition-all duration-300 ${
            isMuted
              ? 'border-red-500/20 text-red-400 bg-red-500/5'
              : isSpeaking
                ? 'border-emerald-500/30 text-emerald-400 bg-emerald-500/10 shadow-[0_0_12px_rgba(16,185,129,0.15)]'
                : 'border-zinc-800 text-zinc-500 hover:text-zinc-300 hover:border-zinc-700 bg-white/[0.02]'
          }`}
          title={isMuted ? 'Microphone muted — click to unmute' : isSpeaking ? 'Speaking — click to mute' : 'Microphone idle — click to mute'}
        >
          {!isMuted && (
            <span className={`absolute inset-0 rounded-lg ${
              isSpeaking
                ? 'animate-ping bg-emerald-500/20'
                : 'animate-pulse bg-emerald-500/10'
            }`} />
          )}
          <div className={`relative w-2 h-2 rounded-full transition-all duration-300 ${
            isMuted
              ? 'bg-red-400'
              : isSpeaking
                ? 'bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.7)]'
                : 'bg-emerald-400/60 shadow-[0_0_6px_rgba(16,185,129,0.3)]'
          }`}>
            {isSpeaking && (
              <span className="absolute inset-0 rounded-full bg-emerald-400 animate-ping opacity-60" />
            )}
          </div>
          <span className={`text-[9px] font-mono tracking-wider uppercase relative z-10 ${
            isSpeaking ? 'font-bold' : ''
          }`}>
            {isMuted ? 'Muted' : isSpeaking ? 'ON AIR' : 'Mic On'}
          </span>
        </button>

        {/* ── Connection Status Dot ── */}
        <div className={`relative w-2 h-2 rounded-full shadow-[0_0_8px_currentColor] ${isConnected ? 'bg-emerald-400 text-emerald-400' : 'bg-red-400 text-red-400'}`}>
          {isConnected && (
            <span className="absolute inset-0 rounded-full bg-emerald-400 animate-ping opacity-40" />
          )}
        </div>
      </div>
    </header>
  )
}
