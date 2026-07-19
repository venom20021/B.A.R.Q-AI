import { useState, useEffect, useCallback, useMemo, startTransition } from 'react'
import { api } from '../utils/api'
import {
  Activity,
  Zap,
  Mic,
  Volume2,
  AlertTriangle,
  WifiOff,
  Clock,
  ChevronRight,
  X,
} from 'lucide-react'
import { motion } from 'framer-motion'
import { StatCard } from '../components/StatCard'
import { GlassPanel } from '../components/GlassPanel'
import { DynamicChart } from '../components/DynamicChart'
import type { DynamicChartSchema } from '../components/DynamicChart'

// ─── Types ─────────────────────────────────────────────────────────────

interface EvolutionEventSummary {
  total_events: number
  event_types: {
    event_type: string
    count: number
    avg_duration_ms: number
    last_timestamp: string
  }[]
  storage_path: string
  daily_file: string
}

interface EvolutionEvent {
  type: string
  timestamp: string
  duration_ms: number
  metadata: Record<string, unknown>
}

interface EvolutionResponse {
  events: EvolutionEvent[]
  summary: EvolutionEventSummary
  total_events: number
}

// ─── Helper: format duration ─────────────────────────────────────────

function fmtDuration(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`
  if (ms >= 1) return `${ms.toFixed(1)}ms`
  return `${(ms * 1000).toFixed(0)}µs`
}

function fmtTimestamp(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  } catch {
    return iso.slice(11, 19)
  }
}

function fmtDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return iso.slice(0, 16)
  }
}

// ─── Helpers: extract stats from summary ──────────────────────────────

function statFrom(summary: EvolutionEventSummary | null, type: string) {
  return summary?.event_types?.find((e) => e.event_type === type) ?? null
}

function countFrom(summary: EvolutionEventSummary | null, type: string): number {
  return statFrom(summary, type)?.count ?? 0
}

function avgFrom(summary: EvolutionEventSummary | null, type: string): number {
  return statFrom(summary, type)?.avg_duration_ms ?? 0
}

// ─── Helpers: prepare chart data from events ──────────────────────────

function prepareTimeline(
  events: EvolutionEvent[],
  type: string,
  limit = 30,
): Record<string, unknown>[] {
  return events
    .filter((e) => e.type === type && e.duration_ms > 0)
    .slice(0, limit)  // events are newest-first, keep up to `limit` newest
    .reverse()        // reverse to chronological order for charts
    .map((e) => ({
      time: fmtTimestamp(e.timestamp),
      ms: Math.round(e.duration_ms * 10) / 10,
      full: e.timestamp,
    }))
}

function prepareMultiTypeTimeline(
  events: EvolutionEvent[],
  types: string[],
  limit = 30,
): Record<string, unknown>[] {
  // Build a map: full_timestamp -> { time, type1, type2, ... }
  const points = new Map<string, Record<string, unknown>>()

  for (const t of types) {
    for (const e of events) {
      if (e.type === t && e.duration_ms > 0) {
        if (!points.has(e.timestamp)) {
          points.set(e.timestamp, { time: fmtTimestamp(e.timestamp), full: e.timestamp })
        }
        const entry = points.get(e.timestamp)!
        entry[t] = Math.round(e.duration_ms * 10) / 10
      }
    }
  }

  return Array.from(points.values())
    .sort((a, b) => (a.full as string).localeCompare(b.full as string))
    .slice(-limit)
}

function prepareCountOverTime(
  events: EvolutionEvent[],
  type: string,
  bucketMinutes = 5,
): Record<string, unknown>[] {
  const filtered = events.filter((e) => e.type === type)
  const buckets = new Map<string, number>()

  for (const e of filtered) {
    try {
      const d = new Date(e.timestamp)
      const bucket = new Date(
        Math.floor(d.getTime() / (bucketMinutes * 60 * 1000)) * (bucketMinutes * 60 * 1000),
      )
      const key = bucket.toISOString()  // use ISO for proper sorting
      buckets.set(key, (buckets.get(key) ?? 0) + 1)
    } catch {
      // skip unparseable timestamps
    }
  }

  return Array.from(buckets.entries())
    .sort(([a], [b]) => a.localeCompare(b))  // sort buckets chronologically
    .slice(-20)
    .map(([key, count]) => ({
      time: new Date(key).toLocaleTimeString('en-US', {
        hour: '2-digit', minute: '2-digit',
      }),
      count,
    }))
}

// ─── Main Component ───────────────────────────────────────────────────

export function EvolutionPage(): JSX.Element {
  const [response, setResponse] = useState<EvolutionResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedTypes, setSelectedTypes] = useState<Set<string>>(new Set())

  const fetchData = useCallback(async () => {
    setLoading(true)
    // Default limit of 100 events is sufficient for the dashboard
    const result = await api<EvolutionResponse>('/voice/evolution')
    if (result) setResponse(result)
    setLoading(false)
  }, [])

  useEffect(() => {
    startTransition(() => { void fetchData() })
  }, [fetchData])

  const summary = response?.summary ?? null
  const events = useMemo(() => response?.events ?? [], [response?.events])

  // ── Memoized chart schemas ─────────────────────────────────────────

  const ttfbChart = useMemo<DynamicChartSchema | null>(() => {
    const data = prepareTimeline(events, 'ttfb', 30)
    if (data.length === 0) return null
    return {
      type: 'LineChart',
      title: 'TTFB Over Time',
      data,
      config: {
        xKey: 'time',
        yKey: 'ms',
        color: '#818cf8',
        showLegend: false,
        showGrid: true,
        yLabel: 'ms',
      },
    }
  }, [events])

  const sttChart = useMemo<DynamicChartSchema | null>(() => {
    const data = prepareTimeline(events, 'stt_latency', 30)
    if (data.length === 0) return null
    return {
      type: 'LineChart',
      title: 'STT Latency Over Time',
      data,
      config: {
        xKey: 'time',
        yKey: 'ms',
        color: '#34d399',
        showLegend: false,
        showGrid: true,
        yLabel: 'ms',
      },
    }
  }, [events])

  const ttsChart = useMemo<DynamicChartSchema | null>(() => {
    const data = prepareTimeline(events, 'tts_latency', 30)
    if (data.length === 0) return null
    return {
      type: 'LineChart',
      title: 'TTS Latency Over Time',
      data,
      config: {
        xKey: 'time',
        yKey: 'ms',
        color: '#f472b6',
        showLegend: false,
        showGrid: true,
        yLabel: 'ms',
      },
    }
  }, [events])

  const errorChart = useMemo<DynamicChartSchema | null>(() => {
    // Combine buffer overflows + ws disconnects + llm errors into one bar chart
    const overflowData = prepareCountOverTime(events, 'buffer_overflow', 10)
    const wsData = prepareCountOverTime(events, 'ws_disconnect', 10)
    const llmErrorData = prepareCountOverTime(events, 'llm_error', 10)

    // Merge by time bucket
    const timeKeys = new Set([
      ...overflowData.map((d) => d.time as string),
      ...wsData.map((d) => d.time as string),
      ...llmErrorData.map((d) => d.time as string),
    ])

    const merged = Array.from(timeKeys).sort().map((time) => ({
      time,
      overflows: (overflowData.find((d) => d.time === time)?.count ?? 0) as number,
      disconnects: (wsData.find((d) => d.time === time)?.count ?? 0) as number,
      llm_errors: (llmErrorData.find((d) => d.time === time)?.count ?? 0) as number,
    }))

    if (merged.length === 0) return null

    return {
      type: 'BarChart',
      title: 'Errors & Disconnects',
      data: merged,
      config: {
        xKey: 'time',
        stacked: true,
        showLegend: true,
        showGrid: true,
        colors: ['#f87171', '#fbbf24', '#a78bfa'],
      },
    }
  }, [events])

  // ── Combined latency chart (TTFB + STT + TTS on one chart) ───────

  const combinedLatencyChart = useMemo<DynamicChartSchema | null>(() => {
    const data = prepareMultiTypeTimeline(events, ['ttfb', 'stt_latency', 'tts_latency'], 30)
    if (data.length === 0) return null
    return {
      type: 'LineChart',
      title: 'Latency Comparison',
      data,
      config: {
        xKey: 'time',
        showLegend: true,
        showGrid: true,
        yLabel: 'ms',
        colors: ['#818cf8', '#34d399', '#f472b6'],
      },
    }
  }, [events])

  // ── Event type filter for detail view ──────────────────────────────

  const toggleType = useCallback((type: string) => {
    setSelectedTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) {
        next.delete(type)
      } else {
        next.add(type)
      }
      return next
    })
  }, [])

  const clearFilters = useCallback(() => {
    setSelectedTypes(new Set())
  }, [])

  const hasFilter = selectedTypes.size > 0

  const filteredEvents = useMemo(() => {
    if (!hasFilter) return events.slice(0, 50)
    return events.filter((e) => selectedTypes.has(e.type)).slice(0, 50)
  }, [events, selectedTypes, hasFilter])

  const container = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.05 } },
  }

  const itemAnim = {
    hidden: { opacity: 0, y: 16 },
    show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' } },
  }

  if (loading && !response) {
    return (
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        <div className="flex items-center justify-center h-64">
          <div className="w-6 h-6 border-2 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin" />
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider flex items-center gap-3">
          <Activity className="w-5 h-5 text-cyan-400" />
          EVOLUTION ENGINE
        </h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">
          Self-optimisation performance telemetry — TTFB, buffer overflows, WebSocket drops, and latency metrics
        </p>
        {summary && (
          <div className="flex items-center gap-3 mt-2">
            <span className="text-xs font-share-tech text-dim-500 tracking-wider">
              FILE: {summary.daily_file}
            </span>
            <span className="text-xs font-share-tech text-dim-500">
              TOTAL: {summary.total_events} events
            </span>
            <button
              onClick={() => void fetchData()}
              className="ml-auto text-xs font-share-tech text-cyan-400/60 hover:text-cyan-300 transition-colors tracking-wider"
            >
              ⟳ Refresh
            </button>
          </div>
        )}
      </motion.div>

      {/* Stat Cards */}
      <motion.div
        variants={container}
        initial="hidden"
        animate="show"
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4"
      >
        <motion.div variants={itemAnim}>
          <StatCard
            title="Total Events"
            value={summary?.total_events ?? 0}
            icon={Activity}
            accent="cyan"
          />
        </motion.div>
        <motion.div variants={itemAnim}>
          <StatCard
            title="Avg TTFB"
            value={avgFrom(summary, 'ttfb') > 0 ? fmtDuration(avgFrom(summary, 'ttfb')) : '—'}
            description={`${countFrom(summary, 'ttfb')} samples`}
            icon={Zap}
            accent="purple"
          />
        </motion.div>
        <motion.div variants={itemAnim}>
          <StatCard
            title="Avg STT"
            value={avgFrom(summary, 'stt_latency') > 0 ? fmtDuration(avgFrom(summary, 'stt_latency')) : '—'}
            description={`${countFrom(summary, 'stt_latency')} samples`}
            icon={Mic}
            accent="green"
          />
        </motion.div>
        <motion.div variants={itemAnim}>
          <StatCard
            title="Avg TTS"
            value={avgFrom(summary, 'tts_latency') > 0 ? fmtDuration(avgFrom(summary, 'tts_latency')) : '—'}
            description={`${countFrom(summary, 'tts_latency')} samples`}
            icon={Volume2}
            accent="plasma"
          />
        </motion.div>
        <motion.div variants={itemAnim}>
          <StatCard
            title="Buffer Overflows"
            value={countFrom(summary, 'buffer_overflow')}
            icon={AlertTriangle}
            accent={countFrom(summary, 'buffer_overflow') > 5 ? 'plasma' : 'green'}
          />
        </motion.div>
        <motion.div variants={itemAnim}>
          <StatCard
            title="WS Drops"
            value={countFrom(summary, 'ws_disconnect')}
            icon={WifiOff}
            accent={countFrom(summary, 'ws_disconnect') > 5 ? 'plasma' : 'cyan'}
          />
        </motion.div>
      </motion.div>

      {/* Charts */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="grid grid-cols-1 lg:grid-cols-2 gap-4"
      >
        {/* Combined Latency Chart (multi-type) */}
        <GlassPanel className="p-4 lg:col-span-2">
          <h3 className="text-xs font-orbitron font-bold text-ghost tracking-wider mb-3 flex items-center gap-2">
            <Zap className="w-4 h-4 text-holographic" />
            Latency Comparison
            <span className="text-[9px] font-share-tech text-dim-500 ml-1 tracking-wider">
              TTFB · STT · TTS
            </span>
          </h3>
          {combinedLatencyChart ? (
            <DynamicChart schema={combinedLatencyChart} />
          ) : (
            <div className="flex items-center justify-center h-[220px] text-xs font-rajdhani text-dim-500 italic">
              No latency data yet — wake word and transcription events will appear here
            </div>
          )}
        </GlassPanel>

        {/* Individual Latency Charts (smaller, side-by-side) */}
        <GlassPanel className="p-4">
          <h3 className="text-xs font-orbitron font-bold text-ghost tracking-wider mb-3 flex items-center gap-2">
            <Zap className="w-4 h-4 text-holographic" />
            TTFB
          </h3>
          {ttfbChart ? (
            <DynamicChart schema={ttfbChart} />
          ) : (
            <div className="flex items-center justify-center h-[160px] text-xs font-rajdhani text-dim-500 italic">
              No data
            </div>
          )}
        </GlassPanel>

        <GlassPanel className="p-4">
          <h3 className="text-xs font-orbitron font-bold text-ghost tracking-wider mb-3 flex items-center gap-2">
            <Mic className="w-4 h-4 text-neural" />
            STT Latency
          </h3>
          {sttChart ? (
            <DynamicChart schema={sttChart} />
          ) : (
            <div className="flex items-center justify-center h-[160px] text-xs font-rajdhani text-dim-500 italic">
              No data
            </div>
          )}
        </GlassPanel>

        <GlassPanel className="p-4">
          <h3 className="text-xs font-orbitron font-bold text-ghost tracking-wider mb-3 flex items-center gap-2">
            <Volume2 className="w-4 h-4 text-plasma" />
            TTS Latency
          </h3>
          {ttsChart ? (
            <DynamicChart schema={ttsChart} />
          ) : (
            <div className="flex items-center justify-center h-[160px] text-xs font-rajdhani text-dim-500 italic">
              No data
            </div>
          )}
        </GlassPanel>

        {/* Errors & Disconnects Chart */}
        <GlassPanel className="p-4">
          <h3 className="text-xs font-orbitron font-bold text-ghost tracking-wider mb-3 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-plasma" />
            Errors &amp; Disconnects
          </h3>
          {errorChart ? (
            <DynamicChart schema={errorChart} />
          ) : (
            <div className="flex items-center justify-center h-[160px] text-xs font-rajdhani text-dim-500 italic">
              No errors recorded — system is healthy
            </div>
          )}
        </GlassPanel>
      </motion.div>

      {/* Event Type Summary */}
      {summary && summary.event_types.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
        >
          <GlassPanel className="p-4">
            <h3 className="text-xs font-orbitron font-bold text-ghost tracking-wider mb-3 flex items-center gap-2">
              <Clock className="w-4 h-4 text-cyan-400" />
              Event Type Breakdown
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
              {summary.event_types.map((et) => {
                const isSelected = selectedTypes.has(et.event_type)
                return (
                  <button
                    key={et.event_type}
                    onClick={() => toggleType(et.event_type)}
                    className={`text-left p-3 rounded-lg border transition-all duration-200 ${
                      isSelected
                        ? 'border-cyan-500/40 bg-cyan-500/10 ring-1 ring-cyan-500/20'
                        : 'border-white/[0.04] bg-white/[0.02] hover:border-white/[0.10] hover:bg-white/[0.04]'
                    }`}
                  >
                    <p className="text-xs font-share-tech text-dim-400 tracking-wider uppercase truncate">
                      {et.event_type.replace(/_/g, ' ')}
                      {isSelected && (
                        <span className="ml-1.5 text-[9px] text-cyan-400">✓</span>
                      )}
                    </p>
                    <p className="text-lg font-orbitron font-bold text-ghost mt-1">
                      {et.count}
                    </p>
                    <p className="text-[10px] font-exo text-dim-500 mt-0.5">
                      {et.avg_duration_ms > 0 ? `avg ${fmtDuration(et.avg_duration_ms)}` : '—'}
                    </p>
                  </button>
                )
              })}
            </div>
          </GlassPanel>
        </motion.div>
      )}

      {/* Latest Events Table */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
      >
        <GlassPanel className="p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-orbitron font-bold text-ghost tracking-wider flex items-center gap-2">
              <ChevronRight className="w-4 h-4 text-cyan-400" />
              Latest Events
              {hasFilter && (
                <span className="text-[10px] font-share-tech text-cyan-400/60 ml-2 flex items-center gap-1">
                  filtered:
                  {Array.from(selectedTypes).map((t) => (
                    <span key={t} className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300">
                      {t.replace(/_/g, ' ')}
                      <button onClick={() => toggleType(t)} className="hover:text-white transition-colors">
                        <X className="w-2.5 h-2.5" />
                      </button>
                    </span>
                  ))}
                </span>
              )}
            </h3>
            {hasFilter && (
              <button
                onClick={clearFilters}
                className="text-[10px] font-share-tech text-dim-500 hover:text-dim-300 transition-colors tracking-wider flex items-center gap-1"
              >
                <X className="w-2.5 h-2.5" />
                Clear all
              </button>
            )}
          </div>

          {filteredEvents.length === 0 ? (
            <div className="flex items-center justify-center h-20 text-xs font-rajdhani text-dim-500 italic">
              No events recorded yet
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs font-rajdhani">
                <thead>
                  <tr className="text-dim-500 tracking-wider border-b border-white/[0.04]">
                    <th className="text-left py-2 pr-4 font-semibold">Type</th>
                    <th className="text-left py-2 pr-4 font-semibold">Time</th>
                    <th className="text-right py-2 pr-4 font-semibold">Duration</th>
                    <th className="text-left py-2 font-semibold">Metadata</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredEvents.map((event, i) => (
                    <tr
                      key={`${event.type}-${event.timestamp}-${i}`}
                      className="border-b border-white/[0.02] hover:bg-white/[0.03] transition-colors"
                    >
                      <td className="py-2 pr-4">
                        <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-share-tech tracking-wider ${
                          event.type === 'ttfb' ? 'bg-purple-500/10 text-purple-300' :
                          event.type === 'stt_latency' ? 'bg-green-500/10 text-green-300' :
                          event.type === 'tts_latency' ? 'bg-pink-500/10 text-pink-300' :
                          event.type === 'buffer_overflow' ? 'bg-red-500/10 text-red-300' :
                          event.type === 'ws_disconnect' ? 'bg-yellow-500/10 text-yellow-300' :
                          event.type === 'llm_error' ? 'bg-orange-500/10 text-orange-300' :
                          'bg-white/5 text-dim-300'
                        }`}>
                          {event.type.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="py-2 pr-4 text-dim-400 font-mono">
                        {fmtDate(event.timestamp)}
                      </td>
                      <td className="py-2 pr-4 text-right font-mono text-dim-300">
                        {event.duration_ms > 0 ? fmtDuration(event.duration_ms) : '—'}
                      </td>
                      <td className="py-2 text-dim-500 truncate max-w-[200px]">
                        {event.metadata && Object.keys(event.metadata).length > 0
                          ? Object.entries(event.metadata)
                            .map(([k, v]) => `${k}: ${String(v).slice(0, 40)}`)
                            .join(', ')
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </GlassPanel>
      </motion.div>
    </div>
  )
}
