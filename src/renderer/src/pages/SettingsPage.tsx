import { useState, useEffect, useCallback } from 'react'
import { Settings, Shield, Bell, Mic, Key, Palette, Loader2, CheckCircle, Briefcase, Video, Volume2, Play } from 'lucide-react'
import { motion } from 'framer-motion'

interface SettingsSection {
  id: string
  label: string
  icon: typeof Settings
  description: string
}

const sections: SettingsSection[] = [
  { id: 'voice', label: 'Voice', icon: Mic, description: 'Wake word, language, speech settings' },
  { id: 'sounds', label: 'Sounds', icon: Volume2, description: 'Preview and toggle audio profiles' },
  { id: 'api', label: 'API Keys', icon: Key, description: 'Connect your accounts and services' },
  { id: 'notifications', label: 'Notifications', icon: Bell, description: 'Alerts and digest preferences' },
  { id: 'jobs', label: 'Job Search', icon: Briefcase, description: 'Job search preferences and filters' },
  { id: 'social', label: 'Social', icon: Video, description: 'Content creation and posting settings' },
  { id: 'privacy', label: 'Privacy', icon: Shield, description: 'Data storage and local processing' },
  { id: 'appearance', label: 'Appearance', icon: Palette, description: 'Theme and display settings' },
]

interface VoiceStatus {
  is_listening: boolean
  wake_word: string
  stt_model: string
  tts_model: string
  recent_commands: { transcript: string; created_at: string }[]
  wake_greeting_enabled?: boolean
  weather_city?: string
}

const TTS_VOICES = [
  { value: 'en-US-JennyNeural', label: 'Jenny (Female - US)' },
  { value: 'en-US-GuyNeural', label: 'Guy (Male - US)' },
  { value: 'en-GB-SoniaNeural', label: 'Sonia (Female - UK)' },
  { value: 'en-GB-RyanNeural', label: 'Ryan (Male - UK)' },
  { value: 'en-AU-NatashaNeural', label: 'Natasha (Female - AU)' },
  { value: 'en-IN-NeerjaNeural', label: 'Neerja (Female - IN)' },
]

const SENSITIVITY_LEVELS = ['low', 'medium', 'high']

export function SettingsPage(): JSX.Element {
  const [activeSection, setActiveSection] = useState('voice')
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null)
  const [voiceLoading, setVoiceLoading] = useState(false)
  const [togglingVoice, setTogglingVoice] = useState(false)
  const [selectedVoice, setSelectedVoice] = useState('en-US-JennyNeural')
  const [sensitivity, setSensitivity] = useState('medium')
  const [voiceUpdating, setVoiceUpdating] = useState(false)
  const [wakeSoundEnabled, setWakeSoundEnabled] = useState(true)
  const [commandSoundEnabled, setCommandSoundEnabled] = useState(true)
  const [soundSettingsLoading, setSoundSettingsLoading] = useState(false)
  const [wakeGreetingEnabled, setWakeGreetingEnabled] = useState(true)
  const [weatherCity, setWeatherCity] = useState('Lucknow')

  // Notification settings
  const [notifSettings, setNotifSettings] = useState({
    telegram_enabled: false,
    email_enabled: false,
    desktop_notifications: true,
    daily_digest_enabled: false,
    job_match_alerts: true,
    content_alerts: true,
  })

  // Job search settings
  const [jobSettings, setJobSettings] = useState({
    scan_interval: '6',
    match_threshold: '70',
    preferred_locations: 'remote',
    preferred_industries: 'technology',
    auto_apply: false,
  })

  // Social settings
  const [socialSettings, setSocialSettings] = useState({
    trend_interval: '6',
    default_platforms: 'youtube,tiktok,instagram',
    auto_post: false,
    watermark_enabled: true,
  })

  // Privacy settings
  const [privacySettings, setPrivacySettings] = useState({
    local_processing_only: true,
    analytics_opt_in: false,
    crash_reporting: false,
  })

  // Appearance settings
  const [appearanceSettings, setAppearanceSettings] = useState({
    theme: 'dark',
    accent: 'cyan',
    font_scale: '100',
    animations: true,
  })

  const fetchVoiceStatus = useCallback(async () => {
    setVoiceLoading(true)
    try {
      const resp = await window.barq?.python.request('/voice/status')
      if (resp && typeof resp === 'object') {
        const data = resp as unknown as VoiceStatus
        setVoiceStatus(data)
        if (data.wake_greeting_enabled !== undefined) {
          setWakeGreetingEnabled(data.wake_greeting_enabled)
        }
        if (data.weather_city) {
          setWeatherCity(data.weather_city)
        }
      }
    } catch { /* ignore */ }
    setVoiceLoading(false)
  }, [])

  const handleWeatherCityChange = useCallback(async (city: string) => {
    setWeatherCity(city)
    try {
      await window.barq?.python.request('/voice/weather-city', {
        method: 'POST',
        body: JSON.stringify({ city }),
        headers: { 'Content-Type': 'application/json' },
      })
    } catch { /* ignore */ }
  }, [])

  const handleWakeGreetingToggle = useCallback(async () => {
    const newVal = !wakeGreetingEnabled
    setWakeGreetingEnabled(newVal)
    try {
      await window.barq?.python.request('/voice/wake-greeting-mode', {
        method: 'POST',
        body: JSON.stringify({ enabled: newVal }),
        headers: { 'Content-Type': 'application/json' },
      })
    } catch { /* ignore */ }
  }, [wakeGreetingEnabled])

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

  const handleVoiceChange = useCallback(async (voice: string) => {
    setSelectedVoice(voice)
    setVoiceUpdating(true)
    try {
      await window.barq?.voice.setTtsVoice(voice)
    } catch { /* ignore */ }
    setVoiceUpdating(false)
  }, [])

  const handleSensitivityChange = useCallback(async (level: string) => {
    setSensitivity(level)
    try {
      await window.barq?.voice.setSensitivity(level)
    } catch { /* ignore */ }
  }, [])

  const handleWakeSoundToggle = useCallback(async () => {
    const newVal = !wakeSoundEnabled
    setWakeSoundEnabled(newVal)
    try {
      await window.barq?.python.request('/voice/sound-settings', {
        wake_sound_enabled: newVal,
      })
    } catch { /* ignore */ }
  }, [wakeSoundEnabled])

  const handleCommandSoundToggle = useCallback(async () => {
    const newVal = !commandSoundEnabled
    setCommandSoundEnabled(newVal)
    try {
      await window.barq?.python.request('/voice/sound-settings', {
        command_sound_enabled: newVal,
      })
    } catch { /* ignore */ }
  }, [commandSoundEnabled])

  const fetchSoundSettings = useCallback(async () => {
    setSoundSettingsLoading(true)
    try {
      const resp = await window.barq?.python.request('/voice/sound-settings')
      if (resp && typeof resp === 'object') {
        const data = resp as Record<string, unknown>
        if (typeof data.wake_sound_enabled === 'boolean') setWakeSoundEnabled(data.wake_sound_enabled)
        if (typeof data.command_sound_enabled === 'boolean') setCommandSoundEnabled(data.command_sound_enabled)
      }
    } catch { /* ignore */ }
    setSoundSettingsLoading(false)
  }, [])

  const fetchSettings = useCallback(async () => {
    try {
      // Fetch notification settings
      const notifResp = await window.barq?.python.request('/notifications/settings')
      if (notifResp && typeof notifResp === 'object') {
        const respData = notifResp as Record<string, unknown>
        // Python API returns flat settings dict directly (no {success, data} wrapper)
        if (!('success' in respData) || !respData.success) {
          setNotifSettings(prev => ({
            ...prev,
            telegram_enabled: String(respData['telegram_enabled'] ?? '') === 'true',
            email_enabled: String(respData['email_enabled'] ?? '') === 'true',
            desktop_notifications: String(respData['desktop_notifications'] ?? 'true') !== 'false',
            daily_digest_enabled: String(respData['daily_digest_enabled'] ?? '') === 'true',
            job_match_alerts: String(respData['job_match_alerts'] ?? 'true') !== 'false',
            content_alerts: String(respData['content_alerts'] ?? 'true') !== 'false',
          }))
        }
      }
    } catch { /* ignore */ }
  }, [])

  const updateNotifSetting = useCallback(async (key: string, value: boolean) => {
    setNotifSettings(prev => ({ ...prev, [key]: value }))
    try {
      await window.barq?.python.request('/notifications/settings', {
        method: 'POST',
        body: JSON.stringify({ [key]: value }),
        headers: { 'Content-Type': 'application/json' },
      })
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    void fetchVoiceStatus()
    void fetchSettings()
    void fetchSoundSettings()
  }, [fetchVoiceStatus, fetchSettings, fetchSoundSettings])

  const renderToggle = (enabled: boolean, onToggle: () => void, disabled = false) => (
    <button
      onClick={onToggle}
      disabled={disabled}
      className={`relative w-9 h-5 rounded-full transition-colors ${enabled ? 'bg-cyan-500' : 'bg-dim-500/30'} ${disabled ? 'opacity-50' : ''}`}
    >
      <span className={`absolute top-[2px] w-4 h-4 bg-white rounded-full transition-transform ${enabled ? 'translate-x-[18px]' : 'translate-x-[2px]'}`} />
    </button>
  )

  const renderSelect = (value: string, options: { value: string; label: string }[], onChange: (v: string) => void) => (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="bg-void-800/80 text-ghost/80 text-xs font-exo px-2 py-1.5 rounded-lg border border-cyan-500/15 focus:outline-none focus:border-cyan-500/30 cursor-pointer"
    >
      {options.map(opt => (
        <option key={opt.value} value={opt.value} className="bg-void-900 text-ghost">{opt.label}</option>
      ))}
    </select>
  )

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
          {/* ─── Voice Section ─── */}
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
                    <p className="text-xs font-exo text-dim-400">Trigger phrase: &quot;{voiceStatus?.wake_word || 'Computer'}&quot;</p>
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
                    <p className="text-xs font-exo text-dim-400">Select voice for spoken responses</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {renderSelect(selectedVoice, TTS_VOICES, handleVoiceChange)}
                    {voiceUpdating && <Loader2 className="w-3 h-3 animate-spin text-cyan-300" />}
                  </div>
                </div>

                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div className="flex-1">
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Wake Word Sensitivity</p>
                    <p className="text-xs font-exo text-dim-400 mt-1">
                      {sensitivity === 'low' && 'Strict — only exact match (fewest false positives)'}
                      {sensitivity === 'medium' && 'Balanced — exact + phonetic variants (recommended)'}
                      {sensitivity === 'high' && 'Sensitive — includes partial matches (most responsive)'}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1 w-48">
                    <div className="flex items-center gap-3 w-full">
                      <span className="text-[10px] font-exo text-dim-500 w-8 text-right">Strict</span>
                      <input
                        type="range"
                        min="1"
                        max="3"
                        value={SENSITIVITY_LEVELS.indexOf(sensitivity) + 1}
                        onChange={(e) => handleSensitivityChange(SENSITIVITY_LEVELS[Number(e.target.value) - 1])}
                        className="flex-1 h-1.5 rounded-full appearance-none cursor-pointer"
                        style={{
                          background: `linear-gradient(to right, ${
                            sensitivity === 'low' ? '#06b6d4' : sensitivity === 'medium' ? '#f59e0b' : '#ef4444'
                          } 0%, ${
                            sensitivity === 'high' ? '#ef4444' : sensitivity === 'medium' ? '#f59e0b' : '#06b6d4'
                          } ${(SENSITIVITY_LEVELS.indexOf(sensitivity) + 1) * 33.3}%, #1e293b ${(SENSITIVITY_LEVELS.indexOf(sensitivity) + 1) * 33.3}%)`,
                        }}
                      />
                      <span className="text-[10px] font-exo text-dim-500 w-8">Sensitive</span>
                    </div>
                    <div className="flex items-center gap-1 text-[10px] font-exo">
                      <span className={`px-2 py-0.5 rounded ${
                        sensitivity === 'low'
                          ? 'bg-cyan-500/20 text-cyan-300'
                          : 'text-dim-500'
                      }`}>Low</span>
                      <span className="text-dim-600">·</span>
                      <span className={`px-2 py-0.5 rounded ${
                        sensitivity === 'medium'
                          ? 'bg-amber-500/20 text-amber-300'
                          : 'text-dim-500'
                      }`}>Med</span>
                      <span className="text-dim-600">·</span>
                      <span className={`px-2 py-0.5 rounded ${
                        sensitivity === 'high'
                          ? 'bg-red-500/20 text-red-300'
                          : 'text-dim-500'
                      }`}>High</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Command History</p>
                    <p className="text-xs font-exo text-dim-400">Track and review voice commands</p>
                  </div>
                  <span className="badge-cyan">Active</span>
                </div>

                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Wake Word Greeting</p>
                    <p className="text-xs font-exo text-dim-400">Speak system status, jobs, stocks & news when woken</p>
                  </div>
                  {renderToggle(wakeGreetingEnabled, handleWakeGreetingToggle)}
                </div>

                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Weather City</p>
                    <p className="text-xs font-exo text-dim-400">Used in the wake greeting weather report</p>
                  </div>
                  {renderSelect(weatherCity, [
                    { value: 'Lucknow', label: 'Lucknow' },
                    { value: 'New York', label: 'New York' },
                    { value: 'London', label: 'London' },
                    { value: 'Tokyo', label: 'Tokyo' },
                    { value: 'Mumbai', label: 'Mumbai' },
                    { value: 'San Francisco', label: 'San Francisco' },
                    { value: 'Berlin', label: 'Berlin' },
                    { value: 'Paris', label: 'Paris' },
                    { value: 'Sydney', label: 'Sydney' },
                    { value: 'Dubai', label: 'Dubai' },
                    { value: 'Bengaluru', label: 'Bengaluru' },
                    { value: 'Delhi', label: 'Delhi' },
                    { value: 'Chennai', label: 'Chennai' },
                    { value: 'Hyderabad', label: 'Hyderabad' },
                  ], handleWeatherCityChange)}
                </div>

                <div className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Always-on Listening</p>
                    <p className="text-xs font-exo text-dim-400">Keep microphone active in background</p>
                  </div>
                  {renderToggle(voiceStatus?.is_listening ?? false, toggleListening, togglingVoice || voiceLoading)}
                </div>

                {voiceStatus?.recent_commands && voiceStatus.recent_commands.length > 0 && (
                  <div className="pt-3 border-t border-cyan-500/8">
                    <p className="text-xs font-share-tech text-dim-500 mb-2 uppercase tracking-wider">Recent Voice Commands</p>
                    {voiceStatus.recent_commands.slice(0, 5).map((c, i) => (
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

          {/* ─── Sounds Section ─── */}
          {activeSection === 'sounds' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-1">Sound Profiles</h3>
                <p className="text-sm font-rajdhani text-dim-400">Preview and toggle audio feedback sounds</p>
              </div>
              <div className="space-y-4">
                {/* Wake Sound Card */}
                <div className="bg-void-700/30 rounded-lg p-4 border border-cyan-500/10">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-cyan-500/15 flex items-center justify-center">
                        <Volume2 className="w-4 h-4 text-cyan-300" />
                      </div>
                      <div>
                        <p className="text-sm font-rajdhani font-semibold text-ghost">Wake Sound</p>
                        <p className="text-xs font-exo text-dim-400">Ascending two-tone (880→1320Hz) — played when the wake word is detected</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => window.barq?.python.request('/voice/sound-preview', { profile: 'wake' })}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-rajdhani font-semibold rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 hover:bg-cyan-500/20 transition-all"
                      >
                        <Play className="w-3 h-3" /> Preview
                      </button>
                      {renderToggle(wakeSoundEnabled, handleWakeSoundToggle)}
                    </div>
                  </div>
                  <div className="flex gap-1 h-6 items-end">
                    {Array.from({ length: 12 }, (_, i) => (
                      <div
                        key={i}
                        className="flex-1 rounded-sm bg-cyan-500/20"
                        style={{
                          height: `${20 + (i / 12) * 60}%`,
                          opacity: wakeSoundEnabled ? 0.3 + (i / 12) * 0.7 : 0.1,
                        }}
                      />
                    ))}
                  </div>
                </div>

                {/* Command Accepted Sound Card */}
                <div className="bg-void-700/30 rounded-lg p-4 border border-cyan-500/10">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-amber-500/15 flex items-center justify-center">
                        <Volume2 className="w-4 h-4 text-amber-300" />
                      </div>
                      <div>
                        <p className="text-sm font-rajdhani font-semibold text-ghost">Command Accepted Sound</p>
                        <p className="text-xs font-exo text-dim-400">Descending ping (1000→750Hz) — played when a voice command is recognized</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => window.barq?.python.request('/voice/sound-preview', { profile: 'command_accepted' })}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-rajdhani font-semibold rounded-lg bg-amber-500/10 text-amber-300 border border-amber-500/20 hover:bg-amber-500/20 transition-all"
                      >
                        <Play className="w-3 h-3" /> Preview
                      </button>
                      {renderToggle(commandSoundEnabled, handleCommandSoundToggle)}
                    </div>
                  </div>
                  <div className="flex gap-1 h-6 items-end">
                    {Array.from({ length: 8 }, (_, i) => (
                      <div
                        key={i}
                        className="flex-1 rounded-sm bg-amber-500/20"
                        style={{
                          height: `${30 + (i / 8) * 50}%`,
                          opacity: commandSoundEnabled ? 0.3 + (i / 8) * 0.7 : 0.1,
                        }}
                      />
                    ))}
                  </div>
                </div>

                <div className="pt-2">
                  <p className="text-xs font-exo text-dim-500">
                    Sound effects play through your system speakers when BARQ detects a wake word
                    or processes a voice command. Use the Preview button to audition each sound,
                    and toggle the switch to mute or unmute from this panel.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* ─── API Keys Section ─── */}
          {activeSection === 'api' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-1">API Keys</h3>
                <p className="text-sm font-rajdhani text-dim-400">Connect your accounts to enable automation</p>
              </div>
              <div className="space-y-4">
                {([
                  { name: 'OpenAI', status: 'connected' as const, key: 'openai_api_key' },
                  { name: 'Ollama', status: 'connected' as const, key: 'ollama_host' },
                  { name: 'LinkedIn', status: 'disconnected' as const, key: 'linkedin_email' },
                  { name: 'YouTube', status: 'disconnected' as const, key: 'youtube_api_key' },
                  { name: 'Twitter/X', status: 'disconnected' as const, key: 'twitter_api_key' },
                  { name: 'TikTok', status: 'disconnected' as const, key: '' },
                  { name: 'Instagram', status: 'disconnected' as const, key: '' },
                  { name: 'OpenWeatherMap', status: 'disconnected' as const, key: '' },
                  { name: 'Spotify', status: 'disconnected' as const, key: '' },
                  { name: 'OpenCage (Maps)', status: 'disconnected' as const, key: '' },
                  { name: 'NewsAPI', status: 'disconnected' as const, key: '' },
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

          {/* ─── Notifications Section ─── */}
          {activeSection === 'notifications' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-1">Notification Preferences</h3>
                <p className="text-sm font-rajdhani text-dim-400">Control how and when BARQ sends alerts</p>
              </div>
              <div className="space-y-4">
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Desktop Notifications</p>
                    <p className="text-xs font-exo text-dim-400">Show alert popups on your desktop</p>
                  </div>
                  {renderToggle(notifSettings.desktop_notifications, () => updateNotifSetting('desktop_notifications', !notifSettings.desktop_notifications))}
                </div>
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Telegram Alerts</p>
                    <p className="text-xs font-exo text-dim-400">Receive important alerts via Telegram</p>
                  </div>
                  {renderToggle(notifSettings.telegram_enabled, () => updateNotifSetting('telegram_enabled', !notifSettings.telegram_enabled))}
                </div>
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Email Alerts</p>
                    <p className="text-xs font-exo text-dim-400">Get daily digest and critical alerts</p>
                  </div>
                  {renderToggle(notifSettings.email_enabled, () => updateNotifSetting('email_enabled', !notifSettings.email_enabled))}
                </div>
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Daily Digest</p>
                    <p className="text-xs font-exo text-dim-400">Receive a daily summary of activity</p>
                  </div>
                  {renderToggle(notifSettings.daily_digest_enabled, () => updateNotifSetting('daily_digest_enabled', !notifSettings.daily_digest_enabled))}
                </div>
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Job Match Alerts</p>
                    <p className="text-xs font-exo text-dim-400">Notify when great job matches found</p>
                  </div>
                  {renderToggle(notifSettings.job_match_alerts, () => updateNotifSetting('job_match_alerts', !notifSettings.job_match_alerts))}
                </div>
                <div className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Content Alerts</p>
                    <p className="text-xs font-exo text-dim-400">Notify when content is published</p>
                  </div>
                  {renderToggle(notifSettings.content_alerts, () => updateNotifSetting('content_alerts', !notifSettings.content_alerts))}
                </div>
              </div>
            </div>
          )}

          {/* ─── Job Search Section ─── */}
          {activeSection === 'jobs' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-1">Job Search Preferences</h3>
                <p className="text-sm font-rajdhani text-dim-400">Configure your job search automation</p>
              </div>
              <div className="space-y-4">
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Scan Interval</p>
                    <p className="text-xs font-exo text-dim-400">How often to scan for new jobs</p>
                  </div>
                  {renderSelect(jobSettings.scan_interval, [
                    { value: '1', label: 'Every hour' },
                    { value: '3', label: 'Every 3 hours' },
                    { value: '6', label: 'Every 6 hours' },
                    { value: '12', label: 'Every 12 hours' },
                    { value: '24', label: 'Daily' },
                  ], (v) => setJobSettings(prev => ({ ...prev, scan_interval: v })))}
                </div>
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Match Threshold</p>
                    <p className="text-xs font-exo text-dim-400">Minimum score to qualify as a match</p>
                  </div>
                  {renderSelect(jobSettings.match_threshold, [
                    { value: '50', label: '50% (Generous)' },
                    { value: '60', label: '60%' },
                    { value: '70', label: '70% (Default)' },
                    { value: '80', label: '80%' },
                    { value: '90', label: '90% (Strict)' },
                  ], (v) => setJobSettings(prev => ({ ...prev, match_threshold: v })))}
                </div>
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Preferred Location</p>
                    <p className="text-xs font-exo text-dim-400">Default location for job searches</p>
                  </div>
                  {renderSelect(jobSettings.preferred_locations, [
                    { value: 'remote', label: 'Remote' },
                    { value: 'hybrid', label: 'Hybrid' },
                    { value: 'onsite', label: 'On-site' },
                    { value: 'any', label: 'Any' },
                  ], (v) => setJobSettings(prev => ({ ...prev, preferred_locations: v })))}
                </div>
                <div className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Auto-Apply</p>
                    <p className="text-xs font-exo text-dim-400">Automatically apply to high-match jobs</p>
                  </div>
                  {renderToggle(jobSettings.auto_apply, () => setJobSettings(prev => ({ ...prev, auto_apply: !prev.auto_apply })))}
                </div>
              </div>
            </div>
          )}

          {/* ─── Social Section ─── */}
          {activeSection === 'social' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-1">Social Media Settings</h3>
                <p className="text-sm font-rajdhani text-dim-400">Configure content creation and posting</p>
              </div>
              <div className="space-y-4">
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Trend Check Interval</p>
                    <p className="text-xs font-exo text-dim-400">How often to check for trending topics</p>
                  </div>
                  {renderSelect(socialSettings.trend_interval, [
                    { value: '1', label: 'Every hour' },
                    { value: '3', label: 'Every 3 hours' },
                    { value: '6', label: 'Every 6 hours' },
                    { value: '12', label: 'Every 12 hours' },
                    { value: '24', label: 'Daily' },
                  ], (v) => setSocialSettings(prev => ({ ...prev, trend_interval: v })))}
                </div>
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Default Platforms</p>
                    <p className="text-xs font-exo text-dim-400">Platforms to post content to by default</p>
                  </div>
                  <span className="text-xs font-exo text-dim-400">YouTube, TikTok, Instagram</span>
                </div>
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Video Watermark</p>
                    <p className="text-xs font-exo text-dim-400">Add logo watermark to generated videos</p>
                  </div>
                  {renderToggle(socialSettings.watermark_enabled, () => setSocialSettings(prev => ({ ...prev, watermark_enabled: !prev.watermark_enabled })))}
                </div>
                <div className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Auto-Post</p>
                    <p className="text-xs font-exo text-dim-400">Automatically post rendered content</p>
                  </div>
                  {renderToggle(socialSettings.auto_post, () => setSocialSettings(prev => ({ ...prev, auto_post: !prev.auto_post })))}
                </div>
              </div>
            </div>
          )}

          {/* ─── Privacy Section ─── */}
          {activeSection === 'privacy' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-1">Privacy & Security</h3>
                <p className="text-sm font-rajdhani text-dim-400">Control data storage and processing</p>
              </div>
              <div className="space-y-4">
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Local Processing Only</p>
                    <p className="text-xs font-exo text-dim-400">All AI processing runs locally (recommended)</p>
                  </div>
                  {renderToggle(privacySettings.local_processing_only, () => setPrivacySettings(prev => ({ ...prev, local_processing_only: !prev.local_processing_only })))}
                </div>
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Usage Analytics</p>
                    <p className="text-xs font-exo text-dim-400">Help improve BARQ with anonymous usage data</p>
                  </div>
                  {renderToggle(privacySettings.analytics_opt_in, () => setPrivacySettings(prev => ({ ...prev, analytics_opt_in: !prev.analytics_opt_in })))}
                </div>
                <div className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Crash Reporting</p>
                    <p className="text-xs font-exo text-dim-400">Automatically report errors for debugging</p>
                  </div>
                  {renderToggle(privacySettings.crash_reporting, () => setPrivacySettings(prev => ({ ...prev, crash_reporting: !prev.crash_reporting })))}
                </div>
                <div className="pt-3 border-t border-cyan-500/8">
                  <p className="text-xs font-exo text-dim-500">Your data stays on your machine. BARQ processes everything locally using Ollama, Whisper, and Edge TTS. No cloud dependency.</p>
                </div>
              </div>
            </div>
          )}

          {/* ─── Appearance Section ─── */}
          {activeSection === 'appearance' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-1">Appearance</h3>
                <p className="text-sm font-rajdhani text-dim-400">Customize the look and feel of BARQ</p>
              </div>
              <div className="space-y-4">
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Theme</p>
                    <p className="text-xs font-exo text-dim-400">Application color scheme</p>
                  </div>
                  {renderSelect(appearanceSettings.theme, [
                    { value: 'dark', label: 'Dark Void' },
                    { value: 'darker', label: 'Midnight' },
                    { value: 'cyber', label: 'Cyberpunk' },
                  ], (v) => setAppearanceSettings(prev => ({ ...prev, theme: v })))}
                </div>
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Accent Color</p>
                    <p className="text-xs font-exo text-dim-400">Primary highlight color</p>
                  </div>
                  <div className="flex gap-2">
                    {['cyan', 'emerald', 'violet', 'amber', 'rose'].map(color => (
                      <button
                        key={color}
                        onClick={() => setAppearanceSettings(prev => ({ ...prev, accent: color }))}
                        className={`w-5 h-5 rounded-full border-2 transition-all ${
                          appearanceSettings.accent === color ? 'border-white scale-110' : 'border-transparent'
                        }`}
                        style={{ backgroundColor: color === 'cyan' ? '#06b6d4' : color === 'emerald' ? '#10b981' : color === 'violet' ? '#8b5cf6' : color === 'amber' ? '#f59e0b' : '#f43f5e' }}
                      />
                    ))}
                  </div>
                </div>
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Font Scale</p>
                    <p className="text-xs font-exo text-dim-400">UI text size</p>
                  </div>
                  {renderSelect(appearanceSettings.font_scale, [
                    { value: '85', label: 'Small' },
                    { value: '100', label: 'Normal' },
                    { value: '115', label: 'Large' },
                    { value: '130', label: 'X-Large' },
                  ], (v) => setAppearanceSettings(prev => ({ ...prev, font_scale: v })))}
                </div>
                <div className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Animations</p>
                    <p className="text-xs font-exo text-dim-400">Enable UI animations and transitions</p>
                  </div>
                  {renderToggle(appearanceSettings.animations, () => setAppearanceSettings(prev => ({ ...prev, animations: !prev.animations })))}
                </div>
              </div>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  )
}
