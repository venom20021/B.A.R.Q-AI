"""Replace the FollowUpPanel placeholder with a real implementation."""
import sys

tsx_path = sys.argv[1] if len(sys.argv) > 1 else '../src/renderer/src/pages/JobsPage.tsx'

with open(tsx_path, 'r', encoding='utf-8') as f:
    content = f.read()

old_marker = '// 3. Follow-Up Automation'
old_section_end = '// 4. Application Pipeline'

idx = content.find(old_marker)
if idx < 0:
    print('MARKER_NOT_FOUND')
    sys.exit(1)

end_idx = content.find(old_section_end, idx)
if end_idx < 0:
    print('END_MARKER_NOT_FOUND')
    sys.exit(1)

new_component = """// 3. Follow-Up Automation
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
// 4. Application Pipeline"""

new_content = content[:idx] + new_component + content[end_idx + len(old_section_end):]

with open(tsx_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print('REPLACEMENT_OK')
