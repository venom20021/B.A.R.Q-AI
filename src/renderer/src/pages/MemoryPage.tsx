import { useState, useEffect, useCallback, startTransition } from 'react'
import { Search, FileText, Plus, Loader2, Trash2 } from 'lucide-react'
import { motion } from 'framer-motion'

import { api } from '../utils/api'

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
  created_at: string
}

export function MemoryPage(): JSX.Element {
  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [notes, setNotes] = useState<Note[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<MemoryItem[]>([])
  const [loadingMemories, setLoadingMemories] = useState(true)
  const [loadingNotes, setLoadingNotes] = useState(true)
  const [searching, setSearching] = useState(false)

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

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) {
      setSearchResults([])
      return
    }
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

  useEffect(() => {
    startTransition(() => { void fetchMemories(); void fetchNotes() })
  }, [fetchMemories, fetchNotes])

  const displayItems = searchResults.length > 0 ? searchResults : memories

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">NOTES & STORAGE</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">Core memory, vector search, notes, and RAG knowledge base</p>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="lg:col-span-2 glass-card">
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-4">
            {searchResults.length > 0 ? `Search Results (${searchResults.length})` : 'Core Memory'}
          </h3>
          {loadingMemories ? (
            <div className="flex items-center justify-center py-8"><Loader2 className="w-5 h-5 text-cyan-300 animate-spin" /></div>
          ) : displayItems.length > 0 ? (
            <div className="space-y-3">
              {displayItems.slice(0, 10).map((item) => (
                <div key={item.key} className="flex items-center justify-between py-2 border-b border-cyan-500/10 last:border-0">
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">{item.key.replace('memory_', '')}</p>
                    <p className="text-xs font-exo text-dim-400">{item.value}</p>
                  </div>
                  <button onClick={() => deleteMemory(item.key)} className="p-1 text-dim-500 hover:text-red-400 transition-colors">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm font-exo text-dim-400 py-4 text-center">No memories stored yet. Add some via settings or voice.</p>
          )}
          <button className="btn-ghost-cyan text-sm mt-4 flex items-center gap-2">
            <Plus className="w-4 h-4" /> Add Memory
          </button>
        </motion.div>

        <div className="space-y-4">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="glass-card">
            <div className="flex items-center gap-2 mb-3">
              <Search className="w-5 h-5 text-cyan-300" />
              <h3 className="text-sm font-rajdhani font-semibold text-ghost">Vector Search</h3>
            </div>
            <div className="flex gap-2">
              <input type="text" value={searchQuery} onChange={(e) => { setSearchQuery(e.target.value); if (!e.target.value) setSearchResults([]) }} onKeyDown={(e) => e.key === 'Enter' && handleSearch()} placeholder="Search your codebase..." className="input-cyan flex-1 text-sm" />
              <button onClick={handleSearch} disabled={searching} className="btn-glass text-sm">{searching ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Go'}</button>
            </div>
            <p className="text-xs font-exo text-dim-400 mt-2">Say: &quot;Find files about user auth&quot;</p>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass-card">
            <div className="flex items-center gap-2 mb-3">
              <FileText className="w-5 h-5 text-neural" />
              <h3 className="text-sm font-rajdhani font-semibold text-ghost">System Notes</h3>
            </div>
            {loadingNotes ? (
              <Loader2 className="w-4 h-4 text-cyan-300 animate-spin mx-auto" />
            ) : notes.length > 0 ? (
              <div className="space-y-2 max-h-[200px] overflow-y-auto scroll-cyan">
                {notes.slice(0, 5).map((note) => (
                  <div key={note.id} className="bg-void-700/50 rounded-lg p-3 border border-cyan-500/5">
                    <p className="text-xs font-rajdhani font-semibold text-ghost/80">{note.title}</p>
                    <p className="text-hud font-share-tech text-dim-500 mt-1">{note.created_at}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs font-exo text-dim-400">No notes yet</p>
            )}
            <button className="btn-ghost-cyan text-xs mt-2 w-full text-left">Create Note</button>
          </motion.div>
        </div>
      </div>
    </div>
  )
}
