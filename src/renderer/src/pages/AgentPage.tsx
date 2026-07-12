import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../utils/api'
import {
  BrainCircuit, Cpu, Eye, ListTodo, Send, Loader2, CheckCircle, XCircle,
  Trash2, Camera, Monitor, Maximize, Search, Layers, Box,
  AlertTriangle, Terminal, Clock, Download, Zap, BarChart3,
  Globe, FileText, Settings2,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

// ─── Types ────────────────────────────────────────────────────────────────────

interface TaskItem {
  task_id: string
  goal: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  result?: string
  error?: string
}

interface MemoryCategory {
  [key: string]: { value: string; updated?: string } | MemoryCategory
}

interface MemoryData {
  identity: MemoryCategory
  preferences: MemoryCategory
  projects: MemoryCategory
  relationships: MemoryCategory
  wishes: MemoryCategory
  notes: MemoryCategory
}

interface VisionResult {
  text?: string
  description?: string
  status?: string
}

interface Capabilities {
  screen_capture: boolean
  webcam: boolean
  gemini_api: boolean
  gemini_live: boolean
}

// ─── Tab Config ───────────────────────────────────────────────────────────────

type TabKey = 'tasks' | 'memory' | 'vision' | 'plans'

interface TabDef {
  key: TabKey
  label: string
  icon: typeof Cpu
}

const TABS: TabDef[] = [
  { key: 'tasks', label: 'Task Queue', icon: ListTodo },
  { key: 'memory', label: 'Memory', icon: Layers },
  { key: 'vision', label: 'Vision', icon: Eye },
  { key: 'plans', label: 'Planner', icon: BrainCircuit },
]

// ═══════════════════════════════════════════════════════════════════════════════
// AgentPage
// ═══════════════════════════════════════════════════════════════════════════════

export function AgentPage(): JSX.Element {
  const [activeTab, setActiveTab] = useState<TabKey>('tasks')

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider flex items-center gap-3">
          <Cpu className="w-6 h-6 text-cyan-400" />
          AGENT SYSTEM
        </h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">
          Autonomous task execution, persistent memory, and visual awareness
        </p>
      </motion.div>

      {/* Tab Navigation */}
      <div className="flex flex-wrap gap-1 mt-4 mb-6 border-b border-cyan-500/10 pb-2">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-t-lg text-xs font-rajdhani font-semibold transition-all
              ${activeTab === tab.key
                ? 'text-cyan-300 bg-cyan-500/8 border-b-2 border-cyan-400'
                : 'text-dim-400 hover:text-ghost hover:bg-void-600/30'
              }`}
          >
            <tab.icon className="w-3.5 h-3.5" />
            {tab.label}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.15 }}
        >
          {activeTab === 'tasks' && <TaskQueuePanel />}
          {activeTab === 'memory' && <MemoryViewerPanel />}
          {activeTab === 'vision' && <VisionPanel />}
          {activeTab === 'plans' && <PlannerPanel />}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1. Task Queue Panel
// ═══════════════════════════════════════════════════════════════════════════════

function TaskQueuePanel(): JSX.Element {
  const [tasks, setTasks] = useState<TaskItem[]>([])
  const [goal, setGoal] = useState('')
  const [priority, setPriority] = useState<'low' | 'normal' | 'high'>('normal')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchTasks = useCallback(async () => {
    try {
      const resp = await api<{ tasks?: TaskItem[] }>('/agent/queue')
      if (resp) setTasks(resp.tasks ?? [])
    } catch { /* ignore */    }
    setLoading(false)
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchTasks()
    pollRef.current = setInterval(() => void fetchTasks(), 3000)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [fetchTasks])

  const submitGoal = useCallback(async () => {
    if (!goal.trim()) return
    setSubmitting(true)
    setError('')
    try {
      await api('/agent/execute', { goal: goal.trim(), priority })
      setGoal('')
      await fetchTasks()
    } catch (e) {
      setError(String(e))
    }
    setSubmitting(false)
  }, [goal, priority, fetchTasks])

  const cancelTask = useCallback(async (taskId: string) => {
    try {
      await api(`/agent/queue/${taskId}/cancel`, {})
      await fetchTasks()
    } catch { /* ignore */ }
  }, [fetchTasks])

  const statusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
      case 'running': return <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
      case 'pending': return <Clock className="w-3.5 h-3.5 text-yellow-400" />
      case 'failed': return <XCircle className="w-3.5 h-3.5 text-red-400" />
      case 'cancelled': return <XCircle className="w-3.5 h-3.5 text-dim-400" />
      default: return <Clock className="w-3.5 h-3.5 text-dim-400" />
    }
  }

  const statusColors: Record<string, string> = {
    completed: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20',
    running: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/20',
    pending: 'bg-yellow-500/10 text-yellow-300 border-yellow-500/20',
    failed: 'bg-red-500/10 text-red-300 border-red-500/20',
    cancelled: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
  }

  return (
    <div className="space-y-4">
      {/* Submit Goal */}
      <div className="glass-card">
        <div className="flex items-center gap-2 mb-4">
          <Zap className="w-5 h-5 text-cyan-300" />
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Execute Goal</h3>
        </div>

        {error && (
          <div className="mb-3 flex items-center gap-2 text-xs font-exo text-red-400 bg-red-500/10 rounded-lg px-3 py-2">
            <AlertTriangle className="w-3 h-3 flex-shrink-0" />
            {error}
          </div>
        )}

        <div className="flex gap-2">
          <input
            type="text"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submitGoal()}
            placeholder="e.g., research quantum computing and save to a file"
            className="input-cyan flex-1 text-sm"
          />
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value as 'low' | 'normal' | 'high')}
            className="bg-void-700 rounded-lg px-2 py-1 text-xs text-ghost border border-cyan-500/10"
          >
            <option value="low">Low</option>
            <option value="normal">Normal</option>
            <option value="high">High</option>
          </select>
          <button onClick={submitGoal} disabled={submitting || !goal.trim()} className="btn-cyan text-sm flex items-center gap-1.5">
            {submitting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
            Execute
          </button>
        </div>
        <p className="text-hud text-dim-500 mt-2 text-xs">
          The agent will plan, execute, and recover from errors automatically using BARQ's tool system
        </p>
      </div>

      {/* Task List */}
      <div className="glass-card">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <ListTodo className="w-5 h-5 text-holographic" />
            <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Task History</h3>
          </div>
          <span className="text-hud text-dim-400 text-xs">{tasks.length} tasks</span>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-5 h-5 animate-spin text-dim-400" />
          </div>
        ) : tasks.length === 0 ? (
          <div className="text-center py-8">
            <ListTodo className="w-8 h-8 text-dim-500 mx-auto mb-2" />
            <p className="text-xs font-exo text-dim-400">No tasks yet. Submit a goal above to get started.</p>
          </div>
        ) : (
          <div className="space-y-2 max-h-96 overflow-y-auto scroll-cyan">
            {tasks.map((task) => (
              <div
                key={task.task_id}
                className="flex items-start gap-3 bg-void-700/30 rounded-lg p-3 border border-cyan-500/5 hover:border-cyan-500/15 transition-colors"
              >
                <div className="mt-0.5">{statusIcon(task.status)}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-rajdhani font-semibold text-ghost truncate">{task.goal}</span>
                    <span className={`text-hud text-[10px] px-1.5 py-0.5 rounded-full border ${statusColors[task.status] || ''}`}>
                      {task.status}
                    </span>
                  </div>
                  <p className="text-hud text-dim-500 text-xs mt-0.5 font-mono">ID: {task.task_id}</p>
                  {task.result && (
                    <p className="text-xs font-exo text-dim-300 mt-1 line-clamp-2">{task.result}</p>
                  )}
                  {task.error && (
                    <p className="text-xs font-exo text-red-400/70 mt-1 line-clamp-2">{task.error}</p>
                  )}
                </div>
                {task.status === 'pending' || task.status === 'running' ? (
                  <button
                    onClick={() => cancelTask(task.task_id)}
                    className="p-1.5 rounded text-dim-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                    title="Cancel task"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 2. Memory Viewer Panel
// ═══════════════════════════════════════════════════════════════════════════════

const CATEGORY_LABELS: Record<string, string> = {
  identity: 'Identity',
  preferences: 'Preferences',
  projects: 'Projects',
  relationships: 'Relationships',
  wishes: 'Wishes',
  notes: 'Notes',
}

const CATEGORY_COLORS: Record<string, string> = {
  identity: 'text-cyan-300 border-cyan-500/20 bg-cyan-500/8',
  preferences: 'text-purple-300 border-purple-500/20 bg-purple-500/8',
  projects: 'text-emerald-300 border-emerald-500/20 bg-emerald-500/8',
  relationships: 'text-amber-300 border-amber-500/20 bg-amber-500/8',
  wishes: 'text-pink-300 border-pink-500/20 bg-pink-500/8',
  notes: 'text-zinc-300 border-zinc-500/20 bg-zinc-500/8',
}

function MemoryViewerPanel(): JSX.Element {
  const [memory, setMemory] = useState<MemoryData | null>(null)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')
  const [newCategory, setNewCategory] = useState('notes')
  const [saving, setSaving] = useState(false)

  const fetchMemory = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await api<{ memory?: MemoryData }>('/agent/memory')
      if (resp) setMemory(resp.memory ?? null)
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { void fetchMemory() }, [fetchMemory])

  const saveMemory = useCallback(async () => {
    if (!newKey.trim() || !newValue.trim()) return
    setSaving(true)
    try {
      await api('/agent/memory', { key: newKey.trim(), value: newValue.trim(), category: newCategory })
      setNewKey('')
      setNewValue('')
      await fetchMemory()
    } catch { /* ignore */ }
    setSaving(false)
  }, [newKey, newValue, newCategory, fetchMemory])

  const deleteMemory = useCallback(async (cat: string, key: string) => {
    try {
      await api(`/agent/memory/${cat}/${encodeURIComponent(key)}`, { method: 'DELETE' })
      await fetchMemory()
    } catch { /* ignore */ }
  }, [fetchMemory])

  // Flatten memory into display items with optional search filter
  const flattenMemory = (mem: MemoryData, filter = ''): { cat: string; key: string; value: string; updated?: string }[] => {
    const items: { cat: string; key: string; value: string; updated?: string }[] = []
    const q = filter.toLowerCase()
    for (const [cat, entries] of Object.entries(mem)) {
      if (typeof entries !== 'object') continue
      for (const [key, entry] of Object.entries(entries)) {
        const val = typeof entry === 'object' && entry !== null ? (entry as { value: string }).value || '' : String(entry)
        const updated = typeof entry === 'object' && entry !== null ? (entry as { updated?: string }).updated : undefined
        if (!q || key.toLowerCase().includes(q) || val.toLowerCase().includes(q) || CATEGORY_LABELS[cat].toLowerCase().includes(q)) {
          items.push({ cat, key, value: val, updated })
        }
      }
    }
    return items
  }

  const items = memory ? flattenMemory(memory, searchQuery) : []

  return (
    <div className="space-y-4">
      {/* Search + Add */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Search */}
        <div className="glass-card">
          <div className="flex items-center gap-2 mb-3">
            <Search className="w-5 h-5 text-cyan-300" />
            <h3 className="text-sm font-rajdhani font-semibold text-ghost">Search Memory</h3>
          </div>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by key, value, or category..."
            className="input-cyan text-sm w-full"
          />
          <p className="text-hud text-dim-500 text-xs mt-1.5">
            {items.length} of {memory ? flattenMemory(memory).length : 0} entries {searchQuery ? '(filtered)' : ''}
          </p>
        </div>

        {/* Add */}
        <div className="glass-card">
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-5 h-5 text-holographic" />
            <h3 className="text-sm font-rajdhani font-semibold text-ghost">Store Fact</h3>
          </div>
          <div className="flex gap-2 mb-2">
            <input
              type="text" value={newKey} onChange={(e) => setNewKey(e.target.value)}
              placeholder="Key (e.g. favorite_color)"
              className="input-cyan text-sm flex-1"
            />
            <select
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              className="bg-void-700 rounded-lg px-2 py-1 text-xs text-ghost border border-cyan-500/10"
            >
              {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
          <div className="flex gap-2">
            <input
              type="text" value={newValue} onChange={(e) => setNewValue(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && saveMemory()}
              placeholder="Value"
              className="input-cyan text-sm flex-1"
            />
            <button onClick={saveMemory} disabled={saving} className="btn-cyan text-xs flex items-center gap-1">
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
              Save
            </button>
          </div>
        </div>
      </div>

      {/* Memory Cards */}
      {loading ? (
        <div className="glass-card flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-dim-400" />
        </div>
      ) : items.length === 0 ? (
        <div className="glass-card text-center py-8">
          <BrainCircuit className="w-8 h-8 text-dim-500 mx-auto mb-2" />
          <p className="text-xs font-exo text-dim-400">No memory entries found. The agent will auto-extract facts from conversations.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {items.map((item) => (
            <div
              key={`${item.cat}-${item.key}`}
              className={`rounded-lg p-3 border ${CATEGORY_COLORS[item.cat] || 'border-zinc-500/10 bg-zinc-500/5'}`}
            >
              <div className="flex items-start justify-between mb-1">
                <div className="flex items-center gap-1.5">
                  <span className="text-hud text-[10px] font-mono uppercase tracking-wider">
                    {CATEGORY_LABELS[item.cat] || item.cat}
                  </span>
                </div>
                <button
                  onClick={() => deleteMemory(item.cat, item.key)}
                  className="p-0.5 rounded text-dim-500 hover:text-red-400 transition-colors"
                  title="Forget"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
              <p className="text-sm font-rajdhani font-semibold break-all">
                {item.key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
              </p>
              <p className="text-xs font-exo text-dim-300 mt-0.5 break-all">{item.value}</p>
              {item.updated && (
                <p className="text-hud text-[10px] text-dim-500 mt-1">{item.updated}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 3. Visual Awareness Panel
// ═══════════════════════════════════════════════════════════════════════════════

const CAPABILITY_DEFS = [
  { key: 'screen_capture' as const, label: 'Screen Capture', icon: Monitor },
  { key: 'webcam' as const, label: 'Webcam', icon: Camera },
  { key: 'gemini_api' as const, label: 'Gemini Vision', icon: Eye },
  { key: 'gemini_live' as const, label: 'Gemini Live Audio', icon: Settings2 },
]

function CapabilitiesStatus({ caps }: { caps: Capabilities | null }): JSX.Element {
  if (!caps) {
    return (
      <div className="flex items-center gap-2 text-xs font-exo text-dim-500">
        <Loader2 className="w-3 h-3 animate-spin" />
        Checking capabilities...
      </div>
    )
  }

  const installedCount = Object.values(caps).filter(Boolean).length
  const total = Object.keys(caps).length
  const allReady = installedCount === total

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-rajdhani font-semibold text-ghost">Capabilities</span>
        <span className={`text-hud text-[10px] px-1.5 py-0.5 rounded-full border ${
          allReady
            ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20'
            : 'bg-amber-500/10 text-amber-300 border-amber-500/20'
        }`}>
          {allReady ? 'All Ready' : `${installedCount}/${total} Ready`}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-1.5">
        {CAPABILITY_DEFS.map(({ key, label, icon: Icon }) => {
          const ok = caps[key]
          return (
            <div
              key={key}
              className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs font-exo transition-colors ${
                ok
                  ? 'text-dim-300 bg-emerald-500/5'
                  : 'text-dim-500 bg-void-700/30'
              }`}
            >
              <Icon className={`w-3 h-3 ${ok ? 'text-emerald-400' : 'text-dim-500'}`} />
              <span className="flex-1">{label}</span>
              {ok
                ? <CheckCircle className="w-3 h-3 text-emerald-400 flex-shrink-0" />
                : <XCircle className="w-3 h-3 text-dim-500 flex-shrink-0" />
              }
            </div>
          )
        })}
      </div>
    </div>
  )
}

function VisionPanel(): JSX.Element {
  const [prompt, setPrompt] = useState("What's on my screen? Be concise.")
  const [result, setResult] = useState<VisionResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [setupRequired, setSetupRequired] = useState(false)
  const [caps, setCaps] = useState<Capabilities | null>(null)

  // Fetch capabilities once on mount
  useEffect(() => {
    (async () => {
      try {
        const resp = await api<{ capabilities?: Capabilities }>('/vision/check')
        if (resp?.capabilities) setCaps(resp.capabilities)
      } catch { /* ignore */ }
    })()
  }, [])

  const detectApiKeyMissing = useCallback((msg: string) => {
    if (msg.toLowerCase().includes('gemini api key')) {
      setSetupRequired(true)
    }
  }, [])

  const handleResponse = useCallback((resp: unknown) => {
    if (resp && typeof resp === 'object') {
      const data = resp as Record<string, unknown>
      if (data.status === 'unavailable') {
        const msg = String(data.message || 'Vision service unavailable')
        setError(msg)
        detectApiKeyMissing(msg)
        return
      }
      setResult(data as VisionResult)
    }
  }, [detectApiKeyMissing])

  const handleError = useCallback((e: unknown) => {
    const msg = String(e)
    setError(msg)
    detectApiKeyMissing(msg)
  }, [detectApiKeyMissing])

  const analyzeScreen = useCallback(async () => {
    setLoading(true)
    setError('')
    setResult(null)
    setSetupRequired(false)
    try {
      const resp = await api<VisionResult>('/vision/screen', { prompt: prompt.trim() || "What's on my screen?" })
      handleResponse(resp)
    } catch (e) {
      handleError(e)
    }
    setLoading(false)
  }, [prompt, handleResponse, handleError])

  const analyzeCamera = useCallback(async () => {
    setLoading(true)
    setError('')
    setResult(null)
    setSetupRequired(false)
    try {
      const resp = await api<VisionResult>('/vision/camera', { prompt: prompt.trim() || "What do you see?" })
      handleResponse(resp)
    } catch (e) {
      handleError(e)
    }
    setLoading(false)
  }, [prompt, handleResponse, handleError])

  return (
    <div className="space-y-4">
      {/* Controls + Capabilities side-by-side */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Main controls */}
        <div className="lg:col-span-2 glass-card">
          <div className="flex items-center gap-2 mb-4">
            <Eye className="w-5 h-5 text-cyan-300" />
            <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Visual Analysis</h3>
          </div>

          <div className="mb-3">
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && analyzeScreen()}
              placeholder="Ask about what's on screen..."
              className="input-cyan text-sm w-full"
            />
          </div>

          <div className="flex gap-2">
            <button
              onClick={analyzeScreen}
              disabled={loading}
              className="btn-cyan text-sm flex items-center gap-1.5"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Monitor className="w-4 h-4" />}
              Analyze Screen
            </button>
            <button
              onClick={analyzeCamera}
              disabled={loading}
              className="btn-ghost-cyan text-sm flex items-center gap-1.5"
            >
              <Camera className="w-4 h-4" />
              Capture Camera
            </button>
          </div>
        </div>

        {/* Capabilities status */}
        <div className="glass-card">
          <CapabilitiesStatus caps={caps} />
        </div>
      </div>

      {/* Result */}
      {error && (
        <div className="glass-card border-red-500/20">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
            <p className="text-xs font-exo text-red-400">{error}</p>
          </div>
          {setupRequired && (
            <div className="mt-3 bg-void-800/60 rounded-lg p-3 border border-amber-500/20">
              <p className="text-xs font-exo text-amber-300 font-semibold">Setup Required</p>
              <ol className="mt-2 text-xs font-exo text-dim-300 space-y-1 list-decimal list-inside">
                <li>Get a <a className="text-cyan-400 underline" href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer">Gemini API key</a> (free)</li>
                <li>Save it to <code className="text-amber-300 bg-void-900/60 px-1 rounded">python/config/api_keys.json</code> as <code className="text-amber-300">{'{"gemini_api_key": "..."}'}</code></li>
                <li>Or set the <code className="text-amber-300">GEMINI_API_KEY</code> environment variable</li>
                <li>Restart the backend server</li>
              </ol>
            </div>
          )}
        </div>
      )}

      {loading && (
        <div className="glass-card text-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-cyan-300 mx-auto mb-2" />
          <p className="text-xs font-exo text-dim-400">Analyzing...</p>
        </div>
      )}

      {result && !loading && (
        <div className="glass-card">
          <div className="flex items-center gap-2 mb-3">
            <CheckCircle className="w-4 h-4 text-emerald-400" />
            <h4 className="text-sm font-rajdhani font-semibold text-ghost">Analysis Result</h4>
          </div>
          <p className="text-sm font-exo text-dim-200 leading-relaxed whitespace-pre-wrap">
            {result.text || result.description || result.status || 'Analysis complete.'}
          </p>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 4. Planner Panel
// ═══════════════════════════════════════════════════════════════════════════════

function PlannerPanel(): JSX.Element {
  const [goal, setGoal] = useState('')
  const [plan, setPlan] = useState<{ goal: string; steps: Array<{ step: number; tool: string; description: string; parameters: Record<string, string>; critical: boolean }> } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const generatePlan = useCallback(async () => {
    if (!goal.trim()) return
    setLoading(true)
    setError('')
    setPlan(null)
    try {
      const data = await api('/agent/plan', { goal: goal.trim() })
      if (data && typeof data === 'object') {
        setPlan(data as unknown as typeof plan)
      }
    } catch (e) {
      setError(String(e))
    }
    setLoading(false)
  }, [goal])

  const toolIcon = (tool: string) => {
    switch (tool) {
      case 'web_search': return <Search className="w-3.5 h-3.5" />
      case 'system_command': return <Terminal className="w-3.5 h-3.5" />
      case 'launch_app': return <Maximize className="w-3.5 h-3.5" />
      case 'create_file': return <Download className="w-3.5 h-3.5" />
      case 'read_file': return <FileText className="w-3.5 h-3.5" />
      case 'browse_url': return <Globe className="w-3.5 h-3.5" />
      case 'send_message': return <Send className="w-3.5 h-3.5" />
      case 'get_weather': return <Cloud className="w-3.5 h-3.5" />
      case 'check_trends': return <BarChart3 className="w-3.5 h-3.5" />
      default: return <Box className="w-3.5 h-3.5" />
    }
  }

  return (
    <div className="space-y-4">
      <div className="glass-card">
        <div className="flex items-center gap-2 mb-4">
          <BrainCircuit className="w-5 h-5 text-holographic" />
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Plan Preview</h3>
        </div>

        <p className="text-xs font-exo text-dim-400 mb-3">
          See how the agent would break down a goal before executing it. Plans use web search, file operations, system commands, and more.
        </p>

        <div className="flex gap-2">
          <input
            type="text"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && generatePlan()}
            placeholder="e.g., research RAG systems and save notes"
            className="input-cyan flex-1 text-sm"
          />
          <button onClick={generatePlan} disabled={loading || !goal.trim()} className="btn-cyan text-sm flex items-center gap-1.5">
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <BrainCircuit className="w-3.5 h-3.5" />}
            Generate Plan
          </button>
        </div>
      </div>

      {error && (
        <div className="glass-card border-red-500/20">
          <div className="flex items-center gap-2 text-xs font-exo text-red-400">
            <AlertTriangle className="w-3 h-3" />
            {error}
          </div>
        </div>
      )}

      {loading && (
        <div className="glass-card text-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-cyan-300 mx-auto mb-2" />
          <p className="text-xs font-exo text-dim-400">Generating plan...</p>
        </div>
      )}

      {plan && !loading && (
        <div className="glass-card">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">
              Plan: {plan.goal.length > 50 ? plan.goal.slice(0, 50) + '...' : plan.goal}
            </h3>
            <span className="text-hud text-[10px] text-dim-400 ml-auto">{plan.steps.length} steps</span>
          </div>

          <div className="space-y-2">
            {plan.steps.map((step) => (
              <div
                key={step.step}
                className="flex items-start gap-3 bg-void-700/30 rounded-lg p-3 border border-cyan-500/5"
              >
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold font-mono flex-shrink-0 ${
                  step.critical
                    ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-400/30'
                    : 'bg-zinc-700/40 text-dim-400 border border-zinc-600/30'
                }`}>
                  {step.step}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-ghost font-rajdhani font-semibold">{step.description}</span>
                    <span className="flex items-center gap-1 text-hud text-[10px] text-dim-400 border border-dim-500/20 rounded px-1.5 py-0.5">
                      {toolIcon(step.tool)}
                      {step.tool}
                    </span>
                    {step.critical && (
                      <span className="text-hud text-[10px] text-cyan-300">Critical</span>
                    )}
                  </div>
                  {Object.keys(step.parameters).length > 0 && (
                    <pre className="text-hud text-dim-500 text-[10px] mt-1 font-mono">
                      {JSON.stringify(step.parameters, null, 1).slice(0, 120)}
                    </pre>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Missing Icon Helper ──────────────────────────────────────────────────────

function Cloud({ className }: { className?: string }): JSX.Element {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z" />
    </svg>
  )
}
