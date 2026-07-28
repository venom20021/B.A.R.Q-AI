// ─── Render Helpers ──────────────────────────────────────────────────

export function renderToggle(enabled: boolean, onToggle: () => void, disabled = false) {
  return (
    <button
      onClick={onToggle}
      disabled={disabled}
      className={`relative w-9 h-5 rounded-full transition-colors ${enabled ? 'bg-cyan-500' : 'bg-dim-500/30'} ${disabled ? 'opacity-50' : ''}`}
    >
      <span className={`absolute top-[2px] w-4 h-4 bg-white rounded-full transition-transform ${enabled ? 'translate-x-[18px]' : 'translate-x-[2px]'}`} />
    </button>
  )
}

export function renderSelect(
  value: string,
  options: { value: string; label: string }[],
  onChange: (v: string) => void,
) {
  return (
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
}
