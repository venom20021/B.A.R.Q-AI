import { useState, useEffect } from 'react'
import { api } from '../../utils/api'
import { useTheme, type AccentColor } from '../../contexts/ThemeContext'
import { Loader2, Save, User } from 'lucide-react'
import { motion } from 'framer-motion'

// ── Assistant Customization Panel ─────────────────────────────────────

export function AssistantCustomization(): JSX.Element {
  const { accent, setAccent } = useTheme()

  // Form state
  const [assistantName, setAssistantName] = useState('BARQ')
  const [userName, setUserName] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState('')

  // Load from backend on mount
  useEffect(() => {
    let mounted = true
    setLoading(true)
    api('/settings/assistant')
      .then((resp) => {
        if (!mounted) return
        if (resp && typeof resp === 'object') {
          const data = resp as Record<string, unknown>
          if (typeof data.assistant_name === 'string') setAssistantName(data.assistant_name)
          if (typeof data.user_name === 'string') setUserName(data.user_name)
          if (typeof data.accent_color === 'string' && ['cyan', 'purple', 'amber', 'red'].includes(data.accent_color)) {
            setAccent(data.accent_color as AccentColor)
          }
        }
      })
      .catch(() => { /* ignore */ })
      .finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false }
  }, [setAccent])

  // Save all settings to backend
  const handleSave = async () => {
    setSaving(true)
    setSavedMsg('')
    try {
      const resp = await api('/settings/assistant', {
        assistant_name: assistantName.trim() || 'BARQ',
        user_name: userName.trim(),
        accent_color: accent,
      })
      if (resp && typeof resp === 'object' && (resp as Record<string, unknown>).status === 'saved') {
        setSavedMsg('Customization saved!')
        setTimeout(() => setSavedMsg(''), 3000)
      }
    } catch {
      setSavedMsg('Failed to save')
      setTimeout(() => setSavedMsg(''), 3000)
    }
    setSaving(false)
  }

  // Accent color options with their visual details
  const colorMap: Record<AccentColor, { hex: string; label: string }> = {
    cyan: { hex: '#06b6d4', label: 'Cyan' },
    purple: { hex: '#a855f7', label: 'Purple' },
    amber: { hex: '#f59e0b', label: 'Amber' },
    red: { hex: '#ef4444', label: 'Red' },
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="w-5 h-5 animate-spin text-cyan-300" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Assistant Name */}
      <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
        <div className="flex-1">
          <p className="text-sm font-rajdhani font-semibold text-ghost">Assistant Name</p>
          <p className="text-xs font-exo text-dim-400">What BARQ calls itself</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-cyan-500/15 flex items-center justify-center">
            <User className="w-3.5 h-3.5 text-cyan-300" />
          </div>
          <input
            type="text"
            value={assistantName}
            onChange={(e) => setAssistantName(e.target.value)}
            placeholder="BARQ"
            className="bg-void-800/60 text-ghost text-sm font-mono px-3 py-1.5 rounded-lg border border-cyan-500/15 focus:outline-none focus:border-cyan-500/30 placeholder:text-dim-500 w-36"
          />
        </div>
      </div>

      {/* User Name */}
      <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
        <div>
          <p className="text-sm font-rajdhani font-semibold text-ghost">Your Name</p>
          <p className="text-xs font-exo text-dim-400">How BARQ addresses you (e.g. "Sir", "Boss", your name)</p>
        </div>
        <input
          type="text"
          value={userName}
          onChange={(e) => setUserName(e.target.value)}
          placeholder="e.g. Sir, Boss, Alex"
          className="bg-void-800/60 text-ghost text-sm font-mono px-3 py-1.5 rounded-lg border border-cyan-500/15 focus:outline-none focus:border-cyan-500/30 placeholder:text-dim-500 w-36"
        />
      </div>

      {/* Accent Color */}
      <div className="flex items-center justify-between py-3 border-b border-cyan-500/8">
        <div>
          <p className="text-sm font-rajdhani font-semibold text-ghost">Accent Color</p>
          <p className="text-xs font-exo text-dim-400">Primary highlight color across the UI</p>
        </div>
        <div className="flex gap-2">
          {(Object.entries(colorMap) as [AccentColor, { hex: string; label: string }][]).map(([color, meta]) => (
            <button
              key={color}
              onClick={() => setAccent(color)}
              title={meta.label}
              className={`w-6 h-6 rounded-full border-2 transition-all duration-200 ${
                accent === color
                  ? 'border-white scale-110 shadow-[0_0_10px_rgba(255,255,255,0.35)]'
                  : 'border-transparent hover:border-white/40 hover:scale-105'
              }`}
              style={{ backgroundColor: meta.hex }}
            />
          ))}
        </div>
      </div>

      {/* Save Button */}
      <div className="flex items-center gap-2 pt-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-rajdhani font-semibold rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 hover:bg-cyan-500/20 transition-all disabled:opacity-40"
        >
          {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
          Save Customization
        </button>
        {savedMsg && (
          <motion.span
            initial={{ opacity: 0, x: -5 }}
            animate={{ opacity: 1, x: 0 }}
            className="text-[10px] font-exo text-green-400"
          >
            {savedMsg}
          </motion.span>
        )}
      </div>
    </div>
  )
}
