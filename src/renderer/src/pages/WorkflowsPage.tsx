import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../utils/api'
import { getBackendConfig } from '../utils/backendConfig'
import {
  Workflow, Play, Square, RefreshCw, Loader2, CheckCircle, XCircle,
  Clock, ChevronDown, ChevronRight, Activity, Zap, ListChecks,
  CalendarClock, Sparkles, Send, Layers, Boxes, Route,
  GitBranch, PenLine, MoonStar, Save, RotateCcw, Database, Globe,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

// ─── Types (mirror python/agent/workflow_runtime.py) ──────────────────────────

interface WorkflowStepDef {
  id: string
  skill: string
  params?: Record<string, unknown>
  description?: string
  next_on_success?: string | null
  next_on_failure?: string | null
  parallel_with?: string[]
  critical?: boolean
}

interface WorkflowDef {
  name: string
  description: string
  steps: WorkflowStepDef[]
  trigger: string
  cron?: string | null
  timeout_seconds?: number
}

type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

interface RunStepResult {
  id: string
  skill: string
  status: 'running' | 'completed' | 'failed'
  result_preview?: string
  error?: string
}

interface RunState {
  run_id: string
  workflow: string
  status: RunStatus
  started_at?: number
  elapsed_seconds?: number
  error?: string
  results?: RunStepResult[]
  step_results?: Record<string, string>
}

interface CheckpointRow {
  checkpoint_key: string
  agent_type: string
  status: string
  updated_at?: string
  goal?: string
  completed_steps?: number
  total_steps?: number
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Merge fresh run states into the existing list, newest-first, capped at 25. */
function mergeRuns(prev: RunState[], updates: RunState[]): RunState[] {
  const map = new Map(updates.map((r) => [r.run_id, r]))
  prev.forEach((r) => { if (!map.has(r.run_id)) map.set(r.run_id, r) })
  return [...map.values()].slice(0, 25)
}

// ─── Status styling (shared) ─────────────────────────────────────────────────

const STATUS_META: Record<RunStatus, { label: string; color: string; icon: typeof Clock }> = {
  queued: { label: 'queued', color: 'bg-zinc-500/10 text-zinc-300 border-zinc-500/20', icon: Clock },
  running: { label: 'running', color: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/20', icon: Loader2 },
  completed: { label: 'completed', color: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20', icon: CheckCircle },
  failed: { label: 'failed', color: 'bg-red-500/10 text-red-300 border-red-500/20', icon: XCircle },
  cancelled: { label: 'cancelled', color: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20', icon: Square },
}

function StatusBadge({ status }: { status: RunStatus }): JSX.Element {
  const meta = STATUS_META[status]
  const Icon = meta.icon
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border text-hud text-[10px] font-semibold ${meta.color}`}>
      <Icon className={`w-2.5 h-2.5 ${status === 'running' || status === 'queued' ? 'animate-spin' : ''}`} />
      {meta.label}
    </span>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// WorkflowsPage
// ═══════════════════════════════════════════════════════════════════════════════

export function WorkflowsPage(): JSX.Element {
  const [workflows, setWorkflows] = useState<WorkflowDef[]>([])
  const [runs, setRuns] = useState<RunState[]>([])
  const [checkpoints, setCheckpoints] = useState<CheckpointRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchAll = useCallback(async () => {
    try {
      const [wfResp, runsResp, cpResp] = await Promise.all([
        api<{ workflows: WorkflowDef[] }>('/agent/workflows'),
        api<{ runs: RunState[] }>('/agent/workflows/runs?limit=20'),
        api<{ checkpoints: CheckpointRow[] }>('/agent/checkpoints?limit=25'),
      ])
      if (wfResp) setWorkflows(wfResp.workflows ?? [])
      if (cpResp) setCheckpoints(cpResp.checkpoints ?? [])
      if (runsResp) {
        const list = runsResp.runs ?? []
        setRuns(list)
        // Hydrate the most recent runs with step-level detail for a richer log
        const top = list.slice(0, 3)
        const hydrated = await Promise.allSettled(
          top.map((r) => api<RunState>(`/agent/workflows/runs/${encodeURIComponent(r.run_id)}`)),
        )
        const updates: RunState[] = []
        hydrated.forEach((res) => {
          if (res.status === 'fulfilled' && res.value) updates.push(res.value)
        })
        if (updates.length > 0) setRuns((prev) => mergeRuns(prev, updates))
      }
    } catch (e) {
      setError(String(e))
    }
    setLoading(false)
  }, [])

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void fetchAll() }, [fetchAll])

  const activeCount = runs.filter((r) => r.status === 'queued' || r.status === 'running').length
  const completedCount = runs.filter((r) => r.status === 'completed').length
  const totalSteps = workflows.reduce((acc, w) => acc + w.steps.length, 0)

  const handleRunsRefresh = useCallback((updated: RunState[]) => {
    setRuns((prev) => mergeRuns(prev, updated))
  }, [])

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider flex items-center gap-3">
            <Workflow className="w-6 h-6 text-cyan-400" />
            WORKFLOW ENGINE
          </h1>
          <p className="text-sm font-rajdhani text-dim-400 mt-1">
            Orchestrator-workers, prompt-chaining &amp; plan-act-reflect pipelines running on BARQ's skill registry
          </p>
        </div>
        <button
          onClick={() => { setLoading(true); void fetchAll() }}
          className="btn-ghost-cyan text-xs flex items-center gap-1.5"
          title="Refresh workflows and runs"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </motion.div>

      {error && (
        <div className="mt-3 flex items-center gap-2 text-xs font-exo text-red-400 bg-red-500/10 rounded-lg px-3 py-2">
          <XCircle className="w-3 h-3 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-5">
        <StatCard icon={Boxes} label="Registered Workflows" value={workflows.length} accent="text-cyan-300" />
        <StatCard icon={ListChecks} label="Total Steps" value={totalSteps} accent="text-purple-300" />
        <StatCard icon={Activity} label="Running Now" value={activeCount} accent={activeCount > 0 ? 'text-amber-300' : 'text-dim-400'} pulse={activeCount > 0} />
        <StatCard icon={CheckCircle} label="Completed Runs" value={completedCount} accent="text-emerald-300" />
      </div>

      {/* Workflow cards */}
      <div className="mt-6">
        <SectionTitle icon={Layers} title="Registered Workflows" hint={`${workflows.length} pipeline(s)`} />
        {loading ? (
          <div className="glass-card flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-dim-400" />
          </div>
        ) : workflows.length === 0 ? (
          <div className="glass-card text-center py-10">
            <Workflow className="w-8 h-8 text-dim-500 mx-auto mb-2" />
            <p className="text-xs font-exo text-dim-400">No workflows registered yet. Seed workflows load on backend startup.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {workflows.map((wf) => (
              <WorkflowCard
                key={wf.name}
                workflow={wf}
                onRun={async (context) => {
                  const resp = await api<{ status: string; run_id: string }>(
                    `/agent/workflows/${wf.name}/run`,
                    { context, background: true },
                  )
                  if (resp?.run_id) {
                    setRuns((prev) => [
                      {
                        run_id: resp.run_id,
                        workflow: wf.name,
                        status: 'queued',
                        started_at: Date.now() / 1000,
                      },
                      ...prev.slice(0, 24),
                    ])
                  }
                  return resp
                }}
              />
            ))}
          </div>
        )}
      </div>

      {/* Live runs */}
      <div className="mt-6">
        <SectionTitle icon={Activity} title="Recent Runs" hint="live progress · auto-refreshing" />
        <RunsPanel runs={runs} onRefresh={handleRunsRefresh} />
      </div>

      {/* Saved checkpoints */}
      <div className="mt-6">
        <SectionTitle icon={Save} title="Saved Checkpoints" hint="resume interrupted agent runs" />
        <CheckpointsPanel checkpoints={checkpoints} onRefresh={fetchAll} />
      </div>

      {/* Agentic modules (W4–W7) */}
      <div className="mt-6">
        <SectionTitle icon={Sparkles} title="Agentic Modules" hint="one-shot workflows" />
        <AgenticModules />
      </div>
    </div>
  )
}

// ─── Stat card ────────────────────────────────────────────────────────────────

function StatCard({ icon: Icon, label, value, accent, pulse }: {
  icon: typeof Boxes
  label: string
  value: number
  accent: string
  pulse?: boolean
}): JSX.Element {
  return (
    <div className="glass-card flex items-center gap-3">
      <div className={`w-9 h-9 rounded-lg bg-void-700/50 border border-cyan-500/10 flex items-center justify-center ${pulse ? 'animate-pulse' : ''}`}>
        <Icon className={`w-4 h-4 ${accent}`} />
      </div>
      <div>
        <p className="text-2xl font-orbitron font-bold text-ghost leading-none">{value}</p>
        <p className="text-hud text-[10px] font-rajdhani font-semibold text-dim-400 mt-1 tracking-wide uppercase">{label}</p>
      </div>
    </div>
  )
}

// ─── Section title ─────────────────────────────────────────────────────────────

function SectionTitle({ icon: Icon, title, hint }: {
  icon: typeof Layers
  title: string
  hint?: string
}): JSX.Element {
  return (
    <div className="flex items-center justify-between mb-3">
      <div className="flex items-center gap-2">
        <Icon className="w-5 h-5 text-holographic" />
        <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">{title}</h3>
      </div>
      {hint && <span className="text-hud text-dim-400 text-xs">{hint}</span>}
    </div>
  )
}

// ─── Workflow card ────────────────────────────────────────────────────────────

function WorkflowCard({ workflow, onRun }: {
  workflow: WorkflowDef
  onRun: (context: Record<string, unknown>) => Promise<{ status?: string; run_id?: string } | undefined>
}): JSX.Element {
  const [expanded, setExpanded] = useState(false)
  const [contextText, setContextText] = useState('{\n  \n}')
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState('')
  const [runId, setRunId] = useState('')

  const totalSteps = workflow.steps.length
  const parallelSteps = workflow.steps.filter((s) => (s.parallel_with ?? []).length > 0).length
  const isCron = workflow.trigger === 'cron'

  const handleRun = useCallback(async () => {
    setRunError('')
    setRunId('')
    let context: Record<string, unknown> = {}
    try {
      context = contextText.trim() ? JSON.parse(contextText) : {}
    } catch {
      setRunError('Context must be valid JSON (use {} for none).')
      return
    }
    setRunning(true)
    try {
      const resp = await onRun(context)
      if (resp?.run_id) {
        setRunId(resp.run_id)
      } else {
        setRunError('Backend did not return a run id.')
      }
    } catch (e) {
      setRunError(String(e))
    }
    setRunning(false)
  }, [contextText, onRun])

  return (
    <div className="glass-card flex flex-col">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-cyan-500/8 border border-cyan-500/15 flex items-center justify-center shrink-0">
            <Route className="w-4 h-4 text-cyan-300" />
          </div>
          <div className="min-w-0">
            <h4 className="text-sm font-rajdhani font-bold text-ghost truncate font-mono">{workflow.name}</h4>
            <p className="text-xs font-exo text-dim-400 line-clamp-2">{workflow.description || 'No description'}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {isCron && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border border-purple-500/20 bg-purple-500/10 text-hud text-[10px] text-purple-300">
              <CalendarClock className="w-2.5 h-2.5" />
              {workflow.cron || 'cron'}
            </span>
          )}
          <button
            onClick={() => setExpanded((v) => !v)}
            className="p-1.5 rounded-lg text-dim-400 hover:text-cyan-300 hover:bg-white/5 transition-colors"
            title={expanded ? 'Collapse' : 'Expand steps'}
          >
            {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Step count chips */}
      <div className="flex items-center gap-2 mt-3">
        <span className="text-hud text-[10px] px-1.5 py-0.5 rounded-full border border-white/10 bg-void-700/40 text-dim-300">
          {totalSteps} step{totalSteps !== 1 ? 's' : ''}
        </span>
        {parallelSteps > 0 && (
          <span className="text-hud text-[10px] px-1.5 py-0.5 rounded-full border border-purple-500/20 bg-purple-500/8 text-purple-300">
            {parallelSteps} parallel
          </span>
        )}
        <span className={`text-hud text-[10px] px-1.5 py-0.5 rounded-full border ${isCron ? 'border-purple-500/20 bg-purple-500/10 text-purple-300' : 'border-cyan-500/15 bg-cyan-500/8 text-cyan-300'}`}>
          {workflow.trigger}
        </span>
      </div>

      {/* Steps flow preview (when expanded) */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden"
          >
            <div className="mt-3 space-y-1 border-t border-white/5 pt-3">
              {workflow.steps.map((step, i) => (
                <div key={step.id} className="flex items-center gap-2">
                  <div className="flex flex-col items-center">
                    <span className="w-5 h-5 rounded-full bg-void-700/60 border border-cyan-500/15 flex items-center justify-center text-hud text-[9px] text-cyan-300 font-mono">
                      {i + 1}
                    </span>
                    {i < workflow.steps.length - 1 && <span className="w-px h-2 bg-cyan-500/20" />}
                  </div>
                  <div className="flex-1 flex items-center gap-1.5 min-w-0 py-0.5">
                    <span className="text-xs font-rajdhani font-semibold text-ghost">{step.id}</span>
                    {(step.parallel_with ?? []).length > 0 && (
                      <span className="text-hud text-[9px] px-1 py-px rounded border border-purple-500/20 text-purple-300">∥</span>
                    )}
                    <span className="text-hud text-[10px] text-dim-500 font-mono truncate flex-1">
                      {step.skill}
                      {step.params ? Object.entries(step.params).map(([k, v]) => `${k}=${String(v)}`).join(' ') : ''}
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {/* Context JSON input */}
            <div className="mt-3">
              <label className="text-hud text-[10px] text-dim-400 font-semibold uppercase tracking-wide block mb-1">
                Run context (JSON) — ${'{context.*}'} placeholders
              </label>
              <textarea
                value={contextText}
                onChange={(e) => setContextText(e.target.value)}
                rows={3}
                spellCheck={false}
                className="w-full bg-void-700/50 border border-cyan-500/10 rounded-lg px-2.5 py-2 text-xs font-mono text-ghost focus:outline-none focus:border-cyan-500/30 resize-y"
              />
              {runError && (
                <p className="mt-1.5 flex items-center gap-1.5 text-xs font-exo text-red-400">
                  <XCircle className="w-3 h-3" /> {runError}
                </p>
              )}
              {runId && (
                <p className="mt-1.5 flex items-center gap-1.5 text-xs font-exo text-cyan-300">
                  <Activity className="w-3 h-3 animate-pulse" /> Queued as {runId} — see Recent Runs below.
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Run button */}
      <div className="mt-3 pt-3 border-t border-white/5 flex items-center justify-between">
        <span className="text-hud text-[10px] text-dim-500 font-mono">timeout {workflow.timeout_seconds ?? 600}s</span>
        <button
          onClick={() => void handleRun()}
          disabled={running}
          className="btn-cyan text-xs flex items-center gap-1.5"
        >
          {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
          {running ? 'Launching…' : 'Run'}
        </button>
      </div>
    </div>
  )
}

// ─── Runs panel (live polling) ────────────────────────────────────────────────

type StreamMode = 'live' | 'connecting' | 'polling'

function RunsPanel({ runs, onRefresh }: {
  runs: RunState[]
  onRefresh: (updated: RunState[]) => void
}): JSX.Element {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const mountedRef = useRef(true)
  const [streamMode, setStreamMode] = useState<StreamMode>('connecting')

  const activeRuns = runs.filter((r) => r.status === 'queued' || r.status === 'running')
  // Stable key — only re-arm the stream when the set of active runs changes
  const activeKey = activeRuns.map((r) => r.run_id).sort().join(',')

  // ── WebSocket live stream (primary) ─────────────────────────────────
  // The backend pushes a full run snapshot on every step transition
  // (running → completed/failed), so updates arrive instantly. The socket
  // is keyed on whether ANY run is active (0 ↔ non-zero) so it persists
  // across individual run transitions instead of dropping mid-burst.
  // HTTP polling below is only a fallback when the WS cannot connect.
  const hasActive = activeRuns.length > 0
  useEffect(() => {
    if (!hasActive) return
    mountedRef.current = true
    let ws: WebSocket | null = null
    let closed = false
    let retries = 0

    const connect = async (): Promise<void> => {
      if (!mountedRef.current || closed) return
      setStreamMode((prev) => (prev === 'live' ? prev : 'connecting'))
      try {
        const config = await getBackendConfig()
        ws = new WebSocket(`${config.wsUrl}/agent/workflows/ws`)
        ws.onopen = () => {
          retries = 0
          if (mountedRef.current) setStreamMode('live')
        }
        ws.onmessage = (ev) => {
          if (!mountedRef.current) return
          try {
            const msg = JSON.parse(ev.data as string) as { type?: string; run?: RunState }
            if (msg.type === 'run' && msg.run) onRefresh([msg.run])
          } catch {
            // ignore malformed frames
          }
        }
        ws.onclose = () => {
          if (!mountedRef.current || closed) return
          retries += 1
          if (retries >= 3) {
            setStreamMode('polling') // fall back to HTTP polling
          } else {
            const delay = Math.min(800 * retries, 3000)
            setTimeout(() => void connect(), delay)
          }
        }
        ws.onerror = () => { ws?.close() }
      } catch {
        setStreamMode('polling')
      }
    }

    void connect()

    return () => {
      closed = true
      mountedRef.current = false
      ws?.close()
    }
  }, [hasActive, onRefresh])

  // ── HTTP polling fallback (only when WebSocket is unavailable) ──────
  const pollActive = useCallback(async (ids: string[]) => {
    if (ids.length === 0) return
    const results = await Promise.allSettled(
      ids.map((id) => api<RunState>(`/agent/workflows/runs/${encodeURIComponent(id)}`)),
    )
    if (!mountedRef.current) return
    const updates: RunState[] = []
    results.forEach((res) => {
      if (res.status === 'fulfilled' && res.value) updates.push(res.value)
    })
    if (updates.length > 0) onRefresh(updates)
  }, [onRefresh])

  useEffect(() => {
    if (streamMode !== 'polling') return
    const ids = activeKey ? activeKey.split(',').filter(Boolean) : []
    if (ids.length === 0) return
    void pollActive(ids)
    const timer = setInterval(() => void pollActive(ids), 1500)
    return () => clearInterval(timer)
  }, [streamMode, activeKey, pollActive])

  if (runs.length === 0) {
    return (
      <div className="glass-card text-center py-10">
        <Activity className="w-8 h-8 text-dim-500 mx-auto mb-2" />
        <p className="text-xs font-exo text-dim-400">No runs yet — hit Run on a workflow above.</p>
      </div>
    )
  }

  return (
    <div className="glass-card p-2 space-y-1.5">
      {activeRuns.length > 0 && (
        <div className="flex items-center justify-between px-3 pt-1.5 pb-0.5">
          <span className={`text-hud text-[9px] font-semibold uppercase tracking-wide flex items-center gap-1.5 ${streamMode === 'live' ? 'text-emerald-300' : streamMode === 'connecting' ? 'text-amber-300' : 'text-dim-400'}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${streamMode === 'live' ? 'bg-emerald-400 animate-pulse' : streamMode === 'connecting' ? 'bg-amber-400 animate-pulse' : 'bg-dim-500'}`} />
            {streamMode === 'live' ? 'Live · WebSocket' : streamMode === 'connecting' ? 'Connecting…' : 'Fallback · 1.5s poll'}
          </span>
        </div>
      )}
      {runs.slice(0, 8).map((run) => {
        const isActive = run.status === 'queued' || run.status === 'running'
        const isOpen = expanded[run.run_id] || isActive
        const steps = run.results ?? []
        const elapsed = run.elapsed_seconds
        return (
          <div key={run.run_id} className={`rounded-lg border transition-colors ${isActive ? 'border-cyan-500/20 bg-cyan-500/5' : 'border-white/5 bg-void-700/25'}`}>
            <button
              onClick={() => setExpanded((prev) => ({ ...prev, [run.run_id]: !prev[run.run_id] }))}
              className="w-full flex items-center gap-3 px-3 py-2.5 text-left"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-rajdhani font-semibold text-ghost font-mono">{run.workflow}</span>
                  <StatusBadge status={run.status} />
                </div>
                <p className="text-hud text-[10px] text-dim-500 font-mono mt-0.5">
                  {run.run_id}
                  {elapsed !== undefined && ` · ${elapsed}s`}
                  {run.step_results && Object.keys(run.step_results).length > 0 && ` · ${Object.keys(run.step_results).length} step result(s)`}
                </p>
                {run.error && <p className="text-xs font-exo text-red-400/80 mt-1 line-clamp-2">{run.error}</p>}
              </div>
              {steps.length > 0 && (
                <div className="flex items-center gap-1 shrink-0">
                  {steps.map((s) => (
                    <span
                      key={s.id}
                      className={`w-2 h-2 rounded-full ${s.status === 'completed' ? 'bg-emerald-400' : s.status === 'failed' ? 'bg-red-400' : 'bg-cyan-400 animate-pulse'}`}
                      title={`${s.id}: ${s.status}`}
                    />
                  ))}
                </div>
              )}
              {isOpen ? <ChevronDown className="w-3.5 h-3.5 text-dim-400 shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-dim-400 shrink-0" />}
            </button>

            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.18 }}
                  className="overflow-hidden"
                >
                  <div className="px-3 pb-3 space-y-1 border-t border-white/5 pt-2">
                    {steps.length === 0 ? (
                      <p className="text-xs font-exo text-dim-500 py-2">
                        {run.status === 'queued' ? 'Waiting for scheduler…' : 'Step progress not yet available.'}
                      </p>
                    ) : steps.map((s) => (
                      <div key={s.id} className="flex items-start gap-2 py-1">
                        {s.status === 'completed' ? (
                          <CheckCircle className="w-3.5 h-3.5 text-emerald-400 mt-0.5 shrink-0" />
                        ) : s.status === 'failed' ? (
                          <XCircle className="w-3.5 h-3.5 text-red-400 mt-0.5 shrink-0" />
                        ) : (
                          <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin mt-0.5 shrink-0" />
                        )}
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-rajdhani font-semibold text-ghost">{s.id}</span>
                            <span className="text-hud text-[10px] text-dim-500 font-mono">{s.skill}</span>
                            <span className={`text-hud text-[9px] ${s.status === 'completed' ? 'text-emerald-400/80' : s.status === 'failed' ? 'text-red-400/80' : 'text-cyan-300/80'}`}>
                              {s.status}
                            </span>
                          </div>
                          {s.result_preview && (
                            <p className="text-xs font-exo text-dim-400 mt-0.5 line-clamp-2 font-mono">{s.result_preview}</p>
                          )}
                          {s.error && <p className="text-xs font-exo text-red-400/70 mt-0.5 line-clamp-3">{s.error}</p>}
                        </div>
                      </div>
                    ))}
                    {run.error && !(run.results ?? []).some((s) => s.status === 'failed') && (
                      <p className="text-xs font-exo text-red-400/80 mt-1">{run.error}</p>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )
      })}
    </div>
  )
}

// ─── Checkpoints panel ────────────────────────────────────────────────────────

function CheckpointsPanel({ checkpoints, onRefresh }: {
  checkpoints: CheckpointRow[]
  onRefresh: () => void
}): JSX.Element {
  const [resuming, setResuming] = useState<Record<string, boolean>>({})
  const [results, setResults] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})

  const handleResume = useCallback(async (key: string) => {
    setErrors((prev) => ({ ...prev, [key]: '' }))
    setResults((prev) => ({ ...prev, [key]: '' }))
    setResuming((prev) => ({ ...prev, [key]: true }))
    try {
      const resp = await api<Record<string, unknown>>(
        `/agent/checkpoints/${encodeURIComponent(key)}/resume`,
        {}, // empty body → forces the bridge to send a POST
      )
      if (resp) {
        setResults((prev) => ({ ...prev, [key]: JSON.stringify(resp, null, 2) }))
        // Resume may flip the checkpoint to complete — refresh the list
        onRefresh()
      } else {
        setErrors((prev) => ({ ...prev, [key]: 'Backend did not return a result.' }))
      }
    } catch (e) {
      setErrors((prev) => ({ ...prev, [key]: String(e) }))
    }
    setResuming((prev) => ({ ...prev, [key]: false }))
  }, [onRefresh])

  if (checkpoints.length === 0) {
    return (
      <div className="glass-card text-center py-10">
        <Database className="w-8 h-8 text-dim-500 mx-auto mb-2" />
        <p className="text-xs font-exo text-dim-400">No checkpoints yet — long agent runs persist their progress here automatically.</p>
      </div>
    )
  }

  return (
    <div className="glass-card p-2 space-y-1.5">
      {checkpoints.map((cp) => {
        const isResuming = resuming[cp.checkpoint_key]
        const result = results[cp.checkpoint_key]
        const err = errors[cp.checkpoint_key]
        const isAgent = cp.agent_type !== 'workflow'
        const progress = cp.total_steps && cp.total_steps > 0
          ? `${cp.completed_steps ?? 0}/${cp.total_steps}`
          : null
        const isComplete = cp.status === 'complete'
        return (
          <div
            key={cp.checkpoint_key}
            className={`rounded-lg border p-3 transition-colors ${isComplete ? 'border-emerald-500/15 bg-emerald-500/5' : 'border-cyan-500/15 bg-void-700/25'}`}
          >
            <div className="flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-xs font-rajdhani font-semibold text-ghost truncate">
                  {cp.goal || cp.checkpoint_key}
                </p>
                <div className="flex items-center gap-2 mt-1 flex-wrap">
                  <span className={`text-hud text-[9px] px-1.5 py-px rounded-full border font-semibold ${isAgent ? 'border-cyan-500/20 bg-cyan-500/10 text-cyan-300' : 'border-purple-500/20 bg-purple-500/10 text-purple-300'}`}>
                    {cp.agent_type}
                  </span>
                  <span className={`text-hud text-[9px] px-1.5 py-px rounded-full border font-semibold ${isComplete ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300' : 'border-amber-500/20 bg-amber-500/10 text-amber-300'}`}>
                    {isComplete ? 'complete' : 'active'}
                  </span>
                  {progress && (
                    <span className="text-hud text-[9px] px-1.5 py-px rounded-full border border-white/10 bg-void-700/40 text-dim-300">
                      {progress} steps
                    </span>
                  )}
                  <span className="text-hud text-[9px] text-dim-500 font-mono truncate">{cp.checkpoint_key}</span>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {cp.updated_at && (
                  <span className="text-hud text-[9px] text-dim-500 hidden sm:inline">{cp.updated_at}</span>
                )}
                <button
                  onClick={() => void handleResume(cp.checkpoint_key)}
                  disabled={isResuming || isComplete}
                  className={`${isComplete ? 'text-xs opacity-50 cursor-not-allowed bg-void-700/40 border border-white/10 rounded-lg px-3 py-1.5 text-dim-400' : 'btn-cyan text-xs'} flex items-center gap-1.5`}
                  title={isComplete ? 'Checkpoint already completed' : 'Resume this agent run from its last saved step'}
                >
                  {isResuming ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />}
                  {isResuming ? 'Resuming…' : isComplete ? 'Done' : 'Resume'}
                </button>
              </div>
            </div>

            {err && (
              <p className="mt-2 flex items-center gap-1.5 text-xs font-exo text-red-400">
                <XCircle className="w-3 h-3 flex-shrink-0" /> {err}
              </p>
            )}
            {result && (
              <pre className="mt-2 bg-void-700/40 border border-white/5 rounded-lg px-2.5 py-2 text-[10px] font-mono text-dim-300 max-h-40 overflow-y-auto scroll-cyan whitespace-pre-wrap">
                {result}
              </pre>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ─── Agentic modules (W4–W7) ──────────────────────────────────────────────────

interface ModuleDef {
  key: string
  title: string
  icon: typeof MoonStar
  accent: string
  description: string
  fields: { key: string; label: string; placeholder: string; default: string }[]
}

const MODULES: ModuleDef[] = [
  {
    key: 'briefing',
    title: 'Morning Briefing',
    icon: MoonStar,
    accent: 'text-amber-300',
    description: 'Parallel weather, calendar, jobs & memory → LLM synthesis → desktop notification.',
    fields: [],
  },
  {
    key: 'memory',
    title: 'Conversation Memory',
    icon: PenLine,
    accent: 'text-cyan-300',
    description: 'Extract action items, facts & entities from a chat turn into long-term memory.',
    fields: [
      { key: 'user_text', label: 'User text', placeholder: "e.g. Remember that I'm launching next month", default: '' },
    ],
  },
  {
    key: 'research',
    title: 'Research → Brain',
    icon: GitBranch,
    accent: 'text-purple-300',
    description: 'Extract report triplets into the knowledge graph for retrieval.',
    fields: [
      { key: 'topic', label: 'Topic', placeholder: 'Quantum error correction', default: '' },
      { key: 'report', label: 'Report text', placeholder: 'Paste the research report…', default: '' },
    ],
  },
  {
    key: 'browser',
    title: 'Browser Task',
    icon: Globe,
    accent: 'text-sky-300',
    description: 'Queue an agentic multi-step browser task — BARQ plans, executes and verifies real Playwright steps on your browser, then reports back.',
    fields: [
      { key: 'goal', label: 'Goal', placeholder: 'e.g. Open LinkedIn and search for senior Python developer jobs in Berlin', default: '' },
    ],
  },
  {
    key: 'critic',
    title: 'Content Critic',
    icon: Zap,
    accent: 'text-emerald-300',
    description: 'Critic → revise loop until your social draft passes the quality gate.',
    fields: [
      { key: 'draft', label: 'Draft', placeholder: 'Paste your draft post…', default: '' },
      { key: 'topic', label: 'Topic (optional)', placeholder: '', default: '' },
      { key: 'platform', label: 'Platform', placeholder: 'linkedin_post', default: 'linkedin_post' },
    ],
  },
  {
    key: 'review',
    title: 'Weekly Review',
    icon: CalendarClock,
    accent: 'text-blue-300',
    description: 'Analytics, skill success rates & memory → weekly summary report with recommendations.',
    fields: [],
  },
]

const MODULE_ENDPOINTS: Record<string, string> = {
  briefing: '/agent/briefing/run',
  memory: '/agent/memory/conversation',
  research: '/agent/research/to-brain',
  critic: '/agent/content/critic',
  review: '/agent/review/weekly',
  browser: '/agent/queue',
}

function AgenticModules(): JSX.Element {
  const [results, setResults] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [running, setRunning] = useState<Record<string, boolean>>({})

  const runModule = useCallback(async (mod: ModuleDef) => {
    setErrors((prev) => ({ ...prev, [mod.key]: '' }))
    setResults((prev) => ({ ...prev, [mod.key]: '' }))

    const inputs = mod.fields.reduce<Record<string, string>>((acc, f) => {
      const el = document.getElementById(`mod-${mod.key}-${f.key}`) as HTMLInputElement | HTMLTextAreaElement | null
      acc[f.key] = el?.value ?? f.default
      return acc
    }, {})

    // Validate required-looking fields
    const missing = mod.fields.filter((f) => f.placeholder && !inputs[f.key].trim())
    if (missing.length > 0) {
      setErrors((prev) => ({ ...prev, [mod.key]: `Missing: ${missing.map((m) => m.label).join(', ')}` }))
      return
    }

    setRunning((prev) => ({ ...prev, [mod.key]: true }))
    try {
      const body: Record<string, unknown> = { ...inputs }
      // briefing takes no body — pass {} to force a POST
      if (mod.key === 'briefing') Object.keys(body).forEach((k) => delete body[k])
      const resp = await api<Record<string, unknown>>(MODULE_ENDPOINTS[mod.key], body)
      setResults((prev) => ({ ...prev, [mod.key]: JSON.stringify(resp ?? {}, null, 2) }))
    } catch (e) {
      setErrors((prev) => ({ ...prev, [mod.key]: String(e) }))
    }
    setRunning((prev) => ({ ...prev, [mod.key]: false }))
  }, [])

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {MODULES.map((mod) => {
        const Icon = mod.icon
        const isRunning = running[mod.key]
        const result = results[mod.key]
        const err = errors[mod.key]
        return (
          <div key={mod.key} className="glass-card flex flex-col">
            <div className="flex items-start gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-void-700/50 border border-cyan-500/10 flex items-center justify-center shrink-0">
                <Icon className={`w-4 h-4 ${mod.accent}`} />
              </div>
              <div>
                <h4 className="text-sm font-rajdhani font-bold text-ghost">{mod.title}</h4>
                <p className="text-xs font-exo text-dim-400 mt-0.5">{mod.description}</p>
              </div>
            </div>

            <div className="mt-3 space-y-2 flex-1">
              {mod.fields.map((f) =>
                f.key === 'draft' || f.key === 'report' ? (
                  <textarea
                    key={f.key}
                    id={`mod-${mod.key}-${f.key}`}
                    rows={2}
                    placeholder={f.placeholder}
                    defaultValue={f.default}
                    spellCheck={false}
                    className="w-full bg-void-700/50 border border-cyan-500/10 rounded-lg px-2.5 py-2 text-xs text-ghost placeholder:text-dim-600 focus:outline-none focus:border-cyan-500/30 resize-y"
                  />
                ) : (
                  <input
                    key={f.key}
                    id={`mod-${mod.key}-${f.key}`}
                    type="text"
                    placeholder={f.placeholder}
                    defaultValue={f.default}
                    spellCheck={false}
                    className="w-full bg-void-700/50 border border-cyan-500/10 rounded-lg px-2.5 py-2 text-xs text-ghost placeholder:text-dim-600 focus:outline-none focus:border-cyan-500/30"
                  />
                ),
              )}
            </div>

            {err && (
              <p className="mt-2 flex items-center gap-1.5 text-xs font-exo text-red-400">
                <XCircle className="w-3 h-3 flex-shrink-0" /> {err}
              </p>
            )}
            {result && (
              <pre className="mt-2 bg-void-700/40 border border-white/5 rounded-lg px-2.5 py-2 text-[10px] font-mono text-dim-300 max-h-40 overflow-y-auto scroll-cyan whitespace-pre-wrap">
                {result}
              </pre>
            )}

            <div className="mt-3 pt-3 border-t border-white/5 flex items-center justify-between">
              <span className="text-hud text-[10px] text-dim-500 font-mono">{mod.key}</span>
              <button
                onClick={() => void runModule(mod)}
                disabled={isRunning}
                className="btn-cyan text-xs flex items-center gap-1.5"
              >
                {isRunning ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
                {isRunning ? 'Running…' : 'Run'}
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
