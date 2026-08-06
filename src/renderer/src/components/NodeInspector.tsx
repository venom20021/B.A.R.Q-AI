import { useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X, Focus, Trash2, Loader2, ScanSearch, Boxes, Activity, Link2, Gauge,
} from 'lucide-react'

// ─── Types (structurally compatible with BrainPage's local interfaces) ──────

export interface NodeInspectorNode {
  id: string
  label?: string
}

export interface NodeInspectorNeighbor {
  entity: string
  relation: string
  weight: number
}

export interface NodeInspectorDetails {
  found: boolean
  entity: string
  degree: number
  weight_sum: number
  neighbors: NodeInspectorNeighbor[]
  top_relations: { relation: string; count: number }[]
}

interface NodeInspectorProps {
  node: NodeInspectorNode | null
  details: NodeInspectorDetails | null
  loading: boolean
  error: string | null
  brainColor: string
  brainLabel: string
  brainType: string
  onClose: () => void
  onFocusNode: () => void
  onSelectNeighbor: (id: string) => void
  onRemove: () => void
  confirmRemove: boolean
  removeBusy: boolean
}

// ─── Small local palette (canvas colours live in BrainPage) ────────────────

const NEON_PALETTE = [
  '#818cf8', '#a78bfa', '#c084fc', '#e879f9',
  '#f472b6', '#34d399', '#2dd4bf', '#22d3ee',
]

function nodeColor(id: string): string {
  let hash = 0
  for (let i = 0; i < id.length; i++) {
    hash = ((hash << 5) - hash + id.charCodeAt(i)) | 0
  }
  return NEON_PALETTE[Math.abs(hash) % NEON_PALETTE.length]
}

function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

// ─── Entity type + match-score heuristics ──────────────────────────────────

const ROLE_RE = /\b(developer|engineer|designer|manager|analyst|scientist|architect|admin|lead|intern|recruiter)\b/i
const SKILL_RE = /\b(python|javascript|typescript|react|node|sql|docker|kubernetes|aws|ai|ml|data|graphql|rust|golang|java|c\+\+|html|css|git|linux|excel|flutter|swift|kotlin)\b/i

function inferEntityType(id: string, brainType: string): string {
  const t = (id || '').trim()
  if (!t) return 'Entity'
  if (ROLE_RE.test(t)) return 'Role'
  if (SKILL_RE.test(t)) return 'Skill'
  if (brainType === 'career' && t.length > 3) return 'Career Entity'
  return 'Entity'
}

function matchScore(details: NodeInspectorDetails | null): number {
  if (!details || !details.found) return 0
  return Math.min(99, 40 + details.degree * 9 + details.weight_sum * 2)
}

function scoreColor(score: number, brainColor: string): string {
  if (score >= 80) return '#34d399'
  if (score >= 55) return brainColor
  return '#fbbf24'
}

function truncate(text: string, max = 34): string {
  const t = (text || '').trim()
  return t.length > max ? `${t.slice(0, max - 1)}…` : t
}

// ─── Deep Entity Drawer Modal (deep inspection surface) ────────────────────

interface DeepDrawerProps {
  node: NodeInspectorNode
  details: NodeInspectorDetails | null
  brainColor: string
  brainLabel: string
  brainType: string
  onClose: () => void
  onFocusNode: () => void
  onSelectNeighbor: (id: string) => void
  onRemove: () => void
  confirmRemove: boolean
  removeBusy: boolean
}

function DeepEntityDrawer(props: DeepDrawerProps): JSX.Element {
  const {
    node, details, brainColor, brainLabel, brainType,
    onClose, onFocusNode, onSelectNeighbor, onRemove, confirmRemove, removeBusy,
  } = props
  const type = inferEntityType(node.id, brainType)
  const score = matchScore(details)
  const sc = scoreColor(score, brainColor)

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />

      <motion.div
        initial={{ opacity: 0, scale: 0.94, y: 14 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.94, y: 14 }}
        transition={{ type: 'spring', stiffness: 340, damping: 30 }}
        className="relative glass-strong rounded-2xl w-[560px] max-w-[94vw] max-h-[86vh] flex flex-col overflow-hidden"
        style={{ borderColor: `${brainColor}40` }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 py-3 border-b shrink-0"
          style={{ borderColor: `${brainColor}20`, background: `linear-gradient(90deg, ${hexToRgba(brainColor, 0.10)}, transparent 45%)` }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <span
              className="w-2.5 h-2.5 rounded-full shrink-0 animate-pulse-ring"
              style={{ backgroundColor: nodeColor(node.id), boxShadow: `0 0 12px ${nodeColor(node.id)}` }}
            />
            <div className="min-w-0">
              <p className="text-[8px] font-share-tech uppercase tracking-[0.2em] text-zinc-500">
                Entity Drawer · {brainLabel}
              </p>
              <h2 className="text-sm font-orbitron font-bold text-ghost truncate" style={{ color: '#e8e8f0' }}>
                {node.id}
              </h2>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
            title="Close entity drawer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto overscroll-contain px-4 py-4 space-y-4">
          {/* Type + match */}
          <div className="flex items-center justify-between">
            <span
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[9px] font-share-tech uppercase tracking-wider"
              style={{ color: brainColor, backgroundColor: `${brainColor}12`, border: `1px solid ${brainColor}30` }}
            >
              <Boxes className="w-3 h-3" />
              {type}
            </span>
            {details?.found && (
              <div className="flex items-center gap-2">
                <span className="text-[8px] font-mono text-zinc-500 uppercase tracking-wider">Match</span>
                <span className="text-lg font-orbitron font-bold" style={{ color: sc, textShadow: `0 0 14px ${hexToRgba(sc, 0.6)}` }}>
                  {score}%
                </span>
              </div>
            )}
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: 'Degree', value: details ? String(details.degree) : '—' },
              { label: 'Connections', value: details ? String(details.neighbors.length) : '—' },
              { label: 'Weight Sum', value: details ? String(details.weight_sum) : '—' },
            ].map((s) => (
              <div
                key={s.label}
                className="rounded-xl border px-3 py-2 text-center"
                style={{ borderColor: `${brainColor}25`, backgroundColor: `${brainColor}06` }}
              >
                <p className="text-[8px] font-mono text-zinc-500 uppercase tracking-wider">{s.label}</p>
                <p className="text-sm font-bold font-mono mt-0.5" style={{ color: brainColor }}>{s.value}</p>
              </div>
            ))}
          </div>

          {/* Top relations */}
          {details && details.top_relations.length > 0 && (
            <div>
              <p className="text-[8px] font-mono text-zinc-500 uppercase tracking-[0.18em] mb-1.5">Relations</p>
              <div className="flex flex-wrap gap-1.5">
                {details.top_relations.map((tr) => (
                  <span
                    key={tr.relation}
                    className="text-[9px] font-mono px-2 py-0.5 rounded-full"
                    style={{ color: brainColor, backgroundColor: `${brainColor}10`, border: `1px solid ${brainColor}22` }}
                  >
                    {tr.relation} ×{tr.count}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Connected entities */}
          <div>
            <p className="text-[8px] font-mono text-zinc-500 uppercase tracking-[0.18em] mb-1.5">
              Connected Entities ({details?.neighbors.length ?? 0})
            </p>
            {!details || !details.found ? (
              <p className="text-[10px] font-mono text-zinc-600">Loading details…</p>
            ) : details.neighbors.length === 0 ? (
              <p className="text-[10px] font-mono text-zinc-600">No connections yet.</p>
            ) : (
              <div className="space-y-1">
                {details.neighbors.map((nb) => (
                  <button
                    key={nb.entity}
                    onClick={() => onSelectNeighbor(nb.entity)}
                    className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-left
                               bg-zinc-900/50 border border-zinc-800/60
                               hover:bg-zinc-800/40 hover:border-zinc-700/80 transition-all group"
                    title={`${node.id} —${nb.relation}→ ${nb.entity}`}
                  >
                    <span
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ backgroundColor: nodeColor(nb.entity), boxShadow: `0 0 8px ${hexToRgba(nodeColor(nb.entity), 0.8)}` }}
                    />
                    <span className="flex-1 min-w-0">
                      <span className="block text-[10px] font-mono text-zinc-200 truncate group-hover:text-white">
                        {nb.entity}
                      </span>
                      <span className="block text-[7px] font-mono uppercase tracking-wide truncate" style={{ color: `${brainColor}85` }}>
                        {nb.relation}
                      </span>
                    </span>
                    <span className="text-[9px] font-mono text-zinc-500 shrink-0">×{nb.weight}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Footer actions */}
        <div className="shrink-0 flex items-center gap-2 px-4 py-3 border-t" style={{ borderColor: `${brainColor}18` }}>
          <button
            onClick={onFocusNode}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[9px] font-share-tech uppercase tracking-wider
                       bg-zinc-900/70 border border-zinc-700/60 text-zinc-300
                       hover:border-cyan-500/40 hover:text-cyan-300 transition-all"
          >
            <Focus className="w-3 h-3" /> Focus on canvas
          </button>
          <div className="flex-1" />
          {details?.found && (
            <button
              onClick={onRemove}
              disabled={removeBusy}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[9px] font-share-tech uppercase tracking-wider transition-all disabled:opacity-50
                         ${confirmRemove
                           ? 'border-red-500/70 bg-red-500/25 text-red-200'
                           : 'border-red-500/25 bg-red-500/5 text-red-400/90 hover:bg-red-500/15'}`}
            >
              {removeBusy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
              {removeBusy ? 'Removing…' : confirmRemove ? 'Confirm remove?' : 'Remove'}
            </button>
          )}
        </div>
      </motion.div>
    </motion.div>
  )
}

// ─── Node Inspector Drawer (right-side glassmorphic panel) ─────────────────

export function NodeInspector(props: NodeInspectorProps): JSX.Element | null {
  const {
    node, details, loading, error, brainColor, brainLabel, brainType,
    onClose, onFocusNode, onSelectNeighbor, onRemove, confirmRemove, removeBusy,
  } = props

  const [deepOpen, setDeepOpen] = useState(false)

  const score = useMemo(() => matchScore(details), [details])
  const sc = scoreColor(score, brainColor)
  const type = useMemo(() => inferEntityType(node?.id ?? '', brainType), [node, brainType])

  // Keep the deep drawer in sync if the node changes while it is open
  const drawerNode = node

  return (
    <>
      <AnimatePresence>
        {node && (
          <motion.aside
            initial={{ opacity: 0, x: 56 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 56 }}
            transition={{ type: 'spring', stiffness: 300, damping: 32 }}
            className="absolute inset-y-0 right-0 z-30 w-80 flex flex-col overflow-hidden
                       backdrop-blur-md bg-[#0d111a]/85 border-l border-[#222736]
                       shadow-[-24px_0_60px_rgba(0,0,0,0.55)]"
          >
            {/* Accent sheen */}
            <div
              className="h-px shrink-0"
              style={{ background: `linear-gradient(90deg, transparent, ${brainColor}99, transparent)` }}
            />

            {/* Header */}
            <div className="flex items-center justify-between px-3.5 py-3 border-b shrink-0" style={{ borderColor: `${brainColor}18` }}>
              <div className="flex items-center gap-2.5 min-w-0">
                <span
                  className="w-2 h-2 rounded-full shrink-0 animate-pulse-ring"
                  style={{ backgroundColor: nodeColor(node.id), boxShadow: `0 0 10px ${nodeColor(node.id)}` }}
                />
                <div className="min-w-0">
                  <span
                    className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[7px] font-share-tech uppercase tracking-[0.15em]"
                    style={{ color: brainColor, backgroundColor: `${brainColor}12` }}
                  >
                    <Gauge className="w-2 h-2" />
                    {type} · {brainLabel}
                  </span>
                  <h2 className="text-[11px] font-orbitron font-bold truncate mt-0.5" style={{ color: '#e8e8f0' }}>
                    {node.id}
                  </h2>
                </div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={onFocusNode}
                  className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
                  title="Centre & zoom on this node"
                >
                  <Focus className="w-3 h-3" />
                </button>
                <button
                  onClick={onClose}
                  className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
                  title="Close node details"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto overscroll-contain px-3.5 py-3 space-y-4">
              {loading ? (
                <div className="flex flex-col items-center justify-center py-14 gap-3">
                  <div
                    className="w-6 h-6 border-2 rounded-full animate-spin"
                    style={{ borderColor: `${brainColor}25`, borderTopColor: brainColor }}
                  />
                  <p className="text-[9px] font-mono text-zinc-500 uppercase tracking-wider animate-pulse">
                    Scanning node…
                  </p>
                </div>
              ) : error ? (
                <div className="flex flex-col items-center justify-center py-14 px-3 text-center">
                  <Link2 className="w-6 h-6 text-red-400/70 mb-2" />
                  <p className="text-[10px] font-mono text-zinc-500">{error}</p>
                </div>
              ) : !details || !details.found ? (
                <div className="flex flex-col items-center justify-center py-14 px-3 text-center">
                  <Activity className="w-6 h-6 text-zinc-700 mb-2" />
                  <p className="text-[10px] font-mono text-zinc-600">Entity not found in this brain.</p>
                </div>
              ) : (
                <>
                  {/* Match score */}
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[8px] font-mono text-zinc-500 uppercase tracking-[0.18em]">Match Score</span>
                      <span className="text-sm font-orbitron font-bold" style={{ color: sc, textShadow: `0 0 12px ${hexToRgba(sc, 0.55)}` }}>
                        {score}%
                      </span>
                    </div>
                    <div className="h-1 rounded-full bg-zinc-800/80 overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${score}%` }}
                        transition={{ duration: 0.6, ease: 'easeOut' }}
                        className="h-full rounded-full"
                        style={{ backgroundColor: sc, boxShadow: `0 0 10px ${hexToRgba(sc, 0.8)}` }}
                      />
                    </div>
                  </div>

                  {/* Stats */}
                  <div className="grid grid-cols-3 gap-1.5">
                    {[
                      { label: 'Degree', value: details.degree },
                      { label: 'Links', value: details.neighbors.length },
                      { label: 'Weight', value: details.weight_sum },
                    ].map((s) => (
                      <div
                        key={s.label}
                        className="rounded-lg border px-2 py-1.5 text-center"
                        style={{ borderColor: `${brainColor}22`, backgroundColor: `${brainColor}06` }}
                      >
                        <p className="text-[7px] font-mono text-zinc-500 uppercase tracking-wider">{s.label}</p>
                        <p className="text-xs font-bold font-mono mt-0.5" style={{ color: brainColor }}>{s.value}</p>
                      </div>
                    ))}
                  </div>

                  {/* Top relations */}
                  {details.top_relations.length > 0 && (
                    <div>
                      <p className="text-[8px] font-mono text-zinc-500 uppercase tracking-[0.18em] mb-1.5">Relations</p>
                      <div className="flex flex-wrap gap-1">
                        {details.top_relations.map((tr) => (
                          <span
                            key={tr.relation}
                            className="text-[8px] font-mono px-1.5 py-0.5 rounded"
                            style={{ color: brainColor, backgroundColor: `${brainColor}12` }}
                          >
                            {tr.relation} ×{tr.count}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Connected entities */}
                  <div>
                    <p className="text-[8px] font-mono text-zinc-500 uppercase tracking-[0.18em] mb-1.5">
                      Connected Entities ({details.neighbors.length})
                    </p>
                    {details.neighbors.length === 0 ? (
                      <p className="text-[9px] font-mono text-zinc-700">No connections yet.</p>
                    ) : (
                      <div className="space-y-1">
                        {details.neighbors.map((nb) => (
                          <button
                            key={nb.entity}
                            onClick={() => onSelectNeighbor(nb.entity)}
                            className="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left
                                       bg-zinc-900/50 border border-zinc-800/60
                                       hover:bg-zinc-800/40 hover:border-zinc-700/70 transition-all group"
                            title={`${node.id} —${nb.relation}→ ${nb.entity}`}
                          >
                            <span
                              className="w-1.5 h-1.5 rounded-full shrink-0"
                              style={{ backgroundColor: nodeColor(nb.entity), boxShadow: `0 0 6px ${hexToRgba(nodeColor(nb.entity), 0.8)}` }}
                            />
                            <span className="flex-1 min-w-0">
                              <span className="block text-[9px] font-mono text-zinc-200 truncate group-hover:text-white">
                                {nb.entity}
                              </span>
                              <span className="block text-[7px] font-mono uppercase tracking-wide truncate" style={{ color: `${brainColor}85` }}>
                                {nb.relation}
                              </span>
                            </span>
                            <span className="text-[8px] font-mono text-zinc-500 shrink-0">×{nb.weight}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>

            {/* Footer */}
            <div className="shrink-0 px-3.5 py-3 border-t space-y-1.5" style={{ borderColor: `${brainColor}18` }}>
              <button
                onClick={() => setDeepOpen(true)}
                disabled={!node}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-[9px] font-share-tech
                           uppercase tracking-[0.15em] transition-all disabled:opacity-40 group"
                style={{
                  color: '#06121a',
                  background: `linear-gradient(90deg, ${brainColor}, ${nodeColor(node.id)})`,
                  boxShadow: `0 0 18px ${hexToRgba(brainColor, 0.45)}`,
                }}
              >
                <ScanSearch className="w-3.5 h-3.5" />
                Open Entity Drawer
              </button>
              {details?.found && (
                <button
                  onClick={onRemove}
                  disabled={removeBusy}
                  className={`w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg border text-[9px] font-share-tech uppercase tracking-wider transition-all disabled:opacity-50
                             ${confirmRemove
                               ? 'border-red-500/70 bg-red-500/25 text-red-200'
                               : 'border-red-500/25 bg-red-500/5 text-red-400/90 hover:bg-red-500/15'}`}
                  title={confirmRemove
                    ? 'Click again to permanently remove this entity'
                    : 'Remove this entity and all its connections from the brain'}
                >
                  {removeBusy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                  {removeBusy ? 'Removing…' : confirmRemove ? 'Confirm remove?' : 'Remove entity'}
                </button>
              )}
              <p className="text-[7px] font-mono text-center truncate" style={{ color: `${brainColor}60` }}>
                {confirmRemove
                  ? 'Click again to permanently delete'
                  : `Click a connected entity to inspect it · ${truncate(brainLabel, 20)}`}
              </p>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* Deep entity drawer */}
      <AnimatePresence>
        {deepOpen && drawerNode && (
          <DeepEntityDrawer
            node={drawerNode}
            details={details}
            brainColor={brainColor}
            brainLabel={brainLabel}
            brainType={brainType}
            onClose={() => setDeepOpen(false)}
            onFocusNode={() => { setDeepOpen(false); onFocusNode() }}
            onSelectNeighbor={onSelectNeighbor}
            onRemove={onRemove}
            confirmRemove={confirmRemove}
            removeBusy={removeBusy}
          />
        )}
      </AnimatePresence>
    </>
  )
}

export default NodeInspector
