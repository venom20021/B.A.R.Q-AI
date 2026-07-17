import { useState, useEffect, useCallback, startTransition } from 'react'
import { api } from '../utils/api'
import { Settings, Shield, Bell, Mic, Key, Palette, User, Loader2, CheckCircle, Briefcase, Video, Volume2, Play, Terminal, Cpu, AlertTriangle, ShieldOff, ShieldCheck, Trash2, Plus, X, Save, Eye, Send } from 'lucide-react'
import { useTheme, type AccentColor } from '../contexts/ThemeContext'
import { motion, AnimatePresence } from 'framer-motion'

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
  { id: 'cloud-llm', label: 'Cloud LLM', icon: Cpu, description: 'Ollama fallback and cloud AI settings' },
  { id: 'notifications', label: 'Notifications', icon: Bell, description: 'Alerts and digest preferences' },
  { id: 'jobs', label: 'Job Search', icon: Briefcase, description: 'Job search preferences and filters' },
  { id: 'social', label: 'Social', icon: Video, description: 'Content creation and posting settings' },
  { id: 'security', label: 'Security', icon: Shield, description: 'Command whitelist and approvals' },
  { id: 'debug', label: 'Debug', icon: Terminal, description: 'Debug logging and diagnostics' },
  { id: 'profile', label: 'Profile', icon: User, description: 'Your name and personal details' },
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

const LANGUAGE_OPTIONS = [
  { value: 'en', label: '🇬🇧 English' },
  { value: 'hi', label: '🇮🇳 Hindi' },
]

const SENSITIVITY_LEVELS = ['low', 'medium', 'high']

// ── Accent Color Picker (module-level component, not created during render) ──

function AccentColorPicker(): JSX.Element {
  const { accent, setAccent } = useTheme()

  const colorMap: Record<AccentColor, { hex: string; label: string }> = {
    cyan: { hex: '#06b6d4', label: 'Cyan' },
    purple: { hex: '#a855f7', label: 'Purple' },
    amber: { hex: '#f59e0b', label: 'Amber' },
    red: { hex: '#ef4444', label: 'Red' },
  }

  return (
    <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
      <div>
        <p className="text-sm font-rajdhani font-semibold text-ghost">Accent Color</p>
        <p className="text-xs font-exo text-dim-400">Primary highlight color</p>
      </div>
      <div className="flex gap-2">
        {(Object.entries(colorMap) as [AccentColor, { hex: string; label: string }][]).map(([color, meta]) => (
          <button
            key={color}
            onClick={() => setAccent(color)}
            title={meta.label}
            className={`w-5 h-5 rounded-full border-2 transition-all ${
              accent === color ? 'border-white scale-110 shadow-[0_0_8px_rgba(255,255,255,0.3)]' : 'border-transparent hover:border-white/40'
            }`}
            style={{ backgroundColor: meta.hex }}
          />
        ))}
      </div>
    </div>
  )
}

// ── Vosk Debug Logs Toggle (module-level component) ────────────────────

function VoskDebugToggle(): JSX.Element {
  const [enabled, setEnabled] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    ;(async () => {
      try {
        const resp = await window.barq?.debug.getVoskLogs()
        if (resp?.success && resp.data) {
          const data = resp.data as { enabled: boolean }
          setEnabled(data.enabled)
        }
      } catch {
        /* ignore */
      }
      setLoading(false)
    })()
  }, [])

  const handleToggle = useCallback(async () => {
    const newVal = !enabled
    setEnabled(newVal)
    try {
      await window.barq?.debug.setVoskLogs(newVal)
    } catch {
      setEnabled(!newVal) // revert on error
    }
  }, [enabled])

  if (loading) {
    return <Loader2 className="w-4 h-4 animate-spin text-cyan-300" />
  }

  return (
    <button
      onClick={handleToggle}
      className={`relative w-9 h-5 rounded-full transition-colors ${enabled ? 'bg-cyan-500' : 'bg-dim-500/30'}`}
    >
      <span className={`absolute top-[2px] w-4 h-4 bg-white rounded-full transition-transform ${enabled ? 'translate-x-[18px]' : 'translate-x-[2px]'}`} />
    </button>
  )
}

// ── Whisper/STT Debug Logs Toggle (module-level component) ──────────────

function WhisperDebugToggle(): JSX.Element {
  const [enabled, setEnabled] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    ;(async () => {
      try {
        const resp = await window.barq?.debug.getWhisperLogs()
        if (resp?.success && resp.data) {
          const data = resp.data as { enabled: boolean }
          setEnabled(data.enabled)
        }
      } catch {
        /* ignore */
      }
      setLoading(false)
    })()
  }, [])

  const handleToggle = useCallback(async () => {
    const newVal = !enabled
    setEnabled(newVal)
    try {
      await window.barq?.debug.setWhisperLogs(newVal)
    } catch {
      setEnabled(!newVal) // revert on error
    }
  }, [enabled])

  if (loading) {
    return <Loader2 className="w-4 h-4 animate-spin text-cyan-300" />
  }

  return (
    <button
      onClick={handleToggle}
      className={`relative w-9 h-5 rounded-full transition-colors ${enabled ? 'bg-cyan-500' : 'bg-dim-500/30'}`}
    >
      <span className={`absolute top-[2px] w-4 h-4 bg-white rounded-full transition-transform ${enabled ? 'translate-x-[18px]' : 'translate-x-[2px]'}`} />
    </button>
  )
}

// ── Main Settings Page Component ──────────────────────────────────────────

export function SettingsPage(): JSX.Element {
  const [activeSection, setActiveSection] = useState('voice')
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null)
  const [voiceLoading, setVoiceLoading] = useState(false)
  const [togglingVoice, setTogglingVoice] = useState(false)
  const [selectedVoice, setSelectedVoice] = useState('en-US-JennyNeural')
  const [selectedLanguage, setSelectedLanguage] = useState('en')  // 'en' or 'hi'
  const [languageUpdating, setLanguageUpdating] = useState(false)
  const [lastDetectedLanguage, setLastDetectedLanguage] = useState('')  // last auto-detected language
  const [lastDetectedAt, setLastDetectedAt] = useState('')  // ISO timestamp of last auto-detection
  const [sensitivity, setSensitivity] = useState('medium')
  const [voiceUpdating, setVoiceUpdating] = useState(false)
  const [wakeSoundEnabled, setWakeSoundEnabled] = useState(true)
  const [commandSoundEnabled, setCommandSoundEnabled] = useState(true)
  const [wakeGreetingEnabled, setWakeGreetingEnabled] = useState(true)
  const [weatherCity, setWeatherCity] = useState('Lucknow')
  const [vadSilenceTimeout, setVadSilenceTimeout] = useState(0.4)
  const [vadSettingsLoading, setVadSettingsLoading] = useState(false)
  // TTS backend selection
  const [ttsBackend, setTtsBackend] = useState('edge')
  const [ttsBackendUpdating, setTtsBackendUpdating] = useState(false)
  const [piperAvailable, setPiperAvailable] = useState(false)
  // Wake word editing
  const [wakeWord, setWakeWord] = useState('')
  const [wakeWordInput, setWakeWordInput] = useState('')
  const [wakeWordUpdating, setWakeWordUpdating] = useState(false)
  const [wakeWordSaved, setWakeWordSaved] = useState(false)

  // Telegram credentials
  const [telegramBotToken, setTelegramBotToken] = useState('')
  const [telegramChatId, setTelegramChatId] = useState('')
  const [showTelegramToken, setShowTelegramToken] = useState(false)
  const [telegramSaving, setTelegramSaving] = useState(false)
  const [telegramTesting, setTelegramTesting] = useState(false)
  const [telegramSavedMsg, setTelegramSavedMsg] = useState('')
  const [telegramConfigured, setTelegramConfigured] = useState(false)

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

  // Cloud LLM settings
  const [cloudLLM, setCloudLLM] = useState({
    enabled: true,
    api_key: '',
    has_key: false,
    model: 'gpt-4o-mini',
    base_url: 'https://api.openai.com/v1',
  })
  const [cloudLLMLoading, setCloudLLMLoading] = useState(false)
  const [cloudLLMSaving, setCloudLLMSaving] = useState(false)
  const [cloudLLMSaved, setCloudLLMSaved] = useState('')
  const [cloudLLMKeyVisible, setCloudLLMKeyVisible] = useState(false)

  // Appearance settings
  const [appearanceSettings, setAppearanceSettings] = useState({
    theme: 'dark',
    accent: 'cyan',
    font_scale: '100',
    animations: true,
  })

  // ─── Cloud LLM Callbacks ──────────────────────────────────────

  const fetchCloudLLM = useCallback(async () => {
    setCloudLLMLoading(true)
    try {
      const resp = await api('/settings/cloud-llm')
      if (resp && typeof resp === 'object') {
        const data = resp as Record<string, unknown>
        setCloudLLM(prev => ({
          ...prev,
          enabled: data.enabled === true,
          has_key: data.has_api_key === true,
          api_key: '',  // never pre-fill masked key
          model: String(data.model || 'gpt-4o-mini'),
          base_url: String(data.base_url || 'https://api.openai.com/v1'),
        }))
      }
    } catch { /* ignore */ }
    setCloudLLMLoading(false)
  }, [])

  const handleSaveCloudLLM = useCallback(async () => {
    setCloudLLMSaving(true)
    setCloudLLMSaved('')
    try {
      const resp = await api('/settings/cloud-llm', {
        enabled: cloudLLM.enabled,
        api_key: cloudLLM.api_key,
        model: cloudLLM.model,
        base_url: cloudLLM.base_url,
      })
      if (resp && typeof resp === 'object' && (resp as Record<string, unknown>).status === 'saved') {
        setCloudLLMSaved('Settings saved!')
        setCloudLLM(prev => ({ ...prev, has_key: cloudLLM.api_key ? true : prev.has_key, api_key: '' }))
        setTimeout(() => setCloudLLMSaved(''), 3000)
      }
    } catch {
      setCloudLLMSaved('Failed to save')
      setTimeout(() => setCloudLLMSaved(''), 3000)
    }
    setCloudLLMSaving(false)
  }, [cloudLLM])

  // ─── Security / Command Whitelist State ───────────────────────────
  const [checkCommand, setCheckCommand] = useState('')
  const [checkResult, setCheckResult] = useState<{ tier: string; description: string; requires_approval: boolean } | null>(null)
  const [checking, setChecking] = useState(false)
  const [approving, setApproving] = useState(false)
  const [approveMsg, setApproveMsg] = useState('')
  const [whitelistRules, setWhitelistRules] = useState<{ safe: string[]; warn: string[]; dangerous: string[] }>({ safe: [], warn: [], dangerous: [] })
  const [rulesLoading, setRulesLoading] = useState(true)
  const [savingRules, setSavingRules] = useState(false)
  const [clearMsg, setClearMsg] = useState('')
  // Custom rule editor
  const [editTier, setEditTier] = useState<'safe' | 'warn' | 'dangerous'>('safe')
  const [newRulePattern, setNewRulePattern] = useState('')
  const [rulesSavedMsg, setRulesSavedMsg] = useState('')

  const fetchVoiceStatus = useCallback(async () => {
    setVoiceLoading(true)
    try {
      const resp = await api('/voice/status')
      if (resp && typeof resp === 'object') {
        const data = resp as unknown as VoiceStatus & { language?: string; tts_voice?: string; last_detected_language?: string; last_detected_at?: string; tts_backend?: string }
        setVoiceStatus(data)
        if (data.wake_greeting_enabled !== undefined) {
          setWakeGreetingEnabled(data.wake_greeting_enabled)
        }
        if (data.weather_city) {
          setWeatherCity(data.weather_city)
        }
        if (data.language) {
          setSelectedLanguage(data.language)
        }
        if (data.tts_voice) {
          setSelectedVoice(data.tts_voice)
        }
        if (data.last_detected_language) {
          setLastDetectedLanguage(data.last_detected_language)
        }
        if (data.last_detected_at) {
          setLastDetectedAt(data.last_detected_at)
        }
        // TTS backend
        if (data.tts_backend) {
          setTtsBackend(data.tts_backend)
        }
        // Wake word
        if (data.wake_word) {
          setWakeWord(data.wake_word)
          setWakeWordInput(data.wake_word)
        }
      }
    } catch { /* ignore */ }
    setVoiceLoading(false)
  }, [])

  const fetchTtsBackend = useCallback(async () => {
    try {
      const resp = await api('/voice/tts-backend')
      if (resp && typeof resp === 'object') {
        const data = resp as Record<string, unknown>
        if (typeof data.backend === 'string') setTtsBackend(data.backend)
        if (typeof data.piper_available === 'boolean') setPiperAvailable(data.piper_available)
      }
    } catch { /* ignore */ }
  }, [])

  const handleTtsBackendChange = useCallback(async (backend: string) => {
    setTtsBackend(backend)
    setTtsBackendUpdating(true)
    try {
      await api('/voice/tts-backend', { backend })
    } catch (err) {
      console.error('[Settings] TTS backend switch failed:', err)
    }
    setTtsBackendUpdating(false)
  }, [])

  const handleWakeWordChange = useCallback(async () => {
    const newWord = wakeWordInput.trim().toLowerCase()
    if (!newWord || newWord.length < 2) return
    setWakeWordUpdating(true)
    setWakeWordSaved(false)
    try {
      const resp = await api('/voice/wake-word', { wake_word: newWord })
      if (resp && typeof resp === 'object') {
        setWakeWord(newWord)
        setWakeWordSaved(true)
        setTimeout(() => setWakeWordSaved(false), 3000)
      }
    } catch {
      setWakeWordInput(wakeWord) // revert on error
    }
    setWakeWordUpdating(false)
  }, [wakeWordInput, wakeWord])

  const handleWeatherCityChange = useCallback(async (city: string) => {
    setWeatherCity(city)
    try {
      await api('/voice/weather-city', { city })
    } catch { /* ignore */ }
  }, [])

  const fetchVadSettings = useCallback(async () => {
    setVadSettingsLoading(true)
    try {
      const resp = await api('/voice/vad-settings')
      if (resp && typeof resp === 'object') {
        const data = resp as Record<string, unknown>
        if (typeof data.silence_timeout === 'number') {
          setVadSilenceTimeout(data.silence_timeout)
        }
      }
    } catch { /* ignore */ }
    setVadSettingsLoading(false)
  }, [])

  const handleVadTimeoutChange = useCallback(async (value: number) => {
    const clamped = Math.round(Math.max(0.1, Math.min(3.0, value)) * 100) / 100
    setVadSilenceTimeout(clamped)
    try {
      await api('/voice/vad-settings', { silence_timeout: clamped })
    } catch { /* ignore */ }
  }, [])

  const handleWakeGreetingToggle = useCallback(async () => {
    const newVal = !wakeGreetingEnabled
    setWakeGreetingEnabled(newVal)
    try {
      await api('/voice/wake-greeting-mode', { enabled: newVal })
    } catch { /* ignore */ }
  }, [wakeGreetingEnabled])

  const toggleListening = useCallback(async () => {
    setTogglingVoice(true)
    try {
      if (voiceStatus?.is_listening) {
        await api('/voice/stop', {})
      } else {
        await api('/voice/start', {})
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

  const handleLanguageChange = useCallback(async (lang: string) => {
    setSelectedLanguage(lang)
    setLanguageUpdating(true)
    try {
      await api('/voice/language', { language: lang })
    } catch (err) {
      console.error('[Settings] Language switch failed:', err)
    }
    setLanguageUpdating(false)
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
      await api('/voice/sound-settings', { wake_sound_enabled: newVal })
    } catch { /* ignore */ }
  }, [wakeSoundEnabled])

  const handleCommandSoundToggle = useCallback(async () => {
    const newVal = !commandSoundEnabled
    setCommandSoundEnabled(newVal)
    try {
      await api('/voice/sound-settings', { command_sound_enabled: newVal })
    } catch { /* ignore */ }
  }, [commandSoundEnabled])

  const fetchSoundSettings = useCallback(async () => {
    setVadSettingsLoading(true)
    try {
      const resp = await api('/voice/sound-settings')
      if (resp && typeof resp === 'object') {
        const data = resp as Record<string, unknown>
        if (typeof data.wake_sound_enabled === 'boolean') setWakeSoundEnabled(data.wake_sound_enabled)
        if (typeof data.command_sound_enabled === 'boolean') setCommandSoundEnabled(data.command_sound_enabled)
      }
    } catch { /* ignore */ }
    setVadSettingsLoading(false)
  }, [])

  const fetchSettings = useCallback(async () => {
    try {
      // Fetch notification settings
      const notifResp = await api('/notifications/settings')
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
      await api('/notifications/settings', { [key]: value })
    } catch { /* ignore */ }
  }, [])

  // ─── Telegram Callbacks ─────────────────────────────────────────

  const fetchTelegramCredentials = useCallback(async () => {
    try {
      const resp = await api('/notifications/telegram/credentials')
      if (resp && typeof resp === 'object') {
        const data = resp as Record<string, unknown>
        if (typeof data.bot_token === 'string' && data.bot_token) {
          setTelegramBotToken(data.bot_token)
          setTelegramConfigured(true)
        }
        if (typeof data.chat_id === 'string' && data.chat_id) {
          setTelegramChatId(data.chat_id)
        }
        // Also check via status endpoint for masked preview
        const statusResp = await api('/notifications/telegram/status')
        if (statusResp && typeof statusResp === 'object') {
          const s = statusResp as Record<string, unknown>
          if (typeof s.configured === 'boolean') {
            setTelegramConfigured(s.configured)
          }
        }
      }
    } catch { /* ignore */ }
  }, [])

  const handleSaveTelegramCredentials = useCallback(async () => {
    setTelegramSaving(true)
    setTelegramSavedMsg('')
    try {
      const resp = await api('/notifications/telegram/credentials', {
        bot_token: telegramBotToken,
        chat_id: telegramChatId,
      })
      if (resp && typeof resp === 'object') {
        const data = resp as Record<string, unknown>
        if (data.status === 'saved') {
          setTelegramConfigured(true)
          setTelegramSavedMsg('Credentials saved!')
          setTimeout(() => setTelegramSavedMsg(''), 3000)
        }
      }
    } catch {
      setTelegramSavedMsg('Failed to save')
      setTimeout(() => setTelegramSavedMsg(''), 3000)
    }
    setTelegramSaving(false)
  }, [telegramBotToken, telegramChatId])

  const handleTestTelegram = useCallback(async () => {
    setTelegramTesting(true)
    setTelegramSavedMsg('')
    try {
      const resp = await api('/notifications/test/telegram')
      if (resp && typeof resp === 'object') {
        const data = resp as Record<string, unknown>
        if (data.success) {
          setTelegramSavedMsg('✅ Test message sent!')
        } else {
          setTelegramSavedMsg('❌ Test failed: ' + (data.message || 'unknown error'))
        }
        setTimeout(() => setTelegramSavedMsg(''), 4000)
      }
    } catch {
      setTelegramSavedMsg('❌ Test request failed')
      setTimeout(() => setTelegramSavedMsg(''), 4000)
    }
    setTelegramTesting(false)
  }, [])

  // ─── Security Callbacks ──────────────────────────────────────────

  const handleCheckCommand = useCallback(async () => {
    if (!checkCommand.trim()) return
    setChecking(true)
    setCheckResult(null)
    setApproveMsg('')
    try {
      const resp = await window.barq?.system.command.check(checkCommand.trim())
      if (resp?.success && resp.data) {
        const data = resp.data as { tier: string; description: string; requires_approval: boolean }
        setCheckResult(data)
      }
    } catch { /* ignore */ }
    setChecking(false)
  }, [checkCommand])

  const handleApproveCommand = useCallback(async () => {
    if (!checkResult || !checkCommand.trim()) return
    setApproving(true)
    setApproveMsg('')
    try {
      const resp = await window.barq?.system.command.approve(checkCommand.trim(), checkResult.tier)
      if (resp?.success && resp.data) {
        const data = resp.data as { status: string; message: string }
        setApproveMsg(data.message || 'Approved')
      }
    } catch { setApproveMsg('Approval failed') }
    setApproving(false)
  }, [checkCommand, checkResult])

  const fetchWhitelistRules = useCallback(async () => {
    setRulesLoading(true)
    try {
      const resp = await window.barq?.system.command.whitelist.rules()
      if (resp?.success && resp.data) {
        const data = resp.data as { rules: { safe: string[]; warn: string[]; dangerous: string[] } }
        setWhitelistRules(data.rules || { safe: [], warn: [], dangerous: [] })
      }
    } catch { /* ignore */ }
    setRulesLoading(false)
  }, [])

  const handleAddRulePattern = useCallback(() => {
    if (!newRulePattern.trim()) return
    setWhitelistRules(prev => ({
      ...prev,
      [editTier]: [...prev[editTier], newRulePattern.trim()],
    }))
    setNewRulePattern('')
  }, [newRulePattern, editTier])

  const handleRemoveRulePattern = useCallback((tier: 'safe' | 'warn' | 'dangerous', index: number) => {
    setWhitelistRules(prev => ({
      ...prev,
      [tier]: prev[tier].filter((_, i) => i !== index),
    }))
  }, [])

  const handleSaveWhitelistRules = useCallback(async () => {
    setSavingRules(true)
    setRulesSavedMsg('')
    try {
      const resp = await window.barq?.system.command.whitelist.setRules(whitelistRules)
      if (resp?.success) {
        setRulesSavedMsg('Rules saved successfully')
        setTimeout(() => setRulesSavedMsg(''), 3000)
      }
    } catch { setRulesSavedMsg('Failed to save')
      setTimeout(() => setRulesSavedMsg(''), 3000) }
    setSavingRules(false)
  }, [whitelistRules])

  const handleClearApprovals = useCallback(async () => {
    try {
      const resp = await window.barq?.system.command.clearApprovals()
      if (resp?.success && resp.data) {
        const data = resp.data as { message: string }
        setClearMsg(data.message || 'Cleared')
        setTimeout(() => setClearMsg(''), 3000)
      }
    } catch { setClearMsg('Failed to clear')
      setTimeout(() => setClearMsg(''), 3000) }
  }, [])

  // Tick forces re-render every second for relative time display
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 1_000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    startTransition(() => {
      void fetchVoiceStatus()
      void fetchSettings()
      void fetchSoundSettings()
      void fetchWhitelistRules()
      void fetchVadSettings()
      void fetchTtsBackend()
      void fetchTelegramCredentials()
      void fetchCloudLLM()
    })
  }, [fetchVoiceStatus, fetchSettings, fetchSoundSettings, fetchWhitelistRules, fetchVadSettings, fetchTtsBackend, fetchTelegramCredentials, fetchCloudLLM])

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
                  <div className="flex-1">
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Wake Word</p>
                    <p className="text-xs font-exo text-dim-400">Say this phrase to wake BARQ</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={wakeWordInput}
                      onChange={(e) => setWakeWordInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleWakeWordChange()}
                      placeholder="e.g. computer, hey barq"
                      className="bg-void-800/60 text-ghost text-sm font-mono px-3 py-1.5 rounded-lg border border-cyan-500/15 focus:outline-none focus:border-cyan-500/30 placeholder:text-dim-500 w-40"
                    />
                    <button
                      onClick={handleWakeWordChange}
                      disabled={wakeWordUpdating || !wakeWordInput.trim() || wakeWordInput.trim().toLowerCase() === wakeWord}
                      className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-rajdhani font-semibold rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 hover:bg-cyan-500/20 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                      {wakeWordUpdating ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <CheckCircle className="w-3 h-3" />
                      )}
                      Save
                    </button>
                    {wakeWordSaved && (
                      <span className="text-[10px] font-exo text-green-400 whitespace-nowrap">Saved!</span>
                    )}
                    <div className="flex items-center gap-1.5 pl-2 border-l border-cyan-500/15">
                      <span className={`inline-block w-1.5 h-1.5 rounded-full ${voiceStatus?.is_listening ? 'bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.5)]' : 'bg-dim-500/50'}`} />
                      <span className={`text-[10px] font-mono font-bold tracking-wider uppercase ${voiceStatus?.is_listening ? 'text-green-400' : 'text-dim-500'}`}>
                        {voiceStatus?.is_listening ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                  </div>
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
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Language</p>
                    <p className="text-xs font-exo text-dim-400">Recognition & response language (auto-detected from speech unless locked)</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {renderSelect(selectedLanguage, LANGUAGE_OPTIONS, handleLanguageChange)}
                    {languageUpdating && <Loader2 className="w-3 h-3 animate-spin text-cyan-300" />}
                  </div>
                </div>

                {/* Auto-detection status indicator */}
                <div className="flex items-center justify-between py-2 border-b border-cyan-500/5">
                  <div className="flex items-center gap-2">
                    <span className={`inline-block w-2 h-2 rounded-full ${
                      lastDetectedLanguage
                        ? lastDetectedLanguage === 'hi'
                          ? 'bg-orange-400 shadow-[0_0_6px_rgba(251,146,60,0.5)]'
                          : 'bg-cyan-400 shadow-[0_0_6px_rgba(6,182,212,0.5)]'
                        : 'bg-dim-500/30'
                    }`} />
                    <div>
                      <p className="text-xs font-rajdhani font-semibold text-ghost">
                        Last Detected{" "}
                        {lastDetectedLanguage ? (
                          <span className={`font-bold ${
                            lastDetectedLanguage === 'hi'
                              ? 'text-orange-300'
                              : 'text-cyan-300'
                          }`}>
                            {lastDetectedLanguage === 'hi' ? '🇮🇳 Hindi' : '🇬🇧 English'}
                          </span>
                        ) : (
                          <span className="text-dim-400">—</span>
                        )}
                      </p>
                      <p className="text-[10px] font-exo text-dim-500">
                        {lastDetectedAt
                          ? (() => {
                              const diff = nowMs - new Date(lastDetectedAt).getTime()
                              const mins = Math.floor(diff / 60000)
                              const secs = Math.floor((diff % 60000) / 1000)
                              if (mins > 0) return `${mins}m ${secs}s ago`
                              return `${secs}s ago`
                            })()
                          : 'Not yet detected — speak to auto-detect'}
                      </p>
                    </div>
                  </div>
                  {lastDetectedLanguage && (
                    <span className={`text-[9px] font-mono font-bold tracking-wider uppercase px-1.5 py-0.5 rounded ${
                      lastDetectedLanguage === 'hi'
                        ? 'bg-orange-500/10 text-orange-300 border border-orange-500/15'
                        : 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/15'
                    }`}>
                      AUTO
                    </span>
                  )}
                </div>

                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">TTS Engine</p>
                    <p className="text-xs font-exo text-dim-400">
                      {ttsBackend === 'piper'
                        ? 'Piper TTS — Fully offline, local ONNX voice model'
                        : 'Edge TTS — High-quality cloud voices (requires internet)'}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="flex items-center">
                      <button
                        onClick={() => handleTtsBackendChange('edge')}
                        className={`px-2.5 py-1.5 text-xs font-rajdhani font-semibold rounded-l-lg border transition-all ${
                          ttsBackend === 'edge'
                            ? 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30'
                            : 'bg-void-800/40 text-dim-400 border-cyan-500/10 hover:text-ghost'
                        }`}
                      >
                        Edge
                      </button>
                      <button
                        onClick={() => handleTtsBackendChange('piper')}
                        disabled={!piperAvailable}
                        className={`px-2.5 py-1.5 text-xs font-rajdhani font-semibold rounded-r-lg border border-l-0 transition-all ${
                          ttsBackend === 'piper'
                            ? 'bg-green-500/15 text-green-300 border-green-500/30'
                            : 'bg-void-800/40 text-dim-400 border-cyan-500/10 hover:text-ghost'
                        } disabled:opacity-40 disabled:cursor-not-allowed`}
                        title={!piperAvailable ? 'Piper model not found in models/piper/' : 'Switch to offline Piper TTS'}
                      >
                        Piper 🎧
                      </button>
                    </div>
                    {ttsBackendUpdating && <Loader2 className="w-3 h-3 animate-spin text-cyan-300" />}
                    {ttsBackend === 'piper' && (
                      <span className="text-[9px] font-mono font-bold tracking-wider uppercase px-1.5 py-0.5 rounded bg-green-500/10 text-green-300 border border-green-500/15">
                        OFFLINE
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">TTS Voice</p>
                    <p className="text-xs font-exo text-dim-400">Select voice for spoken responses {ttsBackend === 'piper' && <span className="text-dim-500">(not used in Piper mode)</span>}</p>
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
                  <div className="flex-1">
                    <p className="text-sm font-rajdhani font-semibold text-ghost">VAD Endpoint Sensitivity</p>
                    <p className="text-xs font-exo text-dim-400 mt-1">
                      {vadSilenceTimeout < 0.3 && 'Aggressive — cuts quickly (best for fast responses, may clip)'}
                      {vadSilenceTimeout >= 0.3 && vadSilenceTimeout < 0.6 && 'Balanced — recommended (300-500ms range)'}
                      {vadSilenceTimeout >= 0.6 && 'Lax — waits longer before ending utterance (catches trailing words)'}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1 w-48">
                    <div className="flex items-center gap-3 w-full">
                      <span className="text-[10px] font-exo text-dim-500 w-auto">Fast</span>
                      <input
                        type="range"
                        min="10"
                        max="300"
                        value={Math.round(vadSilenceTimeout * 100)}
                        onChange={(e) => handleVadTimeoutChange(Number(e.target.value) / 100)}
                        disabled={vadSettingsLoading}
                        className="flex-1 h-1.5 rounded-full appearance-none cursor-pointer disabled:opacity-40"
                        style={{
                          background: `linear-gradient(to right, #06b6d4 0%, #06b6d4 ${((vadSilenceTimeout - 0.1) / 2.9) * 100}%, #1e293b ${((vadSilenceTimeout - 0.1) / 2.9) * 100}%)`,
                        }}
                      />
                      <span className="text-[10px] font-exo text-dim-500 w-auto">Lax</span>
                    </div>
                    <div className="flex items-center gap-1 text-[10px] font-exo">
                      <span className="text-dim-500">{vadSilenceTimeout.toFixed(2)}s silence</span>
                      {vadSettingsLoading && <Loader2 className="w-3 h-3 animate-spin text-cyan-300" />}
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
                        onClick={() => api('/voice/sound-preview', { profile: 'wake' })}
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
                        onClick={() => api('/voice/sound-preview', { profile: 'command_accepted' })}
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

          {/* ─── Cloud LLM Section ─── */}
          {activeSection === 'cloud-llm' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-1">Cloud LLM Fallback</h3>
                <p className="text-sm font-rajdhani text-dim-400">Configure cloud AI fallback when local Ollama is offline</p>
              </div>
              <div className="space-y-4">
                <div className="bg-void-700/30 rounded-lg p-4 border border-cyan-500/10 mb-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Cpu className="w-4 h-4 text-cyan-300" />
                    <h4 className="text-xs font-orbitron font-bold text-ghost tracking-wider uppercase">OpenAI-Compatible Provider</h4>
                  </div>
                  <p className="text-xs font-exo text-dim-400 mb-3">
                    When Ollama is unavailable, BARQ will automatically use this cloud provider.
                    Works with OpenAI, OpenRouter, Groq, Together AI, and any OpenAI-compatible API.
                  </p>

                  {cloudLLMLoading ? (
                    <div className="flex items-center justify-center py-6">
                      <Loader2 className="w-5 h-5 animate-spin text-cyan-300" />
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {/* Enable toggle */}
                      <div className="flex items-center justify-between py-2">
                        <div>
                          <p className="text-xs font-rajdhani font-semibold text-ghost">Enable Cloud Fallback</p>
                          <p className="text-[10px] font-exo text-dim-500">Allow using cloud AI when Ollama is offline</p>
                        </div>
                        {renderToggle(cloudLLM.enabled, () => setCloudLLM(prev => ({ ...prev, enabled: !prev.enabled })))}
                      </div>

                      {/* API Key */}
                      <div>
                        <label className="text-[10px] font-rajdhani font-semibold text-dim-400 uppercase tracking-wider">
                          API Key {cloudLLM.has_key && <span className="text-green-400 normal-case">(saved)</span>}
                        </label>
                        <div className="flex gap-2 mt-1">
                          <input
                            type={cloudLLMKeyVisible ? 'text' : 'password'}
                            value={cloudLLM.api_key}
                            onChange={(e) => setCloudLLM(prev => ({ ...prev, api_key: e.target.value }))}
                            placeholder={cloudLLM.has_key ? '•••••••• (key saved — leave blank to keep)' : 'sk-... or your API key'}
                            className="flex-1 bg-void-800/60 text-ghost text-xs font-mono px-3 py-2 rounded-lg border border-cyan-500/15 focus:outline-none focus:border-cyan-500/30 placeholder:text-dim-500"
                          />
                          <button
                            onClick={() => setCloudLLMKeyVisible(!cloudLLMKeyVisible)}
                            className="flex items-center gap-1 px-2 py-1.5 text-xs font-rajdhani font-semibold rounded-lg bg-void-800/40 text-dim-400 border border-cyan-500/10 hover:text-ghost transition-all"
                          >
                            {cloudLLMKeyVisible ? '🙈' : '👁️'}
                          </button>
                        </div>
                      </div>

                      {/* Model */}
                      <div>
                        <label className="text-[10px] font-rajdhani font-semibold text-dim-400 uppercase tracking-wider">Model</label>
                        <input
                          type="text"
                          value={cloudLLM.model}
                          onChange={(e) => setCloudLLM(prev => ({ ...prev, model: e.target.value }))}
                          placeholder="gpt-4o-mini"
                          className="w-full bg-void-800/60 text-ghost text-xs font-mono px-3 py-2 rounded-lg border border-cyan-500/15 focus:outline-none focus:border-cyan-500/30 placeholder:text-dim-500 mt-1"
                        />
                        <p className="text-[10px] font-exo text-dim-500 mt-1">
                          e.g. gpt-4o-mini, claude-3-haiku, gemini-2.0-flash, llama-3.3-70b
                        </p>
                      </div>

                      {/* Base URL */}
                      <div>
                        <label className="text-[10px] font-rajdhani font-semibold text-dim-400 uppercase tracking-wider">API Base URL</label>
                        <input
                          type="text"
                          value={cloudLLM.base_url}
                          onChange={(e) => setCloudLLM(prev => ({ ...prev, base_url: e.target.value }))}
                          placeholder="https://api.openai.com/v1"
                          className="w-full bg-void-800/60 text-ghost text-xs font-mono px-3 py-2 rounded-lg border border-cyan-500/15 focus:outline-none focus:border-cyan-500/30 placeholder:text-dim-500 mt-1"
                        />
                        <p className="text-[10px] font-exo text-dim-500 mt-1">
                          OpenAI: https://api.openai.com/v1 · OpenRouter: https://openrouter.ai/api/v1 · Groq: https://api.groq.com/openai/v1
                        </p>
                      </div>

                      {/* Save + Status */}
                      <div className="flex items-center gap-2 pt-2">
                        <button
                          onClick={handleSaveCloudLLM}
                          disabled={cloudLLMSaving}
                          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-rajdhani font-semibold rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 hover:bg-cyan-500/20 transition-all disabled:opacity-40"
                        >
                          {cloudLLMSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                          Save
                        </button>
                        {cloudLLMSaved && (
                          <motion.span initial={{ opacity: 0, x: -5 }} animate={{ opacity: 1, x: 0 }} className="text-[10px] font-exo text-green-400">
                            {cloudLLMSaved}
                          </motion.span>
                        )}
                        {cloudLLM.has_key && (
                          <span className="badge-green flex items-center gap-1 ml-auto">
                            <CheckCircle className="w-3 h-3" />
                            Connected
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                {/* Quick provider presets */}
                <div className="pt-2">
                  <p className="text-xs font-rajdhani font-semibold text-ghost mb-2">Quick Provider Presets</p>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { name: 'OpenAI', model: 'gpt-4o-mini', url: 'https://api.openai.com/v1' },
                      { name: 'OpenRouter', model: 'openai/gpt-4o-mini', url: 'https://openrouter.ai/api/v1' },
                      { name: 'Groq (Free)', model: 'llama-3.3-70b-versatile', url: 'https://api.groq.com/openai/v1' },
                    ].map((preset) => (
                      <button
                        key={preset.name}
                        onClick={() => setCloudLLM(prev => ({ ...prev, model: preset.model, base_url: preset.url }))}
                        className="bg-void-700/40 rounded-lg p-2.5 border border-cyan-500/10 hover:border-cyan-500/25 transition-all text-left"
                      >
                        <p className="text-[10px] font-orbitron font-bold text-ghost tracking-wider">{preset.name}</p>
                        <p className="text-[9px] font-exo text-dim-500 mt-0.5 truncate">{preset.model}</p>
                      </button>
                    ))}
                  </div>
                </div>
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
                {/* ── Telegram Credentials ── */}
                <div className="bg-void-700/30 rounded-lg p-4 border border-cyan-500/10 mb-4">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-lg">📱</span>
                    <h4 className="text-xs font-orbitron font-bold text-ghost tracking-wider uppercase">Telegram Configuration</h4>
                  </div>
                  <p className="text-xs font-exo text-dim-400 mb-3">
                    Enter your Telegram bot credentials to receive job alerts, pipeline results, and other notifications.
                    Create a bot via <a href="https://t.me/BotFather" target="_blank" rel="noopener noreferrer" className="text-cyan-300 hover:text-cyan-200 underline underline-offset-2">@BotFather</a> on Telegram.
                  </p>
                  <div className="space-y-3">
                    <div>
                      <label className="text-[10px] font-rajdhani font-semibold text-dim-400 uppercase tracking-wider">Bot Token</label>
                      <div className="flex gap-2 mt-1">
                        <input
                          type="password"
                          value={telegramBotToken}
                          onChange={(e) => setTelegramBotToken(e.target.value)}
                          placeholder="1234567890:ABCdefGHIjklmNOPqrstUVwxyz-1234"
                          className="flex-1 bg-void-800/60 text-ghost text-xs font-mono px-3 py-2 rounded-lg border border-cyan-500/15 focus:outline-none focus:border-cyan-500/30 placeholder:text-dim-500"
                        />
                        <button
                          onClick={() => setShowTelegramToken(!showTelegramToken)}
                          className="flex items-center gap-1 px-2 py-1.5 text-xs font-rajdhani font-semibold rounded-lg bg-void-800/40 text-dim-400 border border-cyan-500/10 hover:text-ghost transition-all"
                        >
                          {showTelegramToken ? '🙈' : '👁️'}
                        </button>
                      </div>
                    </div>
                    <div>
                      <label className="text-[10px] font-rajdhani font-semibold text-dim-400 uppercase tracking-wider">Chat ID</label>
                      <div className="flex gap-2 mt-1">
                        <input
                          type="text"
                          value={telegramChatId}
                          onChange={(e) => setTelegramChatId(e.target.value)}
                          placeholder="123456789"
                          className="flex-1 bg-void-800/60 text-ghost text-xs font-mono px-3 py-2 rounded-lg border border-cyan-500/15 focus:outline-none focus:border-cyan-500/30 placeholder:text-dim-500"
                        />
                        <span className="text-hud text-dim-500 flex items-center text-xs">Get via @userinfobot</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={handleSaveTelegramCredentials}
                        disabled={telegramSaving}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-rajdhani font-semibold rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 hover:bg-cyan-500/20 transition-all disabled:opacity-40"
                      >
                        {telegramSaving ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3" />}
                        Save Credentials
                      </button>
                      <button
                        onClick={handleTestTelegram}
                        disabled={telegramTesting || !telegramConfigured}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-rajdhani font-semibold rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 hover:bg-cyan-500/20 transition-all disabled:opacity-40"
                      >
                        {telegramTesting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
                        Test
                      </button>
                      <AnimatePresence>
                        {telegramSavedMsg && (
                          <motion.span initial={{ opacity: 0, x: -5 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="text-[10px] font-exo text-green-400">
                            {telegramSavedMsg}
                          </motion.span>
                        )}
                      </AnimatePresence>
                    </div>
                    {telegramConfigured && (
                      <div className="flex items-center gap-1.5 pt-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.5)]" />
                        <span className="text-[10px] font-exo text-green-400">Telegram configured</span>
                      </div>
                    )}
                  </div>
                </div>

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

          {/* ─── Security Section ─── */}
          {activeSection === 'security' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-1">Command Whitelist Security</h3>
                <p className="text-sm font-rajdhani text-dim-400">Manage command safety tiers, approve commands, and customize whitelist rules</p>
              </div>

              {/* ─── Command Checker ─── */}
              <div className="bg-void-700/30 rounded-lg p-4 border border-cyan-500/10">
                <div className="flex items-center gap-2 mb-3">
                  <Terminal className="w-4 h-4 text-cyan-300" />
                  <h4 className="text-xs font-orbitron font-bold text-ghost tracking-wider uppercase">Command Classifier</h4>
                </div>
                <p className="text-xs font-exo text-dim-400 mb-3">
                  Type a command to check its safety classification and approve it for execution.
                </p>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={checkCommand}
                    onChange={(e) => setCheckCommand(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleCheckCommand()}
                    placeholder="e.g. rm -rf /"
                    className="flex-1 bg-void-800/60 text-ghost text-sm font-mono px-3 py-2 rounded-lg border border-cyan-500/15 focus:outline-none focus:border-cyan-500/30 placeholder:text-dim-500"
                  />
                  <button
                    onClick={handleCheckCommand}
                    disabled={checking || !checkCommand.trim()}
                    className="flex items-center gap-1.5 px-3 py-2 text-xs font-rajdhani font-semibold rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 hover:bg-cyan-500/20 disabled:opacity-40 transition-all"
                  >
                    {checking ? <Loader2 className="w-3 h-3 animate-spin" /> : <Eye className="w-3 h-3" />}
                    Classify
                  </button>
                </div>

                <AnimatePresence>
                  {checkResult && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden mt-3"
                    >
                      <div className={`rounded-lg p-3 border ${
                        checkResult.tier === 'safe'
                          ? 'bg-green-500/10 border-green-500/20'
                          : checkResult.tier === 'warn'
                            ? 'bg-amber-500/10 border-amber-500/20'
                            : 'bg-red-500/10 border-red-500/20'
                      }`}>
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            {checkResult.tier === 'safe' ? (
                              <ShieldCheck className="w-4 h-4 text-green-400" />
                            ) : checkResult.tier === 'warn' ? (
                              <AlertTriangle className="w-4 h-4 text-amber-400" />
                            ) : (
                              <ShieldOff className="w-4 h-4 text-red-400" />
                            )}
                            <div>
                              <span className={`text-xs font-rajdhani font-bold uppercase ${
                                checkResult.tier === 'safe' ? 'text-green-300' : checkResult.tier === 'warn' ? 'text-amber-300' : 'text-red-300'
                              }`}>
                                {checkResult.tier}
                              </span>
                              <p className="text-xs font-exo text-dim-400 mt-0.5">{checkResult.description}</p>
                            </div>
                          </div>
                          {checkResult.requires_approval && (
                            <button
                              onClick={handleApproveCommand}
                              disabled={approving}
                              className="flex items-center gap-1 px-3 py-1.5 text-xs font-rajdhani font-semibold rounded-lg bg-cyan-500/15 text-cyan-300 border border-cyan-500/25 hover:bg-cyan-500/25 transition-all disabled:opacity-40"
                            >
                              {approving ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3" />}
                              Approve
                            </button>
                          )}
                        </div>
                        {approveMsg && (
                          <p className="text-xs font-exo text-cyan-300 mt-2 flex items-center gap-1">
                            <CheckCircle className="w-3 h-3" /> {approveMsg}
                          </p>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* ─── Custom Rules Editor ─── */}
              <div className="bg-void-700/30 rounded-lg p-4 border border-cyan-500/10">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Shield className="w-4 h-4 text-cyan-300" />
                    <h4 className="text-xs font-orbitron font-bold text-ghost tracking-wider uppercase">Custom Whitelist Rules</h4>
                  </div>
                  <button
                    onClick={handleSaveWhitelistRules}
                    disabled={savingRules}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-rajdhani font-semibold rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 hover:bg-cyan-500/20 transition-all disabled:opacity-40"
                  >
                    {savingRules ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                    Save Rules
                  </button>
                </div>
                {rulesSavedMsg && (
                  <p className="text-xs font-exo text-green-400 mb-2 flex items-center gap-1">
                    <CheckCircle className="w-3 h-3" /> {rulesSavedMsg}
                  </p>
                )}

                {/* Tier tabs */}
                <div className="flex gap-1 mb-3">
                  {(['safe', 'warn', 'dangerous'] as const).map(tier => (
                    <button
                      key={tier}
                      onClick={() => setEditTier(tier)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-rajdhani font-semibold transition-all ${
                        editTier === tier
                          ? tier === 'safe'
                            ? 'bg-green-500/15 text-green-300 border border-green-500/25'
                            : tier === 'warn'
                              ? 'bg-amber-500/15 text-amber-300 border border-amber-500/25'
                              : 'bg-red-500/15 text-red-300 border border-red-500/25'
                          : 'bg-void-800/40 text-dim-400 hover:text-ghost border border-transparent'
                      }`}
                    >
                      {tier === 'safe' && <ShieldCheck className="w-3 h-3 inline mr-1" />}
                      {tier === 'warn' && <AlertTriangle className="w-3 h-3 inline mr-1" />}
                      {tier === 'dangerous' && <ShieldOff className="w-3 h-3 inline mr-1" />}
                      {tier.charAt(0).toUpperCase() + tier.slice(1)}
                    </button>
                  ))}
                </div>

                {/* Add pattern */}
                <div className="flex gap-2 mb-3">
                  <input
                    type="text"
                    value={newRulePattern}
                    onChange={(e) => setNewRulePattern(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleAddRulePattern()}
                    placeholder="Add regex pattern..."
                    className="flex-1 bg-void-800/60 text-ghost text-xs font-mono px-2.5 py-1.5 rounded-lg border border-cyan-500/15 focus:outline-none focus:border-cyan-500/30 placeholder:text-dim-500"
                  />
                  <button
                    onClick={handleAddRulePattern}
                    disabled={!newRulePattern.trim()}
                    className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-rajdhani font-semibold rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 hover:bg-cyan-500/20 disabled:opacity-40 transition-all"
                  >
                    <Plus className="w-3 h-3" /> Add
                  </button>
                </div>

                {/* Rule list */}
                {rulesLoading ? (
                  <div className="flex items-center justify-center py-4">
                    <Loader2 className="w-4 h-4 animate-spin text-dim-400" />
                  </div>
                ) : (
                  <div className="space-y-1 max-h-40 overflow-y-auto scroll-cyan">
                    {whitelistRules[editTier].length === 0 ? (
                      <p className="text-xs font-exo text-dim-500 text-center py-3">No custom {editTier} rules.</p>
                    ) : (
                      whitelistRules[editTier].map((pattern, i) => (
                        <div
                          key={i}
                          className="flex items-center justify-between bg-void-800/40 rounded px-2.5 py-1.5 group"
                        >
                          <code className="text-xs font-mono text-dim-300 truncate flex-1">{pattern}</code>
                          <button
                            onClick={() => handleRemoveRulePattern(editTier, i)}
                            className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-red-500/10 text-dim-400 hover:text-red-400 transition-all"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                )}

                {/* Tips */}
                <div className="mt-3 pt-3 border-t border-cyan-500/8">
                  <p className="text-xs font-exo text-dim-500">
                    Patterns are regex. They are checked <strong>before</strong> built-in patterns,
                    so you can override the default classification for specific commands.
                    Built-in patterns are not affected by this list.
                  </p>
                </div>
              </div>

              {/* ─── Approvals Controls ─── */}
              <div className="bg-void-700/30 rounded-lg p-4 border border-cyan-500/10">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-400" />
                    <div>
                      <h4 className="text-xs font-orbitron font-bold text-ghost tracking-wider uppercase">Session Approvals</h4>
                      <p className="text-xs font-exo text-dim-400">
                        Approved commands persist only for this session—cleared on restart.
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={handleClearApprovals}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-rajdhani font-semibold rounded-lg bg-red-500/10 text-red-300 border border-red-500/20 hover:bg-red-500/20 transition-all"
                  >
                    <Trash2 className="w-3 h-3" />
                    Clear All
                  </button>
                </div>
                {clearMsg && (
                  <p className="text-xs font-exo text-amber-300 mt-2 flex items-center gap-1">
                    <CheckCircle className="w-3 h-3" /> {clearMsg}
                  </p>
                )}
              </div>

              {/* ─── Threat Model Info ─── */}
              <div className="pt-2">
                <h4 className="text-xs font-rajdhani font-bold text-dim-300 mb-2">Safety Tiers</h4>
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-green-500/8 border border-green-500/15 rounded-lg p-3">
                    <div className="flex items-center gap-1.5 mb-1">
                      <ShieldCheck className="w-3.5 h-3.5 text-green-400" />
                      <span className="text-xs font-rajdhani font-bold text-green-300">SAFE</span>
                    </div>
                    <p className="text-hud text-dim-400 text-xs">Read-only commands like ls, echo, ping, git status. Auto-approved.</p>
                  </div>
                  <div className="bg-amber-500/8 border border-amber-500/15 rounded-lg p-3">
                    <div className="flex items-center gap-1.5 mb-1">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                      <span className="text-xs font-rajdhani font-bold text-amber-300">WARN</span>
                    </div>
                    <p className="text-hud text-dim-400 text-xs">Modification commands like mkdir, kill, pip install, git push. Needs approval.</p>
                  </div>
                  <div className="bg-red-500/8 border border-red-500/15 rounded-lg p-3">
                    <div className="flex items-center gap-1.5 mb-1">
                      <ShieldOff className="w-3.5 h-3.5 text-red-400" />
                      <span className="text-xs font-rajdhani font-bold text-red-300">DANGEROUS</span>
                    </div>
                    <p className="text-hud text-dim-400 text-xs">Destructive commands like rm, sudo, dd, reboot. Explicit approval required.</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ─── Debug Section ─── */}
          {activeSection === 'debug' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-1">Debug Settings</h3>
                <p className="text-sm font-rajdhani text-dim-400">Debug logging, diagnostics, and privacy controls</p>
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
                <div className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Vosk Debug Logs</p>
                    <p className="text-xs font-exo text-dim-400">Show verbose Vosk model-loading logs in the console</p>
                  </div>
                  <VoskDebugToggle />
                </div>
                <div className="flex items-center justify-between py-3">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Whisper/STT Debug Logs</p>
                    <p className="text-xs font-exo text-dim-400">Show verbose Whisper transcription logs in the console</p>
                  </div>
                  <WhisperDebugToggle />
                </div>
                <div className="pt-3 border-t border-cyan-500/8">
                  <p className="text-xs font-exo text-dim-500">Your data stays on your machine. BARQ processes everything locally using Ollama, Whisper, and Edge TTS. No cloud dependency.</p>
                </div>
              </div>
            </div>
          )}

          {/* ─── Profile Section ─── */}
          {activeSection === 'profile' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-1">Profile</h3>
                <p className="text-sm font-rajdhani text-dim-400">Set your display name for the dashboard greeting</p>
              </div>
              <div className="space-y-4">
                <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
                  <div className="flex-1">
                    <p className="text-sm font-rajdhani font-semibold text-ghost">Display Name</p>
                    <p className="text-xs font-exo text-dim-400">Shown in the dashboard greeting (e.g. &ldquo;GOOD AFTERNOON, RUBEN&rdquo;)</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      id="user-name-input"
                      placeholder="Enter your name..."
                      defaultValue={(() => {
                        try { return localStorage.getItem('barq_user_name') || '' } catch { return '' }
                      })()}
                      onChange={(e) => {
                        const name = e.target.value.trim()
                        try {
                          localStorage.setItem('barq_user_name', name)
                          window.dispatchEvent(new CustomEvent('barq:profile-updated'))
                        } catch { /* storage unavailable */ }
                      }}
                      className="bg-void-800/60 text-ghost text-sm font-sans px-3 py-2 rounded-lg border border-cyan-500/15 focus:outline-none focus:border-cyan-500/30 placeholder:text-dim-500 w-44"
                    />
                    <button
                      onClick={() => {
                        const input = document.getElementById('user-name-input') as HTMLInputElement
                        if (input) {
                          const name = input.value.trim()
                          try {
                            localStorage.setItem('barq_user_name', name)
                            window.dispatchEvent(new CustomEvent('barq:profile-updated'))
                          } catch { /* ignore */ }
                        }
                      }}
                      className="flex items-center gap-1.5 px-3 py-2 text-xs font-rajdhani font-semibold rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 hover:bg-cyan-500/20 transition-all"
                    >
                      <CheckCircle className="w-3 h-3" /> Save
                    </button>
                  </div>
                </div>

                <div className="bg-cyan-500/8 border border-cyan-500/15 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_6px_rgba(34,211,238,0.5)]" />
                    <span className="text-xs font-rajdhani font-bold text-cyan-300 uppercase tracking-wider">Preview</span>
                  </div>
                  <p className="text-sm font-sans text-white/70">
                    Your dashboard will greet you with &ldquo;
                    {(() => {
                      const hour = new Date().getHours()
                      const greeting = hour < 12 ? 'GOOD MORNING' : hour < 17 ? 'GOOD AFTERNOON' : 'GOOD EVENING'
                      let name = ''
                      try { name = localStorage.getItem('barq_user_name') || '' } catch {}
                      return name ? `${greeting}, ${name.toUpperCase()}` : greeting
                    })()}
                    &rdquo;
                  </p>
                </div>

                <div className="pt-2">
                  <p className="text-xs font-exo text-dim-500">
                    Your name is stored locally and never sent to any server. It only appears
                    in the dashboard greeting to make the experience feel more personal.
                  </p>
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
                <AccentColorPicker />
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
