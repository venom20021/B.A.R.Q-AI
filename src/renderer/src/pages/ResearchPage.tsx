import { useState, useCallback, useEffect, useRef } from 'react'
import { Search, Building2, BrainCircuit, Globe, Loader2, TrendingUp, ExternalLink, FileText, BookOpen, Sparkles, RefreshCw, Clock, ChevronRight, Layers, Download, Save, Eye, X, Zap } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '../utils/api'

// ─── Types ─────────────────────────────────────────────────────────────────

interface SearchResult {
  title: string
  url: string
  snippet: string
  source: string
}

interface CompanyInfo {
  name: string
  description: string
  industry?: string
  founded?: string
  headquarters?: string
  website?: string
  employees?: string
}

interface RagStatus {
  total_entries?: number
  collections?: string[]
  last_updated?: string
}

interface ResearchCard {
  id: string
  phase: 'gathering' | 'elaborating' | 'editing' | 'complete' | 'error'
  title: string
  content: string
  status: 'pending' | 'active' | 'complete' | 'error'
  card_type: 'info' | 'search' | 'quote' | 'finding' | 'gap' | 'insight'
  metadata: Record<string, unknown>
}

interface DeepResearchResult {
  topic: string
  report: string
  sources_count?: number
  facts_count?: number
  depth: string
  cards_count?: number
  note_id?: number
}

// ─── Search web via backend ────────────────────────────────────────────────

async function searchWeb(query: string): Promise<SearchResult[]> {
  try {
    const resp = await api('/web/browse/search', { query, max_results: 8 })
    if (resp && typeof resp === 'object') {
      const data = resp as { results?: SearchResult[] }
      if (data.results && data.results.length > 0) return data.results
    }
  } catch { /* fall through */ }
  return []
}

async function researchCompany(name: string): Promise<CompanyInfo | null> {
  try {
    const resp = await api('/web/browse/search', { query: `${name} company overview information`, max_results: 5 })
    if (resp && typeof resp === 'object') {
      const data = resp as { results?: SearchResult[] }
      if (data.results && data.results.length > 0) {
        const snippets = data.results.slice(0, 3).map(r => r.snippet).filter(Boolean).join(' ')
        return { name, description: snippets || 'No description available' }
      }
    }
  } catch { /* ignore */ }
  return null
}

// ─── Phase Icon Map ────────────────────────────────────────────────────────

function PhaseIcon({ phase, cardType, className }: { phase: string; cardType: string; className?: string }): JSX.Element {
  const cls = className || 'w-3.5 h-3.5'
  if (cardType === 'search') return <Search className={cls} />
  if (cardType === 'finding') return <FileText className={cls} />
  if (cardType === 'gap') return <Search className={cls} />
  if (cardType === 'insight') return <BrainCircuit className={cls} />
  if (phase === 'gathering') return <Globe className={cls} />
  if (phase === 'elaborating') return <Sparkles className={cls} />
  if (phase === 'editing') return <BookOpen className={cls} />
  return <Layers className={cls} />
}

function PhaseColor(phase: string): string {
  switch (phase) {
    case 'gathering': return 'text-cyan-400 border-cyan-500/20 bg-cyan-500/8'
    case 'elaborating': return 'text-violet-400 border-violet-500/20 bg-violet-500/8'
    case 'editing': return 'text-emerald-400 border-emerald-500/20 bg-emerald-500/8'
    case 'complete': return 'text-green-400 border-green-500/20 bg-green-500/8'
    default: return 'text-zinc-400 border-zinc-500/20 bg-zinc-500/8'
  }
}

function StatusDot({ status }: { status: string }): JSX.Element {
  if (status === 'active') return <span className="relative flex w-2 h-2"><span className="animate-ping absolute inset-0 rounded-full bg-cyan-400 opacity-60" /><span className="relative rounded-full w-2 h-2 bg-cyan-400" /></span>
  if (status === 'complete') return <span className="w-2 h-2 rounded-full bg-emerald-400/60" />
  if (status === 'error') return <span className="w-2 h-2 rounded-full bg-red-400/60" />
  return <span className="w-2 h-2 rounded-full bg-zinc-600/40" />
}

// ─── Main Page ─────────────────────────────────────────────────────────────

export function ResearchPage(): JSX.Element {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [researching, setResearching] = useState(false)
  const [activeTab, setActiveTab] = useState<'rag' | 'web' | 'company' | 'deep'>('web')

  // Company research
  const [companyName, setCompanyName] = useState('')
  const [companyInfo, setCompanyInfo] = useState<CompanyInfo | null>(null)
  const [companyLoading, setCompanyLoading] = useState(false)
  const [companySearchResults, setCompanySearchResults] = useState<SearchResult[]>([])

  // RAG status
  const [ragStatus, setRagStatus] = useState<RagStatus | null>(null)
  const [ragResults, setRagResults] = useState<SearchResult[]>([])
  const [ragSearching, setRagSearching] = useState(false)

  // ── Deep Research State ──────────────────────────────────────────────
  const [deepTopic, setDeepTopic] = useState('')
  const [deepDepth, setDeepDepth] = useState<'basic' | 'standard' | 'deep'>('standard')
  const [deepRunning, setDeepRunning] = useState(false)
  const deepRunningRef = useRef(false)
  const [deepCards, setDeepCards] = useState<ResearchCard[]>([])
  const [deepResult, setDeepResult] = useState<DeepResearchResult | null>(null)
  const [deepError, setDeepError] = useState('')
  const [reportExpanded, setReportExpanded] = useState(false)
  const deepCardsEndRef = useRef<HTMLDivElement>(null!)
  const [deepPhase, setDeepPhase] = useState<string>('')

  // Trending topics
  const [trendingTopics] = useState<string[]>([
    'Quantum computing breakthroughs 2025',
    'AI agent architectures',
    'RAG vs fine-tuning',
    'Next-gen semiconductors',
    'Autonomous driving regulation',
    'Edge AI deployment',
    'LLM benchmark improvements',
    'WebAssembly in production',
  ])

  // Auto-scroll deep research cards
  useEffect(() => {
    if (deepCardsEndRef.current) {
      deepCardsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [deepCards, deepPhase])

  // ── Web search ──────────────────────────────────────────────────────
  const handleSearch = useCallback(async () => {
    if (!query.trim()) return
    setResearching(true)
    setResults([])
    setActiveTab('web')
    try {
      const webResults = await searchWeb(query)
      if (webResults.length > 0) {
        setResults(webResults)
      } else {
        const ragData = await api('/memory/rag/query', { query, collection: 'default' })
        if (ragData && typeof ragData === 'object') {
          const d = ragData as { results?: { snippet?: string; source?: string; title?: string }[] }
          const mapped = (d.results ?? []).map(r => ({
            title: r.title || 'Knowledge entry',
            url: '',
            snippet: r.snippet || '',
            source: r.source || 'RAG',
          }))
          if (mapped.length > 0) { setResults(mapped); return }
        }
        setResults([{ title: query, url: '', snippet: 'No results found. Try a different query or check backend connection.', source: 'info' }])
      }
    } catch {
      setResults([{ title: 'Search failed', url: '', snippet: 'Could not reach the search backend.', source: 'error' }])
    }
    setResearching(false)
  }, [query])

  // ── Company research ─────────────────────────────────────────────────
  const handleCompanyResearch = useCallback(async () => {
    if (!companyName.trim()) return
    setCompanyLoading(true)
    setCompanyInfo(null)
    setCompanySearchResults([])
    setActiveTab('company')
    try {
      const info = await researchCompany(companyName)
      if (info) setCompanyInfo(info)
      const searchRes = await searchWeb(`${companyName} news updates 2025`)
      setCompanySearchResults(searchRes.slice(0, 5))
    } catch {
      setCompanyInfo({ name: companyName, description: 'Research failed. Please try again.' })
    }
    setCompanyLoading(false)
  }, [companyName])

  // ── RAG search ──────────────────────────────────────────────────────
  const handleRagSearch = useCallback(async (q?: string) => {
    const searchQuery = q || query
    if (!searchQuery.trim()) return
    setRagSearching(true)
    setRagResults([])
    setActiveTab('rag')
    try {
      const resp = await api('/memory/rag/query', { query: searchQuery, collection: 'default' })
      if (resp && typeof resp === 'object') {
        const d = resp as { results?: { snippet?: string; source?: string; title?: string }[] }
        const mapped = (d.results ?? []).map(r => ({
          title: r.title || 'Knowledge entry',
          url: r.source || '',
          snippet: r.snippet || '',
          source: r.source || 'RAG',
        }))
        setRagResults(mapped.length > 0 ? mapped : [{ title: 'No matches', url: '', snippet: 'No knowledge entries matched your query.', source: 'info' }])
      }
    } catch {
      setRagResults([{ title: 'Query failed', url: '', snippet: 'Could not query the RAG knowledge base.', source: 'error' }])
    }
    setRagSearching(false)
  }, [query])

  // Fetch RAG status on mount
  const fetchRagStatus = useCallback(async () => {
    const data = await api('/memory/rag/status')
    if (data && typeof data === 'object') setRagStatus(data as RagStatus)
  }, [])
  useEffect(() => { fetchRagStatus() }, [fetchRagStatus])

  // ── Deep Research ───────────────────────────────────────────────────
  const handleDeepResearch = useCallback(async () => {
    const topic = deepTopic.trim() || query.trim()
    if (!topic) return

    setDeepRunning(true)
    deepRunningRef.current = true
    setDeepCards([])
    setDeepResult(null)
    setDeepError('')
    setActiveTab('deep')
    setReportExpanded(false)

    // Poll progress while research runs (uses ref to avoid stale closure)
    const pollInterval = setInterval(async () => {
      if (!deepRunningRef.current) { clearInterval(pollInterval); return }
      try {
        const prog = await api<{ active: boolean; progress?: { cards?: ResearchCard[]; phase?: string } }>('/research/deep/progress')
        if (prog?.progress?.cards) {
          setDeepCards(prog.progress.cards)
          setDeepPhase(prog.progress.phase || '')
        }
      } catch { /* ignore */ }
    }, 2000)

    try {
      const resp = await api<{
        topic?: string; report?: string; sources_count?: number; facts_count?: number; depth?: string; note_id?: number
      }>('/research/deep', { topic, depth: deepDepth, save_as_note: false })

      clearInterval(pollInterval)

      if (resp?.report) {
        setDeepResult({
          topic: resp.topic || topic,
          report: resp.report,
          sources_count: resp.sources_count,
          facts_count: resp.facts_count,
          depth: resp.depth || deepDepth,
          note_id: resp.note_id,
        })
        // Final cards fetch
        try {
          const prog = await api<{ active: boolean; progress?: { cards?: ResearchCard[] } }>('/research/deep/progress')
          if (prog?.progress?.cards) setDeepCards(prog.progress.cards)
        } catch { /* ignore */ }
      } else {
        setDeepError('Research returned no results')
      }
    } catch (err) {
      clearInterval(pollInterval)
      setDeepError(String(err))
    } finally {
      setDeepRunning(false)
      deepRunningRef.current = false
    }
  }, [deepTopic, deepDepth, query])

  // Save research as note
  const handleSaveAsNote = useCallback(async () => {
    if (!deepResult?.report) return
    try {
      const resp = await api<{ note?: { id: number } }>('/memory/notes', {
        title: `Research: ${deepResult.topic || 'Deep Research'}`,
        content: deepResult.report,
        tags: [deepResult.depth, 'deep-research', 'auto-generated'],
      })
      if (resp?.note?.id) {
        setDeepResult(prev => prev ? { ...prev, note_id: resp.note!.id } : null)
      }
    } catch { /* ignore */ }
  }, [deepResult])

  // Download report
  const handleDownloadReport = useCallback(() => {
    if (!deepResult?.report) return
    const blob = new Blob([deepResult.report], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `research-${deepResult.topic.slice(0, 30).replace(/[^a-zA-Z0-9]/g, '_')}.md`
    a.click()
    URL.revokeObjectURL(url)
  }, [deepResult])

  // Active results based on tab
  const activeResults = activeTab === 'web' ? results : activeTab === 'rag' ? ragResults : companySearchResults
  const activeLoading = activeTab === 'web' ? researching : activeTab === 'rag' ? ragSearching : companyLoading

  // Quick render markdown for report preview
  function renderMarkdown(md: string): string {
    return md
      .replace(/^### (.+)$/gm, '<h4 class="text-sm font-semibold text-zinc-200 mt-4 mb-1">$1</h4>')
      .replace(/^## (.+)$/gm, '<h3 class="text-base font-bold text-zinc-200 mt-5 mb-2 border-b border-zinc-800 pb-1">$1</h3>')
      .replace(/^# (.+)$/gm, '<h2 class="text-lg font-bold text-zinc-100 mt-6 mb-2">$1</h2>')
      .replace(/\*\*(.+?)\*\*/g, '<strong class="text-zinc-200 font-semibold">$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em class="text-zinc-400 italic">$1</em>')
      .replace(/^- (.+)$/gm, '<li class="text-xs text-zinc-400 ml-4 list-disc">$1</li>')
      .replace(/\n\n/g, '<br/><br/>')
      .replace(/\n/g, '<br/>')
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-violet-500/10 flex items-center justify-center border border-violet-500/20">
            <BrainCircuit className="w-5 h-5 text-violet-400" />
          </div>
          <div>
            <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">DEEP RESEARCH</h1>
            <p className="text-sm font-rajdhani text-dim-400 mt-0.5">Web search, RAG knowledge base, and multi-agent deep research</p>
          </div>
        </div>
      </motion.div>

      {/* ── Search Input ──────────────────────────────────────────────── */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
        className="bg-zinc-900/60 backdrop-blur-sm rounded-xl border border-zinc-800/60 p-5"
      >
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder='Search the web, knowledge base, or start deep research...'
              className="w-full pl-9 pr-3 py-2.5 bg-zinc-800/60 border border-zinc-700/50 rounded-lg text-sm font-exo text-zinc-200 outline-none focus:border-violet-500/40 focus:shadow-[0_0_12px_rgba(139,92,246,0.08)] transition-all placeholder:text-zinc-600"
            />
          </div>
          <button onClick={handleSearch} disabled={researching || !query.trim()}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-violet-500/10 text-violet-400 border border-violet-500/20 text-xs font-rajdhani font-semibold hover:bg-violet-500/20 transition-all disabled:opacity-40"
          >
            {researching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Globe className="w-4 h-4" />}
            Search
          </button>
          <button onClick={() => handleRagSearch()} disabled={ragSearching || !query.trim()}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs font-rajdhani font-semibold hover:bg-emerald-500/20 transition-all disabled:opacity-40"
          >
            {ragSearching ? <Loader2 className="w-4 h-4 animate-spin" /> : <BookOpen className="w-4 h-4" />}
            RAG
          </button>
        </div>

        {/* Trending topics */}
        <div className="flex items-center gap-2 mt-3 overflow-x-auto">
          <Clock className="w-3 h-3 text-zinc-500 shrink-0" />
          {trendingTopics.slice(0, 4).map(topic => (
            <button key={topic} onClick={() => { setQuery(topic); handleSearch() }}
              className="whitespace-nowrap px-2.5 py-1 rounded-lg bg-zinc-800/40 border border-zinc-800/60 text-[10px] font-mono text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/60 hover:border-zinc-700/60 transition-all"
            >
              {topic}
            </button>
          ))}
        </div>
      </motion.div>

      {/* ── Content Grid ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Main results area */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="lg:col-span-2">
          <div className="bg-zinc-900/60 backdrop-blur-sm rounded-xl border border-zinc-800/60 overflow-hidden">
            {/* Tab bar */}
            <div className="flex items-center border-b border-zinc-800/40">
              {([
                { key: 'web', label: 'Web Search', icon: Globe },
                { key: 'rag', label: 'RAG Knowledge', icon: BookOpen },
                { key: 'company', label: 'Company', icon: Building2 },
                { key: 'deep', label: 'Deep Research', icon: Zap },
              ] as const).map(tab => {
                const Icon = tab.icon
                const isActive = activeTab === tab.key
                return (
                  <button key={tab.key} onClick={() => setActiveTab(tab.key)}
                    className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-rajdhani font-semibold transition-all ${
                      isActive ? 'text-violet-300 bg-violet-500/8 border-b-2 border-violet-400' : 'text-zinc-500 hover:text-zinc-300'
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    {tab.label}
                  </button>
                )
              })}
            </div>

            {/* Tab Content */}
            <div className="p-4 min-h-[300px] max-h-[600px] overflow-y-auto">
              <AnimatePresence mode="wait">
                {/* ── Web / RAG / Company Tabs ─────────────────────────────── */}
                {activeTab !== 'deep' && (
                  activeLoading ? (
                    <motion.div key="loading" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-center justify-center py-16">
                      <div className="flex flex-col items-center gap-3">
                        <Loader2 className="w-6 h-6 animate-spin text-violet-400" />
                        <span className="text-xs font-mono text-zinc-500 animate-pulse">
                          {activeTab === 'company' ? 'Researching company...' : activeTab === 'rag' ? 'Querying knowledge base...' : 'Searching the web...'}
                        </span>
                      </div>
                    </motion.div>
                  ) : activeResults.length > 0 ? (
                    <motion.div key="results" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-3">
                      {activeTab === 'company' && companyInfo && (
                        <div className="bg-violet-500/5 rounded-xl border border-violet-500/15 p-4 mb-4">
                          <div className="flex items-center gap-3 mb-2">
                            <Building2 className="w-5 h-5 text-violet-400" />
                            <h3 className="text-sm font-orbitron font-bold text-zinc-200">{companyInfo.name}</h3>
                          </div>
                          <p className="text-xs font-exo text-zinc-400 leading-relaxed">{companyInfo.description}</p>
                        </div>
                      )}
                      {activeResults.map((r, i) => (
                        <motion.div key={i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}
                          className="group bg-zinc-800/30 hover:bg-zinc-800/50 rounded-lg border border-zinc-800/40 hover:border-zinc-700/50 p-3.5 transition-all duration-200"
                        >
                          <div className="flex items-start gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs font-rajdhani font-semibold text-zinc-200 truncate">{r.title}</span>
                                {r.source && (
                                  <span className="shrink-0 text-[9px] font-mono px-1.5 py-0.5 rounded bg-zinc-800/60 text-zinc-500 uppercase tracking-wider">{r.source}</span>
                                )}
                              </div>
                              <p className="text-xs font-exo text-zinc-500 leading-relaxed line-clamp-2">{r.snippet}</p>
                              {r.url && (
                                <a href={r.url} target="_blank" rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 mt-1.5 text-[10px] font-mono text-violet-400/60 hover:text-violet-400 transition-colors"
                                >
                                  <ExternalLink className="w-2.5 h-2.5" /> {r.url.length > 50 ? r.url.slice(0, 50) + '...' : r.url}
                                </a>
                              )}
                            </div>
                          </div>
                        </motion.div>
                      ))}
                    </motion.div>
                  ) : (
                    <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center justify-center py-16">
                      <Search className="w-10 h-10 text-zinc-700 mb-3" />
                      <p className="text-sm font-exo text-zinc-600">No results yet</p>
                      <p className="text-xs font-exo text-zinc-700 mt-1">Search the web, query RAG, or research a company</p>
                    </motion.div>
                  )
                )}

                {/* ── Deep Research Tab ─────────────────────────────────── */}
                {activeTab === 'deep' && (
                  <motion.div key="deep" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-3">
                    {/* Deep Research Input */}
                    {!deepRunning && !deepResult && (
                      <div className="space-y-3">
                        <div className="flex gap-2">
                          <input type="text" value={deepTopic} onChange={(e) => setDeepTopic(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleDeepResearch()}
                            placeholder="Enter a research topic or question..."
                            className="flex-1 bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2.5 text-sm font-exo text-zinc-200 outline-none focus:border-violet-500/40 transition-all placeholder:text-zinc-600"
                          />
                          <button onClick={handleDeepResearch} disabled={deepRunning || (!deepTopic.trim() && !query.trim())}
                            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-violet-500/15 text-violet-400 border border-violet-500/20 text-xs font-rajdhani font-semibold hover:bg-violet-500/25 transition-all disabled:opacity-40"
                          >
                            {deepRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                            Research
                          </button>
                        </div>
                        {/* Depth selector */}
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">Depth:</span>
                          {(['basic', 'standard', 'deep'] as const).map(d => (
                            <button key={d} onClick={() => setDeepDepth(d)}
                              className={`px-2.5 py-1 rounded-lg text-[10px] font-mono transition-all ${
                                deepDepth === d
                                  ? 'bg-violet-500/15 text-violet-400 border border-violet-500/20'
                                  : 'bg-zinc-800/40 text-zinc-500 border border-zinc-800/60 hover:text-zinc-300 hover:bg-zinc-800/60'
                              }`}
                            >
                              {d.charAt(0).toUpperCase() + d.slice(1)}
                              <span className="ml-1 opacity-60">{
                                d === 'basic' ? '(1r)' : d === 'standard' ? '(2r)' : '(3r)'
                              }</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Deep Research Running */}
                    {deepRunning && (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2 mb-3">
                          <Loader2 className="w-4 h-4 animate-spin text-violet-400" />
                          <span className="text-xs font-mono text-zinc-400 animate-pulse">
                            {deepPhase === 'gathering' ? 'Gathering information from web searches...' :
                             deepPhase === 'elaborating' ? 'Adding expert context and depth...' :
                             deepPhase === 'editing' ? 'Compiling final report...' :
                             'Researching...'}
                          </span>
                        </div>

                        {/* Live workspace cards */}
                        {deepCards.length > 0 && (
                          <div className="space-y-1.5">
                            {deepCards.map((card, i) => (
                              <motion.div key={card.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.05 }}>
                                <div className={`flex items-start gap-2.5 px-3 py-2 rounded-lg border transition-all duration-300 ${
                                  card.status === 'active'
                                    ? 'bg-cyan-500/5 border-cyan-500/20'
                                    : card.status === 'complete'
                                    ? 'bg-zinc-800/30 border-zinc-800/40 opacity-80'
                                    : card.status === 'error'
                                    ? 'bg-red-500/5 border-red-500/20'
                                    : 'bg-zinc-800/20 border-zinc-800/30'
                                }`}>
                                  <div className="mt-0.5">
                                    <PhaseIcon phase={card.phase} cardType={card.card_type} className={`w-3 h-3 ${
                                      card.status === 'active' ? 'text-cyan-400' :
                                      card.status === 'complete' ? 'text-emerald-400/60' :
                                      card.status === 'error' ? 'text-red-400' : 'text-zinc-600'
                                    }`} />
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-1.5">
                                      <span className={`text-[11px] font-mono font-medium leading-tight ${
                                        card.status === 'active' ? 'text-cyan-300' :
                                        card.status === 'complete' ? 'text-zinc-400' :
                                        card.status === 'error' ? 'text-red-300' : 'text-zinc-500'
                                      }`}>{card.title.length > 80 ? card.title.slice(0, 80) + '…' : card.title}</span>
                                      <StatusDot status={card.status} />
                                    </div>
                                    {card.content && (
                                      <p className="text-[10px] font-mono text-zinc-600 mt-0.5 line-clamp-1">{card.content}</p>
                                    )}
                                  </div>
                                </div>
                              </motion.div>
                            ))}
                            <div ref={deepCardsEndRef} />
                          </div>
                        )}
                      </div>
                    )}

                    {/* Deep Research Complete */}
                    {!deepRunning && deepResult && (
                      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-3">
                        {/* Research stats */}
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <div className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-500">
                              <Globe className="w-3 h-3" /> {deepResult.sources_count || '—'} sources
                            </div>
                            <div className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-500">
                              <FileText className="w-3 h-3" /> {deepResult.facts_count || '—'} facts
                            </div>
                            <div className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-500">
                              <Layers className="w-3 h-3" /> {deepResult.depth}
                            </div>
                          </div>
                          <div className="flex items-center gap-1.5">
                            {deepResult.note_id && (
                              <span className="text-[9px] font-mono text-emerald-500/60">Saved as note #{deepResult.note_id}</span>
                            )}
                          </div>
                        </div>

                        {/* Action buttons */}
                        <div className="flex items-center gap-2">
                          <button onClick={() => setReportExpanded(!reportExpanded)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-mono font-medium bg-violet-500/10 text-violet-400 border border-violet-500/20 hover:bg-violet-500/20 transition-all"
                          >
                            {reportExpanded ? <X className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                            {reportExpanded ? 'Collapse' : 'View Report'}
                          </button>
                          <button onClick={handleSaveAsNote}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-mono font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/20 transition-all"
                          >
                            <Save className="w-3 h-3" /> Save as Note
                          </button>
                          <button onClick={handleDownloadReport}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-mono font-medium bg-zinc-800/40 text-zinc-400 border border-zinc-800/60 hover:bg-zinc-800/60 hover:text-zinc-300 transition-all"
                          >
                            <Download className="w-3 h-3" /> Download
                          </button>
                        </div>

                        {/* Report preview */}
                        <AnimatePresence>
                          {reportExpanded && (
                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
                              className="bg-zinc-800/30 rounded-xl border border-zinc-800/40 p-4 overflow-auto max-h-[400px]"
                            >
                              <div className="prose prose-invert prose-xs max-w-none text-xs text-zinc-400 leading-relaxed"
                                dangerouslySetInnerHTML={{ __html: renderMarkdown(deepResult.report) }}
                              />
                            </motion.div>
                          )}
                        </AnimatePresence>

                        {/* Summary cards */}
                        {deepCards.length > 0 && (
                          <div className="mt-2">
                            <p className="text-[10px] font-mono text-zinc-600 mb-2">Research workspace ({deepCards.length} cards)</p>
                            <div className="space-y-1 max-h-[200px] overflow-y-auto">
                              {deepCards.slice(-10).map((card) => (
                                <div key={card.id} className="flex items-start gap-2 px-2.5 py-1.5 rounded-lg bg-zinc-800/20 border border-zinc-800/30">
                                  <PhaseIcon phase={card.phase} cardType={card.card_type} className="w-2.5 h-2.5 mt-0.5 text-zinc-500" />
                                  <div className="flex-1 min-w-0">
                                    <span className="text-[10px] font-mono text-zinc-500">{card.title.length > 50 ? card.title.slice(0, 50) + '…' : card.title}</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Start new research */}
                        <button onClick={() => { setDeepResult(null); setDeepCards([]); setDeepError('') }}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-mono text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40 transition-all"
                        >
                          <RefreshCw className="w-3 h-3" /> New Research
                        </button>
                      </motion.div>
                    )}

                    {/* Deep Research Error */}
                    {!deepRunning && deepError && !deepResult && (
                      <div className="flex flex-col items-center gap-3 py-8">
                        <p className="text-xs font-mono text-red-400">{deepError}</p>
                        <button onClick={() => setDeepError('')}
                          className="text-[10px] font-mono text-zinc-500 hover:text-zinc-300 transition-colors"
                        >Try again</button>
                      </div>
                    )}

                    {/* Deep Research Initial State */}
                    {!deepRunning && !deepResult && !deepError && (
                      <div className="flex flex-col items-center justify-center py-12">
                        <Zap className="w-10 h-10 text-zinc-700 mb-3" />
                        <p className="text-sm font-exo text-zinc-600">Multi-agent deep research</p>
                        <p className="text-xs font-exo text-zinc-700 mt-1 text-center max-w-sm">
                          Enter a topic to begin an iterative research loop. BARQ's agents will search the web, elaborate findings, and compile a comprehensive report.
                        </p>
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </motion.div>

        {/* ── Sidebar Panels ─────────────────────────────────────────────── */}
        <div className="space-y-4">
          {/* Company Research */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
            className="bg-zinc-900/60 backdrop-blur-sm rounded-xl border border-zinc-800/60 p-5"
          >
            <div className="flex items-center gap-2 mb-3">
              <Building2 className="w-5 h-5 text-amber-400" />
              <h3 className="text-sm font-rajdhani font-semibold text-zinc-200">Company Research</h3>
            </div>
            <div className="flex gap-2">
              <input type="text" value={companyName} onChange={(e) => setCompanyName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCompanyResearch()}
                placeholder="Search company..."
                className="flex-1 bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs font-exo text-zinc-300 outline-none focus:border-amber-500/40 transition-colors placeholder:text-zinc-600"
              />
              <button onClick={handleCompanyResearch} disabled={companyLoading || !companyName.trim()}
                className="flex items-center justify-center w-9 h-9 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 hover:bg-amber-500/20 transition-all disabled:opacity-40"
              >
                {companyLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ChevronRight className="w-3.5 h-3.5" />}
              </button>
            </div>
            <div className="mt-3 space-y-1">
              {['Google', 'Microsoft', 'Tesla', 'OpenAI', 'Meta'].map(name => (
                <button key={name} onClick={() => { setCompanyName(name); setTimeout(() => handleCompanyResearch(), 100) }}
                  className="block w-full text-left px-3 py-1.5 rounded-lg text-xs font-mono text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40 transition-all"
                >
                  {name}
                </button>
              ))}
            </div>
          </motion.div>

          {/* Deep Research Sidebar */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18 }}
            className="bg-zinc-900/60 backdrop-blur-sm rounded-xl border border-zinc-800/60 p-5"
          >
            <div className="flex items-center gap-2 mb-3">
              <Zap className="w-5 h-5 text-violet-400" />
              <h3 className="text-sm font-rajdhani font-semibold text-zinc-200">Deep Research</h3>
            </div>
            <p className="text-xs font-exo text-zinc-500 mb-3 leading-relaxed">
              Multi-agent iterative research loop. Searches web across multiple rounds, elaborates findings with expert context, and generates comprehensive reports.
            </p>
            <div className="space-y-2 text-xs font-mono">
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-zinc-800/30">
                <Globe className="w-3 h-3 text-cyan-400/60" />
                <span className="text-zinc-500">Gatherer Agent</span>
                <span className="ml-auto text-zinc-600">Iterative search</span>
              </div>
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-zinc-800/30">
                <Sparkles className="w-3 h-3 text-violet-400/60" />
                <span className="text-zinc-500">Elaborator Agent</span>
                <span className="ml-auto text-zinc-600">Expert depth</span>
              </div>
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-zinc-800/30">
                <BookOpen className="w-3 h-3 text-emerald-400/60" />
                <span className="text-zinc-500">Editor Agent</span>
                <span className="ml-auto text-zinc-600">Final report</span>
              </div>
            </div>
            <button onClick={() => { setActiveTab('deep'); setDeepTopic(query) }}
              className="w-full flex items-center justify-center gap-2 mt-3 px-3 py-2 rounded-lg bg-violet-500/10 text-violet-400 border border-violet-500/20 text-xs font-rajdhani font-semibold hover:bg-violet-500/20 transition-all"
            >
              <Zap className="w-3 h-3" />
              Start Deep Research
            </button>
          </motion.div>

          {/* RAG Knowledge Base */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.22 }}
            className="bg-zinc-900/60 backdrop-blur-sm rounded-xl border border-zinc-800/60 p-5"
          >
            <div className="flex items-center gap-2 mb-3">
              <FileText className="w-5 h-5 text-emerald-400" />
              <h3 className="text-sm font-rajdhani font-semibold text-zinc-200">RAG Knowledge Base</h3>
            </div>
            <p className="text-xs font-exo text-zinc-500 mb-3">Query your ingested documents and notes</p>
            {ragStatus ? (
              <div className="space-y-2 text-xs font-mono">
                <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-zinc-800/30">
                  <span className="text-zinc-500">Entries</span>
                  <span className="text-emerald-400 font-semibold">{ragStatus.total_entries ?? 0}</span>
                </div>
                {ragStatus.collections && ragStatus.collections.length > 0 && (
                  <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-zinc-800/30">
                    <span className="text-zinc-500">Collections</span>
                    <span className="text-zinc-300">{ragStatus.collections.length}</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-zinc-800/30">
                <RefreshCw className="w-3 h-3 text-zinc-600" />
                <span className="text-xs font-mono text-zinc-600">Loading status...</span>
              </div>
            )}
            <button onClick={() => handleRagSearch(query || 'latest')} disabled={ragSearching}
              className="w-full flex items-center justify-center gap-2 mt-3 px-3 py-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs font-rajdhani font-semibold hover:bg-emerald-500/20 transition-all"
            >
              {ragSearching ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
              Query Knowledge Base
            </button>
          </motion.div>

          {/* Voice Shortcuts */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
            className="bg-zinc-900/60 backdrop-blur-sm rounded-xl border border-zinc-800/60 p-5"
          >
            <div className="flex items-center gap-2 mb-3">
              <TrendingUp className="w-5 h-5 text-cyan-400" />
              <h3 className="text-sm font-rajdhani font-semibold text-zinc-200">Voice Shortcuts</h3>
            </div>
            <div className="space-y-1.5">
              {[
                { text: 'Search the web for latest AI news', icon: Globe },
                { text: 'Research company Google', icon: Building2 },
                { text: 'Query knowledge base about auth', icon: BookOpen },
                { text: 'Deep research quantum computing', icon: Zap },
              ].map((item, i) => {
                const Icon = item.icon
                return (
                  <button key={i} onClick={() => setQuery(item.text)}
                    className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-xs font-exo text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40 transition-all text-left"
                  >
                    <Icon className="w-3 h-3 shrink-0" />
                    <span className="truncate">Say: &ldquo;{item.text}&rdquo;</span>
                  </button>
                )
              })}
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  )
}
