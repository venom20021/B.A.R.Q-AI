import { useState } from 'react'
import { Search, Filter, Star, ExternalLink, CheckCircle, Clock, AlertCircle } from 'lucide-react'
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

const sampleJobs: Job[] = [
  {
    id: '1',
    title: 'Senior Frontend Engineer',
    company: 'Acme Corp',
    location: 'San Francisco, CA (Remote)',
    salary: '$160k - $200k',
    matchScore: 92,
    source: 'LinkedIn',
    postedDate: '2 days ago',
    status: 'new',
    reasons: ['React/TypeScript', 'Remote-friendly', 'Great culture score']
  },
  {
    id: '2',
    title: 'Full Stack Developer',
    company: 'TechCorp',
    location: 'New York, NY',
    salary: '$140k - $180k',
    matchScore: 78,
    source: 'Indeed',
    postedDate: '1 week ago',
    status: 'reviewing',
    reasons: ['Good tech stack match', 'Slightly below target salary']
  },
  {
    id: '3',
    title: 'Software Engineer II',
    company: 'StartupXYZ',
    location: 'Austin, TX (Hybrid)',
    salary: '$120k - $150k',
    matchScore: 65,
    source: 'Glassdoor',
    postedDate: '3 days ago',
    status: 'approved',
    reasons: ['Interesting domain', 'Lower compensation']
  },
  {
    id: '4',
    title: 'Staff Engineer',
    company: 'BigTech Inc',
    location: 'Seattle, WA',
    salary: '$200k - $280k',
    matchScore: 85,
    source: 'LinkedIn',
    postedDate: '5 days ago',
    status: 'applied',
    reasons: ['Great compensation', 'Strong culture fit']
  }
]

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
  const [filter, setFilter] = useState<Job['status'] | 'all'>('all')
  const [sortBy, setSortBy] = useState<'match' | 'date'>('match')

  const filteredJobs = sampleJobs
    .filter((job) => filter === 'all' || job.status === filter)
    .sort((a, b) =>
      sortBy === 'match' ? b.matchScore - a.matchScore : a.postedDate.localeCompare(b.postedDate)
    )

  const handleApprove = async (jobId: string): Promise<void> => {
    await window.barq?.jobs.approve(jobId)
  }

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
        <button className="btn-cyan flex items-center gap-2">
          <Search className="w-4 h-4" />
          Scan Now
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
      </motion.div>

      {/* Job Listings */}
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
                  <span>{job.location}</span>
                  <span>{job.salary}</span>
                  <span className="badge-dim text-hud">{job.source}</span>
                  <span>{job.postedDate}</span>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {job.reasons.map((reason, ri) => (
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
    </div>
  )
}
