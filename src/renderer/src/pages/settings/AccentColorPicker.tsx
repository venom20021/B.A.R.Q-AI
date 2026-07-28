import { useTheme, type AccentColor } from '../../contexts/ThemeContext'

// ── Accent Color Picker ────────────────────────────────────────────────

export function AccentColorPicker(): JSX.Element {
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
