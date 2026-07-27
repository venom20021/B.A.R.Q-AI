"""Insert the JobDetailModal component and wire it into JobListings."""
import re

TSX_PATH = '../src/renderer/src/pages/JobsPage.tsx'

with open(TSX_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# ── 1. Add the modal component after JobListings closes ─────────────────────

# Find the end of JobListings function (before ResponseAnalytics section)
marker = '// ═══════════════════════════════════════════════════════════════════════════════\n// 2. Response Rate Analytics'

modal_component = '''
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
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 z-10 w-7 h-7 flex items-center justify-center rounded-full bg-void-800/80 text-dim-400 hover:text-ghost hover:bg-void-700/90 transition-all"
          aria-label="Close modal"
        >
          <X className="w-4 h-4" />
        </button>

        {/* ── Header ───────────────────────────────── */}
        <div className="p-5 pb-4 border-b border-cyan-500/10">
          <div className="flex items-start gap-4">
            <div className="flex-1 min-w-0">
              <h2 className="text-lg font-orbitron font-bold text-ghost leading-tight tracking-tight">{job.title}</h2>
              <p className="text-sm font-rajdhani font-semibold text-cyan-300 mt-0.5">{job.company}</p>
            </div>
            <div className="flex flex-col items-center flex-shrink-0">
              <div className={
                "w-14 h-14 rounded-full border-2 flex items-center justify-center text-base font-orbitron font-bold " +
                (job.match_percentage >= 80 ? 'text-neural border-neural' : job.match_percentage >= 60 ? 'text-plasma border-plasma' : 'text-dim-400 border-dim')
              }>
                {job.match_percentage}%
              </div>
              <span className="text-[10px] font-share-tech text-dim-400 mt-0.5">MATCH</span>
            </div>
          </div>

          {/* Quick Info chips */}
          <div className="flex flex-wrap items-center gap-2 mt-3">
            {job.location && (
              <span className="text-xs font-exo text-dim-300 flex items-center gap-1 bg-void-800/50 px-2 py-0.5 rounded">
                <MapPin className="w-3 h-3 text-dim-400" /> {job.location}
              </span>
            )}
            <span className="text-xs font-exo text-dim-300 bg-void-800/50 px-2 py-0.5 rounded">{job.salary}</span>
            <span className="badge-dim text-hud text-[10px]">{job.source}</span>
            <span className={"text-[10px] font-share-tech font-semibold px-1.5 py-0.5 rounded " + (statusColors[job.status] || 'badge-dim')}>
              {job.status.charAt(0).toUpperCase() + job.status.slice(1)}
            </span>
            {job.posted_date && (
              <span className="text-[10px] font-share-tech text-dim-500 bg-void-800/50 px-2 py-0.5 rounded">
                {new Date(job.posted_date).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>

        {/* ── Content ───────────────────────────────── */}
        <div className="p-5 space-y-5">

          {/* Description */}
          {job.description && (
            <div>
              <h4 className="text-xs font-orbitron font-bold text-dim-400 tracking-wider mb-2 flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-cyan-400" /> DESCRIPTION
              </h4>
              <div className="text-sm font-exo text-dim-200 leading-relaxed whitespace-pre-wrap bg-void-800/30 rounded-lg p-3 border border-void-600/20 max-h-60 overflow-y-auto scroll-cyan">
                {job.description}
              </div>
            </div>
          )}

          {/* Match Reasoning */}
          {job.reasoning && (
            <div>
              <h4 className="text-xs font-orbitron font-bold text-dim-400 tracking-wider mb-2 flex items-center gap-1.5">
                <Brain className="w-3.5 h-3.5 text-plasma" /> MATCH REASONING
              </h4>
              <p className="text-sm font-exo text-dim-200 leading-relaxed bg-void-800/30 rounded-lg p-3 border border-void-600/20">
                {job.reasoning}
              </p>
            </div>
          )}

          {/* Pros & Cons side by side */}
          {(job.pros.length > 0 || job.cons.length > 0) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {job.pros.length > 0 && (
                <div className="bg-green-500/5 border border-green-500/10 rounded-lg p-3">
                  <h4 className="text-xs font-orbitron font-bold text-neural tracking-wider mb-2 flex items-center gap-1.5">
                    <CheckCircle className="w-3 h-3" /> PROS
                  </h4>
                  <ul className="space-y-1">
                    {job.pros.map((p, i) => (
                      <li key={i} className="text-xs font-exo text-dim-300 flex items-start gap-1.5">
                        <span className="text-neural mt-0.5 flex-shrink-0 font-bold">+</span>
                        <span>{p}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {job.cons.length > 0 && (
                <div className="bg-red-500/5 border border-red-500/10 rounded-lg p-3">
                  <h4 className="text-xs font-orbitron font-bold text-red-400 tracking-wider mb-2 flex items-center gap-1.5">
                    <XCircle className="w-3 h-3" /> CONS
                  </h4>
                  <ul className="space-y-1">
                    {job.cons.map((c, i) => (
                      <li key={i} className="text-xs font-exo text-dim-300 flex items-start gap-1.5">
                        <span className="text-red-400 mt-0.5 flex-shrink-0 font-bold">−</span>
                        <span>{c}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Footer ───────────────────────────────── */}
        <div className="px-5 py-3.5 border-t border-cyan-500/10 flex items-center justify-between bg-void-800/30 rounded-b-xl">
          <button
            onClick={onClose}
            className="text-xs font-rajdhani font-semibold text-dim-400 hover:text-ghost px-3 py-1.5 rounded-lg hover:bg-void-700/50 transition-all"
          >
            Close
          </button>
          <a
            href={job.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className={
              "btn-cyan text-xs flex items-center gap-1.5 " +
              (!job.source_url || job.source_url.length <= 5 ? 'opacity-50 pointer-events-none' : '')
            }
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Open Job Posting
          </a>
        </div>
      </motion.div>
    </motion.div>
  )
}
'''

# Insert modal component before ResponseAnalytics section
idx = content.find(marker)
if idx < 0:
    print('ERROR: ResponseAnalytics marker not found')
    exit(1)

before = content[:idx]
after = content[idx:]
new_content = before + modal_component + after

# ── 2. Add the modal rendering at the end of JobListings return ────────────

# Find the end of JobListings return: the last </div> before the closing }) of the function
# Look for the pattern: the closing of the outer <div className="space-y-6 relative"> wrapped in JobListings
# Actually, let's find the closing of the return statement in JobListings and add the modal before the closing tag

# Find the closing div of JobListings' return, then add modal rendering before the last line
# The return ends with: </div>\n  )\n}\n\n// ═══════ 2.
# More precisely, after the JobListings function's JSX return, there's typically a </div>\n  )
# followed by }

# Let's find where to insert the modal rendering. 
# The modal should be rendered at the end of the JobListings return, right before the outermost </div>
# So inside the <div className="space-y-6 relative"> block.

# Find a unique marker: the closing of the outermost div in the return
# The return starts with: return (\n    <div className="space-y-6 relative">
# It ends with: </div>\n  )\n}
# But we need to find the LAST </div> before }) that corresponds to JobListings closing

# A simpler approach: insert the modal rendering right before the closing of the return's parent div
# Let's find "          })}\n        </div>\n      )}\n    </div>\n  )\n}\n\n// ═══════" after the Job listing map

# Actually, let me insert the modal rendering right before the last </div> of the return.
# The return is: <div className="space-y-6 relative"> ... content ... </div>
# I'll find the closing div and add the modal before it.

# Find the closing tag pattern: the last </div> before the closing of the JobListings function
# The pattern is: just before the function for JobDetailModal or ResponseAnalytics

# Let me find where inside the return to add <JobDetailModal ... />
# I'll add it right at the end of the outer div, before the closing </div>

# Find the closing of the outer return div
# The structure is:
#   return (
#     <div className="space-y-6 relative">
#       ... (toast, header, scan history, progress, filters, job list)
#       <JobDetailModal ... />   <-- ADD HERE
#     </div>                      <-- this closing tag
#   )
# }

# I'll find this by looking for the last </div> before "  )\n}\n\n// ═══════ 2."
# Let me instead look for the closing of the outermost return
outer_close = '\n    </div>\n  )\n}\n\n// ════════════════════'
modal_render = '\n      {/* Job Detail Modal */}\n      {selectedJob && <JobDetailModal job={selectedJob} onClose={() => setSelectedJob(null)} />}\n'

# Find the closing of the return () block
idx2 = new_content.find(outer_close, new_content.find('return ('))
if idx2 < 0:
    print('ERROR: return close marker not found')
    exit(1)

new_content = new_content[:idx2] + modal_render + new_content[idx2:]

with open(TSX_PATH, 'w', encoding='utf-8') as f:
    f.write(new_content)

print('DONE')
