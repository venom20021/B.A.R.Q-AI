import { useState } from 'react'
import { Settings, Shield, Bell, Mic, Key, Palette } from 'lucide-react'
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

export function SettingsPage(): JSX.Element {
  const [activeSection, setActiveSection] = useState('voice')

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">SETTINGS</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">
          Configure BARQ to work your way
        </p>
      </motion.div>

      <div className="flex gap-6">
        {/* Settings Navigation */}
        <motion.div
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          className="w-56 flex-shrink-0 space-y-1"
        >
          {sections.map((section) => {
            const Icon = section.icon
            const isActive = activeSection === section.id
            return (
              <button
                key={section.id}
                onClick={() => setActiveSection(section.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-all duration-200 ${
                  isActive
                    ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20'
                    : 'text-dim-400 hover:text-ghost hover:bg-void-600/50 border border-transparent'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span className="text-sm font-rajdhani font-semibold">{section.label}</span>
              </button>
            )
          })}
        </motion.div>

        {/* Settings Content */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex-1 glass-card"
        >
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
                    <p className="text-xs font-exo text-dim-400">Trigger phrase: &quot;Hey BARQ&quot;</p>
                  </div>
                  <span className="badge-green">Active</span>
                </div>
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Speech Engine</p>
                    <p className="text-xs font-exo text-dim-400">OpenAI Whisper (local)</p>
                  </div>
                  <span className="badge-cyan">Local</span>
                </div>
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">TTS Voice</p>
                    <p className="text-xs font-exo text-dim-400">Edge TTS - Natural</p>
                  </div>
                  <button className="btn-ghost-cyan text-sm">Change</button>
                </div>
                <div className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Always-on Listening</p>
                    <p className="text-xs font-exo text-dim-400">Keep microphone active in background</p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" className="sr-only peer" defaultChecked />
                    <div className="w-9 h-5 bg-dim-500/30 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-cyan-500" />
                  </label>
                </div>
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
                  { name: 'LinkedIn', status: 'connected' as const },
                  { name: 'YouTube', status: 'connected' as const },
                  { name: 'Twitter/X', status: 'disconnected' as const },
                  { name: 'TikTok', status: 'disconnected' as const },
                  { name: 'Instagram', status: 'disconnected' as const },
                  { name: 'OpenAI', status: 'connected' as const },
                  { name: 'Ollama', status: 'connected' as const },
                ] as const).map((service) => (
                  <div
                    key={service.name}
                    className="flex items-center justify-between py-3 border-b border-cyan-500/10 last:border-0"
                  >
                    <span className="text-sm font-rajdhani font-semibold text-ghost">{service.name}</span>
                    {service.status === 'connected' ? (
                      <span className="badge-green flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-neural shadow-glow-green-sm" />
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
