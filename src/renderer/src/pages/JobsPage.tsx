import { useState, useEffect, useCallback, useRef, startTransition } from 'react'
import {
  Search, Filter, ExternalLink, CheckCircle,
  Loader2, Activity, BarChart3, Mail, Send, RefreshCw,
  TrendingUp, Target, AlertCircle, UserCheck,
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

interface FollowupCandidate {
  id: number
  title: string
  company: string
  source_board: string
  days_since_submission: number
  submitted_at: string
}

// ─── Tab Config ───────────────────────────────────────────────────────────────

type TabKey = 'listings' | 'analytics' | 'followups'

const TABS: { key: TabKey; label: string; icon: typeof Search }[] = [
  { key: 'listings', label: 'Job Listings', icon: Search },
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

export function JobsPage(): JSX.Element {
  const [activeTab, setActiveTab] = useState<TabKey>('listings')

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-4">
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
          {activeTab === 'listings' && <JobListings />}
          {activeTab === 'analytics' && <ResponseAnalytics />}
          {activeTab === 'followups' && <FollowUpPanel />}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1. Job Listings (existing functionality + enhanced sources)
// ═══════════════════════════════════════════════════════════════════════════════

function JobListings(): JSX.Element {
  const [jobs, setJobs] = useState<Job[]>([])
  const [filter, setFilter] = useState<Job['status'] | 'all'>('all')
  const [sortBy, setSortBy] = useState<'match' | 'date'>('match')
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [progress, setProgress] = useState<ScanProgress | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchJobs = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await window.barq?.python.request('/jobs/matches?limit=50')
      const data = (resp as { success?: boolean; data?: { matches?: Record<string, unknown>[] } })?.data
      const matches = data?.matches ?? []
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
          status: 'new' as Job['status'],
          reasoning: String(m['reasoning'] ?? ''),
          pros,
          cons,
        }
      }))
    } catch { setJobs([]) }
    setLoading(false)
  }, [])

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchJobs() }, [fetchJobs])

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const startPolling = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const resp = await window.barq?.python.request('/jobs/scan/progress')
        if (resp && typeof resp === 'object') {
          const p = resp as Record<string, unknown>
          setProgress({
            status: String(p.status || ''),
            phase: String(p.phase || ''),
            phase_index: Number(p.phase_index || 0),
            total_phases: Number(p.total_phases || 4),
            progress_pct: Number(p.progress_pct || 0),
            boards_total: Number(p.boards_total || 0),
            boards_scanned: Number(p.boards_scanned || 0),
            boards_errors: Number(p.boards_errors || 0),
            jobs_found: Number(p.jobs_found || 0),
            jobs_evaluated: Number(p.jobs_evaluated || 0),
            message: String(p.message || ''),
            started_at: p.started_at as number | null,
            elapsed_seconds: Number(p.elapsed_seconds || 0),
          })
          if (p.status === 'complete' || p.status === 'error') {
            if (pollRef.current) clearInterval(pollRef.current)
            pollRef.current = null
            setScanning(false)
            await fetchJobs()
          }
        }
      } catch { /* ignore */ }
    }, 800)
  }, [fetchJobs])

  const handleScan = async (): Promise<void> => {
    setScanning(true)
    setProgress({
      status: 'starting', phase: 'Initializing scan...', phase_index: 0,
      total_phases: 4, progress_pct: 0, boards_total: 13, boards_scanned: 0,
      boards_errors: 0, jobs_found: 0, jobs_evaluated: 0,
      message: 'Starting scan (13 boards)...', started_at: Date.now() / 1000, elapsed_seconds: 0,
    })
    try {
      await window.barq?.python.request('/jobs/scan')
      startPolling()
      setTimeout(() => {
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; setScanning(false); fetchJobs() }
      }, 300_000)
    } catch { setScanning(false); setProgress(null); await fetchJobs() }
  }

  const handleApprove = async (jobId: string): Promise<void> => {
    await window.barq?.jobs.approve(jobId)
    setJobs((prev) => prev.map((j) => j.id === jobId ? { ...j, status: 'approved' as Job['status'] } : j))
  }

  const filteredJobs = jobs
    .filter((job) => filter === 'all' || job.status === filter)
    .sort((a, b) => sortBy === 'match' ? b.match_percentage - a.match_percentage : a.posted_date.localeCompare(b.posted_date))

  const isActiveScan = scanning && progress && ['scanning', 'evaluating', 'starting'].includes(progress.status)

  return (
    <div className="space-y-6">
      {/* Header + Scan Button */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-rajdhani text-dim-400">
            {jobs.length} jobs loaded — scanning 13 boards
          </p>
        </div>
        <button onClick={handleScan} disabled={scanning} className="btn-cyan flex items-center gap-2">
          {scanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          {scanning ? 'Scanning...' : 'Scan Now'}
        </button>
      </div>

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
            {jobs.length === 0 ? 'No jobs found. Click "Scan Now" to search 13 boards.' : 'No jobs match the current filter.'}
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
                  {job.status === 'new' && (
                    <button onClick={() => handleApprove(job.id)} className="btn-cyan text-xs flex items-center gap-1.5">
                      <CheckCircle className="w-3.5 h-3.5" /> Approve & Apply
                    </button>
                  )}
                  <button className="btn-ghost-cyan text-xs flex items-center gap-1.5">
                    <ExternalLink className="w-3.5 h-3.5" /> View
                  </button>
                </div>
              </motion.div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 2. Response Rate Analytics
// ═══════════════════════════════════════════════════════════════════════════════

function ResponseAnalytics(): JSX.Element {
  const [analytics, setAnalytics] = useState<ResponseAnalytics | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      try {
        const resp = await window.barq?.jobs.responseAnalytics()
        if (resp?.success && resp.data) setAnalytics(resp.data as ResponseAnalytics)
      } catch { /* ignore */ }
      startTransition(() => setLoading(false))
    })()
  }, [])

  if (loading) return <div className="flex items-center justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-dim-400" /></div>
  if (!analytics) return <div className="text-center py-20"><p className="text-sm font-rajdhani text-dim-400">No analytics data yet. Start applying to jobs!</p></div>

  const { overall, by_source, funnel, recent_responses } = analytics

  return (
    <div className="space-y-4">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <KPICard icon={Send} label="Submitted" value={overall.submitted} color="text-cyan-300" />
        <KPICard icon={Activity} label="Response Rate" value={`${overall.response_rate}%`} color="text-holographic" />
        <KPICard icon={UserCheck} label="Interviews" value={overall.interviews} color="text-neural" />
        <KPICard icon={Target} label="Offer Rate" value={`${overall.offer_rate}%`} color="text-plasma" />
        <KPICard icon={AlertCircle} label="Need Follow-up" value={overall.pending_followup} color="text-amber-400" />
      </div>

      {/* Funnel Chart */}
      <div className="glass-card">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="w-4 h-4 text-cyan-300" />
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Application Funnel</h3>
        </div>
        <div className="space-y-3">
          {funnel.map((m) => {
            const maxVal = Math.max(m.submitted, 1)
            return (
              <div key={m.month} className="space-y-1">
                <div className="flex items-center justify-between text-xs font-exo">
                  <span className="text-ghost">{m.month}</span>
                  <span className="text-dim-400">{m.submitted} submitted → {m.offers} offers</span>
                </div>
                <div className="flex h-6 gap-0.5 rounded overflow-hidden">
                  <div className="bg-cyan-500/30 transition-all" style={{ width: `${(m.submitted / maxVal) * 100}%` }} title={`Submitted: ${m.submitted}`} />
                  <div className="bg-purple-500/30 transition-all" style={{ width: `${(m.responded / maxVal) * 100}%` }} title={`Responded: ${m.responded}`} />
                  <div className="bg-neural/30 transition-all" style={{ width: `${(m.interviews / maxVal) * 100}%` }} title={`Interviews: ${m.interviews}`} />
                  <div className="bg-amber-400/30 transition-all" style={{ width: `${(m.offers / maxVal) * 100}%` }} title={`Offers: ${m.offers}`} />
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

      {/* By Source */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="glass-card">
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-3">By Source Board</h3>
          <div className="space-y-2">
            {by_source.map((s) => (
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

        <div className="glass-card">
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-3">Recent Responses</h3>
          <div className="space-y-2 max-h-64 overflow-y-auto scroll-cyan">
            {recent_responses.map((r) => (
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
      </div>
    </div>
  )
}

function KPICard({ icon: Icon, label, value, color }: { icon: typeof Send; label: string; value: number | string; color: string }): JSX.Element {
  return (
    <div className="glass-card !p-3">
      <div className="flex items-center gap-2 mb-1">
        <Icon className={`w-3.5 h-3.5 ${color}`} />
        <span className="text-hud text-dim-400 text-xs uppercase tracking-wider">{label}</span>
      </div>
      <p className={`text-lg font-orbitron font-bold ${color}`}>{value}</p>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 3. Follow-Up Automation
// ═══════════════════════════════════════════════════════════════════════════════

function FollowUpPanel(): JSX.Element {
  const [candidates, setCandidates] = useState<FollowupCandidate[]>([])
  const [scheduled, setScheduled] = useState<Array<{ application_id: number; company: string; title: string; followup_number: number; followup_text: string }>>([])
  const [loading, setLoading] = useState(true)
  const [scheduling, setScheduling] = useState(false)
  const [sending, setSending] = useState<number | null>(null)

  const fetchCandidates = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await window.barq?.jobs.followupCandidates()
      if (resp?.success && resp.data) {
        const d = resp.data as { candidates: FollowupCandidate[] }
        setCandidates(d.candidates || [])
      }
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { fetchCandidates() }, [fetchCandidates])

  const handleSchedule = useCallback(async () => {
    setScheduling(true)
    try {
      const resp = await window.barq?.jobs.scheduleFollowups()
      if (resp?.success && resp.data) {
        const d = resp.data as { scheduled: typeof scheduled }
        setScheduled(d.scheduled || [])
        await fetchCandidates()
      }
    } catch { /* ignore */ }
    setScheduling(false)
  }, [fetchCandidates])

  const handleSend = useCallback(async (appId: number, followupNum: number) => {
    setSending(appId)
    try {
      await window.barq?.jobs.sendFollowup({ application_id: appId, followup_number: followupNum })
      setScheduled((prev) => prev.filter((s) => s.application_id !== appId))
      setCandidates((prev) => prev.filter((c) => c.id !== appId))
    } catch { /* ignore */ }
    setSending(null)
  }, [])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Follow-Up Automation</h3>
          <p className="text-xs font-exo text-dim-400 mt-1">
            {candidates.length} applications need follow-up (submitted &gt; 14 days, no response)
          </p>
        </div>
        <button onClick={handleSchedule} disabled={scheduling} className="btn-cyan text-xs flex items-center gap-1.5">
          {scheduling ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          Check & Schedule
        </button>
      </div>

      {/* Scheduled follow-ups */}
      {scheduled.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-xs font-orbitron font-semibold text-holographic tracking-wider">Draft Follow-ups ({scheduled.length})</h4>
          {scheduled.map((s, i) => (
            <motion.div key={s.application_id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="glass-card">
              <div className="flex items-start justify-between mb-2">
                <div>
                  <p className="text-sm font-rajdhani font-semibold text-ghost">{s.company} — {s.title}</p>
                  <p className="text-hud text-cyan-300 text-xs">Follow-up #{s.followup_number}</p>
                </div>
                <button
                  onClick={() => handleSend(s.application_id, s.followup_number)}
                  disabled={sending === s.application_id}
                  className="btn-cyan text-xs flex items-center gap-1.5"
                >
                  {sending === s.application_id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
                  Mark Sent
                </button>
              </div>
              <pre className="bg-void-900/60 rounded-lg p-3 text-hud text-dim-300 text-xs max-h-32 overflow-y-auto font-mono whitespace-pre-wrap">
                {s.followup_text}
              </pre>
            </motion.div>
          ))}
        </div>
      )}

      {/* Candidates needing follow-up */}
      {loading ? (
        <div className="flex items-center justify-center py-12"><Loader2 className="w-5 h-5 animate-spin text-dim-400" /></div>
      ) : candidates.length === 0 ? (
        <div className="text-center py-12">
          <CheckCircle className="w-8 h-8 text-neural mx-auto mb-2" />
          <p className="text-sm font-rajdhani text-dim-400">No follow-ups needed right now!</p>
        </div>
      ) : (
        <div className="space-y-2">
          {candidates.map((c) => (
            <div key={c.id} className="flex items-center justify-between bg-void-700/20 rounded-lg px-4 py-3 border border-cyan-500/5">
              <div className="flex-1">
                <p className="text-sm font-rajdhani font-semibold text-ghost">{c.company} — {c.title}</p>
                <p className="text-hud text-dim-400 text-xs">
                  {c.source_board} · {Math.round(c.days_since_submission)} days since submission
                </p>
              </div>
              <span className="text-xs font-share-tech text-amber-400 bg-amber-400/10 px-2 py-1 rounded">
                {Math.round(c.days_since_submission)}d
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
