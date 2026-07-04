import { useState, useCallback } from 'react'
import { Search, Building2, BrainCircuit, Globe, Loader2 } from 'lucide-react'
import { motion } from 'framer-motion'

export function ResearchPage(): JSX.Element {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<string[]>([])
  const [researching, setResearching] = useState(false)
  const [companyName, setCompanyName] = useState('')
  const [companyResult, setCompanyResult] = useState('')
  const [companyLoading, setCompanyLoading] = useState(false)
  const [ragStatus, setRagStatus] = useState<{ total_entries?: number } | null>(null)

  const fetchRagStatus = useCallback(async () => {
    try {
      const resp = await window.barq?.python.request('/memory/rag/status')
      if (resp && typeof resp === 'object') setRagStatus(resp as typeof ragStatus)
    } catch { /* ignore */ }
  }, [])

  const handleResearch = useCallback(async () => {
    if (!query.trim()) return
    setResearching(true)
    setResults([])
    try {
      const resp = await window.barq?.python.request('/memory/rag/query', {
        method: 'POST',
        body: JSON.stringify({ query, collection: 'default' }),
        headers: { 'Content-Type': 'application/json' },
      })
      if (resp && typeof resp === 'object') {
        const data = resp as { results?: { snippet?: string; source?: string }[] }
        const snippets = (data.results ?? []).map((r) => `[${r.source || 'source'}] ${r.snippet || ''}`)
        setResults(snippets.length > 0 ? snippets : ['No relevant knowledge found'])
      }
    } catch {
      setResults(['Research query failed'])
    }
    setResearching(false)
  }, [query])

  const handleCompanyResearch = useCallback(async () => {
    if (!companyName.trim()) return
    setCompanyLoading(true)
    setCompanyResult('')
    try {
      const resp = await window.barq?.python.request('/memory/rag/query', {
        method: 'POST',
        body: JSON.stringify({ query: `Company research: ${companyName}`, collection: 'default' }),
        headers: { 'Content-Type': 'application/json' },
      })
      if (resp && typeof resp === 'object') {
        const data = resp as { results?: { snippet?: string }[] }
        setCompanyResult(data.results?.[0]?.snippet || 'No company data found. Try ingesting company documents.')
      }
    } catch {
      setCompanyResult('Research failed')
    }
    setCompanyLoading(false)
  }, [companyName])

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">DEEP RESEARCH</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">Autonomous research, RAG knowledge base, and company intelligence</p>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="lg:col-span-2 glass-card">
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-4">Knowledge Base Query</h3>
          <div className="flex gap-2 mb-4">
            <input type="text" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleResearch()} placeholder='e.g., "Research quantum computing breakthroughs"' className="input-cyan flex-1" />
            <button onClick={handleResearch} disabled={researching} className="btn-cyan flex items-center gap-2">
              {researching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              Research
            </button>
          </div>
          <div className="bg-void-900/80 rounded-lg p-4 min-h-[200px] border border-cyan-500/5 overflow-y-auto max-h-[300px] scroll-cyan">
            {results.length > 0 ? (
              results.map((r, i) => (
                <p key={i} className="text-sm font-exo text-dim-400 mb-2 pb-2 border-b border-cyan-500/5 last:border-0">{r}</p>
              ))
            ) : (
              <>
                <p className="text-dim-500 text-sm font-exo">Ask a question or say: &quot;Research quantum computing breakthroughs&quot;</p>
                <p className="text-dim-500 text-sm font-exo mt-1">Results will appear here with citations</p>
              </>
            )}
          </div>
        </motion.div>

        <div className="space-y-4">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="glass-card">
            <div className="flex items-center gap-2 mb-3">
              <Building2 className="w-5 h-5 text-plasma" />
              <h3 className="text-sm font-rajdhani font-semibold text-ghost">Company Research</h3>
            </div>
            <div className="flex gap-2">
              <input type="text" value={companyName} onChange={(e) => setCompanyName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleCompanyResearch()} placeholder="Company name..." className="input-cyan flex-1 text-sm" />
              <button onClick={handleCompanyResearch} disabled={companyLoading} className="btn-glass text-sm">{companyLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Go'}</button>
            </div>
            {companyResult && <p className="text-xs font-exo text-dim-400 mt-2">{companyResult}</p>}
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass-card" onMouseEnter={fetchRagStatus}>
            <div className="flex items-center gap-2 mb-3">
              <BrainCircuit className="w-5 h-5 text-holographic" />
              <h3 className="text-sm font-rajdhani font-semibold text-ghost">RAG Knowledge Base</h3>
            </div>
            <p className="text-xs font-exo text-dim-400">Query ingested documents</p>
            {ragStatus && (
              <p className="text-xs font-exo text-neural mt-2">{ragStatus.total_entries ?? 0} entries indexed</p>
            )}
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="glass-card">
            <div className="flex items-center gap-2 mb-3">
              <Globe className="w-5 h-5 text-cyan-300" />
              <h3 className="text-sm font-rajdhani font-semibold text-ghost">Quick Actions</h3>
            </div>
            <div className="space-y-1">
              <div className="text-xs font-exo text-dim-400 bg-void-700/50 px-3 py-2 rounded-lg border border-cyan-500/5">Say: &quot;Find files about user auth&quot;</div>
              <div className="text-xs font-exo text-dim-400 bg-void-700/50 px-3 py-2 rounded-lg border border-cyan-500/5">Say: &quot;Research Google&quot;</div>
              <div className="text-xs font-exo text-dim-400 bg-void-700/50 px-3 py-2 rounded-lg border border-cyan-500/5">Say: &quot;Summarize my notes&quot;</div>
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  )
}
