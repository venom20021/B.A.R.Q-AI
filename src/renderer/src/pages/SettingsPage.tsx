import { useState, useEffect, useCallback } from 'react'
import { Settings, Shield, Bell, Mic, Key, Palette, Loader2, CheckCircle } from 'lucide-react'
import { motion } from 'framer-motion'

interface SettingsSection {
  id: string
  label: string
  icon: typeof Settings
  description: string
}

const sections: SettingsSection[] = [
  { id: 'voice', label: 'Voice', icon: Mic, description: 'Wake word, language, speech settings' },
  { id: 'api', label: 'API Keys', icon: Key, description: 'Connect your accounts and services' },
  { id: 'notifications', label: 'Notifications', icon: Bell, description: 'Alerts and digest preferences' },
  { id: 'privacy', label: 'Privacy', icon: Shield, description: 'Data storage and local processing' },
  { id: 'appearance', label: 'Appearance', icon: Palette, description: 'Theme and display settings' },
]

interface VoiceStatus {
  is_listening: boolean
  wake_word: string
  stt_model: string
  tts_model: string
  recent_commands: { transcript: string; created_at: string }[]
}

export function SettingsPage(): JSX.Element {
  const [activeSection, setActiveSection] = useState('voice')
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null)
  const [voiceLoading, setVoiceLoading] = useState(false)
  const [togglingVoice, setTogglingVoice] = useState(false)

  const fetchVoiceStatus = useCallback(async () => {
    setVoiceLoading(true)
    try {
      const resp = await window.barq?.python.request('/voice/status')
      if (resp && typeof resp === 'object') setVoiceStatus(resp as unknown as VoiceStatus)
    } catch { /* ignore */ }
    setVoiceLoading(false)
  }, [])

  const toggleListening = useCallback(async () => {
    setTogglingVoice(true)
    try {
      if (voiceStatus?.is_listening) {
        await window.barq?.python.request('/voice/stop', { method: 'POST' })
      } else {
        await window.barq?.python.request('/voice/start', { method: 'POST' })
      }
      await fetchVoiceStatus()
    } catch { /* ignore */ }
    setTogglingVoice(false)
  }, [voiceStatus, fetchVoiceStatus])

  useEffect(() => {
    void fetchVoiceStatus()
  }, [fetchVoiceStatus])

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">SETTINGS</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">Configure BARQ to work your way</p>
      </motion.div>

      <div className="flex gap-6">
        <motion.div initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} className="w-56 flex-shrink-0 space-y-1">
          {sections.map((section) => {
            const Icon = section.icon
            const isActive = activeSection === section.id
            return (
              <button
                key={section.id}
                onClick={() => setActiveSection(section.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all duration-200 ${
                  isActive ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20' : 'text-dim-400 hover:text-ghost hover:bg-void-600/50 border border-transparent'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span className="text-sm font-rajdhani font-semibold">{section.label}</span>
              </button>
            )
          })}
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex-1 glass-card">
          {activeSection === 'voice' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-1">Voice Settings</h3>
                <p className="text-sm font-rajdhani text-dim-400">Configure voice recognition and wake word</p>
              </div>
              <div className="space-y-4">
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Wake Word</p>
                    <p className="text-xs font-exo text-dim-400">Trigger phrase: &quot;{voiceStatus?.wake_word || 'Hey BARQ'}&quot;</p>
                  </div>
                  <span className={`${voiceStatus?.is_listening ? 'badge-green' : 'badge-dim'}`}>
                    {voiceStatus?.is_listening ? 'Active' : 'Inactive'}
                  </span>
                </div>

                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Speech Engine</p>
                    <p className="text-xs font-exo text-dim-400">{voiceStatus?.stt_model || 'whisper'} (local)</p>
                  </div>
                  <span className="badge-cyan">Local</span>
                </div>

                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">TTS Voice</p>
                    <p className="text-xs font-exo text-dim-400">{voiceStatus?.tts_model || 'Edge TTS'} - Natural</p>
                  </div>
                  <button className="btn-ghost-cyan text-sm">Change</button>
                </div>

                <div className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Always-on Listening</p>
                    <p className="text-xs font-exo text-dim-400">Keep microphone active in background</p>
                  </div>
                  <button
                    onClick={toggleListening}
                    disabled={togglingVoice || voiceLoading}
                    className={`relative w-9 h-5 rounded-full transition-colors ${voiceStatus?.is_listening ? 'bg-cyan-500' : 'bg-dim-500/30'} ${togglingVoice ? 'opacity-50' : ''}`}
                  >
                    <span className={`absolute top-[2px] w-4 h-4 bg-white rounded-full transition-transform ${voiceStatus?.is_listening ? 'translate-x-[18px]' : 'translate-x-[2px]'}`} />
                  </button>
                </div>

                {voiceStatus?.recent_commands && voiceStatus.recent_commands.length > 0 && (
                  <div className="pt-3 border-t border-cyan-500/8">
                    <p className="text-xs font-share-tech text-dim-500 mb-2 uppercase tracking-wider">Recent Voice Commands</p>
                    {voiceStatus.recent_commands.slice(0, 3).map((c, i) => (
                      <div key={i} className="text-xs font-exo text-dim-400 py-1 flex justify-between">
                        <span>"{c.transcript}"</span>
                        <span className="text-dim-500">{new Date(c.created_at).toLocaleTimeString()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {activeSection === 'api' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-1">API Keys</h3>
                <p className="text-sm font-rajdhani text-dim-400">Connect your accounts to enable automation</p>
              </div>
              <div className="space-y-4">
                {([
                  { name: 'OpenAI', status: 'connected' as const },
                  { name: 'Ollama', status: 'connected' as const },
                  { name: 'LinkedIn', status: 'disconnected' as const },
                  { name: 'YouTube', status: 'disconnected' as const },
                  { name: 'Twitter/X', status: 'disconnected' as const },
                  { name: 'TikTok', status: 'disconnected' as const },
                  { name: 'Instagram', status: 'disconnected' as const },
                ] as const).map((service) => (
                  <div key={service.name} className="flex items-center justify-between py-3 border-b border-cyan-500/10 last:border-0">
                    <span className="text-sm font-rajdhani font-semibold text-ghost">{service.name}</span>
                    {service.status === 'connected' ? (
                      <span className="badge-green flex items-center gap-1">
                        <CheckCircle className="w-3 h-3" />
                        Connected
                      </span>
                    ) : (
                      <button className="btn-glass text-sm">Connect</button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {(activeSection === 'notifications' || activeSection === 'privacy' || activeSection === 'appearance') && (
            <div className="flex items-center justify-center h-64">
              <p className="text-dim-400 text-sm font-exo">Settings section coming soon</p>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  )
}
