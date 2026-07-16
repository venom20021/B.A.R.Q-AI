import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { motion } from 'framer-motion'
import { BrainCircuit, Info, RotateCw, AlertCircle, Search, X, Zap } from 'lucide-react'
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
  nodes: number
  edges: number
}

interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
  _meta?: GraphMeta
}

// ─── Color Palette ─────────────────────────────────────────────────────────

const COLORS = {
  bg: '#09090b',
  nodeGlow: '#818cf8',
  nodeInner: '#a5b4fc',
  nodeText: '#e2e8f0',
  linkColor: 'rgba(148, 163, 184, 0.18)',
  particleColor: '#818cf8',
  particlePulseColor: '#ffffff',
  highlightNode: '#f472b6',
  highlightLink: 'rgba(244, 114, 182, 0.4)',
  pulseLink: 'rgba(129, 140, 248, 0.35)',
  searchNode: '#34d399',           // emerald — matching a search
  searchNodeGlow: 'rgba(52,211,153,0.6)',
  searchLink: 'rgba(52,211,153,0.35)',
  mutedNode: 'rgba(113,113,122,0.2)',   // dimmed non-matching node
  mutedLink: 'rgba(113,113,122,0.06)',
}

// ─── Pulse timing constants ────────────────────────────────────────────────

const PULSE_DURATION_MS = 2200        // total pulse length
const PULSE_PEAK_MS = 300             // time to reach peak intensity
const PULSE_SUSTAIN_MS = 500          // time held at/above 50% intensity
const AUTO_POLL_INTERVAL_MS = 8000    // check for new graph data every 8s

// ─── Helper: pick a neon hue per node ──────────────────────────────────────

const NEON_PALETTE = [
  '#818cf8', // indigo
  '#a78bfa', // violet
  '#c084fc', // purple
  '#e879f9', // fuchsia
  '#f472b6', // pink
  '#34d399', // emerald
  '#2dd4bf', // teal
  '#22d3ee', // cyan
]

function nodeColor(id: string): string {
  let hash = 0
  for (let i = 0; i < id.length; i++) {
    hash = ((hash << 5) - hash + id.charCodeAt(i)) | 0
  }
  return NEON_PALETTE[Math.abs(hash) % NEON_PALETTE.length]
}

// ─── BrainVisualizer Component ─────────────────────────────────────────────

export function BrainPage(): JSX.Element {
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null)
  const [dimension, setDimension] = useState({ width: 800, height: 600 })
  const containerRef = useRef<HTMLDivElement>(null)
  const graphRef = useRef<any>(null)
  const [highlightNodes, setHighlightNodes] = useState<Set<string>>(new Set())
  const [highlightLinks, setHighlightLinks] = useState<Set<string>>(new Set())

  // Search state
  const [searchQuery, setSearchQuery] = useState('')
  const [searchFocused, setSearchFocused] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // Derived: all node IDs that match the current search query
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

  // Derived: autocomplete suggestions (filtered + ranked by prefix match)
  const searchSuggestions = useMemo(() => {
    if (!searchQuery.trim() || !graphData) return []
    const q = searchQuery.toLowerCase().trim()
    const scored: { id: string; score: number }[] = []
    for (const n of graphData.nodes) {
      const id = n.id.toLowerCase()
      if (id.includes(q)) {
        let score = 0
        if (id === q) score = 100          // exact match
        else if (id.startsWith(q)) score = 50 // prefix match
        else score = 10                     // substring match
        scored.push({ id: n.id, score })
      }
    }
    scored.sort((a, b) => b.score - a.score)
    return scored.slice(0, 8).map(s => s.id)
  }, [searchQuery, graphData])

  // When search changes, update highlight sets
  useEffect(() => {
    if (!matchingNodeIds || !graphData) {
      setHighlightNodes(new Set())
      setHighlightLinks(new Set())
      return
    }

    // Gather all nodes reachable from matched nodes (1 hop)
    const nodeIds = new Set(matchingNodeIds)
    const linkKeys = new Set<string>()

    for (const link of graphData.links) {
      const src = typeof link.source === 'string' ? link.source : (link.source as GraphNode)?.id
      const tgt = typeof link.target === 'string' ? link.target : (link.target as GraphNode)?.id
      if (!src || !tgt) continue

      const srcMatch = matchingNodeIds.has(src)
      const tgtMatch = matchingNodeIds.has(tgt)

      if (srcMatch && tgtMatch) {
        // Both matched — keep both, highlight link
        linkKeys.add(`${src}->${tgt}`)
      } else if (srcMatch) {
        // Source matched — highlight target as neighbour
        nodeIds.add(tgt)
        linkKeys.add(`${src}->${tgt}`)
      } else if (tgtMatch) {
        // Target matched — highlight source as neighbour
        nodeIds.add(src)
        linkKeys.add(`${src}->${tgt}`)
      }
    }

    setHighlightNodes(nodeIds)
    setHighlightLinks(linkKeys)
  }, [matchingNodeIds, graphData])

  // Keyboard shortcut: Ctrl+F / Cmd+F to focus search
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

  // ── Handle selecting a suggestion or typed query ───────────────────────
  const handleSelectSearch = useCallback((entityId: string) => {
    setSearchQuery(entityId)
    setSearchFocused(false)
    // Zoom to the selected node
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

  // Synaptic pulse state
  const [pulseIntensity, setPulseIntensity] = useState(0)
  const pulseAnimRef = useRef<number | null>(null)
  const prevMetaRef = useRef<GraphMeta | null>(null)

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

  // ── Fetch graph data ──────────────────────────────────────────────────
  const fetchGraph = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resp: unknown = await window.barq?.python.request('/api/brain/visualize')
      if (!resp || typeof resp !== 'object') {
        throw new Error('Invalid response from backend')
      }
      const data = resp as GraphData
      // Ensure every node has a unique id label
      const seen = new Set<string>()
      data.nodes = data.nodes.filter((n) => {
        if (!n.id || seen.has(n.id)) return false
        seen.add(n.id)
        return true
      })
      // Ensure links reference node ids (not objects)
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
  }, [])

  useEffect(() => {
    fetchGraph()
  }, [fetchGraph])

  // ── Detect graph changes & trigger synaptic pulse ─────────────────────
  useEffect(() => {
    if (!graphData?._meta) return
    const meta = graphData._meta
    const prev = prevMetaRef.current

    // Trigger pulse on first load OR when nodes/edges actually changed
    const isNewData =
      !prev || prev.nodes !== meta.nodes || prev.edges !== meta.edges

    prevMetaRef.current = meta

    if (isNewData) {
      triggerPulse()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData?._meta?.nodes, graphData?._meta?.edges])

  // ── Auto-poll backend for new graph data ──────────────────────────────
  useEffect(() => {
    const interval = setInterval(() => {
      fetchGraph()
    }, AUTO_POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [fetchGraph])

  // ── Synaptic pulse animation loop ─────────────────────────────────────
  const triggerPulse = useCallback(() => {
    const start = performance.now()

    const animate = (now: number) => {
      const elapsed = now - start

      if (elapsed >= PULSE_DURATION_MS) {
        setPulseIntensity(0)
        pulseAnimRef.current = null
        return
      }

      // Compute intensity: quick rise, gradual decay
      let intensity: number
      if (elapsed < PULSE_PEAK_MS) {
        // Rapid attack to peak
        intensity = elapsed / PULSE_PEAK_MS
      } else if (elapsed < PULSE_SUSTAIN_MS) {
        // Brief sustain at peak
        intensity = 1.0
      } else {
        // Smooth exponential decay
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

  // Cleanup animation frame on unmount
  useEffect(() => {
    return () => {
      if (pulseAnimRef.current) {
        cancelAnimationFrame(pulseAnimRef.current)
      }
    }
  }, [])

  // ── Node hover highlight ──────────────────────────────────────────────
  const handleNodeHover = useCallback((node: GraphNode | null) => {
    setHoveredNode(node)
    if (!node || !graphData) {
      setHighlightNodes(new Set())
      setHighlightLinks(new Set())
      return
    }
    // Highlight the hovered node and its direct neighbours
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

      // Determine visual mode
      let color: string
      let glowIntensity: number
      let outerGlow: string
      let textColor: string

      const isSearchNeighbour = isSearching && !isSearchMatch && highlightNodes.has(node.id)

      if (isSearchMatch) {
        color = COLORS.searchNode
        glowIntensity = 22
        outerGlow = COLORS.searchNodeGlow
        textColor = '#34d399'
      } else if (isSearchNeighbour) {
        // Neighbour of a search match — visible but subdued
        color = nodeColor(node.id)
        glowIntensity = 5
        outerGlow = `${color}33`
        textColor = 'rgba(226,232,240,0.6)'
      } else if (isHoverMatch) {
        color = COLORS.highlightNode
        glowIntensity = 18
        outerGlow = 'rgba(244,114,182,0.5)'
        textColor = COLORS.nodeText
      } else if (isSearching) {
        // Non-matching, non-neighbour node during active search — strongly dimmed
        color = COLORS.mutedNode
        glowIntensity = 0
        outerGlow = 'transparent'
        textColor = 'rgba(113,113,122,0.3)'
      } else {
        color = nodeColor(node.id)
        glowIntensity = 10
        outerGlow = `${color}66`
        textColor = COLORS.nodeText
      }

      const glowRadius = isSearchMatch || isHoverMatch
        ? baseRadius * 2.8
        : isSearchNeighbour
          ? baseRadius * 1.4
          : isSearching
            ? baseRadius * 0.5
            : baseRadius * 1.8

      // Outer glow (skip for fully dimmed nodes)
      if (outerGlow !== 'transparent') {
        const glow = ctx.createRadialGradient(
          node.x!, node.y!, 0,
          node.x!, node.y!, glowRadius,
        )
        glow.addColorStop(0, outerGlow)
        glow.addColorStop(1, `${color}00`)
        ctx.fillStyle = glow
        ctx.beginPath()
        ctx.arc(node.x!, node.y!, glowRadius, 0, 2 * Math.PI)
        ctx.fill()
      }

      // Core circle
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

      // Inner bright dot (skip for fully dimmed)
      if (!isSearching || isSearchMatch || isSearchNeighbour) {
        ctx.beginPath()
        ctx.arc(node.x! - baseRadius * 0.2, node.y! - baseRadius * 0.2, baseRadius * 0.35, 0, 2 * Math.PI)
        ctx.fillStyle = 'rgba(255,255,255,0.4)'
        ctx.fill()
      }

      // Label
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
    [highlightNodes, matchingNodeIds],
  )

  // ── Link painter (search-aware) ────────────────────────────────────────
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
        // During search, dim non-connected links
        ctx.beginPath()
        ctx.moveTo(sx, sy)
        ctx.lineTo(tx, ty)
        ctx.strokeStyle = COLORS.mutedLink
        ctx.lineWidth = 0.3
        ctx.stroke()
        return
      }

      ctx.beginPath()
      ctx.moveTo(sx, sy)
      ctx.lineTo(tx, ty)

      if (isSearching && isHighlighted) {
        ctx.strokeStyle = COLORS.searchLink
        ctx.lineWidth = 1.2
      } else if (isHighlighted) {
        ctx.strokeStyle = COLORS.highlightLink
        ctx.lineWidth = 1.5
      } else {
        ctx.strokeStyle = COLORS.linkColor
        ctx.lineWidth = 0.6
      }
      ctx.stroke()
    },
    [highlightLinks, matchingNodeIds],
  )

  // ── Zoom to fit on load ───────────────────────────────────────────────
  useEffect(() => {
    if (graphData && graphRef.current) {
      setTimeout(() => {
        try {
          graphRef.current.zoomToFit(400, 50)
        } catch { /* ignore */ }
      }, 500)
    }
  }, [graphData])

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <div className="h-full w-full bg-[#09090b] text-zinc-200 overflow-hidden relative font-mono flex flex-col">
      {/* ── Header ────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800/60 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-indigo-500/15 flex items-center justify-center border border-indigo-500/20">
            <BrainCircuit className="w-4 h-4 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-sm font-orbitron font-bold tracking-[0.15em] uppercase text-indigo-300">
              AI Brain
            </h1>
            <p className="text-[9px] font-mono text-zinc-500 tracking-[0.1em]">
              Knowledge Graph Visualization
            </p>
          </div>
        </div>

        {/* Search bar */}
        <div className="relative flex-1 max-w-sm mx-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-500 pointer-events-none" />
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
              onBlur={() => {
                // Delay hiding so click on suggestion registers
                setTimeout(() => setSearchFocused(false), 200)
              }}
              className="w-full pl-9 pr-8 py-1.5 text-[11px] font-mono
                         bg-zinc-900/80 border border-zinc-800 rounded-lg
                         text-zinc-200 placeholder-zinc-600
                         focus:outline-none focus:border-indigo-500/40 focus:shadow-[0_0_12px_rgba(129,140,248,0.08)]
                         transition-all duration-200"
            />
            {/* Clear button */}
            {searchQuery && (
              <button
                onClick={handleClearSearch}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded
                           text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
              >
                <X className="w-3 h-3" />
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
                         shadow-2xl z-50 max-h-48 overflow-y-auto"
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
                    className={`w-full flex items-center gap-2 px-3 py-1.5 text-left
                               text-[11px] font-mono transition-colors
                               ${isMatched ? 'text-emerald-300 bg-emerald-500/8' : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'}`}
                  >
                    <span
                      className="w-1.5 h-1.5 rounded-full shrink-0"
                      style={{ backgroundColor: isMatched ? '#34d399' : '#52525b' }}
                    />
                    <span className="truncate">{id}</span>
                    {isMatched && (
                      <span className="ml-auto text-[8px] uppercase tracking-wider text-emerald-500/60">
                        Match
                      </span>
                    )}
                  </button>
                )
              })}
            </motion.div>
          )}
        </div>

        <div className="flex items-center gap-3">
          {/* Stats badge */}
          {graphData?._meta && (
            <div className="flex items-center gap-3 px-3 py-1.5 rounded-lg bg-zinc-900/80 border border-zinc-800 text-[10px] font-mono">
              {/* Show match count during active search */}
              {searchQuery.trim() && matchingNodeIds ? (
                <span className="text-emerald-400">
                  <span className="text-zinc-500">MATCHES</span>{' '}
                  <span className="font-bold">{matchingNodeIds.size}</span>
                </span>
              ) : (
                <span className="text-indigo-400">
                  <span className="text-zinc-500">NODES</span>{' '}
                  <span className="font-bold">{graphData._meta.nodes}</span>
                </span>
              )}
              <span className="w-px h-3 bg-zinc-800" />
              <span className="text-pink-400">
                <span className="text-zinc-500">EDGES</span>{' '}
                <span className="font-bold">{graphData._meta.edges}</span>
              </span>
            </div>
          )}

          {/* Pulse button */}
          <button
            onClick={triggerPulse}
            className={`relative p-1.5 rounded-lg transition-all duration-200 ${
              pulseIntensity > 0
                ? 'text-indigo-300 bg-indigo-500/15 shadow-[0_0_12px_rgba(129,140,248,0.2)]'
                : 'text-zinc-500 hover:text-indigo-400 hover:bg-indigo-500/10'
            }`}
            title="Fire synaptic pulse"
          >
            <Zap className="w-4 h-4" />
            {/* Pulsing ring when active */}
            {pulseIntensity > 0 && (
              <span
                className="absolute inset-0 rounded-lg animate-ping opacity-40"
                style={{ backgroundColor: 'rgba(129,140,248,0.3)' }}
              />
            )}
          </button>

          {/* Refresh button */}
          <button
            onClick={fetchGraph}
            disabled={loading}
            className="p-1.5 rounded-lg text-zinc-500 hover:text-indigo-400 hover:bg-indigo-500/10 transition-colors disabled:opacity-40"
            title="Refresh graph data"
          >
            <RotateCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* ── Graph Container ─────────────────────────────────────────────── */}
      <div
        ref={containerRef}
        className="flex-1 relative"
      >
        {/* Loading overlay */}
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#09090b]/80 backdrop-blur-sm">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-2 border-indigo-500/30 border-t-indigo-400 rounded-full animate-spin" />
              <p className="text-[10px] font-mono text-zinc-500 tracking-wider uppercase animate-pulse">
                Syncing neural pathways…
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
                className="px-4 py-1.5 text-[10px] font-mono tracking-wider uppercase rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/30 hover:bg-indigo-500/20 transition-colors"
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
              <BrainCircuit className="w-10 h-10 text-zinc-700" />
              <p className="text-xs font-mono">The knowledge graph is empty</p>
              <p className="text-[10px] font-mono text-zinc-600">
                Ingest some text via{' '}
                <code className="text-indigo-500/80">POST /graph/ingest</code>
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
            backgroundColor={COLORS.bg}

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

            // Particles — synaptic pulse modulates count, speed, width, colour
            linkDirectionalParticles={
              // Pulse boosts particles from 2 up to 10
              () => 2 + Math.round(pulseIntensity * 8)
            }
            linkDirectionalParticleWidth={
              // Pulse thickens particles
              1.5 + pulseIntensity * 2.5
            }
            linkDirectionalParticleSpeed={
              // Pulse accelerates particles from 0.005 up to 0.035
              0.005 + pulseIntensity * 0.03
            }
            linkDirectionalParticleColor={() => {
              // Blend from indigo to white during pulse
              if (pulseIntensity < 0.01) return COLORS.particleColor
              const alpha = 0.6 + pulseIntensity * 0.4
              const r = 129 + Math.round(pulseIntensity * 126)  // 129→255
              const g = 140 + Math.round(pulseIntensity * 115)  // 140→255
              const b = 248 + Math.round(pulseIntensity * 7)    // 248→255
              return `rgba(${r},${g},${b},${alpha})`
            }}

            // Interaction
            onNodeHover={handleNodeHover}
            enableNodeDrag={true}
            enableZoomInteraction={true}
            enablePanInteraction={true}
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.3}
            cooldownTicks={100}

            // Warm-up so graph settles before user interacts
            warmupTicks={40}
          />
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
              <span className="text-[9px] font-mono text-zinc-500 uppercase tracking-wider">
                Node
              </span>
            </div>
          </motion.div>
        )}
      </div>

      {/* ── Footer hint ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-center gap-2 py-2 border-t border-zinc-800/40 shrink-0">
        <Info className="w-3 h-3 text-zinc-600" />
        <span className="text-[9px] font-mono text-zinc-600 tracking-wider">
          Drag nodes · Scroll to zoom · Hover to highlight connections
        </span>
      </div>
    </div>
  )
}
