import { useState, useEffect, useCallback, startTransition } from 'react'
import { Search, FileText, Plus, Loader2, Trash2, BookOpen, Edit3, X, Tag, Database, HardDrive, Clock, Save, RefreshCw } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

import { api } from '../utils/api'

// ─── Types ─────────────────────────────────────────────────────────────────

interface MemoryItem {
  key: string
  value: string
  category?: string
}

interface Note {
  id: number
  title: string
  content: string
  tags: string[]
  pinned?: boolean
  created_at: string
}

interface RagStatus {
  total_entries?: number
  collections?: string[]
}

// ─── Main Page ─────────────────────────────────────────────────────────────

export function MemoryPage(): JSX.Element {
  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [notes, setNotes] = useState<Note[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<MemoryItem[]>([])
  const [loadingMemories, setLoadingMemories] = useState(true)
  const [loadingNotes, setLoadingNotes] = useState(true)
  const [searching, setSearching] = useState(false)
  const [activeTab, setActiveTab] = useState<'memories' | 'notes'>('memories')
  const [ragStatus, setRagStatus] = useState<RagStatus | null>(null)

  // Inline form states
  const [showAddMemory, setShowAddMemory] = useState(false)
  const [newMemoryKey, setNewMemoryKey] = useState('')
  const [newMemoryValue, setNewMemoryValue] = useState('')
  const [savingMemory, setSavingMemory] = useState(false)
  const [memoryFeedback, setMemoryFeedback] = useState('')

  const [showCreateNote, setShowCreateNote] = useState(false)
  const [newNoteTitle, setNewNoteTitle] = useState('')
  const [newNoteContent, setNewNoteContent] = useState('')
  const [newNoteTags, setNewNoteTags] = useState('')
  const [savingNote, setSavingNote] = useState(false)
  const [noteFeedback, setNoteFeedback] = useState('')

  // Selected note for detail view
  const [selectedNote, setSelectedNote] = useState<Note | null>(null)

  const fetchMemories = useCallback(async () => {
    setLoadingMemories(true)
    try {
      const resp = await api<{ items?: MemoryItem[] }>('/memory/memory')
      if (resp) setMemories(resp.items ?? [])
    } catch { setMemories([]) }
    setLoadingMemories(false)
  }, [])

  const fetchNotes = useCallback(async () => {
    setLoadingNotes(true)
    try {
      const resp = await api<{ notes?: Note[] }>('/memory/notes')
      if (resp) setNotes(resp.notes ?? [])
    } catch { setNotes([]) }
    setLoadingNotes(false)
  }, [])

  const fetchRagStatus = useCallback(async () => {
    const data = await api('/memory/rag/status')
    if (data && typeof data === 'object') setRagStatus(data as RagStatus)
  }, [])

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) { setSearchResults([]); return }
    setSearching(true)
    try {
      const resp = await api<{ results?: MemoryItem[] }>(`/memory/memory/search?query=${encodeURIComponent(searchQuery)}`)
      if (resp) setSearchResults(resp.results ?? [])
    } catch { setSearchResults([]) }
    setSearching(false)
  }, [searchQuery])

  const deleteMemory = useCallback(async (key: string) => {
    try {
      await api(`/memory/memory/${encodeURIComponent(key)}`, { method: 'DELETE' })
      setMemories((prev) => prev.filter((m) => m.key !== key))
    } catch { /* ignore */ }
  }, [])

  // ── Add memory ──────────────────────────────────────────────────────────
  const handleAddMemory = useCallback(async () => {
    if (!newMemoryKey.trim()) return
    setSavingMemory(true)
    setMemoryFeedback('')
    try {
      await api('/memory/memory', { key: newMemoryKey, value: newMemoryValue })
      setMemoryFeedback('✅ Memory saved')
      setNewMemoryKey('')
      setNewMemoryValue('')
      setShowAddMemory(false)
      await fetchMemories()
      setTimeout(() => setMemoryFeedback(''), 3000)
    } catch {
      setMemoryFeedback('❌ Failed to save memory')
      setTimeout(() => setMemoryFeedback(''), 3000)
    }
    setSavingMemory(false)
  }, [newMemoryKey, newMemoryValue, fetchMemories])

  // ── Create note ─────────────────────────────────────────────────────────
  const handleCreateNote = useCallback(async () => {
    if (!newNoteTitle.trim()) return
    setSavingNote(true)
    setNoteFeedback('')
    const tags = newNoteTags.split(',').map(t => t.trim()).filter(Boolean)
    try {
      await api('/memory/notes', { title: newNoteTitle, content: newNoteContent, tags })
      setNoteFeedback('✅ Note created')
      setNewNoteTitle('')
      setNewNoteContent('')
      setNewNoteTags('')
      setShowCreateNote(false)
      await fetchNotes()
      setTimeout(() => setNoteFeedback(''), 3000)
    } catch {
      setNoteFeedback('❌ Failed to create note')
      setTimeout(() => setNoteFeedback(''), 3000)
    }
    setSavingNote(false)
  }, [newNoteTitle, newNoteContent, newNoteTags, fetchNotes])

  // ── Delete note ─────────────────────────────────────────────────────────
  const handleDeleteNote = useCallback(async (id: number) => {
    try {
      await api(`/memory/notes/${id}`, { method: 'DELETE' })
      setNotes(prev => prev.filter(n => n.id !== id))
      if (selectedNote?.id === id) setSelectedNote(null)
    } catch { /* ignore */ }
  }, [selectedNote])

  useEffect(() => {
    startTransition(() => { void fetchMemories(); void fetchNotes(); void fetchRagStatus() })
  }, [fetchMemories, fetchNotes, fetchRagStatus])

  const displayItems = searchResults.length > 0 ? searchResults : memories
  const noteTags = [...new Set(notes.flatMap(n => n.tags || []))].sort()

  // All memories count from all categories
  const memoryCategories = [...new Set(memories.map(m => m.category || 'general'))]

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* ── Header ────────────────────────────────────────────────────── */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20">
              <BookOpen className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">NOTES & STORAGE</h1>
              <p className="text-sm font-rajdhani text-dim-400 mt-0.5">Core memory, vector search, notes, and RAG knowledge base</p>
            </div>
          </div>
          {/* Stats bar */}
          <div className="flex items-center gap-4 text-[10px] font-mono">
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800/40 border border-zinc-700/50">
              <Database className="w-3 h-3 text-cyan-400" />
              <span className="text-zinc-400">Memories</span>
              <span className="text-cyan-300 font-semibold">{memories.length}</span>
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800/40 border border-zinc-700/50">
              <FileText className="w-3 h-3 text-emerald-400" />
              <span className="text-zinc-400">Notes</span>
              <span className="text-emerald-300 font-semibold">{notes.length}</span>
            </div>
            {ragStatus && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800/40 border border-zinc-700/50">
                <HardDrive className="w-3 h-3 text-violet-400" />
                <span className="text-zinc-400">RAG</span>
                <span className="text-violet-300 font-semibold">{ragStatus.total_entries ?? 0}</span>
              </div>
            )}
          </div>
        </div>
      </motion.div>

      {/* ── Tab Bar ────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-1 border-b border-zinc-800/40">
        {([
          { key: 'memories' as const, label: 'Memories', icon: Database },
          { key: 'notes' as const, label: 'Notes', icon: FileText },
        ]).map(tab => {
          const Icon = tab.icon
          const isActive = activeTab === tab.key
          return (
            <button key={tab.key} onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-rajdhani font-semibold transition-all ${
                isActive ? 'text-emerald-300 bg-emerald-500/8 border-b-2 border-emerald-400' : 'text-zinc-500 hover:text-zinc-300'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {tab.label}
            </button>
          )
        })}
      </div>

      <AnimatePresence mode="wait">
        {activeTab === 'memories' ? (
          <motion.div key="memories" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Memory List */}
            <motion.div className="lg:col-span-2 bg-zinc-900/60 backdrop-blur-sm rounded-xl border border-zinc-800/60 p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-orbitron font-bold text-zinc-200 tracking-wider flex items-center gap-2">
                  <Database className="w-4 h-4 text-cyan-400" />
                  {searchResults.length > 0 ? `Search Results (${searchResults.length})` : 'Core Memory'}
                </h3>
                <button onClick={() => setShowAddMemory(p => !p)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs font-rajdhani font-semibold hover:bg-emerald-500/20 transition-all"
                >
                  {showAddMemory ? <X className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
                  {showAddMemory ? 'Cancel' : 'Add Memory'}
                </button>
              </div>

              {/* Inline add memory form */}
              <AnimatePresence>
                {showAddMemory && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden mb-4"
                  >
                    <div className="bg-emerald-500/5 rounded-xl border border-emerald-500/15 p-4 space-y-3">
                      <div>
                        <label className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider mb-1 block">Key</label>
                        <input type="text" value={newMemoryKey} onChange={e => setNewMemoryKey(e.target.value)}
                          placeholder="e.g., user_preference_theme"
                          className="w-full bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs font-mono text-zinc-300 outline-none focus:border-emerald-500/40 transition-colors placeholder:text-zinc-600"
                        />
                      </div>
                      <div>
                        <label className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider mb-1 block">Value</label>
                        <textarea value={newMemoryValue} onChange={e => setNewMemoryValue(e.target.value)}
                          placeholder="Memory content..."
                          rows={2}
                          className="w-full bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs font-mono text-zinc-300 outline-none focus:border-emerald-500/40 transition-colors placeholder:text-zinc-600 resize-none"
                        />
                      </div>
                      <div className="flex items-center justify-between">
                        <button onClick={handleAddMemory} disabled={savingMemory || !newMemoryKey.trim()}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 text-xs font-rajdhani font-semibold hover:bg-emerald-500/25 transition-all disabled:opacity-40"
                        >
                          {savingMemory ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                          Save
                        </button>
                        {memoryFeedback && <span className="text-[10px] font-mono text-emerald-400">{memoryFeedback}</span>}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Memory items */}
              {loadingMemories ? (
                <div className="flex items-center justify-center py-12"><Loader2 className="w-5 h-5 text-cyan-300 animate-spin" /></div>
              ) : displayItems.length > 0 ? (
                <div className="space-y-2">
                  {displayItems.slice(0, 15).map((item) => (
                    <div key={item.key} className="flex items-start justify-between px-3 py-2.5 rounded-lg bg-zinc-800/30 hover:bg-zinc-800/50 border border-zinc-800/40 hover:border-zinc-700/50 transition-all group">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-rajdhani font-semibold text-zinc-200 truncate">{item.key.replace('memory_', '')}</p>
                          {item.category && (
                            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-zinc-800/60 text-zinc-500 uppercase tracking-wider">{item.category}</span>
                          )}
                        </div>
                        <p className="text-xs font-exo text-zinc-500 mt-0.5 line-clamp-2">{item.value}</p>
                      </div>
                      <button onClick={() => deleteMemory(item.key)}
                        className="p-1.5 rounded text-zinc-600 hover:text-red-400 hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-all shrink-0 ml-2"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12">
                  <Database className="w-10 h-10 text-zinc-700 mx-auto mb-3" />
                  <p className="text-sm font-exo text-zinc-600">No memories stored yet</p>
                  <p className="text-xs font-exo text-zinc-700 mt-1">Add one via voice or the form above</p>
                </div>
              )}

              {/* Category badges */}
              {memoryCategories.length > 1 && (
                <div className="flex items-center gap-1.5 mt-4 pt-3 border-t border-zinc-800/40">
                  <Tag className="w-3 h-3 text-zinc-600" />
                  {memoryCategories.map(cat => (
                    <span key={cat} className="px-2 py-0.5 rounded text-[9px] font-mono bg-zinc-800/40 text-zinc-500">
                      {cat}
                    </span>
                  ))}
                </div>
              )}
            </motion.div>

            {/* Sidebar */}
            <div className="space-y-4">
              {/* Vector Search */}
              <motion.div className="bg-zinc-900/60 backdrop-blur-sm rounded-xl border border-zinc-800/60 p-5">
                <div className="flex items-center gap-2 mb-3">
                  <Search className="w-5 h-5 text-cyan-300" />
                  <h3 className="text-sm font-rajdhani font-semibold text-zinc-200">Vector Search</h3>
                </div>
                <div className="flex gap-2">
                  <input type="text" value={searchQuery}
                    onChange={(e) => { setSearchQuery(e.target.value); if (!e.target.value) setSearchResults([]) }}
                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                    placeholder="Search memories..."
                    className="flex-1 bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs font-mono text-zinc-300 outline-none focus:border-cyan-500/40 transition-colors placeholder:text-zinc-600"
                  />
                  <button onClick={handleSearch} disabled={searching}
                    className="flex items-center justify-center w-9 h-9 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 hover:bg-cyan-500/20 transition-all disabled:opacity-40"
                  >
                    {searching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
                  </button>
                </div>
                <p className="text-[10px] font-mono text-zinc-600 mt-2">Say: &quot;Find files about user auth&quot;</p>
              </motion.div>

              {/* RAG Status */}
              <motion.div className="bg-zinc-900/60 backdrop-blur-sm rounded-xl border border-zinc-800/60 p-5">
                <div className="flex items-center gap-2 mb-3">
                  <HardDrive className="w-5 h-5 text-violet-400" />
                  <h3 className="text-sm font-rajdhani font-semibold text-zinc-200">Knowledge Base</h3>
                </div>
                {ragStatus ? (
                  <div className="space-y-2 text-xs font-mono">
                    <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-zinc-800/30">
                      <span className="text-zinc-500">Entries</span>
                      <span className="text-violet-400 font-semibold">{ragStatus.total_entries ?? 0}</span>
                    </div>
                    {ragStatus.collections && (
                      <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-zinc-800/30">
                        <span className="text-zinc-500">Collections</span>
                        <span className="text-zinc-300">{ragStatus.collections.length}</span>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-xs font-mono text-zinc-600">
                    <RefreshCw className="w-3 h-3 animate-spin" /> Loading...
                  </div>
                )}
              </motion.div>

              {/* Voice hints */}
              <motion.div className="bg-zinc-900/60 backdrop-blur-sm rounded-xl border border-zinc-800/60 p-5">
                <div className="flex items-center gap-2 mb-3">
                  <Clock className="w-5 h-5 text-amber-400" />
                  <h3 className="text-sm font-rajdhani font-semibold text-zinc-200">Quick Actions</h3>
                </div>
                <div className="space-y-1.5">
                  {[
                    'Remember my theme is dark',
                    'What do you know about me?',
                    'Save this note: meeting notes...',
                    'Find files about authentication',
                  ].map((cmd, i) => (
                    <div key={i} className="px-3 py-2 rounded-lg bg-zinc-800/30 text-[10px] font-mono text-zinc-500 leading-relaxed">
                      Say: &ldquo;{cmd}&rdquo;
                    </div>
                  ))}
                </div>
              </motion.div>
            </div>
          </motion.div>
        ) : (
          /* ═══════════════════ NOTES TAB ═══════════════════ */
          <motion.div key="notes" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-4">
            {/* Notes Header */}
            <div className="flex items-center justify-between">
              {noteTags.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  <Tag className="w-3 h-3 text-zinc-500" />
                  {noteTags.map(tag => (
                    <span key={tag}
                      onClick={() => setSearchQuery(tag)}
                      className="px-2 py-0.5 rounded text-[9px] font-mono bg-emerald-500/8 text-emerald-400/70 hover:bg-emerald-500/15 hover:text-emerald-300 cursor-pointer transition-all"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
              <button onClick={() => setShowCreateNote(p => !p)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-xs font-rajdhani font-semibold hover:bg-emerald-500/20 transition-all ml-auto"
              >
                {showCreateNote ? <X className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
                {showCreateNote ? 'Cancel' : 'Create Note'}
              </button>
            </div>

            {/* Inline create note form */}
            <AnimatePresence>
              {showCreateNote && (
                <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
                  className="bg-zinc-900/60 backdrop-blur-sm rounded-xl border border-emerald-500/20 p-5 space-y-3"
                >
                  <input type="text" value={newNoteTitle} onChange={e => setNewNoteTitle(e.target.value)}
                    placeholder="Note title..."
                    className="w-full bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-sm font-rajdhani text-zinc-200 outline-none focus:border-emerald-500/40 transition-colors placeholder:text-zinc-600"
                  />
                  <textarea value={newNoteContent} onChange={e => setNewNoteContent(e.target.value)}
                    placeholder="Write your note content here..."
                    rows={4}
                    className="w-full bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs font-mono text-zinc-300 outline-none focus:border-emerald-500/40 transition-colors placeholder:text-zinc-600 resize-none"
                  />
                  <input type="text" value={newNoteTags} onChange={e => setNewNoteTags(e.target.value)}
                    placeholder="Tags (comma separated): ideas, work, personal"
                    className="w-full bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-[10px] font-mono text-zinc-400 outline-none focus:border-emerald-500/40 transition-colors placeholder:text-zinc-600"
                  />
                  <div className="flex items-center justify-between">
                    <button onClick={handleCreateNote} disabled={savingNote || !newNoteTitle.trim()}
                      className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 text-xs font-rajdhani font-semibold hover:bg-emerald-500/25 transition-all disabled:opacity-40"
                    >
                      {savingNote ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                      {savingNote ? 'Saving...' : 'Save Note'}
                    </button>
                    {noteFeedback && <span className="text-[10px] font-mono text-emerald-400">{noteFeedback}</span>}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Notes Grid */}
            {loadingNotes ? (
              <div className="flex items-center justify-center py-16"><Loader2 className="w-6 h-6 text-emerald-400 animate-spin" /></div>
            ) : notes.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16">
                <FileText className="w-12 h-12 text-zinc-700 mb-3" />
                <p className="text-sm font-exo text-zinc-600">No notes yet</p>
                <p className="text-xs font-exo text-zinc-700 mt-1">Click &quot;Create Note&quot; to get started</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {notes
                  .filter(n => !searchQuery || n.title.toLowerCase().includes(searchQuery.toLowerCase()) || n.tags?.some(t => t.toLowerCase().includes(searchQuery.toLowerCase())))
                  .map((note, i) => (
                    <motion.div key={note.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}
                      onClick={() => setSelectedNote(note)}
                      className={`group relative bg-zinc-900/60 backdrop-blur-sm rounded-xl border hover:border-emerald-500/20 p-4 cursor-pointer transition-all ${
                        selectedNote?.id === note.id ? 'border-emerald-500/30 ring-1 ring-emerald-500/20' : 'border-zinc-800/60'
                      }`}
                    >
                      <div className="flex items-start justify-between mb-2">
                        <h3 className="text-sm font-rajdhani font-semibold text-zinc-200 truncate flex-1">{note.title || 'Untitled'}</h3>
                        <button onClick={(e) => { e.stopPropagation(); handleDeleteNote(note.id) }}
                          className="p-1 rounded text-zinc-600 hover:text-red-400 hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-all shrink-0 ml-2"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                      <p className="text-xs font-exo text-zinc-500 leading-relaxed line-clamp-3">{note.content || 'No content'}</p>
                      {note.tags && note.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {note.tags.slice(0, 3).map((tag, j) => (
                            <span key={j} className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-emerald-500/8 text-emerald-400/70">{tag}</span>
                          ))}
                        </div>
                      )}
                      <p className="text-[9px] font-mono text-zinc-600 mt-2">{new Date(note.created_at).toLocaleDateString()}</p>
                    </motion.div>
                  ))}
              </div>
            )}

            {/* Note Detail / Editor Modal */}
            <AnimatePresence>
              {selectedNote && (
                <NoteDetailModal
                  note={selectedNote}
                  onClose={() => setSelectedNote(null)}
                  onDelete={handleDeleteNote}
                  onUpdate={(updated) => {
                    setNotes(prev => prev.map(n => n.id === updated.id ? updated : n))
                    setSelectedNote(updated)
                  }}
                />
              )}
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ─── Note Detail Modal ─────────────────────────────────────────────────────

function NoteDetailModal({ note, onClose, onDelete, onUpdate }: {
  note: Note
  onClose: () => void
  onDelete: (id: number) => void
  onUpdate: (note: Note) => void
}): JSX.Element {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(note.title)
  const [content, setContent] = useState(note.content)
  const [tags, setTags] = useState((note.tags || []).join(', '))
  const [saving, setSaving] = useState(false)

  const handleSave = useCallback(async () => {
    setSaving(true)
    try {
      const tagArr = tags.split(',').map(t => t.trim()).filter(Boolean)
      const resp = await api<{ note?: Note }>(`/memory/notes/${note.id}`, {
        title,
        content,
        tags: tagArr,
      })
      if (resp && resp.note) onUpdate(resp.note)
      else onUpdate({ ...note, title, content, tags: tagArr })
      setEditing(false)
    } catch { /* ignore */ }
    setSaving(false)
  }, [note, title, content, tags, onUpdate])

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
        className="w-full max-w-lg bg-zinc-900/95 backdrop-blur-xl rounded-2xl border border-zinc-800/80 shadow-2xl p-6 mx-4"
      >
        {editing ? (
          <div className="space-y-4">
            <input type="text" value={title} onChange={e => setTitle(e.target.value)}
              className="w-full bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-sm font-rajdhani text-zinc-200 outline-none focus:border-emerald-500/40 transition-colors"
              placeholder="Title"
            />
            <textarea value={content} onChange={e => setContent(e.target.value)}
              rows={8}
              className="w-full bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs font-mono text-zinc-300 outline-none focus:border-emerald-500/40 transition-colors resize-none"
              placeholder="Note content..."
            />
            <input type="text" value={tags} onChange={e => setTags(e.target.value)}
              className="w-full bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-[10px] font-mono text-zinc-400 outline-none focus:border-emerald-500/40 transition-colors"
              placeholder="Tags (comma separated)"
            />
            <div className="flex items-center justify-between">
              <button onClick={handleSave} disabled={saving}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 text-xs font-rajdhani font-semibold hover:bg-emerald-500/25 transition-all disabled:opacity-40"
              >
                {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                Save
              </button>
              <button onClick={() => setEditing(false)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-zinc-400 hover:text-zinc-200 transition-all text-xs"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-start justify-between">
              <h2 className="text-base font-orbitron font-bold text-zinc-100 tracking-wider">{note.title || 'Untitled'}</h2>
              <div className="flex items-center gap-1">
                <button onClick={() => setEditing(true)}
                  className="p-1.5 rounded text-zinc-500 hover:text-emerald-400 hover:bg-emerald-500/10 transition-all"
                >
                  <Edit3 className="w-3.5 h-3.5" />
                </button>
                <button onClick={() => onDelete(note.id)}
                  className="p-1.5 rounded text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition-all"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
                <button onClick={onClose}
                  className="p-1.5 rounded text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40 transition-all"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
            {note.tags && note.tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {note.tags.map((tag, j) => (
                  <span key={j} className="px-2 py-0.5 rounded text-[9px] font-mono bg-emerald-500/8 text-emerald-400/70">{tag}</span>
                ))}
              </div>
            )}
            <div className="bg-zinc-800/30 rounded-xl p-4 max-h-[400px] overflow-y-auto">
              <p className="text-xs font-exo text-zinc-300 leading-relaxed whitespace-pre-wrap">{note.content || 'No content'}</p>
            </div>
            <p className="text-[10px] font-mono text-zinc-600">
              Created: {new Date(note.created_at).toLocaleString()}
            </p>
          </div>
        )}
      </motion.div>
    </motion.div>
  )
}
