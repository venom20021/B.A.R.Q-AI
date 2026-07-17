import { Mic, LayoutDashboard, StickyNote, ImageIcon, Smartphone, Settings } from 'lucide-react'

export type NavTab = 'DASHBOARD' | 'NOTES' | 'GALLERY' | 'PHONE' | 'SETTINGS'

export type AIState = 'idle' | 'listening' | 'thinking' | 'responding'

interface NavbarProps {
  activeTab: NavTab
  onTabChange: (tab: NavTab) => void
  isConnected: boolean
  isSpeaking: boolean
  isMuted: boolean
  isConversationActive?: boolean
  onMicToggle: () => void
  aiState?: AIState
  language?: string
  ttsVoice?: string
}

const tabs: { id: NavTab; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'DASHBOARD', label: 'Command', icon: LayoutDashboard },
  { id: 'NOTES', label: 'Notes', icon: StickyNote },
  { id: 'GALLERY', label: 'Gallery', icon: ImageIcon },
  { id: 'PHONE', label: 'Mobile', icon: Smartphone },
  { id: 'SETTINGS', label: 'Settings', icon: Settings },
]

export function Navbar({
  activeTab,
  onTabChange,
  isConnected,
  isSpeaking,
  isMuted,
  onMicToggle,
}: NavbarProps): JSX.Element {
  return (
    <>
      {/* ── Floating Transparent Header ─────────────────────────────── */}
      <header className="absolute top-0 left-0 w-full z-50 bg-transparent flex items-center justify-between px-8 py-6 pointer-events-none">
        {/* Left: Minimal BARQ logo */}
        <div className="flex items-center gap-2 pointer-events-auto">
          <div className="w-6 h-6 rounded-md bg-gradient-to-br from-cyan-400 to-cyan-600 flex items-center justify-center shadow-[0_0_8px_rgba(0,229,255,0.12)]">
            <Mic className="w-3 h-3 text-[#0A0A0F]" />
          </div>
        </div>

        {/* Right: Minimal mic + connection */}
        <div className="flex items-center gap-3 pointer-events-auto">
          <button
            onClick={onMicToggle}
            className="flex items-center gap-1.5 px-2 py-1 rounded-lg transition-all duration-200 hover:bg-white/[0.04]"
            title={isMuted ? 'Muted — click to unmute' : 'Mic on — click to mute'}
          >
            <div
              className={`w-1.5 h-1.5 rounded-full transition-all duration-300 ${
                isMuted
                  ? 'bg-red-400'
                  : isSpeaking
                    ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.6)]'
                    : 'bg-emerald-400/50'
              }`}
            >
              {isSpeaking && (
                <span className="absolute inset-0 rounded-full bg-emerald-400 animate-ping opacity-40" />
              )}
            </div>
            <span className={`text-[9px] font-mono tracking-wider uppercase ${
              isMuted ? 'text-red-400' : isSpeaking ? 'text-emerald-400' : 'text-slate-500'
            }`}>
              {isMuted ? 'Muted' : isSpeaking ? 'ON AIR' : 'Mic'}
            </span>
          </button>

          {/* Connection dot */}
          <div className={`w-1.5 h-1.5 rounded-full ${
            isConnected ? 'bg-emerald-400/60 shadow-[0_0_6px_rgba(52,211,153,0.3)]' : 'bg-red-400/60'
          }`} />
        </div>
      </header>

      {/* ── Top-Center Navigation Links ───────────────────────────── */}
   <nav className="fixed top-7 left-1/2 -translate-x-1/2 z-40 pointer-events-none">
        {/* Added the glassmorphic pill background classes back to this div */}
        <div className="flex items-center gap-1 pointer-events-auto bg-slate-950/60 backdrop-blur-md border border-white/10 rounded-full px-2 py-1 shadow-2xl">
          {tabs.map((tab) => {
            const Icon = tab.icon
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => onTabChange(tab.id)}
                className={`relative flex flex-col items-center gap-0.5 px-4 py-2 text-[10px] font-medium tracking-[0.12em] uppercase transition-colors duration-200 group ${
                  isActive
                    ? 'text-cyan-50'
                    : 'text-slate-400 hover:text-cyan-50'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 transition-colors duration-200 ${
                  isActive ? 'text-cyan-50' : 'text-slate-400 group-hover:text-cyan-50'
                }`} />
                <span>{tab.label}</span>
                
            

                {/* Active glowing dot indicator */}
                {isActive && (
                  <span className="absolute -bottom-0.5 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.7)]" />
                )}
              </button>
            )
          })}
        </div>
      </nav>
    </>
  )
}
