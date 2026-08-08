import { useState, type ReactNode } from 'react'
import {
  ChevronDown, Filter, FolderTree, Eye, SlidersHorizontal, RotateCcw,
} from 'lucide-react'

// ─── Types ─────────────────────────────────────────────────────────────────

interface BrainGroup {
  type: string
  label: string
  color: string
  nodes: number
  edges: number
}

interface GraphSidebarProps {
  brainColor: string
  brainsList: BrainGroup[]
  activeBrain: string
  onSelectBrain: (type: string) => void
  nodeCount: number
  edgeCount: number
  // Display settings
  showLabels: boolean
  onShowLabels: (v: boolean) => void
  showThumbnails: boolean
  onShowThumbnails: (v: boolean) => void
  // Force settings
  chargeStrength: number
  onChargeStrength: (v: number) => void
  linkDistance: number
  onLinkDistance: (v: number) => void
  centerStrength: number
  onCenterStrength: (v: number) => void
  onResetForces: () => void
}

// ─── Small UI atoms ─────────────────────────────────────────────────────────

function Toggle({
  checked, onChange, color,
}: { checked: boolean; onChange: (v: boolean) => void; color: string }): JSX.Element {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="w-8 h-[18px] rounded-full relative shrink-0 transition-colors duration-200 focus:outline-none focus-visible:ring-1 focus-visible:ring-zinc-500"
      style={{ backgroundColor: checked ? color : '#3f3f3f' }}
    >
      <span
        className="absolute top-[2px] w-[14px] h-[14px] rounded-full bg-white shadow transition-all duration-200"
        style={{ left: checked ? 16 : 2 }}
      />
    </button>
  )
}

function ForceSlider({
  label, hint, value, min, max, step, format, color, onChange,
}: {
  label: string
  hint?: string
  value: number
  min: number
  max: number
  step: number
  format: (v: number) => string
  color: string
  onChange: (v: number) => void
}): JSX.Element {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-zinc-400">{label}</span>
        <span className="text-[10px] font-mono text-zinc-300" style={{ color }}>{format(value)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1 rounded-full appearance-none cursor-pointer bg-[#3a3a3a] focus:outline-none"
        style={{ accentColor: color }}
      />
      {hint && <p className="text-[9px] text-zinc-600 leading-snug">{hint}</p>}
    </div>
  )
}

function Section({
  open, onToggle, icon, title, children,
}: {
  open: boolean
  onToggle: () => void
  icon: ReactNode
  title: string
  children: ReactNode
}): JSX.Element {
  return (
    <div className="border-b border-[#2c2c2c]">
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-[#262626] transition-colors focus:outline-none"
      >
        <span className="text-zinc-400">{icon}</span>
        <span className="text-[11px] font-medium text-zinc-300 tracking-wide flex-1 text-left">
          {title}
        </span>
        <ChevronDown
          className={`w-3.5 h-3.5 text-zinc-500 transition-transform duration-200 ${open ? '' : '-rotate-90'}`}
        />
      </button>
      {open && <div className="px-3 pb-3 space-y-2.5">{children}</div>}
    </div>
  )
}

// ─── Component ─────────────────────────────────────────────────────────────

export function GraphSidebar(props: GraphSidebarProps): JSX.Element {
  const {
    brainColor, brainsList, activeBrain, onSelectBrain,
    nodeCount, edgeCount,
    showLabels, onShowLabels, showThumbnails, onShowThumbnails,
    chargeStrength, onChargeStrength, linkDistance, onLinkDistance,
    centerStrength, onCenterStrength, onResetForces,
  } = props

  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    Filters: false,
    Groups: true,
    Display: true,
    Forces: true,
  })

  const toggleSection = (name: string): void => {
    setOpenSections(prev => ({ ...prev, [name]: !prev[name] }))
  }

  return (
    <aside
      className="w-[300px] shrink-0 bg-[#1e1e1e] border-r border-[#2c2c2c] flex flex-col overflow-y-auto select-none"
      aria-label="Graph controls"
    >
      {/* Header */}
      <div className="shrink-0 px-3 py-2.5 border-b border-[#2c2c2c]">
        <p className="text-[10px] font-medium text-zinc-500 tracking-widest uppercase">Graph</p>
        <div className="mt-1 flex items-baseline gap-1.5">
          <span className="text-xs font-medium text-zinc-200 truncate">{nodeCount} nodes</span>
          <span className="text-zinc-600">·</span>
          <span className="text-xs text-zinc-400">{edgeCount} edges</span>
        </div>
      </div>

      {/* Filters (skeleton) */}
      <Section
        open={openSections.Filters}
        onToggle={() => toggleSection('Filters')}
        icon={<Filter className="w-3.5 h-3.5" />}
        title="Filters"
      >
        <p className="text-[10px] text-zinc-600 leading-relaxed">
          Node filters are coming soon — plan to hide isolated nodes or focus on hubs.
        </p>
        <div className="opacity-50 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-zinc-400">Hide isolated nodes</span>
            <Toggle checked={false} onChange={() => { /* skeleton */ }} color={brainColor} />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-zinc-400">Show hubs only</span>
            <Toggle checked={false} onChange={() => { /* skeleton */ }} color={brainColor} />
          </div>
        </div>
      </Section>

      {/* Groups — switch the active brain */}
      <Section
        open={openSections.Groups}
        onToggle={() => toggleSection('Groups')}
        icon={<FolderTree className="w-3.5 h-3.5" />}
        title="Groups"
      >
        <div className="space-y-1">
          {brainsList.map((b) => {
            const active = b.type === activeBrain
            return (
              <button
                key={b.type}
                onClick={() => onSelectBrain(b.type)}
                className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-left text-[11px] transition-colors focus:outline-none ${
                  active
                    ? 'bg-[#2a2a2a] text-zinc-100'
                    : 'text-zinc-400 hover:bg-[#252525] hover:text-zinc-200'
                }`}
              >
                <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: b.color }} />
                <span className="flex-1 truncate">{b.label}</span>
                <span className="text-[10px] font-mono text-zinc-600">{b.nodes}</span>
              </button>
            )
          })}
        </div>
      </Section>

      {/* Display — live toggles */}
      <Section
        open={openSections.Display}
        onToggle={() => toggleSection('Display')}
        icon={<Eye className="w-3.5 h-3.5" />}
        title="Display"
      >
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-zinc-300">Labels</span>
            <Toggle checked={showLabels} onChange={onShowLabels} color={brainColor} />
          </div>
          <p className="text-[9px] text-zinc-600 leading-snug">
            Off = labels only on hover / click. On = hub labels always visible.
          </p>
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-zinc-300">Node thumbnails</span>
            <Toggle checked={showThumbnails} onChange={onShowThumbnails} color={brainColor} />
          </div>
          <p className="text-[9px] text-zinc-600 leading-snug">
            Render saved entity images as node faces instead of plain dots.
          </p>
        </div>
      </Section>

      {/* Forces — live D3 tuning */}
      <Section
        open={openSections.Forces}
        onToggle={() => toggleSection('Forces')}
        icon={<SlidersHorizontal className="w-3.5 h-3.5" />}
        title="Forces"
      >
        <div className="space-y-3">
          <ForceSlider
            label="Repulsion"
            value={chargeStrength}
            min={-600}
            max={-50}
            step={10}
            format={(v) => v.toFixed(0)}
            color={brainColor}
            onChange={onChargeStrength}
          />
          <ForceSlider
            label="Link distance"
            value={linkDistance}
            min={10}
            max={120}
            step={2}
            format={(v) => `${v.toFixed(0)}px`}
            color={brainColor}
            onChange={onLinkDistance}
          />
          <ForceSlider
            label="Center pull"
            value={centerStrength}
            min={0}
            max={0.5}
            step={0.01}
            format={(v) => `${Math.round(v * 200)}%`}
            color={brainColor}
            onChange={onCenterStrength}
          />
          <button
            onClick={onResetForces}
            className="w-full flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-md text-[10px] text-zinc-400 border border-[#3a3a3a] hover:text-zinc-200 hover:border-zinc-500 hover:bg-[#262626] transition-colors focus:outline-none"
          >
            <RotateCcw className="w-3 h-3" />
            Reset forces
          </button>
        </div>
      </Section>
    </aside>
  )
}
