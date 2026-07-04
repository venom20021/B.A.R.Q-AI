import { useState, useEffect, useCallback } from 'react'
import { Search, Filter, Star, ExternalLink, CheckCircle, Clock, Loader2 } from 'lucide-react'
import { motion } from 'framer-motion'

interface Job {
  id: string
  title: string
  company: string
  location: string
  salary: string
  matchScore: number
  source: string
  postedDate: string
  status: 'new' | 'reviewing' | 'approved' | 'applied' | 'rejected'
  reasons: string[]
}

const statusColors: Record<Job['status'], string> = {
  new: 'badge-cyan',
  reviewing: 'badge-plasma',
  approved: 'badge-green',
  applied: 'badge-purple',
  rejected: 'badge-dim'
}

const scoreColor = (score: number): string => {
  if (score >= 85) return 'text-neural border-neural'
  if (score >= 70) return 'text-plasma border-plasma'
  return 'text-dim-400 border-dim'
}

export function JobsPage(): JSX.Element {
  const [jobs, setJobs] = useState<Job[]>([])
  const [filter, setFilter] = useState<Job['status'] | 'all'>('all')
  const [sortBy, setSortBy] = useState<'match' | 'date'>('match')
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)

  const fetchJobs = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await window.barq?.python.request('/jobs/matches?limit=50')
      const data = (resp as { success?: boolean; data?: { matches?: Record<string, unknown>[] } } | undefined)?.data
      const matches = data?.matches ?? []
      setJobs(matches.map((m) => ({
        id: String(m['id'] ?? ''),
        title: String(m['title'] ?? 'Untitled'),
        company: String(m['company'] ?? 'Unknown'),
        location: String(m['location'] ?? ''),
        salary: m['salary_min'] && m['salary_max']
          ? `$${Number(m['salary_min']).toLocaleString()} - $${Number(m['salary_max']).toLocaleString()}`
          : 'N/A',
        matchScore: Math.round(Number(m['match_percentage'] ?? m['match_score'] ?? 0)),
        source: String(m['source'] ?? ''),
        postedDate: String(m['posted_date'] ?? ''),
        status: 'new' as Job['status'],
        reasons: [
          ...(m['pros'] ? [String(m['pros']).replace(/[[\]"]/g, '')] : []),
          ...(m['reasoning'] ? [String(m['reasoning']).slice(0, 60)] : []),
        ],
      })))
    } catch {
      setJobs([])
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchJobs()
  }, [fetchJobs])

  const handleScan = async (): Promise<void> => {
    setScanning(true)
    try {
      await window.barq?.python.request('/jobs/scan')
      await fetchJobs()
    } catch {
      // scan failed
    }
    setScanning(false)
  }

  const handleApprove = async (jobId: string): Promise<void> => {
    await window.barq?.jobs.approve(jobId)
    setJobs((prev) =>
      prev.map((j) => (j.id === jobId ? { ...j, status: 'approved' as Job['status'] } : j))
    )
  }

  const filteredJobs = jobs
    .filter((job) => filter === 'all' || job.status === filter)
    .sort((a, b) =>
      sortBy === 'match' ? b.matchScore - a.matchScore : a.postedDate.localeCompare(b.postedDate)
    )

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">JOB SEARCH</h1>
          <p className="text-sm font-rajdhani text-dim-400 mt-1">
            AI-matched opportunities from 35+ job boards
          </p>
        </div>
        <button
          onClick={handleScan}
          disabled={scanning}
          className="btn-cyan flex items-center gap-2"
        >
          {scanning ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Search className="w-4 h-4" />
          )}
          {scanning ? 'Scanning...' : 'Scan Now'}
        </button>
      </motion.div>

      {/* Filters */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center gap-3 flex-wrap"
      >
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-dim-400" />
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as Job['status'] | 'all')}
            className="input-cyan text-sm"
          >
            <option value="all">All Jobs</option>
            <option value="new">New</option>
            <option value="reviewing">Reviewing</option>
            <option value="approved">Approved</option>
            <option value="applied">Applied</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-exo text-dim-400">Sort by:</span>
          <button
            onClick={() => setSortBy('match')}
            className={`text-sm font-rajdhani font-semibold px-3 py-1.5 rounded-lg transition-all duration-200 ${
              sortBy === 'match' ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20' : 'text-dim-400 hover:text-ghost'
            }`}
          >
            Match Score
          </button>
          <button
            onClick={() => setSortBy('date')}
            className={`text-sm font-rajdhani font-semibold px-3 py-1.5 rounded-lg transition-all duration-200 ${
              sortBy === 'date' ? 'bg-cyan-500/10 text-cyan-300 border border-cyan-500/20' : 'text-dim-400 hover:text-ghost'
            }`}
          >
            Date
          </button>
        </div>
        <span className="text-xs font-share-tech text-dim-400 ml-auto">
          {jobs.length} job{jobs.length !== 1 ? 's' : ''} loaded
        </span>
      </motion.div>

      {/* Job Listings */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 text-cyan-300 animate-spin" />
          <span className="ml-3 text-sm font-rajdhani text-dim-400">Loading jobs...</span>
        </div>
      ) : filteredJobs.length === 0 ? (
        <div className="text-center py-20">
          <p className="text-sm font-rajdhani text-dim-400">
            {jobs.length === 0
              ? 'No jobs found. Click "Scan Now" to start searching.'
              : 'No jobs match the current filter.'}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredJobs.map((job, i) => (
            <motion.div
              key={job.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="glass-card-hover"
            >
              <div className="flex items-start justify-between">
                <div className="space-y-2 flex-1">
                  <div className="flex items-center gap-3">
                    <h3 className="text-base font-rajdhani font-semibold text-ghost">{job.title}</h3>
                    <span className={statusColors[job.status]}>
                      {job.status.charAt(0).toUpperCase() + job.status.slice(1)}
                    </span>
                  </div>
                  <p className="text-sm font-exo text-dim-400">{job.company}</p>
                  <div className="flex items-center gap-4 text-sm font-exo text-dim-400">
                    <span>{job.location || 'Remote'}</span>
                    <span>{job.salary}</span>
                    {job.source && <span className="badge-dim text-hud">{job.source}</span>}
                    <span>{job.postedDate || 'Recently'}</span>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {job.reasons.filter(Boolean).slice(0, 3).map((reason, ri) => (
                      <span key={ri} className="text-xs font-exo text-dim-400 bg-void-700/50 px-2 py-1 rounded border border-cyan-500/5">
                        {reason}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Match Score Circle */}
                <div className="flex flex-col items-center gap-2 ml-4">
                  <div className={`w-16 h-16 rounded-full border-2 flex items-center justify-center text-lg font-orbitron font-bold ${scoreColor(job.matchScore)}`}>
                    {job.matchScore}%
                  </div>
                  <span className="text-hud font-share-tech text-dim-400">MATCH</span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 mt-4 pt-4 border-t border-cyan-500/8">
                {job.status === 'new' && (
                  <button
                    onClick={() => handleApprove(job.id)}
                    className="btn-cyan text-sm flex items-center gap-1.5"
                  >
                    <CheckCircle className="w-4 h-4" />
                    Approve &amp; Apply
                  </button>
                )}
                {job.status === 'reviewing' && (
                  <button className="btn-glass text-sm flex items-center gap-1.5">
                    <Star className="w-4 h-4" />
                    Review Details
                  </button>
                )}
                <button className="btn-ghost-cyan text-sm flex items-center gap-1.5">
                  <ExternalLink className="w-4 h-4" />
                  View Original
                </button>
                <span className="flex-1" />
                <div className="flex items-center gap-1 text-hud font-share-tech text-dim-500">
                  {job.status === 'applied' ? (
                    <>
                      <CheckCircle className="w-3 h-3 text-neural" />
                      Applied
                    </>
                  ) : job.status === 'approved' ? (
                    <>
                      <Clock className="w-3 h-3 text-plasma" />
                      Awaiting approval
                    </>
                  ) : null}
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}
