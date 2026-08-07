import { useState, useEffect, useRef, useCallback, useMemo, startTransition } from 'react'
import { motion } from 'framer-motion'
import {
  Info, RotateCw, AlertCircle, Search, X, Zap, GitBranch,
  StickyNote, FileText, MessageCircle, Briefcase, Brain, Sparkles,
  BarChart3, Network, Clock, Filter, FilePlus2, Database, BadgePlus,
  CirclePlus, Loader2,
} from 'lucide-react'
import { NodeInspector } from '../components/NodeInspector'
import { formatDistanceToNow } from '../utils/time'
import {
  loadLastSelected, saveLastSelected,
  rememberSelection, forgetSelection, resolveRestoreTarget,
} from '../utils/brainSelectionMemory'
import ForceGraph2D from 'react-force-graph-2d'

// ─── Types ─────────────────────────────────────────────────────────────────

interface GraphNode {
  id: string
  label?: string
  x?: number
  y?: number
  vx?: number
  vy?: number
}

interface GraphLink {
  source: string | GraphNode
  target: string | GraphNode
  relation?: string
  weight?: number
}

interface GraphMeta {
  brain_type: string
  label: string
  color: string
  neon_glow: string
  nodes: number
  edges: number
}

interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
  _meta?: GraphMeta
}

interface EntityImageRecord {
  id: number
  brain_id: string
  entity: string
  prompt: string
  image_url: string
  created_at: string
}

interface BrainMeta {
  type: string
  label: string
  description: string
  color: string
  neon_glow: string
  icon: string
  nodes: number
  edges: number
}

interface BrainStats {
  brain_type: string
  nodes: number
  edges: number
  density: number
  connected_components: number
  top_entities: { entity: string; centrality: number }[]
}

interface NodeNeighbor {
  entity: string
  relation: string
  weight: number
}

interface NodeDetails {
  found: boolean
  entity: string
  degree: number
  weight_sum: number
  neighbors: NodeNeighbor[]
  top_relations: { relation: string; count: number }[]
}

interface TimelineEntry {
  timestamp: string
  brain_type: string
  subject: string
  relation: string
  object_: string
  is_new_edge: boolean
}

// ─── Icon Map ──────────────────────────────────────────────────────────────

const BRAIN_ICONS: Record<string, typeof Brain> = {
  'sticky-note': StickyNote,
  'file-text': FileText,
  'message-circle': MessageCircle,
  'briefcase': Briefcase,
  'sparkles': Sparkles,
  'brain': Brain,
}

function getBrainIcon(icon: string): typeof Brain {
  return BRAIN_ICONS[icon] ?? Brain
}

// ─── Color Utilities ───────────────────────────────────────────────────────

interface ThemeColors {
  brain_type: string
  label: string
  color: string
  neon_glow: string
  bg: string
  nodeText: string
  linkColor: string
  dimmedLink: string
  mutedNode: string
  mutedLink: string
  highlightNode: string
  highlightLink: string
  searchNode: string
  searchNodeGlow: string
  searchLink: string
}

function buildTheme(meta: GraphMeta | undefined, fallback: GraphMeta): ThemeColors {
  const m = meta ?? fallback
  const hex = m.color
  const rgb = hexToRgb(hex)
  return {
    brain_type: m.brain_type,
    label: m.label,
    color: hex,
    neon_glow: m.neon_glow,
    bg: '#09090b',
    nodeText: '#e2e8f0',
    linkColor: `rgba(${rgb.r},${rgb.g},${rgb.b},0.18)`,
    dimmedLink: `rgba(${rgb.r},${rgb.g},${rgb.b},0.08)`,
    mutedNode: 'rgba(113,113,122,0.2)',
    mutedLink: 'rgba(113,113,122,0.06)',
    highlightNode: hex,
    highlightLink: `rgba(${rgb.r},${rgb.g},${rgb.b},0.35)`,
    searchNode: '#34d399',
    searchNodeGlow: 'rgba(52,211,153,0.6)',
    searchLink: 'rgba(52,211,153,0.35)',
  }
}

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const h = hex.replace('#', '')
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  }
}

function hexToRgba(hex: string, alpha: number): string {
  const { r, g, b } = hexToRgb(hex)
  return `rgba(${r},${g},${b},${alpha})`
}

// Blend two hex colours toward a midpoint (used for link colour gradients).
// Returns a `#rrggbb` hex so the result stays compatible with hexToRgba().
function blendHex(a: string, b: string, t: number): string {
  const ca = hexToRgb(a)
  const cb = hexToRgb(b)
  const r = Math.round(ca.r + (cb.r - ca.r) * t)
  const g = Math.round(ca.g + (cb.g - ca.g) * t)
  const bl = Math.round(ca.b + (cb.b - ca.b) * t)
  return `#${[r, g, bl].map(c => c.toString(16).padStart(2, '0')).join('')}`
}

// Rounded-rect path helper (avoids relying on ctx.roundRect availability).
function roundRectPath(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number, r: number,
): void {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

// ─── Pulse timing constants ────────────────────────────────────────────────

const PULSE_DURATION_MS = 2200
const PULSE_PEAK_MS = 300
const PULSE_SUSTAIN_MS = 500
const AUTO_POLL_INTERVAL_MS = 8000

// ─── Level-of-Detail / visual hierarchy constants ───────────────────────────

// Nodes with degree >= this are "hub" nodes: always labelled, bigger radius,
// and drawn with a breathing outer pulse ring.
const HUB_DEGREE_THRESHOLD = 2
// Max label length before ellipsis truncation (kills horizontal pile-up).
const LABEL_MAX_CHARS = 26
// Idle repaint clock — drives the hub pulse rings + link shimmer at a cheap
// ~7fps without keeping the force simulation hot.
const IDLE_REFRESH_MS = 140

// ─── Fallback meta for initial render before brain list loads ────────────────

const FALLBACK_META: GraphMeta = {
  brain_type: 'general',
  label: 'General Knowledge',
  color: '#818cf8',
  neon_glow: 'rgba(129,140,248,0.5)',
  nodes: 0,
  edges: 0,
}

// ─── Fallback brains used when the backend list call fails or hangs, so the
// page never degrades into a dead skeleton / blank state. Mirrors the backend
// BRAIN_REGISTRY metadata. ────────────────────────────────────────────────────

const FALLBACK_BRAINS: BrainMeta[] = [
  { type: 'general', label: 'General Knowledge', description: 'Catch-all knowledge from auto-extraction and ingestion', color: '#818cf8', neon_glow: 'rgba(129,140,248,0.5)', icon: 'brain', nodes: 0, edges: 0 },
  { type: 'apple_notes', label: 'Apple Notes', description: 'Extracted knowledge from Apple Notes exports', color: '#f59e0b', neon_glow: 'rgba(245,158,11,0.5)', icon: 'sticky-note', nodes: 0, edges: 0 },
  { type: 'google_docs', label: 'Google Docs', description: 'Extracted knowledge from Google Documents', color: '#3b82f6', neon_glow: 'rgba(59,130,246,0.5)', icon: 'file-text', nodes: 0, edges: 0 },
  { type: 'ai_chats', label: 'AI Chats', description: 'Knowledge from AI chat conversations', color: '#10b981', neon_glow: 'rgba(16,185,129,0.5)', icon: 'message-circle', nodes: 0, edges: 0 },
  { type: 'career', label: 'Career Engine', description: 'Job descriptions, skills, companies, and career data', color: '#a855f7', neon_glow: 'rgba(168,85,247,0.5)', icon: 'briefcase', nodes: 0, edges: 0 },
  { type: 'gemini_chats', label: 'Gemini Chats', description: 'Conversations and knowledge from Google Gemini interactions', color: '#d946ef', neon_glow: 'rgba(217,70,239,0.5)', icon: 'sparkles', nodes: 0, edges: 0 },
]

// ─── Request timeout helper — prevents endless spinners on a dead backend ───

function withTimeout<T>(promise: Promise<T> | undefined, ms = 12000): Promise<T | undefined> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const timeout = new Promise<undefined>((resolve) => {
    timer = setTimeout(() => resolve(undefined), ms)
  })
  return Promise.race([promise, timeout]).finally(() => {
    if (timer) clearTimeout(timer)
  })
}

// ─── Helper: pick a neon hue per node ──────────────────────────────────────

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

// ─── Multi-Brain Visualizer Component ──────────────────────────────────────

export function BrainPage(): JSX.Element {
  // ── Brain state ──────────────────────────────────────────────────────
  const [activeBrain, setActiveBrain] = useState('general')
  const [brainsList, setBrainsList] = useState<BrainMeta[]>([])
  const [brainStats, setBrainStats] = useState<BrainStats | null>(null)

  // ── Graph state ──────────────────────────────────────────────────────
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [entityImages, setEntityImages] = useState<Map<string, string>>(new Map())
  const imgCacheRef = useRef<Map<string, HTMLImageElement>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null)
  const [dimension, setDimension] = useState({ width: 800, height: 600 })
  const containerRef = useRef<HTMLDivElement>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const graphRef = useRef<any>(null)
  const [highlightNodes, setHighlightNodes] = useState<Set<string>>(new Set())
  const [highlightLinks, setHighlightLinks] = useState<Set<string>>(new Set())

  // ── Search state ─────────────────────────────────────────────────────
  const [searchQuery, setSearchQuery] = useState('')
  const [searchFocused, setSearchFocused] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // ── Timeline state ──────────────────────────────────────────────────
  const [showTimeline, setShowTimeline] = useState(false)
  const [timelineEntries, setTimelineEntries] = useState<TimelineEntry[]>([])
  const [timelineLoading, setTimelineLoading] = useState(false)
  const [timelineAllBrains, setTimelineAllBrains] = useState(false)
  const [newEntryKeys, setNewEntryKeys] = useState<Set<string>>(new Set())
  const prevTimelineKeysRef = useRef<Set<string>>(new Set())
  const timelineInitializedRef = useRef(false)

  // ── Ingest panel state ─────────────────────────────────────────────
  const [showIngest, setShowIngest] = useState(false)
  const [ingestText, setIngestText] = useState('')
  const [ingestBusy, setIngestBusy] = useState(false)
  const [importBusy, setImportBusy] = useState(false)
  const [ingestResult, setIngestResult] = useState<string | null>(null)
  const [triplet, setTriplet] = useState({ subject: '', relation: '', object: '' })

  // ── Selected node details panel state ──────────────────────────────
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [nodeDetails, setNodeDetails] = useState<NodeDetails | null>(null)
  const [nodeDetailsLoading, setNodeDetailsLoading] = useState(false)
  const [nodeDetailsError, setNodeDetailsError] = useState<string | null>(null)
  const [confirmRemove, setConfirmRemove] = useState(false)
  const [removeBusy, setRemoveBusy] = useState(false)
  const confirmRemoveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── Per-brain last-selected node memory (restored on brain switch / restart)
  const [lastSelectedByBrain, setLastSelectedByBrain] =
    useState<Record<string, string>>(loadLastSelected)
  const activeBrainRef = useRef(activeBrain)

  // Persist the memory whenever it changes
  useEffect(() => {
    saveLastSelected(lastSelectedByBrain)
  }, [lastSelectedByBrain])

  // Keep a ref of the current brain so deferred restores can detect a
  // brain switch that happened while the transition was pending.
  useEffect(() => {
    activeBrainRef.current = activeBrain
  }, [activeBrain])

  // ── Synaptic pulse state ─────────────────────────────────────────────
  const [pulseIntensity, setPulseIntensity] = useState(0)
  const pulseAnimRef = useRef<number | null>(null)
  const prevMetaRef = useRef<GraphMeta | null>(null)
  const flashTimersRef = useRef<ReturnType<typeof setTimeout>[]>([])

  // ── Compute dynamic theme from active brain ──────────────────────────
  const activeMeta = useMemo<GraphMeta>(() => {
    if (graphData?._meta) return graphData._meta
    if (brainsList.length > 0) {
      const b = brainsList.find(b => b.type === activeBrain)
      if (b) {
        return {
          brain_type: b.type,
          label: b.label,
          color: b.color,
          neon_glow: b.neon_glow,
          nodes: b.nodes,
          edges: b.edges,
        }
      }
    }
    return FALLBACK_META
  }, [graphData?._meta, brainsList, activeBrain])

  const theme = useMemo(() => buildTheme(graphData?._meta, FALLBACK_META), [graphData?._meta])

  // ── Per-node degree map (drives radii, hub detection, LOD labels) ────
  const degreeMap = useMemo(() => {
    const m = new Map<string, number>()
    for (const l of graphData?.links ?? []) {
      const s = typeof l.source === 'string' ? l.source : (l.source as GraphNode)?.id
      const t = typeof l.target === 'string' ? l.target : (l.target as GraphNode)?.id
      if (s) m.set(s, (m.get(s) ?? 0) + 1)
      if (t) m.set(t, (m.get(t) ?? 0) + 1)
    }
    return m
  }, [graphData])

  // Hub threshold derived from the degree distribution (top quartile) so
  // "always-on" labels genuinely target the top-degree nodes, even in dense
  // brains where a fixed threshold would label almost everything.
  const hubThreshold = useMemo(() => {
    const degs = Array.from(degreeMap.values()).sort((a, b) => a - b)
    if (degs.length === 0) return HUB_DEGREE_THRESHOLD
    const p75 = degs[Math.min(degs.length - 1, Math.floor(degs.length * 0.75))]
    return Math.max(HUB_DEGREE_THRESHOLD, p75)
  }, [degreeMap])

  // ── Idle animation clock + force-simulation status (bottom HUD) ─────
  // (ref seeded with 0 — first paint uses a static ring; the interval
  //  updates it on the first tick, satisfying the react purity rule)
  const pulseClockRef = useRef(0)
  const [simRunning, setSimRunning] = useState(false)
  useEffect(() => {
    if (!graphData || graphData.nodes.length === 0) return
    // Skip the repaint loop entirely when no hub rings need animating.
    if (!Array.from(degreeMap.values()).some(d => d >= hubThreshold)) return
    const id = setInterval(() => {
      if (document.hidden) return
      pulseClockRef.current = performance.now()
      try {
        graphRef.current?.refresh()
        const running = typeof graphRef.current?.isSimulationRunning === 'function'
          ? graphRef.current.isSimulationRunning()
          : false
        setSimRunning(Boolean(running))
      } catch { /* ignore */ }
    }, IDLE_REFRESH_MS)
    return () => clearInterval(id)
  }, [graphData, degreeMap, hubThreshold])

  // ── Derived search helpers ───────────────────────────────────────────
  const matchingNodeIds = useMemo(() => {
    if (!searchQuery.trim() || !graphData) return null
    const q = searchQuery.toLowerCase().trim()
    const ids = new Set<string>()
    for (const n of graphData.nodes) {
      if (n.id.toLowerCase().includes(q)) {
        ids.add(n.id)
      }
    }
    return ids
  }, [searchQuery, graphData])

  const searchSuggestions = useMemo(() => {
    if (!searchQuery.trim() || !graphData) return []
    const q = searchQuery.toLowerCase().trim()
    const scored: { id: string; score: number }[] = []
    for (const n of graphData.nodes) {
      const id = n.id.toLowerCase()
      if (id.includes(q)) {
        let score = 0
        if (id === q) score = 100
        else if (id.startsWith(q)) score = 50
        else score = 10
        scored.push({ id: n.id, score })
      }
    }
    scored.sort((a, b) => b.score - a.score)
    return scored.slice(0, 8).map(s => s.id)
  }, [searchQuery, graphData])

  // ── Highlight updates on search ──────────────────────────────────────
  useEffect(() => {
    if (!matchingNodeIds || !graphData) {
      // No active search — restore the pinned node's highlight if one is open
      /* eslint-disable react-hooks/set-state-in-effect */
      // `graphData` can be null in this branch (search cleared) — only
      // restore the pinned highlight when the graph is actually present.
      if (selectedNode?.id && graphData) {
        const nodeIds = new Set<string>([selectedNode.id])
        const linkKeys = new Set<string>()
        for (const link of graphData.links) {
          const src = typeof link.source === 'string' ? link.source : (link.source as GraphNode)?.id
          const tgt = typeof link.target === 'string' ? link.target : (link.target as GraphNode)?.id
          if (src === selectedNode.id || tgt === selectedNode.id) {
            if (src) nodeIds.add(src)
            if (tgt) nodeIds.add(tgt)
            if (src && tgt) linkKeys.add(`${src}->${tgt}`)
          }
        }
        setHighlightNodes(nodeIds)
        setHighlightLinks(linkKeys)
      } else {
        setHighlightNodes(new Set())
        setHighlightLinks(new Set())
      }
      /* eslint-enable react-hooks/set-state-in-effect */
      return
    }

    const nodeIds = new Set(matchingNodeIds)
    const linkKeys = new Set<string>()

    for (const link of graphData.links) {
      const src = typeof link.source === 'string' ? link.source : (link.source as GraphNode)?.id
      const tgt = typeof link.target === 'string' ? link.target : (link.target as GraphNode)?.id
      if (!src || !tgt) continue

      const srcMatch = matchingNodeIds.has(src)
      const tgtMatch = matchingNodeIds.has(tgt)

      if (srcMatch && tgtMatch) {
        linkKeys.add(`${src}->${tgt}`)
      } else if (srcMatch) {
        nodeIds.add(tgt)
        linkKeys.add(`${src}->${tgt}`)
      } else if (tgtMatch) {
        nodeIds.add(src)
        linkKeys.add(`${src}->${tgt}`)
      }
    }

    setHighlightNodes(nodeIds)
    setHighlightLinks(linkKeys)
  }, [matchingNodeIds, graphData, selectedNode?.id])

  // ── Keyboard shortcut ────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // ── Handle selecting a search suggestion ─────────────────────────────
  const handleSelectSearch = useCallback((entityId: string) => {
    setSearchQuery(entityId)
    setSearchFocused(false)
    if (graphRef.current && graphData) {
      const node = graphData.nodes.find(n => n.id === entityId)
      if (node && node.x != null && node.y != null) {
        graphRef.current.centerAt(node.x, node.y, 600)
        graphRef.current.zoom(3, 600)
      }
    }
  }, [graphData])

  const handleClearSearch = useCallback(() => {
    setSearchQuery('')
    setSearchFocused(false)
    inputRef.current?.blur()
  }, [])

  // ── Responsive container ──────────────────────────────────────────────
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        setDimension({ width: Math.floor(width), height: Math.floor(height) })
      }
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  // ── Fetch brains list on mount ───────────────────────────────────────
  useEffect(() => {
    const fetchBrains = async () => {
      try {
        const resp: unknown = await withTimeout(window.barq?.python.request('/api/brain/list'))
        if (Array.isArray(resp) && resp.length > 0) {
          setBrainsList(resp as BrainMeta[])
        } else {
          // Backend unreachable / hung / returned nothing — use the known
          // brains so the page never renders as a dead skeleton.
          setBrainsList(FALLBACK_BRAINS)
        }
      } catch {
        setBrainsList(FALLBACK_BRAINS)
      }
    }
    fetchBrains()
  }, [])

  // ── Fetch brain stats ────────────────────────────────────────────────
  const fetchBrainStats = useCallback(async () => {
    try {
      const resp: unknown = await withTimeout(window.barq?.python.request(`/api/brain/${activeBrain}/stats`))
      if (resp && typeof resp === 'object') {
        setBrainStats(resp as BrainStats)
      }
    } catch {
      setBrainStats(null)
    }
  }, [activeBrain])

  // ── Fetch graph data for the active brain ────────────────────────────
  const fetchGraph = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resp: unknown = await withTimeout(window.barq?.python.request(`/api/brain/${activeBrain}/visualize`))
      if (!resp || typeof resp !== 'object') {
        throw new Error('Backend unreachable or timed out — check the Python sidecar')
      }
      const data = resp as GraphData

      // Deduplicate nodes
      const seen = new Set<string>()
      data.nodes = data.nodes.filter((n) => {
        if (!n.id || seen.has(n.id)) return false
        seen.add(n.id)
        return true
      })

      // Normalize link references
      data.links = data.links.map((l) => ({
        ...l,
        source: typeof l.source === 'object' ? (l.source as GraphNode).id : l.source,
        target: typeof l.target === 'object' ? (l.target as GraphNode).id : l.target,
      }))

      setGraphData(data)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load graph'
      setError(msg)
      console.error('[BrainPage]', err)
    } finally {
      setLoading(false)
    }
  }, [activeBrain])

  // ── Fetch saved entity images → thumbnail markers on nodes ──────────
  const fetchEntityImages = useCallback(async () => {
    try {
      const resp: unknown = await withTimeout(
        window.barq?.python.request('/api/brain/images?brain_id=' + encodeURIComponent(activeBrain)),
      )
      if (!resp || typeof resp !== 'object') return
      const items = (resp as { items?: EntityImageRecord[] }).items
      if (!Array.isArray(items)) return
      // Backend returns newest-first → first occurrence per entity wins.
      // Guard against a stale response landing after a brain switch
      if (activeBrainRef.current !== activeBrain) return
      const byEntity = new Map<string, string>()
      for (const it of items) {
        if (it && it.entity && it.image_url && !byEntity.has(it.entity)) byEntity.set(it.entity, it.image_url)
      }
      setEntityImages(byEntity)
      // Preload thumbnails so paintNode can draw them synchronously.
      for (const url of byEntity.values()) {
        if (imgCacheRef.current.has(url)) continue
        const img = new Image()
        img.onload = () => {
          imgCacheRef.current.set(url, img)
          graphRef.current?.refresh()
        }
        img.src = url
      }
    } catch {
      // Thumbnails are progressive enhancement - never block the graph.
    }
  }, [activeBrain])

  // ── Fetch timeline entries ───────────────────────────────────────────
  const fetchTimeline = useCallback(async () => {
    setTimelineLoading(true)
    try {
      const endpoint = timelineAllBrains
        ? '/api/brain/timeline?limit=100'
        : `/api/brain/${activeBrain}/timeline?limit=100`
      const resp: unknown = await withTimeout(window.barq?.python.request(endpoint))
      if (Array.isArray(resp)) {
        const fresh = resp as TimelineEntry[]

        // Detect new entries by comparing composite keys
        const freshKeys = new Set(
          fresh.map(e => `${e.timestamp}-${e.subject}-${e.object_}-${e.relation}`)
        )

        // Skip flash on initial population — only flash on subsequent polls
        if (!timelineInitializedRef.current) {
          timelineInitializedRef.current = true
          prevTimelineKeysRef.current = freshKeys
          setTimelineEntries(fresh)
          setTimelineLoading(false)
          return
        }

        const prevKeys = prevTimelineKeysRef.current
        const addedKeys = new Set<string>()
        for (const k of freshKeys) {
          if (!prevKeys.has(k)) addedKeys.add(k)
        }

        setTimelineEntries(fresh)
        prevTimelineKeysRef.current = freshKeys

        // Set flash keys and schedule their removal
        if (addedKeys.size > 0) {
          setNewEntryKeys(addedKeys)
          // Auto-clear flash after 2.5s
          const timer = setTimeout(() => {
            setNewEntryKeys(prev => {
              const next = new Set(prev)
              for (const k of addedKeys) next.delete(k)
              return next
            })
          }, 2500)
          flashTimersRef.current.push(timer)
        }
      }
    } catch {
      // silently fail
    } finally {
      setTimelineLoading(false)
    }
  }, [activeBrain, timelineAllBrains])

  // ── Fetch details for the selected node (defined before refreshAll which
  //     re-fetches it after graph mutations) ─────────────────────────────
  const fetchNodeDetails = useCallback(async (entityId: string) => {
    setNodeDetailsLoading(true)
    setNodeDetailsError(null)
    try {
      const resp: unknown = await withTimeout(
        window.barq?.python.request(
          `/api/brain/${activeBrain}/node/${encodeURIComponent(entityId)}`,
        ),
      )
      if (resp && typeof resp === 'object') {
        setNodeDetails(resp as NodeDetails)
      } else {
        setNodeDetails(null)
        setNodeDetailsError('Backend unreachable or timed out — could not load node details')
      }
    } catch (e) {
      setNodeDetails(null)
      setNodeDetailsError(e instanceof Error ? e.message : String(e))
    } finally {
      setNodeDetailsLoading(false)
    }
  }, [activeBrain])

  // ── Refresh graph + stats + tab counts after any mutation ────────────
  const refreshAll = useCallback(async () => {
    await Promise.allSettled([fetchGraph(), fetchBrainStats(), fetchEntityImages()])
    const resp: unknown = await withTimeout(window.barq?.python.request('/api/brain/list'))
    if (Array.isArray(resp) && resp.length > 0) setBrainsList(resp as BrainMeta[])
    // Keep the details panel fresh when the graph changed under it
    if (selectedNode?.id) fetchNodeDetails(selectedNode.id)
    if (showTimeline) fetchTimeline()
  }, [fetchGraph, fetchBrainStats, showTimeline, fetchTimeline, selectedNode, fetchNodeDetails, fetchEntityImages])

  // ── Ingest pasted text into the active brain (LLM extraction) ────────
  const handleIngestText = async (): Promise<void> => {
    if (!ingestText.trim()) return
    setIngestBusy(true)
    setIngestResult(null)
    try {
      const resp: unknown = await window.barq?.python.request(
        `/api/brain/${activeBrain}/ingest`, { text: ingestText },
      )
      const r = resp as { triplets_added?: number; nodes?: number; edges?: number; note?: string; provider?: string } | undefined
      const providerLabel = r?.provider === 'ollama'
        ? 'via Ollama'
        : r?.provider === 'gemini'
          ? 'via Gemini'
          : null
      setIngestResult(
        r?.note
          ?? `Added ${r?.triplets_added ?? 0} triplets ${providerLabel ? `${providerLabel} ` : ''}— ${r?.nodes ?? '?'} nodes, ${r?.edges ?? '?'} edges`,
      )
      setIngestText('')
      await refreshAll()
    } catch (e) {
      setIngestResult(`Ingest failed: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setIngestBusy(false)
    }
  }

  // ── Add a direct triplet to the active brain ─────────────────────────
  const handleAddTriplet = async (): Promise<void> => {
    if (!triplet.subject.trim() || !triplet.object.trim()) return
    setIngestBusy(true)
    setIngestResult(null)
    try {
      const resp: unknown = await window.barq?.python.request(
        `/api/brain/${activeBrain}/triplet`, {
          subject: triplet.subject.trim(),
          relation: triplet.relation.trim() || 'RELATED_TO',
          object: triplet.object.trim(),
        },
      )
      const r = resp as { nodes?: number; edges?: number } | undefined
      setIngestResult(`Triplet added — ${r?.nodes ?? '?'} nodes, ${r?.edges ?? '?'} edges`)
      setTriplet({ subject: '', relation: '', object: '' })
      await refreshAll()
    } catch (e) {
      setIngestResult(`Add failed: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setIngestBusy(false)
    }
  }

  // ── Auto-import real BARQ data (notes / memory / jobs) ───────────────
  const handleImportSources = async (): Promise<void> => {
    setImportBusy(true)
    setIngestResult(null)
    try {
      const resp: unknown = await window.barq?.python.request('/api/brain/import-from-sources', {})
      const r = resp as { results?: { direct_triplets?: Record<string, number> } } | undefined
      const d = r?.results?.direct_triplets
      const summary = d
        ? Object.entries(d).filter(([, v]) => v > 0).map(([k, v]) => `${k}: ${v}`).join(' · ')
        : ''
      setIngestResult(`Imported from BARQ data${summary ? ` — ${summary}` : ''}`)
      await refreshAll()
    } catch (e) {
      setIngestResult(`Import failed: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setImportBusy(false)
    }
  }

  // ── Seed a demo graph into empty brains ──────────────────────────────
  const handleSeedDemo = async (): Promise<void> => {
    setIngestBusy(true)
    setIngestResult(null)
    try {
      const resp: unknown = await window.barq?.python.request('/api/brain/seed-demo', {})
      const r = resp as { total_added?: number } | undefined
      setIngestResult(`Demo graph seeded — ${r?.total_added ?? 0} triplets added`)
      await refreshAll()
    } catch (e) {
      setIngestResult(`Seed failed: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setIngestBusy(false)
    }
  }

  // ── Re-fetch when activeBrain or timeline toggle changes ────────────
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    fetchGraph()
    fetchBrainStats()
    fetchEntityImages()
    if (showTimeline) {
      timelineInitializedRef.current = false
      fetchTimeline()
    }
  }, [fetchGraph, fetchBrainStats, showTimeline, fetchTimeline, fetchEntityImages])
  /* eslint-enable react-hooks/set-state-in-effect */

  // ── Synaptic pulse animation loop ────────────────────────────────────
  const triggerPulse = useCallback(() => {
    const start = performance.now()

    const animate = (now: number) => {
      const elapsed = now - start

      if (elapsed >= PULSE_DURATION_MS) {
        setPulseIntensity(0)
        pulseAnimRef.current = null
        return
      }

      let intensity: number
      if (elapsed < PULSE_PEAK_MS) {
        intensity = elapsed / PULSE_PEAK_MS
      } else if (elapsed < PULSE_SUSTAIN_MS) {
        intensity = 1.0
      } else {
        const decay = (elapsed - PULSE_SUSTAIN_MS) / (PULSE_DURATION_MS - PULSE_SUSTAIN_MS)
        intensity = Math.max(0, 1 - decay * decay)
      }

      setPulseIntensity(intensity)
      pulseAnimRef.current = requestAnimationFrame(animate)
    }

    if (pulseAnimRef.current) {
      cancelAnimationFrame(pulseAnimRef.current)
    }
    pulseAnimRef.current = requestAnimationFrame(animate)
  }, [])

  // ── Detect graph changes & trigger synaptic pulse ────────────────────
  useEffect(() => {
    if (!graphData?._meta) return
    const meta = graphData._meta
    const prev = prevMetaRef.current

    const isNewData = !prev || prev.nodes !== meta.nodes || prev.edges !== meta.edges
    prevMetaRef.current = meta

    if (isNewData) {
      startTransition(() => {
        triggerPulse()
      })
    }
    // We intentionally depend on nodes/edges changes only, not the full meta object
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData?._meta?.nodes, graphData?._meta?.edges])

  // ── Auto-poll backend for new graph data ─────────────────────────────
  useEffect(() => {
    const interval = setInterval(() => {
      fetchGraph()
      fetchEntityImages()
    }, AUTO_POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchGraph, fetchEntityImages])

  // ── Auto-poll timeline entries while panel is open ────────────────────
  useEffect(() => {
    if (!showTimeline) return
    const interval = setInterval(() => {
      fetchTimeline()
    }, AUTO_POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [showTimeline, fetchTimeline])

  // Cleanup animation frame + flash timers on unmount
  useEffect(() => {
    return () => {
      if (pulseAnimRef.current) {
        cancelAnimationFrame(pulseAnimRef.current)
      }
      for (const t of flashTimersRef.current) clearTimeout(t)
      flashTimersRef.current = []
      if (confirmRemoveTimerRef.current) {
        clearTimeout(confirmRemoveTimerRef.current)
        confirmRemoveTimerRef.current = null
      }
    }
  }, [])

  // ── Node selection / details panel ───────────────────────────────────
  const applySelectionHighlight = useCallback((entityId: string) => {
    if (!graphData) return
    const nodeIds = new Set<string>([entityId])
    const linkKeys = new Set<string>()
    for (const link of graphData.links) {
      const src = typeof link.source === 'string' ? link.source : (link.source as GraphNode)?.id
      const tgt = typeof link.target === 'string' ? link.target : (link.target as GraphNode)?.id
      if (src === entityId || tgt === entityId) {
        if (src) nodeIds.add(src)
        if (tgt) nodeIds.add(tgt)
        if (src && tgt) linkKeys.add(`${src}->${tgt}`)
      }
    }
    setHighlightNodes(nodeIds)
    setHighlightLinks(linkKeys)
  }, [graphData])

  // ── Node hover highlight ─────────────────────────────────────────────
  const handleNodeHover = useCallback((node: GraphNode | null) => {
    setHoveredNode(node)
    if (!node || !graphData) {
      // If a node is pinned in the details panel, keep its highlight alive
      if (selectedNode && selectedNode.id !== node?.id) {
        applySelectionHighlight(selectedNode.id)
      } else {
        setHighlightNodes(new Set())
        setHighlightLinks(new Set())
      }
      return
    }

    const nodeIds = new Set<string>([node.id])
    const linkKeys = new Set<string>()
    for (const link of graphData.links) {
      const src = typeof link.source === 'string' ? link.source : (link.source as GraphNode)?.id
      const tgt = typeof link.target === 'string' ? link.target : (link.target as GraphNode)?.id
      if (src === node.id) {
        if (tgt) nodeIds.add(tgt)
        if (src && tgt) linkKeys.add(`${src}->${tgt}`)
      } else if (tgt === node.id) {
        if (src) nodeIds.add(src)
        if (src && tgt) linkKeys.add(`${src}->${tgt}`)
      }
    }
    setHighlightNodes(nodeIds)
    setHighlightLinks(linkKeys)
  }, [graphData, selectedNode, applySelectionHighlight])

  const handleNodeClick = useCallback((node: GraphNode) => {
    if (!node || !node.id) return
    setSelectedNode(node)
    setHoveredNode(null)
    applySelectionHighlight(node.id)
    fetchNodeDetails(node.id)
    // Remember this node as the last-selected for the active brain
    setLastSelectedByBrain(prev => rememberSelection(prev, activeBrain, node.id))
  }, [applySelectionHighlight, fetchNodeDetails, activeBrain])

  const closeNodeDetails = useCallback(() => {
    setSelectedNode(null)
    setNodeDetails(null)
    setNodeDetailsError(null)
    setHighlightNodes(new Set())
    setHighlightLinks(new Set())
    // Never leave the remove button armed for the next node that gets opened.
    setConfirmRemove(false)
    if (confirmRemoveTimerRef.current) {
      clearTimeout(confirmRemoveTimerRef.current)
      confirmRemoveTimerRef.current = null
    }
  }, [])

  // Forget the remembered node for a brain (explicit dismissal / removal)
  const clearSelectionMemory = useCallback((brainType: string) => {
    setLastSelectedByBrain(prev => forgetSelection(prev, brainType))
  }, [])

  // Explicit panel close (X): dismiss AND forget, so the panel stays closed
  // when the user returns to this brain.
  const dismissNodeDetails = useCallback(() => {
    clearSelectionMemory(activeBrain)
    closeNodeDetails()
  }, [clearSelectionMemory, activeBrain, closeNodeDetails])

  // Clicking a neighbour in the panel jumps to that entity
  const selectNeighbor = useCallback((entityId: string) => {
    const node = graphData?.nodes.find(n => n.id === entityId)
    if (node) handleNodeClick(node)
  }, [graphData, handleNodeClick])

  // Centre + zoom the graph on the selected node
  const focusSelectedNode = useCallback(() => {
    if (!selectedNode || !graphRef.current) return
    const node = graphData?.nodes.find(n => n.id === selectedNode.id)
    if (node && node.x != null && node.y != null) {
      graphRef.current.centerAt(node.x, node.y, 600)
      graphRef.current.zoom(3, 600)
    }
  }, [selectedNode, graphData])

  // ── Remove entity (two-step inline confirm) ──────────────────────────
  const handleRemoveEntity = useCallback(async (): Promise<void> => {
    if (!selectedNode?.id) return
    if (!confirmRemove) {
      // Arm the confirm state; auto-disarm after a few seconds if unused.
      setConfirmRemove(true)
      if (confirmRemoveTimerRef.current) clearTimeout(confirmRemoveTimerRef.current)
      confirmRemoveTimerRef.current = setTimeout(() => {
        setConfirmRemove(false)
        confirmRemoveTimerRef.current = null
      }, 4000)
      return
    }
    setConfirmRemove(false)
    setRemoveBusy(true)
    const entityId = selectedNode.id
    try {
      const resp: unknown = await withTimeout(
        window.barq?.python.request(
          `/api/brain/${activeBrain}/node/${encodeURIComponent(entityId)}/remove`, {},
        ),
      )
      const r = resp as { found?: boolean; removed_edges?: number } | undefined
      if (r && r.found !== false) {
        setIngestResult(
          `Removed '${entityId}'${r.removed_edges ? ` + ${r.removed_edges} edge${r.removed_edges === 1 ? '' : 's'}` : ''}`,
        )
        // The node no longer exists — don't restore it later
        clearSelectionMemory(activeBrain)
        closeNodeDetails()
      } else {
        setNodeDetailsError(`Entity '${entityId}' not found in this brain`)
      }
      await refreshAll()
    } catch (e) {
      setNodeDetailsError(`Remove failed: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setRemoveBusy(false)
    }
  }, [selectedNode, confirmRemove, activeBrain, closeNodeDetails, refreshAll, clearSelectionMemory])

  // ── Restore the last-selected node for the active brain ──────────────
  // Runs whenever the graph finishes loading for the current brain: if there
  // is no selection open yet and this brain has a remembered entity that
  // still exists, reopen the details panel for it.
  useEffect(() => {
    if (!graphData || selectedNode) return
    const target = resolveRestoreTarget(
      graphData.nodes.map(n => n.id),
      lastSelectedByBrain,
      activeBrain,
    )
    if (!target) return
    if (target.missing) {
      // Stale memory — the entity no longer exists in this brain
      startTransition(() => clearSelectionMemory(activeBrain))
      return
    }
    const node = graphData.nodes.find(n => n.id === target.id)
    // startTransition defers the state updates out of the effect body (the
    // react-hooks/set-state-in-effect rule permits this) — the `selectedNode`
    // guard above prevents any restore loop.
    startTransition(() => {
      // Skip if the user switched brains while the transition was pending
      if (activeBrainRef.current !== activeBrain) return
      if (node) handleNodeClick(node)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData, activeBrain, selectedNode, lastSelectedByBrain])

  // ── Node painter: degree-scaled radii + hub pulse rings + LOD labels ──
  const paintNode = useCallback(
    (node: GraphNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      // Guard against non-finite coordinates: during the first paint frames the
      // force simulation may not have assigned x/y yet, and createRadialGradient
      // throws on NaN/Infinity — which would crash the whole app (no boundary).
      if (
        node.x == null || !Number.isFinite(node.x) ||
        node.y == null || !Number.isFinite(node.y)
      ) return
      const label = node.id || ''
      const fontSize = Math.max(6, 12 / globalScale)
      const degree = degreeMap.get(node.id) ?? 0
      const isHub = degree >= hubThreshold

      // Screen-space radius scaled by connectivity → visual hierarchy.
      const baseRadius = Math.max(3.5, Math.min(13, 3.5 + Math.sqrt(degree) * 2.1)) / globalScale

      const isSearching = matchingNodeIds !== null
      const isSearchMatch = matchingNodeIds?.has(node.id) ?? false
      const isHoverMatch = highlightNodes.has(node.id) && !isSearching
      const isSearchNeighbour = isSearching && !isSearchMatch && highlightNodes.has(node.id)
      const isSelected = selectedNode?.id === node.id

      let color: string
      let glowIntensity: number
      let outerGlow: string
      let textColor: string

      if (isSearchMatch) {
        color = theme.searchNode
        glowIntensity = 24
        outerGlow = theme.searchNodeGlow
        textColor = '#34d399'
      } else if (isSearchNeighbour) {
        color = nodeColor(node.id)
        glowIntensity = 5
        outerGlow = `${color}33`
        textColor = 'rgba(226,232,240,0.65)'
      } else if (isHoverMatch) {
        color = theme.highlightNode
        glowIntensity = 20
        outerGlow = theme.highlightLink
        textColor = theme.nodeText
      } else if (isSelected) {
        color = theme.highlightNode
        glowIntensity = 16
        outerGlow = `${color}99`
        textColor = theme.nodeText
      } else if (isSearching) {
        color = theme.mutedNode
        glowIntensity = 0
        outerGlow = 'transparent'
        textColor = 'rgba(113,113,122,0.35)'
      } else {
        color = nodeColor(node.id)
        glowIntensity = isHub ? 14 : 9
        outerGlow = `${color}${isHub ? '99' : '55'}`
        textColor = theme.nodeText
      }

      const activeRadius = isSearching && !isSearchMatch && !isSearchNeighbour
        ? baseRadius * 0.45
        : baseRadius

      const glowRadius = (isSearchMatch || isHoverMatch || isSelected)
        ? baseRadius * 3
        : isSearchNeighbour
          ? baseRadius * 1.5
          : isSearching
            ? baseRadius * 0.6
            : baseRadius * (isHub ? 2.4 : 1.9)

      if (outerGlow !== 'transparent') {
        const glow = ctx.createRadialGradient(
          node.x!, node.y!, 0,
          node.x!, node.y!, glowRadius,
        )
        glow.addColorStop(0, hexToRgba(color, 0.45))
        glow.addColorStop(1, `${color}00`)
        ctx.fillStyle = glow
        ctx.beginPath()
        ctx.arc(node.x!, node.y!, glowRadius, 0, 2 * Math.PI)
        ctx.fill()
      }

      // Hub pulse ring — a slowly breathing outer ring on high-degree nodes.
      if (isHub && !isSearching) {
        const t = pulseClockRef.current / 1000
        const ringPhase = (Math.sin(t * 1.7) + 1) / 2 // 0..1
        const ringRadius = activeRadius * (1.6 + ringPhase * 0.5)
        ctx.beginPath()
        ctx.arc(node.x!, node.y!, ringRadius, 0, 2 * Math.PI)
        ctx.strokeStyle = hexToRgba(color, 0.22 + ringPhase * 0.28)
        ctx.lineWidth = 1.1 / globalScale
        ctx.stroke()
      }

      // ── Entity thumbnail layer ───────────────────────────────────
      // Saved renders become the node face — circular-cropped photo,
      // rimmed in the node colour. Falls back to the flat disc while
      // the image is still loading (or missing).
      const thumbUrl = entityImages.get(node.id)
      const thumb = thumbUrl ? imgCacheRef.current.get(thumbUrl) : undefined
      const thumbReady = !!thumb && thumb.complete && thumb.naturalWidth > 0

      if (thumbReady && thumb) {
        const cover = Math.max((activeRadius * 2) / thumb.naturalWidth, (activeRadius * 2) / thumb.naturalHeight)
        const dw = thumb.naturalWidth * cover
        const dh = thumb.naturalHeight * cover

        ctx.save()
        ctx.beginPath()
        ctx.arc(node.x!, node.y!, activeRadius, 0, 2 * Math.PI)
        if (glowIntensity > 0) {
          ctx.shadowColor = color
          ctx.shadowBlur = glowIntensity
        }
        ctx.clip()
        ctx.drawImage(thumb, node.x! - dw / 2, node.y! - dh / 2, dw, dh)
        ctx.restore()

        // Colour rim so the node still reads as typed
        ctx.beginPath()
        ctx.arc(node.x!, node.y!, activeRadius, 0, 2 * Math.PI)
        ctx.strokeStyle = hexToRgba(color, 0.9)
        ctx.lineWidth = 1.2 / globalScale
        ctx.stroke()
      } else {
        ctx.beginPath()
        ctx.arc(node.x!, node.y!, activeRadius, 0, 2 * Math.PI)
        ctx.fillStyle = color
        if (glowIntensity > 0) {
          ctx.shadowColor = color
          ctx.shadowBlur = glowIntensity
        }
        ctx.fill()
        ctx.shadowBlur = 0
      }

      // Specular highlight (skipped in muted search state)
      if (!isSearching || isSearchMatch || isSearchNeighbour || isSelected) {
        ctx.beginPath()
        ctx.arc(
          node.x! - activeRadius * 0.2,
          node.y! - activeRadius * 0.2,
          activeRadius * 0.32,
          0, 2 * Math.PI,
        )
        ctx.fillStyle = 'rgba(255,255,255,0.45)'
        ctx.fill()
      }

      // ── Level-of-Detail labels ───────────────────────────────────────
      // Always: hubs, hovered, matched, selected. Otherwise only when zoomed
      // past 2× — this is what eliminates label pile-up at default zoom.
      const showLabel =
        isHub || isHoverMatch || isSearchMatch || isSearchNeighbour || isSelected ||
        globalScale > 2.0

      if (showLabel) {
        const clean = label.length > LABEL_MAX_CHARS
          ? `${label.slice(0, LABEL_MAX_CHARS - 1)}…`
          : label
        ctx.font = `${fontSize}px "JetBrains Mono", "Fira Code", monospace`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        const labelY = node.y! + activeRadius + 3
        const textW = ctx.measureText(clean).width

        // Dark backing pill so overlapping labels stay readable.
        ctx.fillStyle = 'rgba(9,10,15,0.72)'
        roundRectPath(ctx, node.x! - textW / 2 - 4, labelY - 2, textW + 8, fontSize + 4, 4)
        ctx.fill()

        ctx.shadowColor = 'rgba(0,0,0,0.9)'
        ctx.shadowBlur = 4
        ctx.fillStyle = textColor
        ctx.fillText(clean, node.x!, labelY)
        ctx.shadowBlur = 0
      }
    },
    [highlightNodes, matchingNodeIds, theme, degreeMap, hubThreshold, selectedNode, entityImages],
  )

  // ── Link painter: glowing vector links, colour blended source→target ──
  const paintLink = useCallback(
    (link: GraphLink, ctx: CanvasRenderingContext2D) => {
      const src = typeof link.source === 'object' ? (link.source as GraphNode) : null
      const tgt = typeof link.target === 'object' ? (link.target as GraphNode) : null
      if (!src || !tgt || src.x == null || src.y == null || tgt.x == null || tgt.y == null) return
      const sx: number = src.x
      const sy: number = src.y
      const tx: number = tgt.x
      const ty: number = tgt.y

      const key = `${src.id}->${tgt.id}`
      const isSearching = matchingNodeIds !== null
      const isHighlighted = highlightLinks.has(key)

      if (isSearching && !isHighlighted) {
        ctx.beginPath()
        ctx.moveTo(sx, sy)
        ctx.lineTo(tx, ty)
        ctx.strokeStyle = theme.mutedLink
        ctx.lineWidth = 0.35
        ctx.stroke()
        return
      }

      // Blend the two endpoint colours → each edge carries its own hue.
      const mix = blendHex(nodeColor(src.id), nodeColor(tgt.id), 0.5)
      const accent = activeMeta.color

      if (isSearching && isHighlighted) {
        ctx.beginPath()
        ctx.moveTo(sx, sy)
        ctx.lineTo(tx, ty)
        ctx.shadowColor = theme.searchNode
        ctx.shadowBlur = 6
        ctx.strokeStyle = theme.searchLink
        ctx.lineWidth = 1.3
        ctx.stroke()
        ctx.shadowBlur = 0
        return
      }

      const alpha = isHighlighted ? 0.85 : 0.45
      const width = isHighlighted ? 1.4 : 1.0
      const glowColor = isHighlighted ? hexToRgba(accent, 0.9) : mix

      // Soft under-glow pass — makes edges clearly visible on the grid.
      ctx.beginPath()
      ctx.moveTo(sx, sy)
      ctx.lineTo(tx, ty)
      ctx.strokeStyle = hexToRgba(mix, alpha * 0.35)
      ctx.lineWidth = width * 2.6
      ctx.stroke()

      // Bright core pass with shadow glow.
      ctx.beginPath()
      ctx.moveTo(sx, sy)
      ctx.lineTo(tx, ty)
      ctx.shadowColor = glowColor
      ctx.shadowBlur = 4
      ctx.strokeStyle = isHighlighted
        ? hexToRgba(accent, 0.9)
        : hexToRgba(mix, alpha)
      ctx.lineWidth = width
      ctx.stroke()
      ctx.shadowBlur = 0
    },
    [highlightLinks, matchingNodeIds, theme, activeMeta.color],
  )

  // ── Zoom to fit on load ──────────────────────────────────────────────
  useEffect(() => {
    if (graphData && graphRef.current) {
      setTimeout(() => {
        try {
          graphRef.current.zoomToFit(400, 50)
        } catch { /* ignore */ }
      }, 500)
    }
  }, [graphData])

  // ── Handle brain tab switch ──────────────────────────────────────────
  const handleBrainChange = useCallback((brainType: string) => {
    if (brainType === activeBrain) return
    setActiveBrain(brainType)
    setSearchQuery('')
    setGraphData(null)
    setBrainStats(null)
    closeNodeDetails()
  }, [activeBrain, closeNodeDetails])

  // ── Render ────────────────────────────────────────────────────────────
  const brainColor = activeMeta.color

  return (
    <div className="h-full w-full bg-[#09090b] text-zinc-200 overflow-hidden relative font-mono flex flex-col">
      {/* ── Brain Tabs ────────────────────────────────────────────────── */}
      <div className="shrink-0 border-b border-zinc-800/60">
        {/* Top row: title + search + controls */}
        <div className="flex items-center justify-between px-4 py-2">
          <div className="flex items-center gap-3">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center border"
              style={{
                backgroundColor: `${brainColor}18`,
                borderColor: `${brainColor}30`,
              }}
            >
              <Network className="w-3.5 h-3.5" style={{ color: brainColor }} />
            </div>
            <div>
              <h1
                className="text-xs font-orbitron font-bold tracking-[0.15em] uppercase"
                style={{ color: brainColor }}
              >
                {activeMeta.label}
              </h1>
              <p className="text-[8px] font-mono text-zinc-500 tracking-[0.1em]">
                Multi-Domain Knowledge Graph
              </p>
            </div>
          </div>

          {/* Search bar — floating pill with Ctrl+F hint */}
          <div className="relative flex-1 max-w-sm mx-auto">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3 h-3 text-zinc-500 pointer-events-none" />
              <input
                ref={inputRef}
                type="text"
                placeholder="Search entities…"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value)
                  setSearchFocused(true)
                }}
                onFocus={() => setSearchFocused(true)}
                onBlur={() => setTimeout(() => setSearchFocused(false), 200)}
                className="w-full pl-8 pr-16 py-1.5 text-[10px] font-mono rounded-full
                           bg-zinc-900/70 backdrop-blur-md border border-zinc-700/60
                           text-zinc-200 placeholder-zinc-600
                           focus:outline-none transition-all duration-200"
                style={{
                  borderColor: searchFocused ? `${brainColor}50` : undefined,
                  boxShadow: searchFocused ? `0 0 14px ${brainColor}22` : undefined,
                }}
              />
              {/* kbd shortcut hint */}
              {!searchQuery && (
                <kbd
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none
                             px-1.5 py-0.5 rounded text-[7px] font-mono text-zinc-500
                             border border-zinc-700/70 bg-zinc-800/70"
                >
                  Ctrl F
                </kbd>
              )}
              {searchQuery && (
                <button
                  onClick={handleClearSearch}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded
                             text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
                >
                  <X className="w-2.5 h-2.5" />
                </button>
              )}
            </div>

            {/* Autocomplete dropdown */}
            {searchFocused && searchSuggestions.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="absolute top-full left-0 right-0 mt-1 py-1 rounded-lg
                           bg-zinc-900/95 backdrop-blur-xl border border-zinc-800
                           shadow-2xl z-50 max-h-40 overflow-y-auto"
              >
                {searchSuggestions.map((id) => {
                  const isMatched = matchingNodeIds?.has(id) ?? false
                  return (
                    <button
                      key={id}
                      onMouseDown={(e) => {
                        e.preventDefault()
                        handleSelectSearch(id)
                      }}
                      className={`w-full flex items-center gap-2 px-2.5 py-1.5 text-left
                                 text-[10px] font-mono transition-colors
                                 ${isMatched ? 'bg-emerald-500/8' : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'}`}
                      style={{ color: isMatched ? '#34d399' : undefined }}
                    >
                      <span
                        className="w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ backgroundColor: isMatched ? '#34d399' : '#52525b' }}
                      />
                      <span className="truncate">{id}</span>
                    </button>
                  )
                })}
              </motion.div>
            )}
          </div>

          {/* Controls */}
          <div className="flex items-center gap-2">
            {/* Stats badge */}
            {graphData?._meta && (
              <div
                className="flex items-center gap-2 px-2.5 py-1 rounded-lg bg-zinc-900/80 border text-[9px] font-mono"
                style={{ borderColor: `${brainColor}25` }}
              >
                {searchQuery.trim() && matchingNodeIds ? (
                  <span className="text-emerald-400">
                    <span className="text-zinc-500">MATCHES</span>{' '}
                    <span className="font-bold">{matchingNodeIds.size}</span>
                  </span>
                ) : (
                  <span style={{ color: brainColor }}>
                    <span className="text-zinc-500">NODES</span>{' '}
                    <span className="font-bold">{graphData._meta.nodes}</span>
                  </span>
                )}
                <span className="w-px h-2.5 bg-zinc-800" />
                <span className="text-zinc-400">
                  <span className="text-zinc-500">EDGES</span>{' '}
                  <span className="font-bold">{graphData._meta.edges}</span>
                </span>
              </div>
            )}

            {/* Re-import now — run the scheduled brain re-import immediately */}
            <button
              onClick={handleImportSources}
              disabled={importBusy}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[9px] font-mono tracking-wider uppercase
                         transition-all duration-200 disabled:opacity-40 hover:brightness-125"
              style={{
                color: importBusy ? brainColor : '#34d399',
                backgroundColor: importBusy ? `${brainColor}15` : '#34d39914',
                border: `1px solid ${importBusy ? `${brainColor}30` : '#34d3992e'}`,
                boxShadow: importBusy ? 'none' : '0 0 12px rgba(52,211,153,0.12)',
              }}
              title="Run the scheduled re-import now — notes / memory / jobs → knowledge graphs (no 6-hour wait)"
            >
              {importBusy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Database className="w-3 h-3" />}
              Re-import now
            </button>

            {/* Compact result feedback when the ingest panel is closed */}
            {ingestResult && !showIngest && (
              <span
                className="max-w-[200px] truncate px-2 py-1 rounded-lg bg-zinc-900/80 border text-[8px] font-mono text-zinc-400"
                style={{ borderColor: `${brainColor}20` }}
                title={ingestResult}
              >
                {ingestResult}
              </span>
            )}

            {/* Add knowledge — ingest text / triplets into the active brain */}
            <button
              onClick={() => setShowIngest(v => !v)}
              className="relative p-1 rounded-lg transition-all duration-200"
              style={{
                color: showIngest ? brainColor : '#71717a',
                backgroundColor: showIngest ? `${brainColor}15` : undefined,
              }}
              title="Add knowledge — ingest text or triplets into this brain"
            >
              <FilePlus2 className="w-3.5 h-3.5" />
            </button>

            {/* Timeline toggle — effect handles fetch when showTimeline flips true */}
            <button
              onClick={() => setShowTimeline(v => !v)}
              className="relative p-1 rounded-lg transition-all duration-200"
              style={{
                color: showTimeline ? brainColor : '#71717a',
                backgroundColor: showTimeline ? `${brainColor}15` : undefined,
              }}
              title="Toggle timeline history"
            >
              <Clock className="w-3.5 h-3.5" />
            </button>

            {/* Pulse button */}
            <button
              onClick={triggerPulse}
              className="relative p-1 rounded-lg transition-all duration-200"
              style={{
                color: pulseIntensity > 0 ? brainColor : '#71717a',
                backgroundColor: pulseIntensity > 0 ? `${brainColor}15` : undefined,
              }}
              title="Fire synaptic pulse"
            >
              <Zap className="w-3.5 h-3.5" />
              {pulseIntensity > 0 && (
                <span
                  className="absolute inset-0 rounded-lg animate-ping opacity-40"
                  style={{ backgroundColor: `${brainColor}30` }}
                />
              )}
            </button>

            {/* Refresh button */}
            <button
              onClick={fetchGraph}
              disabled={loading}
              className="p-1 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 transition-colors disabled:opacity-40"
              title="Refresh graph data"
            >
              <RotateCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* ── Brain Tab Bar ──────────────────────────────────────────────── */}
        <div className="flex items-center gap-0.5 px-4 pb-0 overflow-x-auto">
          {brainsList.length === 0 ? (
            // Skeleton tabs while loading
            Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-t-lg bg-zinc-900/30 border-b-2 border-transparent animate-pulse"
              >
                <div className="w-3 h-3 rounded bg-zinc-800" />
                <div className="w-16 h-2.5 rounded bg-zinc-800" />
              </div>
            ))
          ) : (
            brainsList.map((brain) => {
              const isActive = brain.type === activeBrain
              const Icon = getBrainIcon(brain.icon)
              return (
                <button
                  key={brain.type}
                  onClick={() => handleBrainChange(brain.type)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-mono
                             transition-all duration-200 rounded-t-lg border-b-2
                             ${isActive
                               ? 'bg-zinc-900/60 font-semibold'
                               : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900/30 border-transparent'
                             }`}
                  style={{
                    borderBottomColor: isActive ? brain.color : 'transparent',
                    color: isActive ? brain.color : undefined,
                  }}
                  title={`${brain.label} — ${brain.nodes} nodes, ${brain.edges} edges`}
                >
                  <Icon className="w-3 h-3 shrink-0" />
                  <span className="truncate max-w-[90px]">{brain.label}</span>
                  {brain.nodes > 0 && (
                    <span
                      className="text-[8px] ml-auto opacity-60"
                      style={{ color: brain.color }}
                    >
                      {brain.nodes}
                    </span>
                  )}
                </button>
              )
            })
          )}
        </div>
      </div>

      {/* ── Ingest Panel ────────────────────────────────────────────────── */}
      {showIngest && (
        <div
          className="shrink-0 border-b px-4 py-3 space-y-3"
          style={{ borderColor: `${brainColor}18`, backgroundColor: 'rgba(9,9,11,0.92)' }}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CirclePlus className="w-3.5 h-3.5" style={{ color: brainColor }} />
              <span
                className="text-[10px] font-orbitron font-bold tracking-[0.15em] uppercase"
                style={{ color: brainColor }}
              >
                Add Knowledge — {activeMeta.label}
              </span>
            </div>
            <button
              onClick={() => setShowIngest(false)}
              className="p-0.5 rounded text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              <X className="w-3 h-3" />
            </button>
          </div>

          {/* Paste text → LLM extraction into the active brain */}
          <div className="space-y-2">
            <textarea
              value={ingestText}
              onChange={(e) => setIngestText(e.target.value)}
              placeholder="Paste text to extract relationships — e.g. 'Python is used for data science at Google'…"
              rows={3}
              className="w-full px-3 py-2 text-[10px] font-mono bg-zinc-900/80 border border-zinc-800 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none resize-none"
              style={{ borderColor: ingestBusy ? `${brainColor}50` : undefined }}
            />
            <button
              onClick={handleIngestText}
              disabled={ingestBusy || !ingestText.trim()}
              className="px-3 py-1.5 text-[10px] font-mono tracking-wider uppercase rounded-lg transition-all disabled:opacity-40 flex items-center gap-1.5"
              style={{ backgroundColor: `${brainColor}15`, color: brainColor, borderColor: `${brainColor}30`, borderWidth: 1 }}
            >
              {ingestBusy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
              Extract & Add
            </button>
          </div>

          {/* Direct triplet form */}
          <div className="flex items-center gap-2 flex-wrap">
            <input
              value={triplet.subject}
              onChange={(e) => setTriplet(t => ({ ...t, subject: e.target.value }))}
              placeholder="subject (e.g. python)"
              className="flex-1 min-w-[110px] px-2.5 py-1.5 text-[10px] font-mono bg-zinc-900/80 border border-zinc-800 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none"
            />
            <input
              value={triplet.relation}
              onChange={(e) => setTriplet(t => ({ ...t, relation: e.target.value }))}
              placeholder="relation (e.g. USED_FOR)"
              className="flex-1 min-w-[110px] px-2.5 py-1.5 text-[10px] font-mono bg-zinc-900/80 border border-zinc-800 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none"
            />
            <input
              value={triplet.object}
              onChange={(e) => setTriplet(t => ({ ...t, object: e.target.value }))}
              placeholder="object (e.g. data science)"
              className="flex-1 min-w-[110px] px-2.5 py-1.5 text-[10px] font-mono bg-zinc-900/80 border border-zinc-800 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none"
            />
            <button
              onClick={handleAddTriplet}
              disabled={ingestBusy || !triplet.subject.trim() || !triplet.object.trim()}
              className="px-3 py-1.5 text-[10px] font-mono tracking-wider uppercase rounded-lg transition-all disabled:opacity-40"
              style={{ backgroundColor: `${brainColor}15`, color: brainColor, borderColor: `${brainColor}30`, borderWidth: 1 }}
            >
              Add Triplet
            </button>
          </div>

          {/* Data source actions + result feedback */}
          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={handleImportSources}
              disabled={importBusy}
              className="px-3 py-1.5 text-[10px] font-mono tracking-wider uppercase rounded-lg transition-all disabled:opacity-40 flex items-center gap-1.5"
              style={{ backgroundColor: `${brainColor}15`, color: brainColor, borderColor: `${brainColor}30`, borderWidth: 1 }}
            >
              {importBusy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Database className="w-3 h-3" />}
              Import from BARQ data
            </button>
            <button
              onClick={handleSeedDemo}
              disabled={ingestBusy}
              className="px-3 py-1.5 text-[10px] font-mono tracking-wider uppercase rounded-lg transition-all disabled:opacity-40 flex items-center gap-1.5"
              style={{ backgroundColor: `${brainColor}12`, color: brainColor, borderColor: `${brainColor}25`, borderWidth: 1 }}
            >
              <BadgePlus className="w-3 h-3" />
              Load demo graph
            </button>
            {ingestResult && (
              <span className="text-[9px] font-mono text-zinc-400 flex-1 min-w-[160px]">
                {ingestResult}
              </span>
            )}
          </div>
        </div>
      )}

      {/* ── Graph Container ─────────────────────────────────────────────── */}
      <div ref={containerRef} className="flex-1 relative overflow-hidden">
        {/* ── Cybernetic backdrop: radial spotlight + grid ──────────────── */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: `radial-gradient(1100px 640px at 50% 30%, ${hexToRgba(brainColor, 0.12)}, rgba(9,10,15,0) 62%), radial-gradient(1500px 900px at 50% 45%, rgba(24,19,43,0.9), rgba(9,10,15,1) 78%)`,
          }}
        />
        <div
          className="absolute inset-0 pointer-events-none opacity-70"
          style={{
            backgroundImage:
              'linear-gradient(rgba(22,27,38,0.6) 1px, transparent 1px),' +
              'linear-gradient(90deg, rgba(22,27,38,0.6) 1px, transparent 1px)',
            backgroundSize: '34px 34px',
            maskImage: 'radial-gradient(ellipse at 50% 38%, black 25%, transparent 80%)',
            WebkitMaskImage: 'radial-gradient(ellipse at 50% 38%, black 25%, transparent 80%)',
          }}
        />

        {/* Loading overlay */}
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#0d111a]/75 backdrop-blur-sm">
            <div className="flex flex-col items-center gap-3">
              <div
                className="w-8 h-8 border-2 rounded-full animate-spin"
                style={{
                  borderColor: `${brainColor}30`,
                  borderTopColor: brainColor,
                }}
              />
              <p className="text-[10px] font-mono text-zinc-500 tracking-wider uppercase animate-pulse">
                Loading {activeMeta.label}…
              </p>
            </div>
          </div>
        )}

        {/* Error overlay */}
        {error && !loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#0d111a]/75 backdrop-blur-sm">
            <div className="flex flex-col items-center gap-3 px-6 py-8 rounded-xl bg-zinc-900/60 border border-red-900/40">
              <AlertCircle className="w-8 h-8 text-red-400" />
              <p className="text-xs font-mono text-zinc-400 text-center max-w-xs">{error}</p>
              <button
                onClick={fetchGraph}
                className="px-4 py-1.5 text-[10px] font-mono tracking-wider uppercase rounded-lg transition-colors"
                style={{
                  backgroundColor: `${brainColor}15`,
                  color: brainColor,
                  borderColor: `${brainColor}30`,
                  borderWidth: 1,
                }}
              >
                Retry
              </button>
            </div>
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && graphData && graphData.nodes.length === 0 && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#0d111a]/55">
            <div className="flex flex-col items-center gap-2 text-zinc-500">
              <GitBranch className="w-10 h-10 text-zinc-700" />
              <p className="text-xs font-mono" style={{ color: brainColor }}>
                {activeMeta.label} is empty
              </p>
              <p className="text-[10px] font-mono text-zinc-600">
                Use the{' '}
                <code style={{ color: brainColor }}>＋</code>{' '}
                Add Knowledge button above to ingest text or triplets
              </p>
            </div>
          </div>
        )}

        {/* ForceGraph2D */}
        {graphData && !loading && (
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            width={dimension.width}
            height={dimension.height}
            // Transparent canvas so the cybernetic CSS backdrop shows through
            backgroundColor="rgba(0,0,0,0)"

            // Nodes
            nodeRelSize={4}
            nodeCanvasObject={paintNode}
            nodeCanvasObjectMode={() => 'replace'}
            nodePointerAreaPaint={(node, color, ctx) => {
              if (
                node.x == null || !Number.isFinite(node.x) ||
                node.y == null || !Number.isFinite(node.y)
              ) return
              // Bigger hit area for hubs = easier to grab high-degree nodes
              const deg = degreeMap.get(node.id as string) ?? 0
              const r = Math.max(7, 9 + Math.sqrt(deg) * 2.5)
              ctx.beginPath()
              ctx.arc(node.x!, node.y!, r, 0, 2 * Math.PI)
              ctx.fillStyle = color
              ctx.fill()
            }}

            // Links
            linkCanvasObject={paintLink}

            // Particles — pulse modulates count, speed, width, colour
            linkDirectionalParticles={() => 2 + Math.round(pulseIntensity * 8)}
            linkDirectionalParticleWidth={1.5 + pulseIntensity * 2.5}
            linkDirectionalParticleSpeed={0.005 + pulseIntensity * 0.03}
            linkDirectionalParticleColor={() => {
              if (pulseIntensity < 0.01) return theme.linkColor
              const alpha = 0.6 + pulseIntensity * 0.4
              const { r, g, b } = hexToRgb(activeMeta.color)
              const pr = r + Math.round(pulseIntensity * (255 - r))
              const pg = g + Math.round(pulseIntensity * (255 - g))
              const pb = b + Math.round(pulseIntensity * (255 - b))
              return `rgba(${pr},${pg},${pb},${alpha})`
            }}

            // Interaction
            onNodeHover={handleNodeHover}
            onNodeClick={handleNodeClick}
            onBackgroundClick={closeNodeDetails}
            enableNodeDrag={true}
            enableZoomInteraction={true}
            enablePanInteraction={true}
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.3}
            cooldownTicks={100}
            warmupTicks={40}
          />
        )}

        {/* Timeline panel overlay */}
        {showTimeline && (
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
            className="absolute top-0 right-0 bottom-0 z-20 w-72 border-l overflow-hidden"
            style={{ borderColor: `${brainColor}20`, backgroundColor: 'rgba(9,9,11,0.92)' }}
          >
            <div className="flex flex-col h-full">
              {/* Panel header */}
              <div
                className="flex items-center justify-between px-3 py-2 border-b shrink-0"
                style={{ borderColor: `${brainColor}15` }}
              >
                <div className="flex items-center gap-2">
                  <Clock className="w-3 h-3" style={{ color: brainColor }} />
                  <span
                    className="text-[10px] font-orbitron font-bold tracking-[0.15em] uppercase"
                    style={{ color: brainColor }}
                  >
                    Timeline
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  {/* Filter toggle: all brains vs current brain */}
                  <button
                    onClick={() => setTimelineAllBrains(v => !v)}
                    className="p-1 rounded text-[8px] font-mono transition-colors"
                    style={{
                      color: timelineAllBrains ? brainColor : '#71717a',
                      backgroundColor: timelineAllBrains ? `${brainColor}12` : undefined,
                    }}
                    title={timelineAllBrains ? 'Showing all brains' : 'Showing current brain only'}
                  >
                    <Filter className="w-2.5 h-2.5" />
                  </button>
                  <span className="text-[8px] font-mono text-zinc-600 px-1">
                    {timelineAllBrains ? 'ALL' : activeBrain.slice(0, 4).toUpperCase()}
                  </span>
                  <button
                    onClick={() => setShowTimeline(false)}
                    className="p-0.5 rounded text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
                    title="Close timeline panel"
                  >
                    <X className="w-2.5 h-2.5" />
                  </button>
                </div>
              </div>

              {/* Entries list */}
              <div className="flex-1 overflow-y-auto overscroll-contain">
                {timelineLoading && timelineEntries.length === 0 ? (
                  <div className="flex items-center justify-center py-12">
                    <div
                      className="w-5 h-5 border-2 rounded-full animate-spin"
                      style={{
                        borderColor: `${brainColor}25`,
                        borderTopColor: brainColor,
                      }}
                    />
                  </div>
                ) : timelineEntries.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
                    <Clock className="w-6 h-6 text-zinc-700 mb-2" />
                    <p className="text-[10px] font-mono text-zinc-600">
                      No timeline events yet.
                    </p>
                    <p className="text-[8px] font-mono text-zinc-700 mt-1">
                      Triplet additions will appear here.
                    </p>
                  </div>
                ) : (
                  <div className="py-1">
                    {timelineEntries.map((entry, idx) => {
                      const brainMeta = brainsList.find(b => b.type === entry.brain_type)
                      const entryColor = brainMeta?.color ?? brainColor
                      const timestamp = new Date(entry.timestamp)
                      const timeAgo = formatDistanceToNow(timestamp)
                      const entryKey = `${entry.timestamp}-${entry.subject}-${entry.object_}-${entry.relation}`
                      const isNew = newEntryKeys.has(entryKey)

                      return (
                        <motion.div
                          key={`${entry.timestamp}-${entry.subject}-${entry.object_}-${idx}`}
                          initial={{ opacity: 0, y: -4 }}
                          animate={{
                            opacity: 1,
                            y: 0,
                            backgroundColor: isNew
                              ? [`${entryColor}22`, `${entryColor}08`, 'transparent']
                              : 'transparent',
                          }}
                          transition={{
                            delay: Math.min(idx * 0.02, 0.5),
                            backgroundColor: isNew
                              ? { duration: 2.5, ease: 'easeOut' }
                              : undefined,
                          }}
                          className="relative px-3 py-1.5 hover:bg-zinc-800/30 transition-colors border-l-2 group"
                          style={{
                            borderLeftColor: idx === 0 ? entryColor : `${entryColor}25`,
                          }}
                        >
                          {/* Timestamp + brain label (if showing all) */}
                          <div className="flex items-center gap-1.5 mb-0.5">
                            <span className="text-[8px] font-mono text-zinc-600">
                              {timeAgo}
                            </span>
                            {timelineAllBrains && brainMeta && (
                              <>
                                <span className="text-[6px] text-zinc-700">·</span>
                                <span
                                  className="text-[8px] font-mono"
                                  style={{ color: entryColor }}
                                >
                                  {brainMeta.label}
                                </span>
                              </>
                            )}
                            <span className="ml-auto">
                              {entry.is_new_edge ? (
                                <span
                                  className="text-[7px] font-mono px-1 rounded"
                                  style={{
                                    color: entryColor,
                                    backgroundColor: `${entryColor}12`,
                                  }}
                                >
                                  NEW
                                </span>
                              ) : (
                                <span className="text-[7px] font-mono text-zinc-700">
                                  +1
                                </span>
                              )}
                            </span>
                          </div>

                          {/* Triplet: subject → relation → object */}
                          <div className="flex items-center gap-1 text-[9px] font-mono leading-tight">
                            <span className="text-zinc-200 truncate max-w-[80px]">{entry.subject}</span>
                            <span
                              className="text-[7px] shrink-0 px-0.5"
                              style={{ color: entryColor }}
                            >
                              {entry.relation}
                            </span>
                            <span className="text-zinc-200 truncate max-w-[80px]">{entry.object_}</span>
                          </div>
                        </motion.div>
                      )
                    })}
                  </div>
                )}
              </div>

              {/* Footer */}
              <div
                className="shrink-0 px-3 py-1.5 border-t text-[8px] font-mono"
                style={{ borderColor: `${brainColor}15`, color: `${brainColor}60` }}
              >
                {timelineEntries.length} event{timelineEntries.length !== 1 ? 's' : ''} ·{' '}
                <button
                  onClick={fetchTimeline}
                  className="hover:brightness-125 transition-all underline underline-offset-2 decoration-dotted"
                  style={{ color: brainColor }}
                >
                  refresh
                </button>
              </div>
            </div>
          </motion.div>
        )}

        {/* Glassmorphic Node Inspector drawer (right side) */}
        <NodeInspector
          node={selectedNode}
          details={nodeDetails}
          loading={nodeDetailsLoading}
          error={nodeDetailsError}
          brainColor={brainColor}
          brainLabel={activeMeta.label}
          brainType={activeBrain}
          onClose={dismissNodeDetails}
          onFocusNode={focusSelectedNode}
          onSelectNeighbor={selectNeighbor}
          onRemove={handleRemoveEntity}
          confirmRemove={confirmRemove}
          removeBusy={removeBusy}
        />

        {/* Hover info tooltip */}
        {hoveredNode && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="absolute bottom-4 left-1/2 -translate-x-1/2 pointer-events-none"
          >
            <div className="px-4 py-2 rounded-lg bg-zinc-900/90 backdrop-blur-md border border-zinc-800 shadow-2xl flex items-center gap-3">
              <span
                className="w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: nodeColor(hoveredNode.id) }}
              />
              <span className="text-xs font-mono text-zinc-200">{hoveredNode.id}</span>
              <span className="text-[9px] font-mono text-zinc-500 uppercase tracking-wider">Node</span>
            </div>
          </motion.div>
        )}
      </div>

      {/* ── Footer: floating HUD status bar ─────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-1.5 border-t border-zinc-800/40 shrink-0">
        <div className="flex items-center gap-3">
          {/* Force simulation status + live counts */}
          <span className="flex items-center gap-1.5">
            <span
              className={`w-1.5 h-1.5 rounded-full ${simRunning ? 'animate-pulse' : ''}`}
              style={{
                backgroundColor: simRunning ? '#34d399' : '#71717a',
                boxShadow: simRunning ? '0 0 8px rgba(52,211,153,0.9)' : 'none',
              }}
            />
            <span
              className="text-[8px] font-mono uppercase tracking-wider"
              style={{ color: simRunning ? '#34d399' : '#71717a' }}
            >
              Force Sim {simRunning ? 'Active' : 'Idle'}
            </span>
          </span>
          {graphData && (
            <span className="text-[8px] font-mono text-zinc-500 tracking-wider">
              <span style={{ color: brainColor }}>{graphData.nodes.length}</span> Nodes ·{' '}
              <span style={{ color: brainColor }}>{graphData.links.length}</span> Edges
            </span>
          )}
          <span className="hidden md:flex items-center gap-1.5 text-[8px] font-mono text-zinc-600 tracking-wider">
            <Info className="w-3 h-3" />
            Drag · Scroll to zoom · Hover to highlight
          </span>
        </div>

        {/* Per-brain stats */}
        {brainStats && (
          <div className="flex items-center gap-3 text-[8px] font-mono text-zinc-600">
            <span>
              Density: <span style={{ color: brainColor }}>{brainStats.density.toFixed(4)}</span>
            </span>
            <span className="w-px h-2.5 bg-zinc-800" />
            <span>
              Components: <span style={{ color: brainColor }}>{brainStats.connected_components}</span>
            </span>
            {brainStats.top_entities.length > 0 && (
              <>
                <span className="w-px h-2.5 bg-zinc-800" />
                <span className="flex items-center gap-1">
                  <BarChart3 className="w-2.5 h-2.5" />
                  Top:{' '}
                  {brainStats.top_entities.slice(0, 3).map((e) => (
                    <span key={e.entity} className="text-zinc-400">{e.entity}</span>
                  ))}
                </span>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
