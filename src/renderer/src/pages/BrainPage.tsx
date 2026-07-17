import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { motion } from 'framer-motion'
import {
  Info, RotateCw, AlertCircle, Search, X, Zap, GitBranch,
  StickyNote, FileText, MessageCircle, Briefcase, Brain,
  BarChart3, Network, Clock, Filter,
} from 'lucide-react'
import { formatDistanceToNow } from '../utils/time'
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

interface TimelineEntry {
  timestamp: string
  brain_type: string
  subject: string
  relation: string
  object_: string
  is_new_edge: boolean
}

interface TimelineSummaryEntry {
  brain_type: string
  label: string
  color: string
  total_events: number
  new_edges: number
  latest_timestamp: string
}

// ─── Icon Map ──────────────────────────────────────────────────────────────

const BRAIN_ICONS: Record<string, typeof Brain> = {
  'sticky-note': StickyNote,
  'file-text': FileText,
  'message-circle': MessageCircle,
  'briefcase': Briefcase,
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

// ─── Pulse timing constants ────────────────────────────────────────────────

const PULSE_DURATION_MS = 2200
const PULSE_PEAK_MS = 300
const PULSE_SUSTAIN_MS = 500
const AUTO_POLL_INTERVAL_MS = 8000

// ─── Fallback meta for initial render before brain list loads ────────────────

const FALLBACK_META: GraphMeta = {
  brain_type: 'general',
  label: 'General Knowledge',
  color: '#818cf8',
  neon_glow: 'rgba(129,140,248,0.5)',
  nodes: 0,
  edges: 0,
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
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null)
  const [dimension, setDimension] = useState({ width: 800, height: 600 })
  const containerRef = useRef<HTMLDivElement>(null)
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
  const activeBrainMeta = brainsList.find(b => b.type === activeBrain)

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
      setHighlightNodes(new Set())
      setHighlightLinks(new Set())
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
  }, [matchingNodeIds, graphData])

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
        const resp: unknown = await window.barq?.python.request('/api/brain/list')
        if (Array.isArray(resp)) {
          setBrainsList(resp as BrainMeta[])
        }
      } catch {
        // silently fail — fall back to hardcoded defaults
      }
    }
    fetchBrains()
  }, [])

  // ── Fetch brain stats ────────────────────────────────────────────────
  const fetchBrainStats = useCallback(async () => {
    try {
      const resp: unknown = await window.barq?.python.request(`/api/brain/${activeBrain}/stats`)
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
      const resp: unknown = await window.barq?.python.request(`/api/brain/${activeBrain}/visualize`)
      if (!resp || typeof resp !== 'object') {
        throw new Error('Invalid response from backend')
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

  // ── Fetch timeline entries ───────────────────────────────────────────
  const fetchTimeline = useCallback(async () => {
    setTimelineLoading(true)
    try {
      const endpoint = timelineAllBrains
        ? '/api/brain/timeline?limit=100'
        : `/api/brain/${activeBrain}/timeline?limit=100`
      const resp: unknown = await window.barq?.python.request(endpoint)
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

  // ── Re-fetch when activeBrain or timeline toggle changes ────────────
  useEffect(() => {
    fetchGraph()
    fetchBrainStats()
    if (showTimeline) {
      // Reset init flag so filter/brain switches don't flash stale entries
      timelineInitializedRef.current = false
      fetchTimeline()
    }
  }, [fetchGraph, fetchBrainStats, showTimeline, fetchTimeline])

  // ── Detect graph changes & trigger synaptic pulse ────────────────────
  useEffect(() => {
    if (!graphData?._meta) return
    const meta = graphData._meta
    const prev = prevMetaRef.current

    const isNewData = !prev || prev.nodes !== meta.nodes || prev.edges !== meta.edges
    prevMetaRef.current = meta

    if (isNewData) {
      triggerPulse()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData?._meta?.nodes, graphData?._meta?.edges])

  // ── Auto-poll backend for new graph data ─────────────────────────────
  useEffect(() => {
    const interval = setInterval(() => {
      fetchGraph()
    }, AUTO_POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchGraph])

  // ── Auto-poll timeline entries while panel is open ────────────────────
  useEffect(() => {
    if (!showTimeline) return
    const interval = setInterval(() => {
      fetchTimeline()
    }, AUTO_POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [showTimeline, fetchTimeline])

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

  // Cleanup animation frame + flash timers on unmount
  useEffect(() => {
    return () => {
      if (pulseAnimRef.current) {
        cancelAnimationFrame(pulseAnimRef.current)
      }
      for (const t of flashTimersRef.current) clearTimeout(t)
      flashTimersRef.current = []
    }
  }, [])

  // ── Node hover highlight ─────────────────────────────────────────────
  const handleNodeHover = useCallback((node: GraphNode | null) => {
    setHoveredNode(node)
    if (!node || !graphData) {
      setHighlightNodes(new Set())
      setHighlightLinks(new Set())
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
  }, [graphData])

  // ── Node painter (glowing neon circles + labels + search highlight) ──
  const paintNode = useCallback(
    (node: GraphNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const label = node.id || ''
      const fontSize = Math.max(6, 12 / globalScale)
      const baseRadius = Math.max(3, 6 / globalScale)

      const isSearching = matchingNodeIds !== null
      const isSearchMatch = matchingNodeIds?.has(node.id) ?? false
      const isHoverMatch = highlightNodes.has(node.id) && !isSearching
      const isSearchNeighbour = isSearching && !isSearchMatch && highlightNodes.has(node.id)

      let color: string
      let glowIntensity: number
      let outerGlow: string
      let textColor: string

      if (isSearchMatch) {
        color = theme.searchNode
        glowIntensity = 22
        outerGlow = theme.searchNodeGlow
        textColor = '#34d399'
      } else if (isSearchNeighbour) {
        color = nodeColor(node.id)
        glowIntensity = 5
        outerGlow = `${color}33`
        textColor = 'rgba(226,232,240,0.6)'
      } else if (isHoverMatch) {
        color = theme.highlightNode
        glowIntensity = 18
        outerGlow = theme.highlightLink
        textColor = theme.nodeText
      } else if (isSearching) {
        color = theme.mutedNode
        glowIntensity = 0
        outerGlow = 'transparent'
        textColor = 'rgba(113,113,122,0.3)'
      } else {
        color = nodeColor(node.id)
        glowIntensity = 10
        outerGlow = `${color}66`
        textColor = theme.nodeText
      }

      const glowRadius = isSearchMatch || isHoverMatch
        ? baseRadius * 2.8
        : isSearchNeighbour
          ? baseRadius * 1.4
          : isSearching
            ? baseRadius * 0.5
            : baseRadius * 1.8

      if (outerGlow !== 'transparent') {
        const glow = ctx.createRadialGradient(
          node.x!, node.y!, 0,
          node.x!, node.y!, glowRadius,
        )
        glow.addColorStop(0, `${hexToRgba(color, 0.4)}`)
        glow.addColorStop(1, `${color}00`)
        ctx.fillStyle = glow
        ctx.beginPath()
        ctx.arc(node.x!, node.y!, glowRadius, 0, 2 * Math.PI)
        ctx.fill()
      }

      const coreRadius = isSearchMatch || isSearchNeighbour
        ? baseRadius
        : isSearching
          ? baseRadius * 0.5
          : baseRadius
      ctx.beginPath()
      ctx.arc(node.x!, node.y!, coreRadius, 0, 2 * Math.PI)
      ctx.fillStyle = color
      if (glowIntensity > 0) {
        ctx.shadowColor = color
        ctx.shadowBlur = glowIntensity
      }
      ctx.fill()
      ctx.shadowBlur = 0

      if (!isSearching || isSearchMatch || isSearchNeighbour) {
        ctx.beginPath()
        ctx.arc(node.x! - baseRadius * 0.2, node.y! - baseRadius * 0.2, baseRadius * 0.35, 0, 2 * Math.PI)
        ctx.fillStyle = 'rgba(255,255,255,0.4)'
        ctx.fill()
      }

      ctx.font = `${fontSize}px "JetBrains Mono", "Fira Code", monospace`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      const labelY = node.y! + coreRadius + 3

      ctx.shadowColor = 'rgba(0,0,0,0.8)'
      ctx.shadowBlur = 4
      ctx.fillStyle = textColor
      ctx.fillText(label, node.x!, labelY)
      ctx.shadowBlur = 0
    },
    [highlightNodes, matchingNodeIds, theme],
  )

  // ── Link painter (search-aware, theme-aware) ─────────────────────────
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
        ctx.lineWidth = 0.3
        ctx.stroke()
        return
      }

      ctx.beginPath()
      ctx.moveTo(sx, sy)
      ctx.lineTo(tx, ty)

      if (isSearching && isHighlighted) {
        ctx.strokeStyle = theme.searchLink
        ctx.lineWidth = 1.2
      } else if (isHighlighted) {
        ctx.strokeStyle = theme.highlightLink
        ctx.lineWidth = 1.5
      } else {
        ctx.strokeStyle = theme.linkColor
        ctx.lineWidth = 0.6
      }
      ctx.stroke()
    },
    [highlightLinks, matchingNodeIds, theme],
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
  }, [activeBrain])

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

          {/* Search bar */}
          <div className="relative flex-1 max-w-xs mx-3">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-zinc-500 pointer-events-none" />
              <input
                ref={inputRef}
                type="text"
                placeholder="Search entities…  (Ctrl+F)"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value)
                  setSearchFocused(true)
                }}
                onFocus={() => setSearchFocused(true)}
                onBlur={() => setTimeout(() => setSearchFocused(false), 200)}
                className="w-full pl-8 pr-7 py-1 text-[10px] font-mono
                           bg-zinc-900/80 border border-zinc-800 rounded-lg
                           text-zinc-200 placeholder-zinc-600
                           focus:outline-none transition-all duration-200"
                style={{
                  borderColor: searchFocused ? `${brainColor}50` : undefined,
                  boxShadow: searchFocused ? `0 0 12px ${brainColor}15` : undefined,
                }}
              />
              {searchQuery && (
                <button
                  onClick={handleClearSearch}
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 p-0.5 rounded
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

      {/* ── Graph Container ─────────────────────────────────────────────── */}
      <div ref={containerRef} className="flex-1 relative">
        {/* Loading overlay */}
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#09090b]/80 backdrop-blur-sm">
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
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#09090b]/80 backdrop-blur-sm">
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
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#09090b]/60">
            <div className="flex flex-col items-center gap-2 text-zinc-500">
              <GitBranch className="w-10 h-10 text-zinc-700" />
              <p className="text-xs font-mono" style={{ color: brainColor }}>
                {activeMeta.label} is empty
              </p>
              <p className="text-[10px] font-mono text-zinc-600">
                Ingest content via{' '}
                <code style={{ color: brainColor }}>
                  POST /graph/ingest
                </code>
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
            backgroundColor={theme.bg}

            // Nodes
            nodeRelSize={4}
            nodeCanvasObject={paintNode}
            nodeCanvasObjectMode={() => 'replace'}
            nodePointerAreaPaint={(node, color, ctx) => {
              const r = 8
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

      {/* ── Footer: Stats bar ────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-1.5 border-t border-zinc-800/40 shrink-0">
        <div className="flex items-center gap-3">
          <Info className="w-3 h-3 text-zinc-600" />
          <span className="text-[8px] font-mono text-zinc-600 tracking-wider">
            Drag nodes · Scroll to zoom · Hover to highlight connections
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
