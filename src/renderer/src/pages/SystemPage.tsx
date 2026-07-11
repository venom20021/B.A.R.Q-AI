import { useState, useCallback, useEffect } from 'react'
import {
  Monitor, Maximize, Minimize, Grid3x3, Image, Workflow,
  Loader2, CheckCircle, ExternalLink, FolderTree, Filter,
  GitBranch, Package, Terminal, MonitorUp, Undo2, Eye,
  Save, Play, Trash2, Plus, GripVertical,
  ArrowUpDown, HardDrive, LayoutGrid,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

// ─── Types ────────────────────────────────────────────────────────────────────

interface DropZoneRule {
  name: string
  description: string
  conditions: Array<{ field: string; operator: string; value: unknown }>
  action: string
  target_folder: string
  priority: number
  enabled: boolean
}

interface SortPreview {
  preview_id: string
  total_files: number
  groups: Record<string, { files: string[]; count: number }>
  preview: Array<{ file: string; file_name: string; target_folder: string }>
}

interface GitResult {
  status: string
  operation: string
  output: string
  return_code: number
}

interface PackageResult {
  status: string
  manager: string
  operation: string
  output: string
  return_code: number
}

interface Monitor {
  index: number
  name: string
  is_primary: boolean
  width?: number
  height?: number
}

interface SystemStatus {
  platform: string
  hostname: string
  python_version: string
  cpus: number
  cpu_percent: number
  memory?: { total_gb: number; available_gb: number; used_gb: number; percent: number }
  disk?: { total_gb: number; used_gb: number; free_gb: number; percent: number }
}

// ─── Tab Config ───────────────────────────────────────────────────────────────

type TabKey = 'windows' | 'wallpaper' | 'protocols' | 'dropzones' | 'sort' | 'git' | 'packages' | 'monitors' | 'terminal' | 'system'

interface TabDef {
  key: TabKey
  label: string
  icon: typeof Monitor
}

const TABS: TabDef[] = [
  { key: 'windows', label: 'Windows', icon: Monitor },
  { key: 'wallpaper', label: 'Wallpaper', icon: Image },
  { key: 'protocols', label: 'Protocols', icon: Workflow },
  { key: 'dropzones', label: 'Drop Zones', icon: Filter },
  { key: 'sort', label: 'Sort Wizard', icon: ArrowUpDown },
  { key: 'git', label: 'Git', icon: GitBranch },
  { key: 'packages', label: 'Packages', icon: Package },
  { key: 'monitors', label: 'Monitors', icon: MonitorUp },
  { key: 'terminal', label: 'Terminal', icon: Terminal },
  { key: 'system', label: 'System', icon: HardDrive },
]

// ═══════════════════════════════════════════════════════════════════════════════
// Component
// ═══════════════════════════════════════════════════════════════════════════════

export function SystemPage(): JSX.Element {
  const [activeTab, setActiveTab] = useState<TabKey>('windows')

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">SYSTEM CONTROL</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">
          Window management, file organization, git, packages, and system monitoring
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
          {activeTab === 'windows' && <WindowManagement />}
          {activeTab === 'wallpaper' && <WallpaperPanel />}
          {activeTab === 'protocols' && <ProtocolsPanel />}
          {activeTab === 'dropzones' && <DropZonePanel />}
          {activeTab === 'sort' && <SortWizardPanel />}
          {activeTab === 'git' && <GitPanel />}
          {activeTab === 'packages' && <PackagePanel />}
          {activeTab === 'monitors' && <MonitorPanel />}
          {activeTab === 'terminal' && <TerminalPanel />}
          {activeTab === 'system' && <SystemInfoPanel />}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1. Window Management
// ═══════════════════════════════════════════════════════════════════════════════

function WindowManagement(): JSX.Element {
  const windowAction = useCallback(async (action: string) => {
    try {
      await window.barq?.python.request('/system/window/control', {
        method: 'POST',
        body: JSON.stringify({ action }),
        headers: { 'Content-Type': 'application/json' },
      })
    } catch { /* ignore */ }
  }, [])

  return (
    <div className="glass-card">
      <div className="flex items-center gap-2 mb-4">
        <Grid3x3 className="w-5 h-5 text-cyan-300" />
        <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Window Management</h3>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <button onClick={() => windowAction('maximize')} className="btn-ghost-cyan text-sm flex items-center gap-2">
          <Maximize className="w-4 h-4" /> Maximize
        </button>
        <button onClick={() => windowAction('minimize')} className="btn-ghost-cyan text-sm flex items-center gap-2">
          <Minimize className="w-4 h-4" /> Minimize
        </button>
        <button onClick={() => windowAction('snap_left')} className="btn-ghost-cyan text-sm flex items-center gap-2">
          <LayoutGrid className="w-4 h-4" /> Snap Left
        </button>
        <button onClick={() => windowAction('snap_right')} className="btn-ghost-cyan text-sm flex items-center gap-2">
          <LayoutGrid className="w-4 h-4" /> Snap Right
        </button>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 2. AI Wallpaper
// ═══════════════════════════════════════════════════════════════════════════════

function WallpaperPanel(): JSX.Element {
  const [prompt, setPrompt] = useState('')
  const [status, setStatus] = useState('')
  const [url, setUrl] = useState('')
  const [applying, setApplying] = useState(false)

  const setWallpaper = useCallback(async () => {
    if (!prompt.trim()) return
    setApplying(true)
    setStatus('Generating...')
    try {
      const resp = await window.barq?.python.request('/desktop/wallpaper/set', {
        method: 'POST',
        body: JSON.stringify({ description: prompt, source: 'auto' }),
        headers: { 'Content-Type': 'application/json' },
      })
      if (resp && typeof resp === 'object') {
        const data = resp as { status?: string; image_url?: string }
        setStatus(data.status || 'Applied')
        if (data.image_url) setUrl(data.image_url)
      }
    } catch { setStatus('Failed') }
    setApplying(false)
  }, [prompt])

  return (
    <div className="glass-card">
      <div className="flex items-center gap-2 mb-4">
        <Image className="w-5 h-5 text-holographic" />
        <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">AI Wallpaper</h3>
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && setWallpaper()}
          placeholder='e.g., "cyberpunk city"'
          className="input-cyan flex-1 text-sm"
        />
        <button onClick={setWallpaper} disabled={applying} className="btn-cyan text-sm">
          {applying ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Set'}
        </button>
      </div>
      {status && (
        <div className="mt-2 flex items-center gap-2 text-xs font-exo">
          <CheckCircle className={`w-3 h-3 ${status === 'Failed' ? 'text-red-400' : 'text-neural'}`} />
          <span className={status === 'Failed' ? 'text-red-400' : 'text-neural'}>{status}</span>
          {url && <ExternalLink className="w-3 h-3 text-dim-400" />}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 3. Custom Protocols
// ═══════════════════════════════════════════════════════════════════════════════

const DEFAULT_PROTOCOLS = [
  { name: 'Job Hunt Mode', desc: 'Open job boards, update resume, start scanning', action: 'job_hunt_mode' },
  { name: 'Deep Work Mode', desc: 'Kill distractions, set focus wallpaper, start timer', action: 'deep_work_mode' },
  { name: 'Gaming Mode', desc: 'Close background apps, free up RAM', action: 'gaming_mode' },
]

function ProtocolsPanel(): JSX.Element {
  const activateProtocol = useCallback(async (name: string) => {
    try {
      await window.barq?.python.request(`/desktop/protocols/activate/${encodeURIComponent(name)}`, { method: 'POST' })
    } catch { /* ignore */ }
  }, [])

  return (
    <div className="glass-card">
      <div className="flex items-center gap-2 mb-4">
        <Workflow className="w-5 h-5 text-neural" />
        <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Custom Protocols</h3>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {DEFAULT_PROTOCOLS.map((p) => (
          <button
            key={p.name}
            onClick={() => activateProtocol(p.action)}
            className="bg-void-700/50 rounded-lg p-4 cursor-pointer hover:bg-void-600/50 transition-colors border border-cyan-500/5 hover:border-cyan-500/15 text-left"
          >
            <p className="text-sm font-rajdhani font-semibold text-ghost">{p.name}</p>
            <p className="text-xs font-exo text-dim-400 mt-1">{p.desc}</p>
          </button>
        ))}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 4. Smart Drop Zones
// ═══════════════════════════════════════════════════════════════════════════════

function DropZonePanel(): JSX.Element {
  const [rules, setRules] = useState<DropZoneRule[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [action, setAction] = useState('move')
  const [targetFolder, setTargetFolder] = useState('')
  const [conditionField, setConditionField] = useState('extension')
  const [conditionOp, setConditionOp] = useState('in')
  const [conditionVal, setConditionVal] = useState('')

  const loadRules = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await window.barq?.system.dropZone.listRules()
      if (resp?.success && resp.data) {
        const d = resp.data as { rules: DropZoneRule[] }
        setRules(d.rules || [])
      }
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { loadRules() }, [loadRules])

  const createRule = useCallback(async () => {
    if (!name.trim()) return
    const rule: DropZoneRule = {
      name,
      description: desc,
      conditions: [{ field: conditionField, operator: conditionOp, value: conditionField === 'extension' ? conditionVal.split(',').map(s => s.trim()) : conditionVal }],
      action,
      target_folder: targetFolder,
      priority: rules.length,
      enabled: true,
    }
    try {
      await window.barq?.system.dropZone.createRule(rule)
      setShowForm(false)
      setName('')
      setDesc('')
      setConditionVal('')
      setTargetFolder('')
      await loadRules()
    } catch { /* ignore */ }
  }, [name, desc, action, targetFolder, conditionField, conditionOp, conditionVal, rules.length, loadRules])

  const deleteRule = useCallback(async (index: number) => {
    try {
      await window.barq?.system.dropZone.deleteRule(index)
      await loadRules()
    } catch { /* ignore */ }
  }, [loadRules])

  return (
    <div className="glass-card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Filter className="w-5 h-5 text-cyan-300" />
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Smart Drop Zones</h3>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="btn-ghost-cyan text-xs flex items-center gap-1">
          <Plus className="w-3 h-3" /> Add Rule
        </button>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin text-dim-400" />
        </div>
      )}

      <AnimatePresence>
        {showForm && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden mb-4"
          >
            <div className="bg-void-700/40 rounded-lg p-4 border border-cyan-500/10 space-y-3">
              <input
                type="text" value={name} onChange={(e) => setName(e.target.value)}
                placeholder="Rule name" className="input-cyan text-sm w-full"
              />
              <input
                type="text" value={desc} onChange={(e) => setDesc(e.target.value)}
                placeholder="Description (optional)" className="input-cyan text-sm w-full"
              />
              <div className="grid grid-cols-3 gap-2">
                <select value={conditionField} onChange={(e) => setConditionField(e.target.value)}
                  className="bg-void-700 rounded-lg px-3 py-2 text-xs text-ghost border border-cyan-500/10">
                  <option value="extension">Extension</option>
                  <option value="name">Name</option>
                  <option value="size_mb">Size (MB)</option>
                  <option value="modified_at">Modified</option>
                  <option value="pattern">Regex</option>
                </select>
                <select value={conditionOp} onChange={(e) => setConditionOp(e.target.value)}
                  className="bg-void-700 rounded-lg px-3 py-2 text-xs text-ghost border border-cyan-500/10">
                  <option value="in">In</option>
                  <option value="equals">Equals</option>
                  <option value="contains">Contains</option>
                  <option value="greater_than">&gt;</option>
                  <option value="less_than">&lt;</option>
                  <option value="regex">Regex</option>
                </select>
                <input
                  type="text" value={conditionVal} onChange={(e) => setConditionVal(e.target.value)}
                  placeholder='e.g. .jpg,.png' className="input-cyan text-xs w-full"
                />
              </div>
              <select value={action} onChange={(e) => setAction(e.target.value)}
                className="bg-void-700 rounded-lg px-3 py-2 text-xs text-ghost border border-cyan-500/10 w-full">
                <option value="move">Move to folder</option>
                <option value="copy">Copy to folder</option>
                <option value="delete">Delete</option>
              </select>
              <input
                type="text" value={targetFolder} onChange={(e) => setTargetFolder(e.target.value)}
                placeholder="Target folder path" className="input-cyan text-sm w-full"
              />
              <button onClick={createRule} className="btn-cyan text-sm w-full">
                <Save className="w-3 h-3" /> Create Rule
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="space-y-2">
        {rules.map((rule, i) => (
          <div key={i} className="flex items-center justify-between bg-void-700/30 rounded-lg px-4 py-3 border border-cyan-500/5">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <GripVertical className="w-3 h-3 text-dim-500" />
                <span className="text-sm font-rajdhani font-semibold text-ghost">{rule.name}</span>
                <span className={`text-hud text-xs px-1.5 py-0.5 rounded ${rule.enabled ? 'bg-neural/10 text-neural' : 'bg-dim-500/10 text-dim-400'}`}>
                  {rule.action}
                </span>
              </div>
              {rule.description && (
                <p className="text-xs font-exo text-dim-400 mt-0.5 ml-5">{rule.description}</p>
              )}
              <p className="text-hud text-dim-500 ml-5 mt-0.5">
                {rule.conditions.map((c) => `${c.field} ${c.operator} ${JSON.stringify(c.value)}`).join(', ')}
                {rule.target_folder && ` → ${rule.target_folder}`}
              </p>
            </div>
            <button onClick={() => deleteRule(i)} className="p-1.5 rounded hover:bg-red-500/10 text-dim-400 hover:text-red-400 transition-colors">
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
        {!loading && rules.length === 0 && (
          <p className="text-xs font-exo text-dim-500 text-center py-6">No drop zone rules yet. Add one to auto-organize files.</p>
        )}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 5. File Sort Wizard
// ═══════════════════════════════════════════════════════════════════════════════

const SORT_STRATEGIES = [
  { value: 'type', label: 'By Type', icon: Filter },
  { value: 'date', label: 'By Date', icon: FolderTree },
  { value: 'size', label: 'By Size', icon: HardDrive },
  { value: 'name', label: 'By Name', icon: ArrowUpDown },
  { value: 'extension_group', label: 'Smart Groups', icon: LayoutGrid },
]

function SortWizardPanel(): JSX.Element {
  const [directory, setDirectory] = useState('')
  const [strategy, setStrategy] = useState('type')
  const [reverse, setReverse] = useState(false)
  const [preview, setPreview] = useState<SortPreview | null>(null)
  const [undoId, setUndoId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<string | null>(null)

  const runPreview = useCallback(async () => {
    if (!directory.trim()) return
    setLoading(true)
    setResult(null)
    try {
      const resp = await window.barq?.system.sort.preview({ directory, strategy, reverse })
      if (resp?.success && resp.data) {
        setPreview(resp.data as SortPreview)
      }
    } catch { setResult('Preview failed') }
    setLoading(false)
  }, [directory, strategy, reverse])

  const runExecute = useCallback(async () => {
    if (!directory.trim()) return
    setLoading(true)
    setResult(null)
    try {
      const resp = await window.barq?.system.sort.execute({
        directory, strategy, reverse,
        preview_id: preview?.preview_id,
      })
      if (resp?.success && resp.data) {
        const d = resp.data as { files_sorted: number; undo_id: string }
        setResult(`Sorted ${d.files_sorted} files`)
        setUndoId(d.undo_id)
        setPreview(null)
      }
    } catch { setResult('Sort failed') }
    setLoading(false)
  }, [directory, strategy, reverse, preview])

  const runUndo = useCallback(async () => {
    if (!undoId) return
    setLoading(true)
    try {
      const resp = await window.barq?.system.sort.undo(undoId)
      if (resp?.success && resp.data) {
        const d = resp.data as { files_restored: number }
        setResult(`Restored ${d.files_restored} files`)
        setUndoId(null)
      }
    } catch { setResult('Undo failed') }
    setLoading(false)
  }, [undoId])

  return (
    <div className="glass-card">
      <div className="flex items-center gap-2 mb-4">
        <ArrowUpDown className="w-5 h-5 text-holographic" />
        <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">File Sorting Wizard</h3>
      </div>

      <div className="flex gap-2 mb-3">
        <input
          type="text" value={directory} onChange={(e) => setDirectory(e.target.value)}
          placeholder="Directory to sort (e.g. ~/Downloads)"
          className="input-cyan flex-1 text-sm"
        />
      </div>

      <div className="flex gap-2 mb-3 flex-wrap">
        {SORT_STRATEGIES.map((s) => (
          <button
            key={s.value}
            onClick={() => setStrategy(s.value)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-rajdhani font-semibold transition-all
              ${strategy === s.value
                ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-400/30'
                : 'bg-void-700/40 text-dim-400 hover:text-ghost border border-transparent'
              }`}
          >
            <s.icon className="w-3 h-3" /> {s.label}
          </button>
        ))}
        <button
          onClick={() => setReverse(!reverse)}
          className={`px-3 py-1.5 rounded-lg text-xs font-rajdhani font-semibold transition-all
            ${reverse ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-400/30' : 'bg-void-700/40 text-dim-400 border border-transparent'}`}
        >
          Reverse
        </button>
      </div>

      <div className="flex gap-2">
        <button onClick={runPreview} disabled={loading} className="btn-ghost-cyan text-xs flex items-center gap-1">
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Eye className="w-3 h-3" />} Preview
        </button>
        <button onClick={runExecute} disabled={loading} className="btn-cyan text-xs flex items-center gap-1">
          <Play className="w-3 h-3" /> Execute Sort
        </button>
        {undoId && (
          <button onClick={runUndo} className="btn-ghost-cyan text-xs flex items-center gap-1 text-amber-400">
            <Undo2 className="w-3 h-3" /> Undo
          </button>
        )}
      </div>

      {result && (
        <div className="mt-3 flex items-center gap-2 text-xs font-exo">
          <CheckCircle className="w-3 h-3 text-neural" />
          <span className="text-neural">{result}</span>
        </div>
      )}

      {preview && (
        <div className="mt-4 space-y-2 max-h-60 overflow-y-auto scroll-cyan">
          <p className="text-hud text-dim-400 text-xs mb-2">
            Preview: {preview.total_files} files in {Object.keys(preview.groups).length} groups
          </p>
          {Object.entries(preview.groups).map(([folder, group]) => (
            <div key={folder} className="bg-void-700/20 rounded-lg p-3">
              <p className="text-xs font-rajdhani font-semibold text-cyan-300 mb-1">
                {folder} ({group.count} files)
              </p>
              <div className="flex flex-wrap gap-1">
                {group.files.slice(0, 8).map((f, i) => (
                  <span key={i} className="text-hud text-dim-500 bg-void-800/30 px-1.5 py-0.5 rounded">{f}</span>
                ))}
                {group.files.length > 8 && (
                  <span className="text-hud text-dim-500">+{group.files.length - 8} more</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 6. Git Operations
// ═══════════════════════════════════════════════════════════════════════════════

const GIT_OPS = ['status', 'log', 'diff', 'branch', 'pull', 'push', 'add', 'commit', 'checkout']

function GitPanel(): JSX.Element {
  const [repoPath, setRepoPath] = useState('')
  const [operation, setOperation] = useState('status')
  const [message, setMessage] = useState('')
  const [output, setOutput] = useState('')
  const [loading, setLoading] = useState(false)

  const runGit = useCallback(async () => {
    if (!repoPath.trim()) return
    setLoading(true)
    try {
      const data: Record<string, unknown> = { repo_path: repoPath, operation }
      if (operation === 'commit' && message) data.message = message
      const resp = await window.barq?.system.git(data)
      if (resp?.success && resp.data) {
        const result = resp.data as GitResult
        setOutput(result.output || '(empty output)')
      }
    } catch { setOutput('Error running git command') }
    setLoading(false)
  }, [repoPath, operation, message])

  return (
    <div className="glass-card">
      <div className="flex items-center gap-2 mb-4">
        <GitBranch className="w-5 h-5 text-holographic" />
        <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Git Operations</h3>
      </div>

      <div className="flex gap-2 mb-3">
        <input
          type="text" value={repoPath} onChange={(e) => setRepoPath(e.target.value)}
          placeholder="Repository path" className="input-cyan flex-1 text-sm"
        />
      </div>

      <div className="flex gap-1.5 mb-3 flex-wrap">
        {GIT_OPS.map((op) => (
          <button
            key={op}
            onClick={() => setOperation(op)}
            className={`px-2.5 py-1 rounded text-hud font-rajdhani font-semibold transition-all
              ${operation === op
                ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-400/20'
                : 'bg-void-700/40 text-dim-400 hover:text-ghost border border-transparent'
              }`}
          >
            {op}
          </button>
        ))}
      </div>

      {operation === 'commit' && (
        <input
          type="text" value={message} onChange={(e) => setMessage(e.target.value)}
          placeholder="Commit message" className="input-cyan text-sm w-full mb-3"
        />
      )}

      <button onClick={runGit} disabled={loading} className="btn-cyan text-xs flex items-center gap-1">
        {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />} Run
      </button>

      {output && (
        <pre className="mt-3 bg-void-900/60 rounded-lg p-3 text-hud text-dim-300 text-xs max-h-48 overflow-y-auto scroll-cyan font-mono whitespace-pre-wrap">
          {output}
        </pre>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 7. Package Manager
// ═══════════════════════════════════════════════════════════════════════════════

const PACKAGE_MANAGERS = ['npm', 'pip', 'brew', 'pnpm', 'yarn', 'cargo']

function PackagePanel(): JSX.Element {
  const [manager, setManager] = useState('npm')
  const [operation, setOperation] = useState('install')
  const [packageName, setPackageName] = useState('')
  const [output, setOutput] = useState('')
  const [loading, setLoading] = useState(false)
  const [cwd, setCwd] = useState('')

  const runPkg = useCallback(async () => {
    setLoading(true)
    try {
      const data: Record<string, unknown> = { manager, operation, cwd: cwd || undefined }
      if (packageName) data.package = packageName
      const resp = await window.barq?.system.packageManager(data)
      if (resp?.success && resp.data) {
        const result = resp.data as PackageResult
        setOutput(result.output || '(empty output)')
      }
    } catch { setOutput('Error running package manager') }
    setLoading(false)
  }, [manager, operation, packageName, cwd])

  return (
    <div className="glass-card">
      <div className="flex items-center gap-2 mb-4">
        <Package className="w-5 h-5 text-neural" />
        <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Package Manager</h3>
      </div>

      <div className="flex gap-1.5 mb-3 flex-wrap">
        {PACKAGE_MANAGERS.map((m) => (
          <button
            key={m}
            onClick={() => setManager(m)}
            className={`px-2.5 py-1 rounded text-hud font-rajdhani font-semibold transition-all
              ${manager === m
                ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-400/20'
                : 'bg-void-700/40 text-dim-400 hover:text-ghost border border-transparent'
              }`}
          >
            {m}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-2 mb-3">
        <input
          type="text" value={packageName} onChange={(e) => setPackageName(e.target.value)}
          placeholder={manager === 'npm' ? 'Package name' : manager === 'pip' ? 'Package name' : 'Package/formula'}
          className="input-cyan text-sm"
        />
        <select
          value={operation}
          onChange={(e) => setOperation(e.target.value)}
          className="bg-void-700 rounded-lg px-3 py-2 text-xs text-ghost border border-cyan-500/10"
        >
          <option value="install">Install</option>
          <option value="uninstall">Uninstall</option>
          <option value="update">Update</option>
          <option value="list">List</option>
          <option value="search">Search</option>
          <option value="info">Info</option>
          {['npm', 'pnpm', 'yarn'].includes(manager) && <option value="run">Run Script</option>}
        </select>
      </div>

      <input
        type="text" value={cwd} onChange={(e) => setCwd(e.target.value)}
        placeholder="Working directory (optional)" className="input-cyan text-sm w-full mb-3"
      />

      <button onClick={runPkg} disabled={loading} className="btn-cyan text-xs flex items-center gap-1">
        {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />} Run
      </button>

      {output && (
        <pre className="mt-3 bg-void-900/60 rounded-lg p-3 text-hud text-dim-300 text-xs max-h-48 overflow-y-auto scroll-cyan font-mono whitespace-pre-wrap">
          {output}
        </pre>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 8. Multi-Monitor Management
// ═══════════════════════════════════════════════════════════════════════════════

function MonitorPanel(): JSX.Element {
  const [monitors, setMonitors] = useState<Monitor[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      try {
        const resp = await window.barq?.system.monitors()
        if (resp?.success && resp.data) {
          const d = resp.data as { monitors: Monitor[] }
          setMonitors(d.monitors || [])
        }
      } catch { /* ignore */ }
      setLoading(false)
    })()
  }, [])

  const moveToMonitor = useCallback(async (monitorIndex: number) => {
    try {
      await window.barq?.python.request('/system/window/control', {
        method: 'POST',
        body: JSON.stringify({ action: 'move_to_monitor', monitor_index: monitorIndex }),
        headers: { 'Content-Type': 'application/json' },
      })
    } catch { /* ignore */ }
  }, [])

  return (
    <div className="glass-card">
      <div className="flex items-center gap-2 mb-4">
        <MonitorUp className="w-5 h-5 text-cyan-300" />
        <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Multi-Monitor</h3>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin text-dim-400" />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {monitors.map((m) => (
          <div
            key={m.index}
            className="bg-void-700/30 rounded-lg p-4 border border-cyan-500/5 hover:border-cyan-500/15 transition-colors"
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Monitor className="w-4 h-4 text-cyan-300" />
                <span className="text-sm font-rajdhani font-semibold text-ghost">{m.name}</span>
              </div>
              {m.is_primary && (
                <span className="text-hud text-xs text-neural bg-neural/10 px-1.5 py-0.5 rounded">Primary</span>
              )}
            </div>
            {m.width && m.height && (
              <p className="text-hud text-dim-400 text-xs">{m.width} × {m.height}</p>
            )}
            <button
              onClick={() => moveToMonitor(m.index)}
              className="mt-2 text-hud text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
            >
              Move window here →
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 9. Terminal
// ═══════════════════════════════════════════════════════════════════════════════

function TerminalPanel(): JSX.Element {
  const [command, setCommand] = useState('')
  const [output, setOutput] = useState('')
  const [loading, setLoading] = useState(false)
  const termRef = useCallback((node: HTMLPreElement | null) => {
    if (node) node.scrollTop = node.scrollHeight
  }, [])

  const runCommand = useCallback(async () => {
    if (!command.trim()) return
    setLoading(true)
    setOutput('')
    try {
      const resp = await window.barq?.python.request('/system/terminal/run', {
        method: 'POST',
        body: JSON.stringify({ command }),
        headers: { 'Content-Type': 'application/json' },
      })
      if (resp && typeof resp === 'object') {
        const data = resp as { output?: string; return_code?: number }
        const out = data.output || '(no output)'
        setOutput(`${out}\n\nExit code: ${data.return_code ?? -1}`)
      }
    } catch { setOutput('Error executing command') }
    setLoading(false)
  }, [command])

  return (
    <div className="glass-card">
      <div className="flex items-center gap-2 mb-4">
        <Terminal className="w-5 h-5 text-neural" />
        <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Terminal</h3>
      </div>

      <div className="flex gap-2 mb-3">
        <input
          type="text"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && runCommand()}
          placeholder="$ command"
          className="input-cyan flex-1 text-sm font-mono"
        />
        <button onClick={runCommand} disabled={loading} className="btn-cyan text-sm">
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
        </button>
      </div>

      {(output || loading) && (
        <pre
          ref={termRef}
          className="bg-void-900/80 rounded-lg p-4 text-hud text-dim-300 text-xs max-h-64 overflow-y-auto scroll-cyan font-mono whitespace-pre-wrap border border-cyan-500/5"
        >
          {loading && !output && <span className="text-dim-500 animate-pulse">Running...</span>}
          {output}
        </pre>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 10. System Info
// ═══════════════════════════════════════════════════════════════════════════════

function SystemInfoPanel(): JSX.Element {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [micLevel, setMicLevel] = useState(0)
  const [isListening, setIsListening] = useState(false)

  useEffect(() => {
    (async () => {
      try {
        const resp = await window.barq?.python.request('/system/status')
        if (resp && typeof resp === 'object') {
          const data = resp as Record<string, unknown>
          setStatus({
            platform: String(data.platform || ''),
            hostname: String(data.hostname || ''),
            python_version: String(data.python_version || ''),
            cpus: Number(data.cpus || 0),
            cpu_percent: Number(data.cpu_percent || 0),
            memory: data.memory as SystemStatus['memory'],
            disk: data.disk as SystemStatus['disk'],
          })
        }
      } catch { /* ignore */ }
      setLoading(false)
    })()
  }, [])

  // Poll mic level for real-time indicator
  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const resp = await window.barq?.python.request('/voice/mic-level')
        if (resp && typeof resp === 'object') {
          const data = resp as Record<string, unknown>
          setMicLevel(Number(data.level || 0))
          setIsListening(Boolean(data.is_listening))
        }
      } catch { /* ignore */ }
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  // Map 0-1 level to 0-12 bars with a noise floor
  const barCount = 12
  const activeBars = isListening
    ? Math.max(1, Math.round(micLevel * barCount))
    : 0

  if (loading) {
    return (
      <div className="glass-card flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-dim-400" />
      </div>
    )
  }

  return (
    <div className="glass-card">
      <div className="flex items-center gap-2 mb-4">
        <HardDrive className="w-5 h-5 text-cyan-300" />
        <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">System Information</h3>
      </div>

      {/* ─── Mic Level Indicator ─── */}
      <div className="bg-void-700/30 rounded-lg p-4 mb-4 border border-cyan-500/8">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${isListening ? 'bg-green-400 shadow-[0_0_8px_rgba(74,222,128,0.5)]' : 'bg-dim-500'}`} />
            <span className="text-sm font-rajdhani font-semibold text-ghost">Microphone</span>
          </div>
          <span className={`text-hud text-xs ${isListening ? 'text-green-400' : 'text-dim-500'}`}>
            {isListening ? 'Active — Wake word listening' : 'Inactive'}
          </span>
        </div>
        <div className="flex items-center gap-[3px] h-8">
          {Array.from({ length: barCount }, (_, i) => {
            const isActive = i < activeBars
            const intensity = isActive ? (i + 1) / barCount : 0
            const r = Math.round(10 + intensity * 56)
            const g = Math.round(180 + intensity * 75)
            const b = Math.round(212)
            return (
              <div
                key={i}
                className="flex-1 rounded-sm transition-all duration-75"
                style={{
                  height: `${20 + (i / barCount) * 60}%`,
                  backgroundColor: isActive
                    ? `rgba(${r}, ${g}, ${b}, ${0.4 + intensity * 0.6})`
                    : 'rgba(30, 41, 59, 0.5)',
                  boxShadow: isActive && i >= barCount - 3
                    ? '0 0 6px rgba(6, 182, 212, 0.4)'
                    : 'none',
                }}
              />
            )
          })}
        </div>
        <div className="flex justify-between mt-1.5">
          <span className="text-hud text-[10px] text-dim-500">Silence</span>
          <span className="text-hud text-[10px] text-dim-400">{isListening ? Math.round(micLevel * 100) : 0}%</span>
          <span className="text-hud text-[10px] text-dim-500">Peak</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {status?.platform && (
          <InfoCard label="Platform" value={status.platform} />
        )}
        {status?.hostname && (
          <InfoCard label="Hostname" value={status.hostname} />
        )}
        {status?.cpus && (
          <InfoCard label="CPU Cores" value={`${status.cpus} (${status.cpu_percent ?? 0}% used)`} />
        )}
        {status?.memory && (
          <InfoCard
            label="Memory"
            value={`${status.memory.used_gb.toFixed(1)} / ${status.memory.total_gb.toFixed(1)} GB (${status.memory.percent}%)`}
          />
        )}
        {status?.disk && (
          <InfoCard
            label="Disk"
            value={`${status.disk.used_gb.toFixed(1)} / ${status.disk.total_gb.toFixed(1)} GB (${status.disk.percent}%)`}
          />
        )}
        {status?.python_version && (
          <InfoCard label="Python" value={status.python_version.split(' ')[0]} />
        )}
      </div>
    </div>
  )
}

function InfoCard({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="bg-void-700/30 rounded-lg p-3 border border-cyan-500/5">
      <p className="text-hud text-dim-500 text-xs uppercase tracking-wider mb-0.5">{label}</p>
      <p className="text-sm font-rajdhani font-semibold text-ghost">{value}</p>
    </div>
  )
}
