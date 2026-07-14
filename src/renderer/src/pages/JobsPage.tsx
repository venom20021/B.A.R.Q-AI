import { useState, useEffect, useCallback, useRef, startTransition } from 'react'
import { api } from '../utils/api'
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

type TabKey = 'listings' | 'analytics' | 'followups' | 'pipeline'

const TABS: { key: TabKey; label: string; icon: typeof Search }[] = [
  { key: 'listings', label: 'Job Listings', icon: Search },
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
          {activeTab === 'pipeline' && <PipelinePanel />}
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
      const resp = await api('/jobs/matches?limit=50')
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
        const resp = await api('/jobs/scan/progress')
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
      await api('/jobs/scan')
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

// ═══════════════════════════════════════════════════════════════════════════════
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
  const [progress, setProgress] = useState<PipelineProgress | null>(null)
  const [running, setRunning] = useState(false)
  const [settings, setSettings] = useState<PipelineSettings>({
    mode: 'notify',
    auto_apply: false,
    max_per_run: 10,
    generate_pdf: true,
    send_telegram: true,
    min_match_score: 60,
  })
  const [showResults, setShowResults] = useState(false)
  const [liveLogs, setLiveLogs] = useState<string[]>([])
  const logEndRef = useRef<HTMLDivElement | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Resume upload state
  const [resumeContent, setResumeContent] = useState('')
  const [resumeInfo, setResumeInfo] = useState<{ exists: boolean; full_name: string; skills_count: number; char_count: number } | null>(null)
  const [resumeUploading, setResumeUploading] = useState(false)
  const [resumeSavedMsg, setResumeSavedMsg] = useState('')

  // Auto-scroll log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [liveLogs])

  // Fetch resume info on mount
  useEffect(() => {
    (async () => {
      const data = await api('/jobs/resume')
      if (data && typeof data === 'object') {
        const d = data as Record<string, unknown>
        setResumeInfo({
          exists: Boolean(d.exists),
          full_name: (d.parsed as Record<string, unknown>)?.full_name as string || '',
          skills_count: Number((d.parsed as Record<string, unknown>)?.skills_count || 0),
          char_count: Number(d.char_count || 0),
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
