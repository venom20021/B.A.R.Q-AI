import { useState, useEffect, useCallback, useRef, startTransition } from 'react'
import { api } from '../utils/api'
import { usePersistentState } from '../hooks/usePersistentState'
import {
  Search, Filter, ExternalLink, CheckCircle, XCircle,
  Loader2, Activity, BarChart3, Mail, Send, RefreshCw,
  TrendingUp, Target, AlertCircle, UserCheck, Upload,
  X, MapPin, FileText, Brain, Lightbulb,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

// ─── Types ────────────────────────────────────────────────────────────────────

interface Job {
  id: string
  title: string
  company: string
  location: string
  salary: string
  match_score: number
  match_percentage: number
  source: string
  posted_date: string
  status: 'new' | 'reviewing' | 'approved' | 'applied' | 'rejected'
  description: string
  source_url: string
  reasoning: string
  pros: string[]
  cons: string[]
}

interface ScanProgress {
  status: string
  phase: string
  phase_index: number
  total_phases: number
  progress_pct: number
  boards_total: number
  boards_scanned: number
  boards_errors: number
  jobs_found: number
  jobs_evaluated: number
  message: string
  started_at: number | null
  elapsed_seconds: number
}

interface ResponseAnalytics {
  overall: {
    total_applications: number
    submitted: number
    responded: number
    interviews: number
    rejections: number
    offers: number
    pending_followup: number
    response_rate: number
    interview_rate: number
    offer_rate: number
  }
  by_source: Array<{
    source: string
    total: number
    responded: number
    interviews: number
    response_rate: number
    avg_response_time_days: number
  }>
  funnel: Array<{
    month: string
    submitted: number
    responded: number
    interviews: number
    offers: number
  }>
  recent_responses: Array<{
    id: number
    type: string
    date: string
    title: string
    company: string
    source: string
  }>
}

interface MatchAnalytics {
  total_jobs: number
  total_evaluated: number
  score_tiers: Array<{
    tier: string
    count: number
    avg_percentage: number
  }>
  top_sources: Array<{
    source: string
    job_count: number
    avg_match: number
  }>
  recent_scans: Array<{
    date: string
    summary: string
  }>
  application_statuses: Array<{
    status: string
    count: number
  }>
}

interface FollowupCandidate {
  id: number
  title: string
  company: string
  source_board: string
  days_since_submission: number
  submitted_at: string
}

function _mapJobStatus(backendStatus: string): Job['status'] {
  /* Map backend application statuses to the frontend Job status type. */
  const map: Record<string, Job['status']> = {
    'new': 'new',
    'queued': 'approved',
    'submitted': 'applied',
    'ready_for_review': 'applied',
    'failed': 'rejected',
    'draft': 'new',
  }
  return map[backendStatus] || 'new'
}

// ─── Tab Config ───────────────────────────────────────────────────────────────

type TabKey = 'listings' | 'suggestions' | 'analytics' | 'followups' | 'pipeline'

const TABS: { key: TabKey; label: string; icon: typeof Search }[] = [
  { key: 'listings', label: 'Job Listings', icon: Search },
  { key: 'suggestions', label: 'Suggestions', icon: Lightbulb },
  { key: 'pipeline', label: 'Pipeline', icon: Activity },
  { key: 'analytics', label: 'Analytics', icon: BarChart3 },
  { key: 'followups', label: 'Follow-Ups', icon: Mail },
]

const statusColors: Record<Job['status'], string> = {
  new: 'badge-cyan',
  reviewing: 'badge-plasma',
  approved: 'badge-green',
  applied: 'badge-purple',
  rejected: 'badge-dim'
}

const phaseIcons = ['🌐', '🔍', '🧠', '✅']

// ═══════════════════════════════════════════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════════════════════════════════════════

interface DrillTarget {
  status?: Job['status']
  minScore?: number
  sourceBoard?: string
}

export function JobsPage(): JSX.Element {
  const [activeTab, setActiveTab] = usePersistentState<TabKey>('JobsPage.activeTab', 'listings')
  const [drillFilter, setDrillFilter] = useState<DrillTarget | null>(null)

  const handleDrillDown = useCallback((target: DrillTarget) => {
    setDrillFilter(target)
    setActiveTab('listings')
  }, [])

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-4 h-full overflow-y-auto scroll-cyan">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">JOB SEARCH</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">
          AI-matched opportunities from 35+ job boards with response tracking and follow-ups
        </p>
      </motion.div>

      {/* Tab Navigation */}
      <div className="flex gap-1 border-b border-cyan-500/10 pb-2">
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
          {activeTab === 'listings' && <JobListings drillFilter={drillFilter} onDrillConsumed={() => setDrillFilter(null)} />}
          {activeTab === 'suggestions' && <RoleSuggestions onSearchRole={(role) => { navigator.clipboard.writeText(role); setActiveTab('listings'); }} />}
          {activeTab === 'pipeline' && <PipelinePanel />}
          {activeTab === 'analytics' && <ResponseAnalytics onNavigateToFilter={handleDrillDown} />}
          {activeTab === 'followups' && <FollowUpPanel />}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1. Job Listings (existing functionality + enhanced sources)
// ═══════════════════════════════════════════════════════════════════════════════

function JobListings({ drillFilter, onDrillConsumed }: { drillFilter?: DrillTarget | null; onDrillConsumed?: () => void }): JSX.Element {
  const [jobs, setJobs] = usePersistentState<Job[]>('JobsPage.jobs', [])
  const [filter, setFilter] = usePersistentState<Job['status'] | 'all'>('JobsPage.filter', 'all')
  const [sortBy, setSortBy] = usePersistentState<'match' | 'date'>('JobsPage.sortBy', 'match')
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = usePersistentState('JobsPage.scanning', false)
  const [progress, setProgress] = usePersistentState<ScanProgress | null>('JobsPage.scanProgress', null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // Toast state
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const [applyingJobs, setApplyingJobs] = useState<Record<string, 'idle' | 'loading' | 'success' | 'error'>>({})

  // Scan history state
  const [scanHistory, setScanHistory] = useState<Array<{ id: number; action: string; description: string; severity: string; created_at: string }>>([])
  const [showHistory, setShowHistory] = useState(false)
  const [autoScanEnabled, setAutoScanEnabled] = useState(false)
  const [selectedJob, setSelectedJob] = useState<Job | null>(null)
  const [minScoreFilter, setMinScoreFilter] = useState<number | null>(null)
  const [sourceBoardFilter, setSourceBoardFilter] = useState<string | null>(null)

  const showToast = useCallback((message: string, type: 'success' | 'error') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 4000)
  }, [])

  const fetchJobs = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await api<{ matches?: Record<string, unknown>[] }>('/jobs/matches?limit=50')
      const matches = resp?.matches ?? []
      // 🚨 DIAGNOSTIC: Log raw payload from backend
      console.log('🔍 FETCHED JOBS PAYLOAD:', JSON.stringify(matches.map(m => ({id: m['id'], status: m['status'], title: m['title']}))));
      console.log('🔍 usePersistentState jobs BEFORE overwrite:', JSON.stringify(jobs.map(j => ({id: j.id, status: j.status}))));
      setJobs(matches.map((m) => {
        const prosRaw = String(m['pros'] ?? '[]')
        const consRaw = String(m['cons'] ?? '[]')
        let pros: string[] = []
        let cons: string[] = []
        try { pros = JSON.parse(prosRaw) as string[] } catch { pros = prosRaw.replace(/[[\]"]/g, '').split(',').filter(Boolean) }
        try { cons = JSON.parse(consRaw) as string[] } catch { cons = consRaw.replace(/[[\]"]/g, '').split(',').filter(Boolean) }
        return {
          id: String(m['id'] ?? ''),
          title: String(m['title'] ?? 'Untitled'),
          company: String(m['company'] ?? 'Unknown'),
          location: String(m['location'] ?? ''),
          salary: m['salary_min'] && m['salary_max']
            ? `$${Number(m['salary_min']).toLocaleString()} - $${Number(m['salary_max']).toLocaleString()}`
            : 'N/A',
          match_score: Math.round(Number(m['match_score'] ?? 0)),
          match_percentage: Math.round(Number(m['match_percentage'] ?? 0)),
          source: String(m['source'] ?? ''),
          posted_date: String(m['posted_date'] ?? ''),
          description: String(m['description'] ?? ''),
          source_url: String(m['source_url'] ?? ''),
          status: _mapJobStatus(String(m['status'] ?? 'new')),
          reasoning: String(m['reasoning'] ?? ''),
          pros,
          cons,
        }
      }))
    } catch { setJobs([]) }
    setLoading(false)
  }, [])

  // Apply drill-down filter on mount
  useEffect(() => {
    if (drillFilter && onDrillConsumed) {
      if (drillFilter.status) setFilter(drillFilter.status)
      if (drillFilter.minScore != null) setMinScoreFilter(drillFilter.minScore)
      if (drillFilter.sourceBoard != null) setSourceBoardFilter(drillFilter.sourceBoard)
      onDrillConsumed()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchJobs() }, [fetchJobs])

  // Fetch scan history on mount
  useEffect(() => {
    (async () => {
      try {
        const [historyResp, autoStatusResp] = await Promise.all([
          api<{ scans?: Array<{ id: number; action: string; description: string; severity: string; created_at: string }> }>('/jobs/scan/history?hours=24'),
          api<{ enabled?: boolean }>('/jobs/scan/auto-status'),
        ])
        if (historyResp?.scans) setScanHistory(historyResp.scans)
        if (autoStatusResp?.enabled !== undefined) setAutoScanEnabled(autoStatusResp.enabled)
      } catch { /* ignore */ }
    })()
  }, [])

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        (eventSourceRef.current as EventSource).close()
        eventSourceRef.current = null
      }
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
      }
    }
  }, [])

  const openEventSource = useCallback(() => {
    // Close any existing EventSource or poll interval
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current)
      pollIntervalRef.current = null
    }
    if (eventSourceRef.current) {
      (eventSourceRef.current as EventSource).close()
      eventSourceRef.current = null
    }

    // Poll scan progress through the IPC bridge (api() utility) instead of
    // using EventSource (SSE) directly from the renderer.  Direct EventSource
    // from the Electron renderer to a remote (cloud) backend URL would be
    // blocked by CORS — the same issue that plagued the PDF upload.
    // The api() utility routes through the main process (Node.js HTTP)
    // which has no CORS restrictions.
    const pollInterval = setInterval(async () => {
      try {
        const data = await api<Record<string, unknown>>('/jobs/scan/progress')
        if (!data) return

        if (data.final) {
          clearInterval(pollInterval)
          eventSourceRef.current = null
          setScanning(false)
          fetchJobs()
          return
        }

        setProgress({
          status: String(data.status || ''),
          phase: String(data.phase || ''),
          phase_index: Number(data.phase_index || 0),
          total_phases: Number(data.total_phases || 4),
          progress_pct: Number(data.progress_pct || 0),
          boards_total: Number(data.boards_total || 0),
          boards_scanned: Number(data.boards_scanned || 0),
          boards_errors: Number(data.boards_errors || 0),
          jobs_found: Number(data.jobs_found || 0),
          jobs_evaluated: Number(data.jobs_evaluated || 0),
          message: String(data.message || ''),
          started_at: data.started_at as number | null,
          elapsed_seconds: Number(data.elapsed_seconds || 0),
        })

        if (data.status === 'complete' || data.status === 'error') {
          clearInterval(pollInterval)
          eventSourceRef.current = null
          setScanning(false)
          fetchJobs()
        }
      } catch { /* ignore — next poll will retry */ }
    }, 2000)

    pollIntervalRef.current = pollInterval
  }, [fetchJobs])

  const handleAutoScanToggle = async (): Promise<void> => {
    const newState = !autoScanEnabled
    try {
      const resp = await api<{ status?: string }>('/jobs/scan/auto-toggle', { enabled: newState })
      if (resp?.status) {
        setAutoScanEnabled(newState)
        showToast(newState ? 'Auto-scan enabled (every hour)' : 'Auto-scan disabled', 'success')
      }
    } catch {
      showToast('Failed to toggle auto-scan', 'error')
    }
  }

  const refreshScanHistory = useCallback(async () => {
    try {
      const resp = await api<{ scans?: Array<{ id: number; action: string; description: string; severity: string; created_at: string }> }>('/jobs/scan/history?hours=24')
      if (resp?.scans) setScanHistory(resp.scans)
    } catch { /* ignore */ }
  }, [])

  const handleScan = async (): Promise<void> => {
    setScanning(true)
    // Use dynamic board count from backend (defaults to 28)
    const TOTAL_BOARDS = progress?.boards_total || 28
    setProgress({
      status: 'starting', phase: 'Initializing scan...', phase_index: 0,
      total_phases: 4, progress_pct: 0, boards_total: TOTAL_BOARDS, boards_scanned: 0,
      boards_errors: 0, jobs_found: 0, jobs_evaluated: 0,
      message: `Starting scan (${TOTAL_BOARDS} boards)...`, started_at: Date.now() / 1000, elapsed_seconds: 0,
    })
    try {
      await api('/jobs/scan', {})
      openEventSource()
      // Safety timeout: close EventSource after 5 minutes
      setTimeout(() => {
        let shouldCleanup = false
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current)
          pollIntervalRef.current = null
          shouldCleanup = true
        }
        if (eventSourceRef.current) {
          (eventSourceRef.current as EventSource).close()
          eventSourceRef.current = null
          shouldCleanup = true
        }
        if (shouldCleanup) {
          setScanning(false)
          fetchJobs()
        }
      }, 300_000)
    } catch {
      setScanning(false)
      setProgress(null)
      showToast('Failed to start scan', 'error')
      await fetchJobs()
    }
  }

  const handleApprove = async (jobId: string): Promise<void> => {
    // Optimistic update: show loading state
    setApplyingJobs((prev) => ({ ...prev, [jobId]: 'loading' }))

    try {
      const resp = await api<{ status?: string; application_id?: number }>(`/jobs/${jobId}/apply`, {})
      if (resp?.status === 'accepted') {
        setApplyingJobs((prev) => ({ ...prev, [jobId]: 'success' }))
        setJobs((prev) => prev.map((j) => j.id === jobId ? { ...j, status: 'approved' as Job['status'] } : j))
        showToast('Application queued for processing!', 'success')
        // Reset button after 3 seconds
        setTimeout(() => {
          setApplyingJobs((prev) => ({ ...prev, [jobId]: 'idle' }))
        }, 3000)
      } else {
        throw new Error('Unexpected response')
      }
    } catch {
      showToast('Failed to queue application. Please try again.', 'error')
      setApplyingJobs((prev) => ({ ...prev, [jobId]: 'idle' }))
    }
  }

  const filteredJobs = jobs
    .filter((job) => filter === 'all' || job.status === filter)
    .filter((job) => minScoreFilter == null || job.match_percentage >= minScoreFilter)
    .filter((job) => sourceBoardFilter == null || job.source === sourceBoardFilter)
    .sort((a, b) => sortBy === 'match' ? b.match_percentage - a.match_percentage : a.posted_date.localeCompare(b.posted_date))

  // On mount: resume EventSource if a scan was in progress
  useEffect(() => {
    if (scanning && !eventSourceRef.current && !pollIntervalRef.current && progress) {
      if (progress.status === 'scanning' || progress.status === 'evaluating' || progress.status === 'starting') {
        openEventSource()
      } else if (['complete', 'idle', 'error'].includes(progress.status) || !progress) {
        setScanning(false)
        setProgress(null)
        fetchJobs()
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const isActiveScan = scanning && progress && ['scanning', 'evaluating', 'starting'].includes(progress.status)

  return (
    <div className="space-y-6 relative">
      {/* Toast Notification */}
      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: -20, x: '-50%' }}
            animate={{ opacity: 1, y: 0, x: '-50%' }}
            exit={{ opacity: 0, y: -20, x: '-50%' }}
            transition={{ type: 'spring', stiffness: 400, damping: 25 }}
            className={`fixed top-4 left-1/2 z-50 px-4 py-2.5 rounded-lg shadow-lg text-xs font-rajdhani font-semibold flex items-center gap-2
              ${toast.type === 'success' ? 'bg-green-500/15 text-green-400 border border-green-400/20' : 'bg-red-500/15 text-red-400 border border-red-400/20'}`}
          >
            {toast.type === 'success' ? <CheckCircle className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
            {toast.message}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header + Scan Button + Auto-Scan Toggle */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <p className="text-sm font-rajdhani text-dim-400">
            {jobs.length} jobs loaded
          </p>
          {/* Auto-Scan Toggle */}
          <button
            onClick={handleAutoScanToggle}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-rajdhani font-semibold transition-all
              ${autoScanEnabled
                ? 'bg-green-500/10 text-green-400 border border-green-400/20'
                : 'bg-void-800/50 text-dim-400 border border-void-600/30 hover:text-ghost'
              }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${autoScanEnabled ? 'bg-green-400 animate-pulse shadow-[0_0_6px_rgba(74,222,128,0.5)]' : 'bg-dim-600'}`} />
            {autoScanEnabled ? 'Auto-Scan ON' : 'Auto-Scan OFF'}
          </button>
        </div>
        <div className="flex items-center gap-2">
          {/* Scan History Toggle */}
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="btn-ghost-cyan text-[11px] flex items-center gap-1.5"
          >
            <Activity className="w-3.5 h-3.5" />
            History
            {scanHistory.length > 0 && (
              <span className="text-dim-500 font-share-tech">({scanHistory.length})</span>
            )}
          </button>
          <button onClick={handleScan} disabled={scanning} className="btn-cyan flex items-center gap-2">
            {scanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            {scanning ? 'Scanning...' : 'Scan Now'}
          </button>
        </div>
      </div>

      {/* Scan History Panel */}
      <AnimatePresence>
        {showHistory && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="glass-card overflow-hidden"
          >
            <div className="p-3 space-y-2">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-xs font-rajdhani font-semibold text-ghost flex items-center gap-1.5">
                  <Activity className="w-3 h-3 text-cyan-400" />
                  Recent Scans (24h)
                </h4>
                <button onClick={refreshScanHistory} className="text-dim-400 hover:text-ghost transition-colors">
                  <RefreshCw className="w-3 h-3" />
                </button>
              </div>
              {scanHistory.length === 0 ? (
                <p className="text-xs font-exo text-dim-500 text-center py-3">No scan history in the last 24 hours</p>
              ) : (
                <div className="space-y-1 max-h-48 overflow-y-auto scroll-cyan">
                  {scanHistory.map((entry) => (
                    <div key={entry.id} className="flex items-start gap-2 bg-void-800/30 rounded px-2.5 py-1.5">
                      <div className="flex-shrink-0 mt-0.5">
                        {entry.action === 'scan_error' ? (
                          <XCircle className="w-3 h-3 text-red-400" />
                        ) : (
                          <CheckCircle className="w-3 h-3 text-neural" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-[11px] font-exo text-dim-400 line-clamp-2">
                          {entry.description}
                        </p>
                        <p className="text-[10px] font-share-tech text-dim-600 mt-0.5">
                          {new Date(entry.created_at).toLocaleString()}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Scan Progress */}
      {isActiveScan && progress && (
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="glass-card overflow-hidden">
          <div className="p-4 space-y-3">
            <div className="flex items-center gap-3">
              <span className="text-xl">{phaseIcons[progress.phase_index] || '🔍'}</span>
              <span className="text-sm font-rajdhani font-semibold text-ghost">{progress.phase || 'Scanning...'}</span>
              <span className="text-xs font-share-tech text-cyan-300 ml-auto">{progress.progress_pct}%</span>
            </div>
            <div className="w-full h-2 bg-void-800/60 rounded-full overflow-hidden">
              <motion.div className="h-full rounded-full bg-gradient-to-r from-cyan-500 via-blue-500 to-purple-500"
                initial={{ width: 0 }} animate={{ width: `${progress.progress_pct}%` }} transition={{ duration: 0.3 }}
              />
            </div>
            <div className="flex items-center gap-3 text-xs font-exo text-dim-400">
              <Activity className="w-3 h-3 text-cyan-400 animate-pulse" />
              <span className="flex-1">{progress.message}</span>
              <span className="text-dim-500 font-share-tech">{progress.elapsed_seconds}s</span>
            </div>
            <div className="flex items-center gap-4 text-xs font-share-tech text-dim-500">
              <span>Boards: <span className="text-ghost">{progress.boards_scanned}/{progress.boards_total}</span></span>
              {progress.boards_errors > 0 && <span className="text-red-400">{progress.boards_errors} errors</span>}
              <span>Jobs: <span className="text-neural">{progress.jobs_found}</span></span>
              {progress.jobs_evaluated > 0 && <span>Evaluated: <span className="text-plasma">{progress.jobs_evaluated}</span></span>}
            </div>
          </div>
        </motion.div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-dim-400" />
          <select value={filter} onChange={(e) => setFilter(e.target.value as Job['status'] | 'all')} className="input-cyan text-sm">
            <option value="all">All Jobs</option>
            <option value="new">New</option>
            <option value="reviewing">Reviewing</option>
            <option value="approved">Approved</option>
            <option value="applied">Applied</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-exo text-dim-400">Sort:</span>
          <button onClick={() => setSortBy('match')}
            className={`text-sm font-rajdhani font-semibold px-3 py-1.5 rounded-lg transition-all ${sortBy === 'match' ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20' : 'text-dim-400 hover:text-ghost'}`}>
            Match %
          </button>
          <button onClick={() => setSortBy('date')}
            className={`text-sm font-rajdhani font-semibold px-3 py-1.5 rounded-lg transition-all ${sortBy === 'date' ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20' : 'text-dim-400 hover:text-ghost'}`}>
            Date
          </button>
        </div>
      </div>

      {/* Job List */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 text-cyan-300 animate-spin" />
          <span className="ml-3 text-sm font-rajdhani text-dim-400">Loading jobs...</span>
        </div>
      ) : filteredJobs.length === 0 ? (
        <div className="text-center py-20">
          <p className="text-sm font-rajdhani text-dim-400">
            {jobs.length === 0 ? `No jobs found. Click "Scan Now" to search ${progress?.boards_total || 28} boards.` : 'No jobs match the current filter.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredJobs.slice(0, 30).map((job, i) => {
            return (
              <motion.div key={job.id} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }} className="glass-card-hover">
                <div className="flex items-start justify-between">
                  <div className="space-y-1.5 flex-1">
                    <div className="flex items-center gap-3">
                      <h3 className="text-base font-rajdhani font-semibold text-ghost">{job.title}</h3>
                      <span className={statusColors[job.status]}>{job.status.charAt(0).toUpperCase() + job.status.slice(1)}</span>
                    </div>
                    <p className="text-sm font-exo text-dim-400">{job.company}</p>
                    <div className="flex items-center gap-4 text-xs font-exo text-dim-400">
                      <span>{job.location || 'Remote'}</span>
                      <span>{job.salary}</span>
                      <span className="badge-dim text-hud">{job.source}</span>
                    </div>
                    {job.reasoning && <p className="text-xs font-exo text-dim-400 line-clamp-2">{job.reasoning}</p>}
                    {job.pros.length > 0 && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {job.pros.slice(0, 2).map((p, ri) => <span key={ri} className="text-hud text-xs text-neural bg-neural/8 px-1.5 py-0.5 rounded">{p}</span>)}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col items-center gap-1 ml-4 min-w-[60px]">
                    <div className={`w-14 h-14 rounded-full border-2 flex items-center justify-center text-base font-orbitron font-bold
                      ${job.match_percentage >= 80 ? 'text-neural border-neural' : job.match_percentage >= 60 ? 'text-plasma border-plasma' : 'text-dim-400 border-dim'}`}>
                      {job.match_percentage}%
                    </div>
                    <span className="text-hud font-share-tech text-dim-400">MATCH</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 mt-3 pt-3 border-t border-cyan-500/8">
                  {job.status === 'new' && (() => {
                    const btnState = applyingJobs[job.id] || 'idle'
                    const isBtnDisabled = btnState === 'loading' || btnState === 'success'
                    let btnContent
                    let btnClass = 'btn-cyan text-xs flex items-center gap-1.5'

                    if (btnState === 'loading') {
                      btnClass = 'btn-cyan text-xs flex items-center gap-1.5 opacity-70'
                      btnContent = <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Launching Agent...</>
                    } else if (btnState === 'success') {
                      btnClass = 'bg-green-500/10 text-green-400 border border-green-400/20 text-xs flex items-center gap-1.5'
                      btnContent = <><CheckCircle className="w-3.5 h-3.5" /> Queued ✓</>
                    } else if (btnState === 'error') {
                      btnClass = 'bg-red-500/10 text-red-400 border border-red-400/20 text-xs flex items-center gap-1.5'
                      btnContent = <><XCircle className="w-3.5 h-3.5" /> Retry</>
                    } else {
                      btnContent = <><CheckCircle className="w-3.5 h-3.5" /> Approve & Apply</>
                    }

                    return (
                      <button
                        onClick={() => handleApprove(job.id)}
                        disabled={isBtnDisabled}
                        className={btnClass}
                      >
                        {btnContent}
                      </button>
                    )
                  })()}
                  <button
                    onClick={() => setSelectedJob(job)}
                    className="btn-ghost-cyan text-xs flex items-center gap-1.5"
                  >
                    <ExternalLink className="w-3.5 h-3.5" /> View
                  </button>
                </div>
              </motion.div>
            )
          })}
        </div>
      )}
      {/* Job Detail Modal */}
      <AnimatePresence>
        {selectedJob && <JobDetailModal job={selectedJob} onClose={() => setSelectedJob(null)} />}
      </AnimatePresence>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1b. Job Detail Modal
// ═══════════════════════════════════════════════════════════════════════════════

function JobDetailModal({ job, onClose }: { job: Job; onClose: () => void }): JSX.Element {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.92, y: 30 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.92, y: 30 }}
        transition={{ type: 'spring', stiffness: 300, damping: 25 }}
        className="relative w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-xl border border-cyan-500/15 bg-void-900/95 shadow-2xl shadow-cyan-500/5 scroll-cyan"
        onClick={(e) => e.stopPropagation()}
      >
        <button onClick={onClose} className="absolute top-3 right-3 z-10 w-7 h-7 flex items-center justify-center rounded-full bg-void-800/80 text-dim-400 hover:text-ghost hover:bg-void-700/90 transition-all" aria-label="Close modal"><X className="w-4 h-4" /></button>
        <div className="p-5 pb-4 border-b border-cyan-500/10">
          <div className="flex items-start gap-4">
            <div className="flex-1 min-w-0">
              <h2 className="text-lg font-orbitron font-bold text-ghost leading-tight tracking-tight">{job.title}</h2>
              <p className="text-sm font-rajdhani font-semibold text-cyan-300 mt-0.5">{job.company}</p>
            </div>
            <div className="flex flex-col items-center flex-shrink-0">
              <div className={"w-14 h-14 rounded-full border-2 flex items-center justify-center text-base font-orbitron font-bold " + (job.match_percentage >= 80 ? 'text-neural border-neural' : job.match_percentage >= 60 ? 'text-plasma border-plasma' : 'text-dim-400 border-dim')}>{job.match_percentage}%</div>
              <span className="text-[10px] font-share-tech text-dim-400 mt-0.5">MATCH</span>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 mt-3">
            {job.location && <span className="text-xs font-exo text-dim-300 flex items-center gap-1 bg-void-800/50 px-2 py-0.5 rounded"><MapPin className="w-3 h-3 text-dim-400" /> {job.location}</span>}
            <span className="text-xs font-exo text-dim-300 bg-void-800/50 px-2 py-0.5 rounded">{job.salary}</span>
            <span className="badge-dim text-hud text-[10px]">{job.source}</span>
            <span className={"text-[10px] font-share-tech font-semibold px-1.5 py-0.5 rounded " + (statusColors[job.status] || 'badge-dim')}>{job.status.charAt(0).toUpperCase() + job.status.slice(1)}</span>
            {job.posted_date && <span className="text-[10px] font-share-tech text-dim-500 bg-void-800/50 px-2 py-0.5 rounded">{new Date(job.posted_date).toLocaleDateString()}</span>}
          </div>
        </div>
        <div className="p-5 space-y-5">
          {job.description && (
            <div>
              <h4 className="text-xs font-orbitron font-bold text-dim-400 tracking-wider mb-2 flex items-center gap-1.5"><FileText className="w-3.5 h-3.5 text-cyan-400" /> DESCRIPTION</h4>
              <div className="text-sm font-exo text-dim-200 leading-relaxed whitespace-pre-wrap bg-void-800/30 rounded-lg p-3 border border-void-600/20 max-h-60 overflow-y-auto scroll-cyan">{job.description}</div>
            </div>
          )}
          {job.reasoning && (
            <div>
              <h4 className="text-xs font-orbitron font-bold text-dim-400 tracking-wider mb-2 flex items-center gap-1.5"><Brain className="w-3.5 h-3.5 text-plasma" /> MATCH REASONING</h4>
              <p className="text-sm font-exo text-dim-200 leading-relaxed bg-void-800/30 rounded-lg p-3 border border-void-600/20">{job.reasoning}</p>
            </div>
          )}
          {(job.pros.length > 0 || job.cons.length > 0) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {job.pros.length > 0 && (
                <div className="bg-green-500/5 border border-green-500/10 rounded-lg p-3">
                  <h4 className="text-xs font-orbitron font-bold text-neural tracking-wider mb-2 flex items-center gap-1.5"><CheckCircle className="w-3 h-3" /> PROS</h4>
                  <ul className="space-y-1">{job.pros.map((p, i) => <li key={i} className="text-xs font-exo text-dim-300 flex items-start gap-1.5"><span className="text-neural mt-0.5 flex-shrink-0 font-bold">+</span><span>{p}</span></li>)}</ul>
                </div>
              )}
              {job.cons.length > 0 && (
                <div className="bg-red-500/5 border border-red-500/10 rounded-lg p-3">
                  <h4 className="text-xs font-orbitron font-bold text-red-400 tracking-wider mb-2 flex items-center gap-1.5"><XCircle className="w-3 h-3" /> CONS</h4>
                  <ul className="space-y-1">{job.cons.map((c, i) => <li key={i} className="text-xs font-exo text-dim-300 flex items-start gap-1.5"><span className="text-red-400 mt-0.5 flex-shrink-0 font-bold">−</span><span>{c}</span></li>)}</ul>
                </div>
              )}
            </div>
          )}
        </div>
        <div className="px-5 py-3.5 border-t border-cyan-500/10 flex items-center justify-between bg-void-800/30 rounded-b-xl">
          <button onClick={onClose} className="text-xs font-rajdhani font-semibold text-dim-400 hover:text-ghost px-3 py-1.5 rounded-lg hover:bg-void-700/50 transition-all">Close</button>
          <div className="flex items-center gap-2">
            {/* Search Online fallback — works even without a URL */}
            <button
              onClick={() => {
                const query = encodeURIComponent(`${job.title} ${job.company}`)
                const searchUrl = `https://www.google.com/search?q=${query}`
                window.barq.openExternal(searchUrl).catch((err) =>
                  console.error('[JobsPage] Failed to open search:', err)
                )
              }}
              className="btn-ghost-cyan text-xs flex items-center gap-1.5"
              title="Search for this job on Google"
            >
              <Search className="w-3.5 h-3.5" /> Search Online
            </button>
            {/* Open Job Posting — disabled when no valid URL */}
            {(() => {
              const hasValidUrl = typeof job.source_url === 'string' && (job.source_url.startsWith('http://') || job.source_url.startsWith('https://'))
              return (
                <div className="relative group">
                  <button
                    onClick={() => {
                      console.log('DEBUG URL:', job.source_url)
                      if (hasValidUrl && job.source_url.length > 10) {
                        window.barq.openExternal(job.source_url).catch((err) =>
                          console.error('[JobsPage] Failed to open URL:', err)
                        )
                      } else {
                        console.warn('[JobsPage] Invalid URL:', job.source_url)
                      }
                    }}
                    disabled={!hasValidUrl}
                    className={"btn-cyan text-xs flex items-center gap-1.5 " + (!hasValidUrl ? 'opacity-50 cursor-not-allowed' : '')}
                  >
                    <ExternalLink className="w-3.5 h-3.5" /> Open Job Posting
                  </button>
                  {/* Tooltip explaining why button is disabled */}
                  {!hasValidUrl && (
                    <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 px-2 py-1 bg-void-700 text-dim-300 text-[10px] font-rajdhani rounded shadow-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                      No job URL found — use Search Online instead
                      <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-void-700" />
                    </div>
                  )}
                </div>
              )
            })()}
          </div>
        </div>
      </motion.div>
    </motion.div>
  )
}
// ═══════════════════════════════════════════════════════════════════════════════
// 2. Response Rate Analytics
// ═══════════════════════════════════════════════════════════════════════════════

function ResponseAnalytics({ onNavigateToFilter }: { onNavigateToFilter?: (target: DrillTarget) => void }): JSX.Element {
  const [matchData, setMatchData] = useState<MatchAnalytics | null>(null)
  const [responseData, setResponseData] = useState<ResponseAnalytics | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      try {
        const [match, resp] = await Promise.all([
          api<MatchAnalytics>('/jobs/analytics/matches'),
          api<ResponseAnalytics>('/jobs/analytics/responses'),
        ])
        if (match) setMatchData(match)
        if (resp) setResponseData(resp)
      } catch { /* ignore */ }
      startTransition(() => setLoading(false))
    })()
  }, [])

  if (loading) return <div className="flex items-center justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-dim-400" /></div>
  if (!matchData) return <div className="text-center py-20"><p className="text-sm font-rajdhani text-dim-400">No analytics data yet. Start applying to jobs!</p></div>

  const hasResponseData = responseData && responseData.overall.total_applications > 0 && responseData.overall.submitted > 0

  // ── Helpers ────────────────────────────────────────────────────────────

  const totalJobs = matchData.total_jobs
  const evaluated = matchData.total_evaluated
  const tiers = matchData.score_tiers
  const topSources = matchData.top_sources
  const recentScans = matchData.recent_scans
  const appStatuses = matchData.application_statuses

  // Calculate a simple average match % across all tiers
  const avgMatchPct = tiers.length > 0
    ? Math.round(tiers.reduce((sum, t) => sum + t.avg_percentage * t.count, 0) / Math.max(tiers.reduce((sum, t) => sum + t.count, 0), 1))
    : 0

  const tierColors: Record<string, string> = {
    excellent: 'bg-neural/10 text-neural border-neural/30',
    strong: 'bg-cyan-500/10 text-cyan-300 border-cyan-500/20',
    good: 'bg-plasma/10 text-plasma border-plasma/20',
    fair: 'bg-dim/10 text-dim-400 border-dim/30',
  }

  const tierBarColors: Record<string, string> = {
    excellent: 'bg-neural',
    strong: 'bg-cyan-400',
    good: 'bg-plasma',
    fair: 'bg-dim-500',
  }

  return (
    <div className="space-y-4">
      {/* ── Match Summary KPI ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <AnalyticCard icon={Search} label="Jobs Scanned" value={totalJobs} color="text-cyan-300" />
        <AnalyticCard icon={Activity} label="Evaluated" value={evaluated} color="text-holographic" />
        <AnalyticCard icon={Target} label="Avg Match" value={`${avgMatchPct}%`} color="text-plasma" />
        <AnalyticCard icon={BarChart3} label="Queued Apps" value={appStatuses.reduce((s, a) => s + a.count, 0)} color="text-neural"
          onClick={onNavigateToFilter ? () => onNavigateToFilter({ status: 'approved' }) : undefined} />
      </div>

      {/* ── Score Tiers ──────────────────────────────────────────────────── */}
      <div className="glass-card">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="w-4 h-4 text-cyan-300" />
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Match Score Distribution</h3>
        </div>
        <div className="space-y-3">
          {tiers.length === 0 ? (
            <p className="text-xs font-exo text-dim-400 text-center py-4">No evaluations yet. Run a scan first.</p>
          ) : (
            tiers.map((t) => {
              const maxCount = Math.max(...tiers.map(x => x.count), 1)
              const pct = Math.round((t.count / maxCount) * 100)
              const minScoreForTier: Record<string, number> = {
                excellent: 80, strong: 70, good: 60, fair: 0,
              }
              const score = minScoreForTier[t.tier] ?? 0
              return (
                <div
                  key={t.tier}
                  onClick={onNavigateToFilter ? () => onNavigateToFilter({ minScore: score }) : undefined}
                  className={"space-y-1 transition-all " + (onNavigateToFilter ? 'cursor-pointer hover:scale-[1.01] active:scale-[0.99]' : '')}
                >
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-rajdhani font-semibold border ${tierColors[t.tier] || tierColors.fair}`}>
                        {t.tier === 'excellent' ? '80%+' : t.tier === 'strong' ? '70%+' : t.tier === 'good' ? '60%+' : '<60%'}
                      </span>
                      <span className="font-rajdhani font-semibold text-ghost">{t.count} jobs</span>
                    </div>
                    <span className="font-share-tech text-dim-400">{t.avg_percentage}% avg</span>
                  </div>
                  <div className="w-full h-2 bg-void-800/60 rounded-full overflow-hidden">
                    <motion.div
                      className={`h-full rounded-full ${tierBarColors[t.tier] || tierBarColors.fair}`}
                      initial={{ width: 0 }}
                      animate={{ width: `${pct}%` }}
                      transition={{ duration: 0.5, ease: 'easeOut' }}
                    />
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* ── Top Sources + App Statuses ────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="glass-card">
          <div className="flex items-center gap-2 mb-3">
            <BarChart3 className="w-3.5 h-3.5 text-cyan-300" />
            <h3 className="text-xs font-orbitron font-bold text-ghost tracking-wider">Top Sources</h3>
          </div>
          {topSources.length === 0 ? (
            <p className="text-xs font-exo text-dim-400 text-center py-4">No source data yet.</p>
          ) : (
            <div className="space-y-1.5">
              {topSources.slice(0, 6).map((s) => (
                <div
                  key={s.source}
                  onClick={onNavigateToFilter ? () => onNavigateToFilter({ sourceBoard: s.source }) : undefined}
                  className={"flex items-center justify-between bg-void-700/20 rounded-lg px-3 py-1.5 transition-all " +
                    (onNavigateToFilter ? 'cursor-pointer hover:bg-void-600/30 hover:scale-[1.02] active:scale-[0.98]' : '')
                    }
                >
                  <span className="text-xs font-rajdhani font-semibold text-ghost">{s.source}</span>
                  <div className="flex items-center gap-3 text-[10px] font-share-tech">
                    <span className="text-dim-400">{s.job_count} jobs</span>
                    {s.avg_match > 0 && <span className="text-plasma">{s.avg_match}% avg</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="glass-card">
          <div className="flex items-center gap-2 mb-3">
            <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
            <h3 className="text-xs font-orbitron font-bold text-ghost tracking-wider">Application Status</h3>
          </div>
          {appStatuses.length === 0 ? (
            <p className="text-xs font-exo text-dim-400 text-center py-4">No applications yet.</p>
          ) : (
            <div className="space-y-1.5">
              {appStatuses.map((a) => {
                const targetStatus = _mapJobStatus(a.status)
                return (
                  <div
                    key={a.status}
                    onClick={onNavigateToFilter ? () => onNavigateToFilter({ status: targetStatus }) : undefined}
                    className={"flex items-center justify-between bg-void-700/20 rounded-lg px-3 py-1.5 transition-all cursor-pointer " +
                      (onNavigateToFilter ? 'hover:bg-void-600/30 hover:scale-[1.02] active:scale-[0.98]' : '')
                    }
                  >
                    <span className="text-xs font-rajdhani font-semibold text-ghost capitalize">{a.status.replace(/_/g, ' ')}</span>
                    <span className="text-xs font-orbitron font-bold text-cyan-300">{a.count}</span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── Recent Scans ─────────────────────────────────────────────────── */}
      {recentScans.length > 0 && (
        <div className="glass-card">
          <div className="flex items-center gap-2 mb-3">
            <RefreshCw className="w-3.5 h-3.5 text-dim-400" />
            <h3 className="text-xs font-orbitron font-bold text-ghost tracking-wider">Recent Activity</h3>
          </div>
          <div className="space-y-1.5 max-h-32 overflow-y-auto scroll-cyan">
            {recentScans.map((s, i) => (
              <div key={i} className="text-xs font-exo text-dim-400 flex items-start gap-2">
                <span className="text-dim-600 mt-0.5">•</span>
                <span>{s.summary}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Response Analytics ───────────────────────────────────────────── */}
      {hasResponseData && (
        <>
          <div className="border-t border-cyan-500/10 pt-4">
            <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-3 flex items-center gap-2">
              <Send className="w-4 h-4 text-cyan-300" />
              Response Analytics
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
              <AnalyticCard icon={Send} label="Submitted" value={responseData.overall.submitted} color="text-cyan-300" />
              <AnalyticCard icon={Activity} label="Response Rate" value={`${responseData.overall.response_rate}%`} color="text-holographic" />
              <AnalyticCard icon={UserCheck} label="Interviews" value={responseData.overall.interviews} color="text-neural" />
              <AnalyticCard icon={Target} label="Offer Rate" value={`${responseData.overall.offer_rate}%`} color="text-plasma" />
              <AnalyticCard icon={AlertCircle} label="Need Follow-up" value={responseData.overall.pending_followup} color="text-amber-400" />
            </div>

            {/* Funnel */}
            {responseData.funnel.length > 0 && (
              <div className="glass-card mb-4">
                <div className="flex items-center gap-2 mb-4">
                  <TrendingUp className="w-4 h-4 text-cyan-300" />
                  <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Application Funnel</h3>
                </div>
                <div className="space-y-3">
                  {responseData.funnel.map((m) => {
                    const maxVal = Math.max(m.submitted, 1)
                    return (
                      <div key={m.month} className="space-y-1">
                        <div className="flex items-center justify-between text-xs font-exo">
                          <span className="text-ghost">{m.month}</span>
                          <span className="text-dim-400">{m.submitted} submitted → {m.offers} offers</span>
                        </div>
                        <div className="flex h-6 gap-0.5 rounded overflow-hidden">
                          <div className="bg-cyan-500/30 transition-all" style={{ width: `${(m.submitted / maxVal) * 100}%` }} />
                          <div className="bg-purple-500/30 transition-all" style={{ width: `${(m.responded / maxVal) * 100}%` }} />
                          <div className="bg-neural/30 transition-all" style={{ width: `${(m.interviews / maxVal) * 100}%` }} />
                          <div className="bg-amber-400/30 transition-all" style={{ width: `${(m.offers / maxVal) * 100}%` }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
                <div className="flex items-center gap-4 mt-3 text-hud text-xs text-dim-400">
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-cyan-500/50" /> Submitted</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-purple-500/50" /> Responded</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-neural/50" /> Interviews</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded bg-amber-400/50" /> Offers</span>
                </div>
              </div>
            )}

            {/* By Source Board */}
            {responseData.by_source.length > 0 && (
              <div className="glass-card">
                <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-3">By Source Board</h3>
                <div className="space-y-2">
                  {responseData.by_source.map((s) => (
                    <div key={s.source} className="flex items-center justify-between bg-void-700/20 rounded-lg px-3 py-2">
                      <div>
                        <span className="text-sm font-rajdhani font-semibold text-ghost">{s.source}</span>
                        <span className="text-xs font-exo text-dim-400 ml-2">{s.total} apps</span>
                      </div>
                      <div className="flex items-center gap-3 text-xs font-share-tech">
                        <span className="text-neural">{s.response_rate}% rate</span>
                        <span className="text-purple-400">{s.interviews} interviews</span>
                        <span className="text-dim-400">{s.avg_response_time_days ? `${s.avg_response_time_days}d avg` : '—'}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Recent Responses */}
            {responseData.recent_responses.length > 0 && (
              <div className="glass-card">
                <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-3">Recent Responses</h3>
                <div className="space-y-2 max-h-64 overflow-y-auto scroll-cyan">
                  {responseData.recent_responses.map((r) => (
                    <div key={r.id} className="flex items-center justify-between bg-void-700/20 rounded-lg px-3 py-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-rajdhani font-semibold text-ghost truncate">{r.title}</p>
                        <p className="text-hud text-dim-400 truncate">{r.company} · {r.source}</p>
                      </div>
                      <div className="flex items-center gap-2 text-xs">
                        <span className={`px-1.5 py-0.5 rounded font-share-tech ${
                          r.type === 'interview' ? 'bg-neural/10 text-neural' :
                          r.type === 'offer' ? 'bg-amber-400/10 text-amber-400' :
                          'bg-red-400/10 text-red-400'
                        }`}>{r.type}</span>
                        <span className="text-dim-500">{r.date?.slice(0, 10)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function AnalyticCard({ icon: Icon, label, value, color, onClick }: { icon: typeof Search; label: string; value: number | string; color: string; onClick?: () => void }): JSX.Element {
  return (
    <motion.div
      className={"glass-card !p-3 " + (onClick ? 'cursor-pointer hover:scale-[1.03] hover:border-cyan-500/30 hover:shadow-lg hover:shadow-cyan-500/5 active:scale-[0.97] transition-all duration-200' : '')}
      onClick={onClick}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
    >
      <div className="flex items-center gap-2 mb-1">
        <Icon className={`w-3.5 h-3.5 ${color}`} />
        <span className="text-hud text-dim-400 text-xs uppercase tracking-wider">{label}</span>
      </div>
      <p className={`text-lg font-orbitron font-bold ${color}`}>{value}</p>
    </motion.div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 3. Resume-Based Role Suggestions
// ═══════════════════════════════════════════════════════════════════════════════

interface RoleSuggestion {
  title: string
  match_score: number
  reasoning: string
  matched_skills: string[]
}

function RoleSuggestions({ onSearchRole }: { onSearchRole?: (role: string) => void }): JSX.Element {
  const [suggestions, setSuggestions] = useState<RoleSuggestion[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    (async () => {
      setLoading(true)
      try {
        const resp = await api<{ suggestions?: RoleSuggestion[]; resume_info?: { name: string; skills_count: number; experience_count: number } }>('/jobs/suggestions')
        if (resp?.suggestions) {
          setSuggestions(resp.suggestions)
        } else {
          setError('No suggestions available')
        }
      } catch {
        setError('Failed to load suggestions')
      }
      setLoading(false)
    })()
  }, [])

  const handleSearchRole = useCallback((role: string) => {
    if (onSearchRole) {
      onSearchRole(role)
    } else {
      // Fallback: copy to clipboard
      navigator.clipboard.writeText(role)
    }
  }, [onSearchRole])

  if (loading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="w-6 h-6 text-cyan-300 animate-spin" /><span className="ml-3 text-sm font-rajdhani text-dim-400">Analyzing your resume...</span></div>
  }

  if (error) {
    return (
      <div className="glass-card p-6 text-center">
        <Lightbulb className="w-8 h-8 text-dim-600 mx-auto mb-2" />
        <p className="text-sm font-rajdhani text-dim-400">{error}</p>
        <p className="text-xs font-exo text-dim-500 mt-1">Make sure your resume is saved and try again.</p>
      </div>
    )
  }

  if (suggestions.length === 0) {
    return (
      <div className="glass-card p-6 text-center">
        <Lightbulb className="w-8 h-8 text-dim-600 mx-auto mb-2" />
        <p className="text-sm font-rajdhani text-dim-400">No role suggestions yet. Update your resume and refresh.</p>
      </div>
    )
  }

  const maxScore = Math.max(...suggestions.map(s => s.match_score), 1)

  return (
    <div className="space-y-4">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider flex items-center gap-2">
          <Lightbulb className="w-4 h-4 text-amber-400" />
          RECOMMENDED ROLES
        </h3>
        <p className="text-xs font-exo text-dim-400 mt-1">
          Job titles you should target based on your resume. Higher match = better fit.
        </p>
      </motion.div>

      <div className="grid gap-3">
        {suggestions.map((s, i) => {
          const pct = Math.round((s.match_score / maxScore) * 100)
          return (
            <motion.div
              key={s.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="glass-card-hover"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0 space-y-2">
                  <div className="flex items-center gap-2">
                    <h4 className="text-base font-rajdhani font-semibold text-ghost">{s.title}</h4>
                    <span className={"text-[10px] font-share-tech font-semibold px-1.5 py-0.5 rounded " +
                      (s.match_score >= 80 ? 'bg-neural/10 text-neural' :
                       s.match_score >= 60 ? 'bg-cyan-500/10 text-cyan-300' :
                       'bg-plasma/10 text-plasma')
                    }>{s.match_score}% match</span>
                  </div>
                  <p className="text-xs font-exo text-dim-400 leading-relaxed">{s.reasoning}</p>
                  {s.matched_skills.length > 0 && (
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {s.matched_skills.map((skill) => (
                        <span key={skill} className="text-[10px] font-share-tech text-cyan-300 bg-cyan-500/8 px-1.5 py-0.5 rounded border border-cyan-500/10">
                          {skill}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex-shrink-0 flex flex-col items-center">
                  <div className={"w-14 h-14 rounded-full border-2 flex items-center justify-center text-base font-orbitron font-bold " +
                    (s.match_score >= 80 ? 'text-neural border-neural' :
                     s.match_score >= 60 ? 'text-cyan-300 border-cyan-400' :
                     'text-plasma border-plasma')
                  }>
                    {s.match_score}%
                  </div>
                  <span className="text-hud font-share-tech text-dim-500 mt-0.5">MATCH</span>
                </div>
              </div>
              <div className="mt-3 pt-3 border-t border-cyan-500/8 flex items-center gap-2">
                <button
                  onClick={() => handleSearchRole(s.title)}
                  className="btn-ghost-cyan text-xs flex items-center gap-1.5"
                >
                  <Search className="w-3.5 h-3.5" />
                  Search Jobs
                </button>
              </div>
              {/* Score bar */}
              <div className="mt-2 w-full h-1.5 bg-void-800/60 rounded-full overflow-hidden">
                <motion.div
                  className={"h-full rounded-full " +
                    (s.match_score >= 80 ? 'bg-gradient-to-r from-neural to-cyan-400' :
                     s.match_score >= 60 ? 'bg-gradient-to-r from-cyan-500 to-blue-500' :
                     'bg-gradient-to-r from-plasma to-amber-400')
                  }
                  initial={{ width: 0 }}
                  animate={{ width: `${pct}%` }}
                  transition={{ duration: 0.6, delay: i * 0.08, ease: 'easeOut' }}
                />
              </div>
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 4. Follow-Up Automation
// ═══════════════════════════════════════════════════════════════

function FollowUpPanel(): JSX.Element {
  const [candidates, setCandidates] = useState<FollowupCandidate[]>([])
  const [history, setHistory] = useState<Array<{id:number;application_id:number;company:string;title:string;followup_number:number;sent_at:string}>>([])
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState<Record<number, boolean>>({})
  const [msg, setMsg] = useState<{text:string;type:'success'|'error'}|null>(null)
  const [showHistory, setShowHistory] = useState(false)

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const [candResp, histResp] = await Promise.all([
        api<{candidates:FollowupCandidate[];count:number}>('/jobs/followups/candidates'),
        api<{history:Array<{id:number;application_id:number;company:string;title:string;followup_number:number;sent_at:string}>;count:number}>('/jobs/followups/history'),
      ])
      if (candResp?.candidates) setCandidates(candResp.candidates)
      if (histResp?.history) setHistory(histResp.history)
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const handleSendFollowup = useCallback(async (candidate: FollowupCandidate) => {
    setSending(prev => ({ ...prev, [candidate.id]: true }))
    setMsg(null)
    try {
      const resp = await api('/jobs/followups/send', {
        application_id: candidate.id,
        followup_number: 1,
      })
      if (resp && typeof resp === 'object') {
        const data = resp as Record<string, unknown>
        if (data.status === 'sent') {
          setMsg({ text: 'Sent!', type: 'success' })
          setCandidates(prev => prev.filter(c => c.id !== candidate.id))
          setTimeout(() => setMsg(null), 3000)
        } else {
          setMsg({ text: 'Failed to send', type: 'error' })
          setTimeout(() => setMsg(null), 3000)
        }
      }
    } catch {
      setMsg({ text: 'Request failed', type: 'error' })
      setTimeout(() => setMsg(null), 3000)
    }
    setSending(prev => ({ ...prev, [candidate.id]: false }))
  }, [])

  return (
    <div className="space-y-4">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider flex items-center gap-2">
            <Mail className="w-4 h-4 text-cyan-400" />
            FOLLOW-UP AUTOMATION
          </h3>
          <p className="text-xs font-exo text-dim-400 mt-1">Applications needing a gentle nudge ({candidates.length} pending)</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowHistory(!showHistory)} className="btn-ghost-cyan text-xs flex items-center gap-1.5">
            <RefreshCw className="w-3 h-3" />
            {showHistory ? 'Hide History' : 'History'} ({history.length})
          </button>
          <button onClick={fetchData} className="btn-ghost-cyan text-xs">
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>
      </motion.div>

      {/* Toast message */}
      <AnimatePresence>
        {msg && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className={'text-xs font-rajdhani font-semibold px-3 py-1.5 rounded-lg border flex items-center gap-1.5 ' + (msg.type === 'success' ? 'bg-green-500/10 text-green-400 border-green-400/20' : 'bg-red-500/10 text-red-400 border-red-400/20')}
          >
            {msg.type === 'success' ? <CheckCircle className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
            {msg.text}
          </motion.div>
        )}
      </AnimatePresence>

      {/* History panel */}
      <AnimatePresence>
        {showHistory && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="glass-card overflow-hidden"
          >
            <div className="p-3">
              <h4 className="text-xs font-rajdhani font-semibold text-ghost mb-2 flex items-center gap-1.5">
                <Send className="w-3 h-3 text-cyan-400" />
                Sent Follow-Ups
              </h4>
              {history.length === 0 ? (
                <p className="text-xs font-exo text-dim-500 text-center py-2">No follow-ups sent yet</p>
              ) : (
                <div className="space-y-1 max-h-40 overflow-y-auto scroll-cyan">
                  {history.map((h) => (
                    <div key={h.id} className="flex items-center justify-between bg-void-800/30 rounded px-2.5 py-1.5">
                      <div>
                        <p className="text-[11px] font-exo text-dim-400">{h.title} @ {h.company}</p>
                        <p className="text-[10px] font-share-tech text-dim-600">Follow-up #{h.followup_number}</p>
                      </div>
                      <span className="text-[10px] font-share-tech text-dim-500">{new Date(h.sent_at).toLocaleDateString()}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Candidates list */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-5 h-5 animate-spin text-cyan-300" />
          <span className="ml-2 text-xs font-rajdhani text-dim-400">Loading candidates...</span>
        </div>
      ) : candidates.length === 0 ? (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center py-16">
          <div className="w-16 h-16 rounded-full bg-cyan-500/5 border border-cyan-500/10 flex items-center justify-center mx-auto mb-3">
            <Mail className="w-7 h-7 text-dim-400" />
          </div>
          <p className="text-sm font-rajdhani text-dim-400">No applications need follow-up right now</p>
          <p className="text-xs font-exo text-dim-500 mt-1">Candidates appear here 14+ days after submission</p>
        </motion.div>
      ) : (
        <div className="space-y-2">
          {candidates.map((c, i) => (
            <motion.div key={c.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }} className="glass-card-hover">
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-rajdhani font-semibold text-ghost">{c.title}</h4>
                    <span className="badge-cyan text-[10px]">{c.source_board}</span>
                  </div>
                  <p className="text-xs font-exo text-dim-400">{c.company}</p>
                  <div className="flex items-center gap-3 text-[10px] font-share-tech">
                    <span>Submitted: {new Date(c.submitted_at).toLocaleDateString()}</span>
                    <span className={c.days_since_submission >= 21 ? 'text-amber-400' : 'text-dim-500'}>
                      {c.days_since_submission} days ago
                      {c.days_since_submission >= 21 && ' ⚠️ overdue'}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => handleSendFollowup(c)}
                  disabled={sending[c.id]}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-rajdhani font-semibold rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 hover:bg-cyan-500/20 transition-all disabled:opacity-40 min-w-[120px] justify-center"
                >
                  {sending[c.id] ? (
                    <><Loader2 className="w-3 h-3 animate-spin" /> Sending...</>
                  ) : (
                    <><Send className="w-3 h-3" /> Send Follow-Up</>
                  )}
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════
// 4. Application Pipeline — Enhanced Real-Time UI
// ═══════════════════════════════════════════════════════════════════════════════

interface PipelineProgress {
  status: string
  phase: string
  phase_index: number
  total_phases: number
  progress_pct: number
  jobs_total: number
  jobs_processed: number
  jobs_succeeded: number
  jobs_failed: number
  current_job: string
  message: string
  started_at: number | null
  elapsed_seconds: number
  results: Array<{
    application_id: number
    job_listing_id: number
    title: string
    company: string
    url: string
    match_percentage: number
    status: string
    optimized_resume: string
    cover_letter: string
    pdf_paths: Record<string, string>
    telegram_sent: boolean
    auto_applied: boolean
    error: string
  }>
}

interface PipelineSettings {
  mode: 'notify' | 'auto_apply'
  auto_apply: boolean
  max_per_run: number
  generate_pdf: boolean
  send_telegram: boolean
  min_match_score: number
}

// ─── Pipeline Phase Config ────────────────────────────────────────────────

const PIPELINE_PHASES = [
  { id: 0, icon: '📄', label: 'Load Resume', desc: 'Parse user resume' },
  { id: 1, icon: '📋', label: 'Fetch Jobs', desc: 'Load approved listings' },
  { id: 2, icon: '✏️', label: 'Optimize', desc: 'Tailor resume per JD' },
  { id: 3, icon: '✉️', label: 'Cover Letter', desc: 'AI-generated letter' },
  { id: 4, icon: '📎', label: 'Documents', desc: 'Generate PDFs' },
  { id: 5, icon: '📲', label: 'Notify', desc: 'Telegram & auto-apply' },
] as const

// ─── Helper: format seconds ───────────────────────────────────────────────

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}m ${s}s`
}

// ═══════════════════════════════════════════════════════════════════════════
// Circular Progress Ring
// ═══════════════════════════════════════════════════════════════════════════

function CircularProgress({ pct, size = 80, strokeWidth = 5 }: { pct: number; size?: number; strokeWidth?: number }): JSX.Element {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (pct / 100) * circumference
  return (
    <svg width={size} height={size} className="transform -rotate-90 drop-shadow-lg">
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="rgba(0,229,255,0.08)" strokeWidth={strokeWidth} />
      <motion.circle
        cx={size / 2} cy={size / 2} r={radius} fill="none"
        stroke="url(#progressGrad)" strokeWidth={strokeWidth}
        strokeLinecap="round" strokeDasharray={circumference}
        initial={{ strokeDashoffset: circumference }}
        animate={{ strokeDashoffset: offset }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      />
      <defs>
        <linearGradient id="progressGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#00E5FF" />
          <stop offset="100%" stopColor="#8B5CF6" />
        </linearGradient>
      </defs>
    </svg>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// Animated Counter
// ═══════════════════════════════════════════════════════════════════════════

function AnimatedCounter({ value, label, color = 'text-cyan-300' }: { value: number; label: string; color?: string }): JSX.Element {
  return (
    <motion.div
      className="text-center"
      initial={{ scale: 0.8, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: 'spring', stiffness: 300, damping: 20 }}
    >
      <motion.span
        key={value}
        className={`block text-lg font-orbitron font-bold ${color}`}
        initial={{ y: -10, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.2 }}
      >
        {value}
      </motion.span>
      <span className="text-hud text-[10px] font-exo text-dim-500 uppercase tracking-wider">{label}</span>
    </motion.div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// PipelinePanel
// ═══════════════════════════════════════════════════════════════════════════

function PipelinePanel(): JSX.Element {
  const [progress, setProgress] = usePersistentState<PipelineProgress | null>('JobsPage.pipeline.progress', null)
  const [running, setRunning] = usePersistentState('JobsPage.pipeline.running', false)
  const [settings, setSettings] = usePersistentState<PipelineSettings>('JobsPage.pipeline.settings', {
    mode: 'notify',
    auto_apply: false,
    max_per_run: 10,
    generate_pdf: true,
    send_telegram: true,
    min_match_score: 60,
  })
  const [showResults, setShowResults] = usePersistentState('JobsPage.pipeline.showResults', false)
  const [liveLogs, setLiveLogs] = usePersistentState<string[]>('JobsPage.pipeline.liveLogs', [])
  const logEndRef = useRef<HTMLDivElement | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Resume upload state
  const [resumeContent, setResumeContent] = useState('')
  const [resumeInfo, setResumeInfo] = useState<{ exists: boolean; full_name: string; skills_count: number; char_count: number } | null>(null)
  const [resumeUploading, setResumeUploading] = useState(false)
  const [resumeSavedMsg, setResumeSavedMsg] = useState('')
  const [resumeUploadMode, setResumeUploadMode] = useState<'markdown' | 'pdf'>('markdown')
  const [pdfUploading, setPdfUploading] = useState(false)
  const [pdfUploadResult, setPdfUploadResult] = useState<{ message: string; parsed?: { full_name?: string; skills_count?: number; page_count?: number } } | null>(null)
  const [pdfUploadError, setPdfUploadError] = useState<string | null>(null)
  const pdfInputRef = useRef<HTMLInputElement | null>(null)

  // Auto-scroll log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [liveLogs])

  // Fetch resume info on mount
  useEffect(() => {
    (async () => {
      const data = await api<{
        exists?: boolean; parsed?: { full_name?: string; skills_count?: number };
        char_count?: number
      }>('/jobs/resume')
      if (data) {
        setResumeInfo({
          exists: Boolean(data.exists),
          full_name: data?.parsed?.full_name || '',
          skills_count: Number(data?.parsed?.skills_count || 0),
          char_count: Number(data?.char_count || 0),
        })
      }
    })()
  }, [])

  const handleResumeUpload = useCallback(async () => {
    if (!resumeContent.trim() || resumeContent.trim().length < 50) return
    setResumeUploading(true)
    setResumeSavedMsg('')
    try {
      const resp = await api('/jobs/resume/upload', { content: resumeContent })
      if (resp && typeof resp === 'object') {
        const data = resp as Record<string, unknown>
        if (data.status === 'saved') {
          setResumeSavedMsg('✅ Resume saved! The pipeline will use this file.')
          setResumeInfo(prev => prev ? { ...prev, exists: true, char_count: resumeContent.length } : { exists: true, full_name: '', skills_count: 0, char_count: resumeContent.length })
          setTimeout(() => setResumeSavedMsg(''), 5000)
        }
      }
    } catch {
      setResumeSavedMsg('❌ Failed to save resume')
      setTimeout(() => setResumeSavedMsg(''), 3000)
    }
    setResumeUploading(false)
  }, [resumeContent])

  const uploadPdfResume = useCallback(async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setPdfUploadError('Only PDF files are accepted')
      setTimeout(() => setPdfUploadError(null), 5000)
      return
    }
    if (file.size > 10 * 1024 * 1024) {
      setPdfUploadError('PDF file exceeds 10MB limit')
      setTimeout(() => setPdfUploadError(null), 5000)
      return
    }
    setPdfUploading(true)
    setPdfUploadResult(null)
    setPdfUploadError(null)
    try {
      // Read the file as base64 so we can send it through the IPC bridge
      // (api() utility goes through the main process — no CORS issues).
      // Direct fetch() from the Electron renderer to a remote backend can
      // fail due to CORS preflight / web security.
      const reader = new FileReader()
      const base64Data = await new Promise<string>((resolve, reject) => {
        reader.onload = () => {
          const result = reader.result as string
          // Strip the "data:application/pdf;base64," prefix
          const comma = result.indexOf(',')
          resolve(comma >= 0 ? result.slice(comma + 1) : result)
        }
        reader.onerror = () => reject(reader.error)
        reader.readAsDataURL(file)
      })

      const resp = await api<{ status: string; message: string; char_count?: number; page_count?: number; parsed?: { full_name?: string; skills_count?: number; experience_count?: number } }>('/jobs/resume/upload-pdf-base64', {
        filename: file.name,
        data: base64Data,
      })

      if (resp?.status === 'saved') {
        setPdfUploadResult({
          message: resp.message || 'Resume extracted from PDF',
          parsed: {
            full_name: resp?.parsed?.full_name || '',
            skills_count: Number(resp?.parsed?.skills_count || 0),
            page_count: Number(data?.page_count || 0),
          },
        })
        // Refresh resume info
        const resumeData = await api<{ exists?: boolean; parsed?: { full_name?: string; skills_count?: number }; char_count?: number }>('/jobs/resume')
        if (resumeData) {
          setResumeInfo({
            exists: Boolean(resumeData.exists),
            full_name: resumeData?.parsed?.full_name || '',
            skills_count: Number(resumeData?.parsed?.skills_count || 0),
            char_count: Number(resumeData?.char_count || 0),
          })
        }
      }
    } catch (err) {
      setPdfUploadError(err instanceof Error ? err.message : 'Failed to upload PDF')
      setTimeout(() => setPdfUploadError(null), 5000)
    }
    setPdfUploading(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Fetch settings on mount
  useEffect(() => {
    (async () => {
      const data = await api('/jobs/pipeline/settings')
      if (data) {
        startTransition(() => {
          setSettings(prev => ({ ...prev, ...(data as Partial<PipelineSettings>) }))
        })
      }
    })()
  }, [])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const data = await api<PipelineProgress>('/jobs/pipeline/progress')
        if (data) {
          setProgress(data)
          // Add log entry for each unique message
          setLiveLogs(prev => {
            if (!data.message) return prev
            const newEntry = `[${formatDuration(data.elapsed_seconds)}] ${data.message}`
            const last = prev[prev.length - 1] || ''
            // Only add when message actually changes
            if (last === newEntry) return prev
            return [...prev, newEntry].slice(-50)
          })
          if (data.status === 'complete' || data.status === 'error') {
            if (pollRef.current) clearInterval(pollRef.current)
            pollRef.current = null
            setRunning(false)
            setShowResults(true)
            setLiveLogs(prev => [...prev, `[${formatDuration(data.elapsed_seconds)}] ${data.status === 'complete' ? '✅ Pipeline complete!' : '❌ Pipeline failed'}`])
          }
        }
      } catch { /* ignore */ }
    }, 1000)
  }, [])

  const handleRunPipeline = useCallback(async () => {
    setRunning(true)
    setShowResults(false)
    setLiveLogs(['[0s] 🚀 Starting pipeline...'])
    setProgress({
      status: 'starting', phase: 'Starting pipeline...', phase_index: 0,
      total_phases: 6, progress_pct: 0, jobs_total: 0, jobs_processed: 0,
      jobs_succeeded: 0, jobs_failed: 0, current_job: '', message: 'Initializing...',
      started_at: Date.now() / 1000, elapsed_seconds: 0, results: [],
    })
    try {
      await window.barq?.jobs.pipeline.run({
        mode: settings.mode,
        auto_apply: settings.auto_apply,
        max_per_run: settings.max_per_run,
        generate_pdf: settings.generate_pdf,
        send_telegram: settings.send_telegram,
        min_match_score: settings.min_match_score,
      })
      startPolling()
      // Safety timeout: auto-stop polling after 15 minutes
      setTimeout(() => {
        if (pollRef.current) {
          clearInterval(pollRef.current)
          pollRef.current = null
          setRunning(false)
        }
      }, 900_000)
    } catch {
      setRunning(false)
    }
  }, [settings, startPolling])

  const isActivePipeline = running && progress && ['running', 'starting'].includes(progress.status)
  const isComplete = progress?.status === 'complete' || progress?.status === 'error'
  const results = progress?.results ?? []

  // ETA calculation
  const speed = progress?.elapsed_seconds && progress.jobs_processed > 0
    ? progress.elapsed_seconds / progress.jobs_processed
    : 0
  const remainingJobs = progress ? Math.max(0, progress.jobs_total - progress.jobs_processed) : 0
  const etaSeconds = speed * remainingJobs

  // Current phase index for the flow stepper
  const currentPhaseIdx = progress?.phase_index ?? 0

  return (
    <div className="space-y-5">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h3 className="text-base font-orbitron font-bold text-ghost tracking-wider flex items-center gap-2">
            <Activity className="w-4 h-4 text-cyan-400" />
            APPLICATION PIPELINE
          </h3>
          <p className="text-xs font-exo text-dim-400 mt-1">
            Resume optimization → Cover letters → PDFs → Telegram notifications in one click
          </p>
        </div>
        <button
          onClick={handleRunPipeline}
          disabled={running}
          className="btn-cyan flex items-center gap-2 px-5 py-2.5"
        >
          {running ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="text-xs">Processing...</span>
            </>
          ) : (
            <>
              <Activity className="w-4 h-4" />
              <span className="text-xs">Run Pipeline</span>
            </>
          )}
        </button>
      </motion.div>

      {/* ── Pipeline Flow Stepper ───────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="glass-card overflow-hidden"
      >
        <div className="px-4 py-3">
          <div className="flex items-start justify-between gap-0 relative">
            {/* Background connecting line */}
            <div className="absolute top-5 left-[5%] right-[5%] h-px bg-void-700/50" />
            {/* Active connecting line fill */}
            {isActivePipeline && (
              <motion.div
                className="absolute top-5 left-[5%] h-px bg-gradient-to-r from-cyan-400 via-blue-500 to-purple-500"
                initial={{ width: '0%' }}
                animate={{ width: `${Math.min(90, ((currentPhaseIdx) / (PIPELINE_PHASES.length - 1)) * 90)}%` }}
                transition={{ duration: 0.4, ease: 'easeOut' }}
              />
            )}
            {PIPELINE_PHASES.map((phase, idx) => {
              const isCompleted = progress && idx < currentPhaseIdx
              const isCurrent = progress && idx === currentPhaseIdx
              const isPending = !progress || idx > currentPhaseIdx

              return (
                <div key={phase.id} className="flex flex-col items-center gap-1.5 z-10 flex-1 min-w-0">
                  <motion.div
                    className={`w-9 h-9 rounded-full flex items-center justify-center text-sm
                      transition-all duration-300 shadow-lg
                      ${isCompleted ? 'bg-green-500/20 border border-green-400/30 shadow-green-500/10' : ''}
                      ${isCurrent ? 'bg-cyan-500/20 border-2 border-cyan-400 shadow-glow-cyan-sm' : ''}
                      ${isPending ? 'bg-void-800/60 border border-void-600/30' : ''}
                    `}
                    animate={isCurrent ? { scale: [1, 1.08, 1] } : { scale: 1 }}
                    transition={{ duration: 2, repeat: isCurrent ? Infinity : 0, ease: 'easeInOut' }}
                  >
                    {isCompleted ? '✅' : isCurrent ? <Loader2 className="w-4 h-4 animate-spin text-cyan-300" /> : phase.icon}
                  </motion.div>
                  <span className={`text-[10px] font-rajdhani font-semibold text-center leading-tight
                    ${isCompleted ? 'text-green-400' : ''}
                    ${isCurrent ? 'text-cyan-300' : ''}
                    ${isPending ? 'text-dim-500' : ''}
                  `}>
                    {phase.label}
                  </span>
                  <span className="text-[9px] font-exo text-dim-600 text-center leading-tight hidden md:block">
                    {phase.desc}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
        {/* Phase description bar */}
        {isActivePipeline && progress && (
          <motion.div
            key={progress.phase}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            className="bg-cyan-500/5 border-t border-cyan-500/8 px-4 py-2 flex items-center gap-2"
          >
            <span className="text-xs font-rajdhani font-semibold text-cyan-300">
              {PIPELINE_PHASES[currentPhaseIdx]?.icon} {progress.phase}
            </span>
            <span className="text-[10px] font-exo text-dim-400 flex-1 truncate">{progress.message}</span>
            <span className="text-[10px] font-share-tech text-dim-500">{progress.progress_pct}%</span>
          </motion.div>
        )}
      </motion.div>

      {/* ── Live Progress Dashboard ─────────────────────────────────────── */}
      {isActivePipeline && progress && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-card overflow-hidden"
        >
          <div className="flex items-center gap-6 p-4">
            {/* Circular progress */}
            <div className="relative flex-shrink-0">
              <CircularProgress pct={progress.progress_pct} size={80} />
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-sm font-orbitron font-bold text-cyan-300">{progress.progress_pct}%</span>
              </div>
            </div>

            {/* Stats grid */}
            <div className="flex-1 grid grid-cols-2 sm:grid-cols-4 gap-3">
              <AnimatedCounter value={progress.jobs_total} label="Total Jobs" color="text-ghost" />
              <AnimatedCounter value={progress.jobs_processed} label="Processed" color="text-cyan-300" />
              <AnimatedCounter value={progress.jobs_succeeded} label="Succeeded" color="text-neural" />
              <AnimatedCounter value={progress.jobs_failed} label="Failed" color={progress.jobs_failed > 0 ? 'text-red-400' : 'text-dim-400'} />
            </div>

            {/* Elapsed / ETA */}
            <div className="flex-shrink-0 text-right">
              <div className="text-xs font-share-tech text-dim-500">Elapsed</div>
              <div className="text-sm font-orbitron font-bold text-ghost">{formatDuration(progress.elapsed_seconds)}</div>
              {progress.jobs_processed > 1 && remainingJobs > 0 && (
                <>
                  <div className="text-xs font-share-tech text-dim-500 mt-1">ETA</div>
                  <div className="text-xs font-orbitron font-bold text-purple-400">{formatDuration(etaSeconds)}</div>
                </>
              )}
            </div>
          </div>

          {/* Mini progress bar */}
          <div className="h-1 w-full bg-void-800/60">
            <motion.div
              className="h-full bg-gradient-to-r from-cyan-500 via-blue-500 to-purple-500"
              initial={{ width: 0 }}
              animate={{ width: `${progress.progress_pct}%` }}
              transition={{ duration: 0.3 }}
            />
          </div>
        </motion.div>
      )}

      {/* ── Live Log Stream ─────────────────────────────────────────────── */}
      {isActivePipeline && liveLogs.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="glass-card !p-0 overflow-hidden"
        >
          <div className="flex items-center gap-2 px-4 py-2 border-b border-cyan-500/8 bg-void-900/40">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span className="text-xs font-rajdhani font-semibold text-dim-400 uppercase tracking-wider">Live Log</span>
            <span className="text-[10px] font-share-tech text-dim-500 ml-auto">{liveLogs.length} entries</span>
          </div>
          <div className="max-h-36 overflow-y-auto scroll-cyan p-3 space-y-1 font-mono bg-black/30">
            {liveLogs.map((entry, i) => {
              const isError = entry.includes('❌') || entry.includes('failed')
              const isSuccess = entry.includes('✅') || entry.includes('complete')
              const isProgress = entry.includes('→') || entry.includes('...') || entry.includes('generating')
              return (
                <div
                  key={i}
                  className={`text-[10px] leading-5
                    ${isError ? 'text-red-400' : ''}
                    ${isSuccess ? 'text-green-400' : ''}
                    ${isProgress ? 'text-cyan-300' : ''}
                    ${!isError && !isSuccess && !isProgress ? 'text-dim-400' : ''}
                  `}
                >
                  <span className="text-dim-600">$</span> {entry}
                </div>
              )
            })}
            <div ref={logEndRef} />
          </div>
        </motion.div>
      )}

      {/* ── Settings Card ────────────────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className={`glass-card transition-all duration-300 ${running ? 'opacity-50 pointer-events-none' : ''}`}
      >
        <h4 className="text-xs font-orbitron font-bold text-dim-400 tracking-wider mb-3 flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_rgba(0,229,255,0.5)]" />
          PIPELINE SETTINGS
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Mode Toggle */}
          <div className="space-y-1.5">
            <label className="text-hud text-xs font-rajdhani font-semibold text-dim-400">Pipeline Mode</label>
            <div className="flex gap-2">
              <button
                onClick={() => setSettings(prev => ({ ...prev, mode: 'notify', auto_apply: false, send_telegram: true }))}
                className={`flex-1 px-3 py-2 text-[11px] font-rajdhani font-semibold rounded-lg transition-all ${settings.mode === 'notify' ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 shadow-glow-cyan-sm' : 'bg-void-800/40 text-dim-400 border border-transparent hover:border-cyan-500/10'}`}
              >
                📲 Notify
              </button>
              <button
                onClick={() => setSettings(prev => ({ ...prev, mode: 'auto_apply', auto_apply: true, send_telegram: true }))}
                className={`flex-1 px-3 py-2 text-[11px] font-rajdhani font-semibold rounded-lg transition-all ${settings.mode === 'auto_apply' ? 'bg-plasma/10 text-plasma border border-plasma/20 shadow-glow-plasma-sm' : 'bg-void-800/40 text-dim-400 border border-transparent hover:border-plasma/10'}`}
              >
                🤖 Auto Apply
              </button>
            </div>
          </div>

          {/* Min Match Score */}
          <div className="space-y-1.5">
            <label className="text-hud text-xs font-rajdhani font-semibold text-dim-400">
              Min Match Score: <span className="text-cyan-300 tabular-nums">{settings.min_match_score}%</span>
            </label>
            <input
              type="range"
              min={30}
              max={95}
              step={5}
              value={settings.min_match_score}
              onChange={(e) => setSettings(prev => ({ ...prev, min_match_score: Number(e.target.value) }))}
              className="w-full h-1.5 rounded-full appearance-none bg-void-800/60 accent-cyan-400 cursor-pointer"
            />
            <div className="flex justify-between text-hud text-[10px] text-dim-500">
              <span>30%</span>
              <span>95%</span>
            </div>
          </div>

          {/* Max Per Run */}
          <div className="space-y-1.5">
            <label className="text-hud text-xs font-rajdhani font-semibold text-dim-400">
              Jobs per Run: <span className="text-cyan-300 tabular-nums">{settings.max_per_run}</span>
            </label>
            <input
              type="range"
              min={1}
              max={25}
              step={1}
              value={settings.max_per_run}
              onChange={(e) => setSettings(prev => ({ ...prev, max_per_run: Number(e.target.value) }))}
              className="w-full h-1.5 rounded-full appearance-none bg-void-800/60 accent-cyan-400 cursor-pointer"
            />
            <div className="flex justify-between text-hud text-[10px] text-dim-500">
              <span>1</span>
              <span>25</span>
            </div>
          </div>
        </div>

        {/* Toggles */}
        <div className="flex items-center gap-4 mt-3 pt-3 border-t border-cyan-500/8">
          <label className="flex items-center gap-2 cursor-pointer group">
            <input
              type="checkbox"
              checked={settings.generate_pdf}
              onChange={(e) => setSettings(prev => ({ ...prev, generate_pdf: e.target.checked }))}
              className="w-3.5 h-3.5 rounded accent-cyan-400"
            />
            <span className="text-[11px] font-exo text-dim-400 group-hover:text-ghost transition-colors">Generate PDFs</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer group">
            <input
              type="checkbox"
              checked={settings.send_telegram}
              onChange={(e) => setSettings(prev => ({ ...prev, send_telegram: e.target.checked }))}
              className="w-3.5 h-3.5 rounded accent-cyan-400"
            />
            <span className="text-[11px] font-exo text-dim-400 group-hover:text-ghost transition-colors">Send Telegram</span>
          </label>
        </div>
      </motion.div>

      {/* ── Resume Upload ────────────────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25 }}
        className={`glass-card transition-all duration-300 ${running ? 'opacity-50 pointer-events-none' : ''}`}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">📄</span>
            <h4 className="text-xs font-orbitron font-bold text-ghost tracking-wider uppercase">Resume</h4>
          </div>
          {resumeInfo?.exists ? (
            <span className="flex items-center gap-1.5 text-xs font-exo text-green-400">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.5)] animate-pulse" />
              {resumeInfo.full_name || 'Resume'} ({resumeInfo.skills_count} skills, {resumeInfo.char_count} chars)
            </span>
          ) : (
            <span className="text-xs font-exo text-amber-400 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.5)] animate-pulse" />
              Not found — upload below
            </span>
          )}
        </div>

        {/* ── Upload type tabs ──────────────────────────────────────────── */}
        <div className="flex gap-2 mb-3">
          <button
            onClick={() => setResumeUploadMode('markdown')}
            className={`px-3 py-1.5 text-[10px] font-rajdhani font-semibold rounded-lg transition-all ${
              resumeUploadMode === 'markdown'
                ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20'
                : 'bg-void-800/40 text-dim-400 border border-transparent hover:border-cyan-500/10'
            }`}
          >
            ✏️ Paste Markdown
          </button>
          <button
            onClick={() => setResumeUploadMode('pdf')}
            className={`px-3 py-1.5 text-[10px] font-rajdhani font-semibold rounded-lg transition-all ${
              resumeUploadMode === 'pdf'
                ? 'bg-plasma/10 text-plasma border border-plasma/20'
                : 'bg-void-800/40 text-dim-400 border border-transparent hover:border-plasma/10'
            }`}
          >
            📎 Upload PDF
          </button>
        </div>

        {/* ── Markdown paste mode ──────────────────────────────────────── */}
        {resumeUploadMode === 'markdown' && (
          <>
            <p className="text-xs font-exo text-dim-400 mb-3">
              Paste your resume markdown below. The pipeline reads from <code className="bg-void-800/40 px-1.5 py-0.5 rounded text-cyan-300 text-[10px]">~/career-ops/cv.md</code>.
            </p>
            <textarea
              value={resumeContent}
              onChange={(e) => setResumeContent(e.target.value)}
              placeholder="Paste your resume here (markdown format, at least 50 chars)..."
              rows={5}
              className="w-full bg-void-800/60 text-ghost text-xs font-mono px-3 py-2 rounded-lg border border-cyan-500/15 focus:outline-none focus:border-cyan-500/30 focus:shadow-glow-cyan-sm placeholder:text-dim-500 resize-none transition-all duration-200"
            />
            <div className="flex items-center justify-between mt-2">
              <div className="flex items-center gap-2">
                <button
                  onClick={handleResumeUpload}
                  disabled={resumeUploading || resumeContent.trim().length < 50}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-rajdhani font-semibold rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 hover:bg-cyan-500/20 hover:shadow-glow-cyan-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {resumeUploading ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3" />}
                  {resumeUploading ? 'Saving...' : 'Upload Resume'}
                </button>
                {resumeSavedMsg && (
                  <motion.span
                    initial={{ opacity: 0, x: -5 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="text-[10px] font-exo text-green-400"
                  >
                    {resumeSavedMsg}
                  </motion.span>
                )}
              </div>
              <span className="text-[10px] font-exo text-dim-500">
                {resumeContent.length > 0 ? `${resumeContent.length} chars` : ''}
              </span>
            </div>
          </>
        )}

        {/* ── PDF upload mode ──────────────────────────────────────────── */}
        {resumeUploadMode === 'pdf' && (
          <>
            <p className="text-xs font-exo text-dim-400 mb-3">
              Upload a PDF resume. Text will be extracted and saved to <code className="bg-void-800/40 px-1.5 py-0.5 rounded text-cyan-300 text-[10px]">~/career-ops/cv.md</code>.
            </p>
            <div
              onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('border-cyan-400') }}
              onDragLeave={(e) => e.currentTarget.classList.remove('border-cyan-400')}
              onDrop={async (e) => {
                e.preventDefault();
                e.currentTarget.classList.remove('border-cyan-400');
                const file = e.dataTransfer.files[0];
                if (file) await uploadPdfResume(file);
              }}
              className="border-2 border-dashed border-void-600/40 rounded-xl p-8 text-center
                         hover:border-cyan-500/30 transition-all cursor-pointer
                         bg-void-900/30 hover:bg-void-800/40 group"
            >
              <input
                ref={pdfInputRef}
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (file) await uploadPdfResume(file);
                }}
              />
              <motion.div
                className="flex flex-col items-center gap-2"
                whileHover={{ scale: 1.02 }}
              >
                <Upload className="w-8 h-8 text-dim-400 group-hover:text-cyan-300 transition-colors" />
                <p className="text-xs font-rajdhani font-semibold text-dim-400 group-hover:text-ghost transition-colors">
                  Drop your PDF here or click to browse
                </p>
                <p className="text-[10px] font-exo text-dim-500">
                  Max 10MB · Text-based PDFs only
                </p>
              </motion.div>
              <button
                onClick={() => pdfInputRef.current?.click()}
                className="mt-3 px-4 py-2 text-xs font-rajdhani font-semibold rounded-lg
                           bg-plasma/10 text-plasma border border-plasma/20
                           hover:bg-plasma/20 hover:shadow-glow-plasma-sm transition-all"
              >
                <Upload className="w-3.5 h-3.5 inline mr-1.5" />
                Select PDF File
              </button>
            </div>
            {pdfUploading && (
              <div className="flex items-center gap-2 mt-3 text-xs font-rajdhani text-cyan-300">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Extracting text from PDF...
              </div>
            )}
            {pdfUploadResult && (
              <motion.div
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                className="mt-3 p-3 rounded-lg bg-green-500/5 border border-green-500/20"
              >
                <div className="flex items-start gap-2">
                  <CheckCircle className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-xs font-rajdhani font-semibold text-green-400">
                      {pdfUploadResult.message}
                    </p>
                    {pdfUploadResult.parsed && (
                      <p className="text-[10px] font-exo text-dim-400 mt-1">
                        Found: {pdfUploadResult.parsed.full_name || 'Unknown'} · {pdfUploadResult.parsed.skills_count} skills · {pdfUploadResult.page_count} pages
                      </p>
                    )}
                  </div>
                </div>
              </motion.div>
            )}
            {pdfUploadError && (
              <motion.div
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                className="mt-3 p-3 rounded-lg bg-red-500/5 border border-red-500/20"
              >
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                  <p className="text-xs font-rajdhani text-red-400">{pdfUploadError}</p>
                </div>
              </motion.div>
            )}
          </>
        )}
      </motion.div>

      {/* ── Live Job Processing Feed ─────────────────────────────────────── */}
      {isActivePipeline && progress && progress.current_job && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass-card overflow-hidden"
        >
          <div className="flex items-center gap-2 px-4 py-2 border-b border-cyan-500/8">
            <Loader2 className="w-3 h-3 animate-spin text-cyan-400" />
            <span className="text-xs font-rajdhani font-semibold text-dim-400 uppercase tracking-wider">Currently Processing</span>
          </div>
          <motion.div
            key={progress.current_job}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="p-4 flex items-center gap-4"
          >
            {/* Processing indicator */}
            <div className="relative w-10 h-10 flex-shrink-0">
              <motion.div
                className="absolute inset-0 rounded-full border-2 border-cyan-400"
                animate={{ rotate: 360 }}
                transition={{ duration: 1.5, repeat: Infinity, ease: 'linear' }}
              />
              <div className="absolute inset-0 flex items-center justify-center">
                <Loader2 className="w-4 h-4 text-cyan-300 animate-spin" />
              </div>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-rajdhani font-semibold text-ghost truncate">{progress.current_job}</p>
              <p className="text-[10px] font-exo text-dim-400">{progress.message}</p>
            </div>
            <div className="flex items-center gap-3 text-xs font-share-tech text-dim-500">
              <span className="text-ghost">{progress.jobs_processed}/{progress.jobs_total}</span>
              {progress.jobs_succeeded > 0 && <span className="text-neural">✓{progress.jobs_succeeded}</span>}
              {progress.jobs_failed > 0 && <span className="text-red-400">✗{progress.jobs_failed}</span>}
            </div>
          </motion.div>
        </motion.div>
      )}

      {/* ── Completion Celebration ───────────────────────────────────────── */}
      {isComplete && progress && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className={`glass-card overflow-hidden border ${progress.status === 'error' ? 'border-red-500/20' : 'border-neural/20'}`}
        >
          {/* Confetti-like header */}
          <div className={`px-4 py-4 ${progress.status === 'error' ? 'bg-red-500/5' : 'bg-gradient-to-r from-green-500/5 via-cyan-500/5 to-purple-500/5'}`}>
            <div className="flex items-center gap-3">
              <motion.span
                initial={{ rotate: -20, scale: 0 }}
                animate={{ rotate: 0, scale: 1 }}
                transition={{ type: 'spring', stiffness: 200 }}
                className="text-3xl"
              >
                {progress.status === 'error' ? '⚠️' : '🎉'}
              </motion.span>
              <div className="flex-1">
                <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">
                  Pipeline {progress.status === 'error' ? 'Failed' : 'Complete'}
                </h3>
                <p className="text-xs font-exo text-dim-400 mt-0.5">{progress.message}</p>
              </div>
              <div className="flex items-center gap-4 text-xs font-share-tech">
                <div className="text-center">
                  <div className="text-sm font-orbitron font-bold text-neural">{progress.jobs_succeeded}</div>
                  <div className="text-[9px] text-dim-500 uppercase tracking-wider">Succeeded</div>
                </div>
                {progress.jobs_failed > 0 && (
                  <div className="text-center">
                    <div className="text-sm font-orbitron font-bold text-red-400">{progress.jobs_failed}</div>
                    <div className="text-[9px] text-dim-500 uppercase tracking-wider">Failed</div>
                  </div>
                )}
                <div className="text-center">
                  <div className="text-sm font-orbitron font-bold text-ghost">{formatDuration(progress.elapsed_seconds)}</div>
                  <div className="text-[9px] text-dim-500 uppercase tracking-wider">Duration</div>
                </div>
              </div>
            </div>
          </div>

          {/* Success/Fail Rate bar */}
          {progress.jobs_total > 0 && (
            <div className="h-1.5 w-full bg-void-800/60">
              <motion.div
                className="h-full bg-gradient-to-r from-green-400 to-cyan-400"
                initial={{ width: 0 }}
                animate={{ width: `${progress.jobs_total > 0 ? (progress.jobs_succeeded / progress.jobs_total) * 100 : 0}%` }}
                transition={{ duration: 0.6, ease: 'easeOut' }}
              />
            </div>
          )}
        </motion.div>
      )}

      {/* ── Results Section ───────────────────────────────────────────────── */}
      {showResults && results.length > 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-3">
          <h4 className="text-xs font-orbitron font-bold text-ghost tracking-wider flex items-center gap-2">
            <CheckCircle className="w-3.5 h-3.5 text-neural" />
            Results <span className="text-dim-400 font-exo font-normal">({results.length} jobs)</span>
          </h4>
          <div className="grid gap-2">
            {results.map((r, i) => (
              <motion.div
                key={`${r.application_id}-${i}`}
                initial={{ opacity: 0, y: 10, x: -10 }}
                animate={{ opacity: 1, y: 0, x: 0 }}
                transition={{ delay: i * 0.04, type: 'spring', stiffness: 200, damping: 25 }}
                className={`glass-card-hover !p-3 ${r.status === 'failed' ? 'border-red-500/10 hover:border-red-500/20' : ''}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1 flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <motion.span
                        initial={{ rotate: -30, opacity: 0 }}
                        animate={{ rotate: 0, opacity: 1 }}
                        transition={{ delay: i * 0.04 + 0.2 }}
                      >
                        {r.status === 'completed' ? '✅' : '❌'}
                      </motion.span>
                      <h4 className="text-sm font-rajdhani font-semibold text-ghost truncate">{r.title}</h4>
                      <span className="text-xs font-exo text-dim-400 hidden sm:inline">{r.company}</span>
                    </div>
                    <div className="flex items-center gap-3 text-hud text-xs flex-wrap">
                      {r.match_percentage > 0 && (
                        <span className={`font-share-tech ${r.match_percentage >= 80 ? 'text-neural' : r.match_percentage >= 60 ? 'text-plasma' : 'text-dim-400'}`}>
                          {r.match_percentage}% match
                        </span>
                      )}
                      {r.telegram_sent && <span className="text-cyan-300 flex items-center gap-1">📲 Telegram</span>}
                      {r.auto_applied && <span className="text-purple-400 flex items-center gap-1">🤖 Applied</span>}
                      {r.url && (
                        <a href={r.url} target="_blank" rel="noopener noreferrer" className="text-cyan-300 hover:text-cyan-200 underline underline-offset-2 flex items-center gap-1">
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                    {r.error && <p className="text-xs font-exo text-red-400">{r.error}</p>}
                    {r.pdf_paths && Object.keys(r.pdf_paths).length > 0 && (
                      <div className="flex items-center gap-2 mt-1.5">
                        {Object.entries(r.pdf_paths).map(([type, path]) => (
                          <span key={type} className="text-hud text-[10px] text-dim-500 bg-void-800/40 px-1.5 py-0.5 rounded border border-void-600/20">
                            📎 {type.charAt(0).toUpperCase() + type.slice(1)}: {path.split(/[/\\]/).pop()}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  {/* Match badge */}
                  {r.match_percentage > 0 && (
                    <div className={`w-10 h-10 rounded-full border-2 flex items-center justify-center text-xs font-orbitron font-bold flex-shrink-0
                      ${r.match_percentage >= 80 ? 'text-neural border-neural/40' : r.match_percentage >= 60 ? 'text-plasma border-plasma/40' : 'text-dim-400 border-dim/30'}`}>
                      {r.match_percentage}%
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}

      {/* ── Empty State ───────────────────────────────────────────────────── */}
      {!running && !progress && !showResults && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card text-center py-14 space-y-4"
        >
          <motion.div
            animate={{ y: [0, -4, 0] }}
            transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
          >
            <Activity className="w-12 h-12 text-dim-500 mx-auto" />
          </motion.div>
          <div>
            <p className="text-sm font-rajdhani font-semibold text-ghost">
              Ready to Process Applications
            </p>
            <p className="text-xs font-exo text-dim-400 mt-1 max-w-lg mx-auto">
              The pipeline will parse your resume, optimize it for each job description,
              generate tailored cover letters and PDFs, then notify you on Telegram.
            </p>
          </div>

          {/* Flow diagram */}
          <div className="flex items-center justify-center gap-2 py-3 overflow-x-auto">
            {PIPELINE_PHASES.map((phase, i) => (
              <div key={phase.id} className="flex items-center gap-2">
                <div className="flex flex-col items-center gap-1 min-w-[56px]">
                  <div className="w-8 h-8 rounded-full bg-void-800/60 border border-void-600/20 flex items-center justify-center text-sm">
                    {phase.icon}
                  </div>
                  <span className="text-[9px] font-rajdhani font-semibold text-dim-500 text-center leading-tight">{phase.label}</span>
                </div>
                {i < PIPELINE_PHASES.length - 1 && (
                  <span className="text-dim-600 text-xs pb-5">→</span>
                )}
              </div>
            ))}
          </div>

          <div className="flex items-center justify-center gap-6 text-[10px] font-exo text-dim-500 flex-wrap">
            <span>📄 Resume → ✏️ Optimize → ✉️ Cover Letter → 📎 PDFs → 📲 Telegram</span>
          </div>
        </motion.div>
      )}

      {/* ── Idle with results still visible ──────────────────────────────── */}
      {!running && !isActivePipeline && !progress && showResults && (
        <div className="text-center py-6">
          <p className="text-xs font-rajdhani text-dim-400">
            Run the pipeline again to process new applications.
          </p>
        </div>
      )}
    </div>
  )
}
