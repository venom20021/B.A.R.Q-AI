import { useState, useEffect, useCallback } from 'react'
import { motion } from 'framer-motion'
import { StickyNote, Search, Plus, Trash2, Pin } from 'lucide-react'

interface Note {
  id: number
  title: string
  content: string
  tags: string[]
  pinned?: boolean
  color?: string
  created_at: string
}

export default function NotesView({ glassPanel }: { glassPanel: string }): JSX.Element {
  const [notes, setNotes] = useState<Note[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  const fetchNotes = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await window.barq?.python.request('/notes')
      if (resp && typeof resp === 'object') {
        const d = resp as { notes?: Note[] }
        if (d.notes) setNotes(d.notes)
      }
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  const createNote = useCallback(async () => {
    try {
      await window.barq?.python.request('/notes', {
        method: 'POST',
        body: JSON.stringify({ title: 'New Note', content: '', tags: [] }),
        headers: { 'Content-Type': 'application/json' },
      })
      await fetchNotes()
    } catch { /* ignore */ }
  }, [fetchNotes])

  const deleteNote = useCallback(async (id: number) => {
    try {
      await window.barq?.python.request(`/notes/${id}`, { method: 'DELETE' })
      await fetchNotes()
    } catch { /* ignore */ }
  }, [fetchNotes])

  useEffect(() => { fetchNotes() }, [fetchNotes])

  const filtered = notes.filter(n =>
    n.title.toLowerCase().includes(search.toLowerCase()) ||
    n.content.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className={`h-full ${glassPanel} p-6 overflow-y-auto`}>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-emerald-500/15 flex items-center justify-center">
            <StickyNote className="w-4 h-4 text-emerald-400" />
          </div>
          <div>
            <h2 className="text-sm font-orbitron font-bold text-zinc-100 tracking-wider">NOTES</h2>
            <p className="text-[10px] font-mono text-zinc-500">{notes.length} notes</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-500" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search notes..."
              className="w-48 pl-8 pr-3 py-1.5 bg-zinc-900/60 border border-white/5 rounded-lg text-xs font-mono text-zinc-300 placeholder-zinc-600 focus:outline-none focus:border-emerald-500/30 focus:shadow-[0_0_10px_rgba(16,185,129,0.1)] transition-all"
            />
          </div>
          <button
            onClick={createNote}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-lg text-[11px] font-bold tracking-wider uppercase hover:bg-emerald-500/20 transition-all"
          >
            <Plus className="w-3.5 h-3.5" /> New
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48">
          <div className="w-5 h-5 border-2 border-emerald-500/30 border-t-emerald-400 rounded-full animate-spin" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-48 text-zinc-600">
          <StickyNote className="w-10 h-10 mb-3 opacity-30" />
          <p className="text-xs font-mono">{search ? 'No matching notes' : 'No notes yet — click + to create one'}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((note, i) => (
            <motion.div
              key={note.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03 }}
              className={`group relative rounded-xl border border-white/5 bg-zinc-900/40 backdrop-blur-sm p-4 hover:border-emerald-500/15 transition-all cursor-pointer ${note.pinned ? 'ring-1 ring-emerald-500/20' : ''}`}
            >
              {note.pinned && <Pin className="absolute top-2 right-8 w-3 h-3 text-emerald-400/50" />}
              <button
                onClick={(e) => { e.stopPropagation(); deleteNote(note.id) }}
                className="absolute top-2 right-2 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-red-500/10 text-zinc-500 hover:text-red-400 transition-all"
              >
                <Trash2 className="w-3 h-3" />
              </button>
              <h3 className="text-sm font-semibold text-zinc-200 mb-1 truncate">{note.title || 'Untitled'}</h3>
              <p className="text-[11px] font-mono text-zinc-500 line-clamp-3">{note.content || 'No content'}</p>
              {note.tags && note.tags.length > 0 && (
                <div className="flex gap-1 mt-2 flex-wrap">
                  {note.tags.slice(0, 3).map((tag, j) => (
                    <span key={j} className="px-1.5 py-0.5 bg-emerald-500/8 text-emerald-400/70 rounded text-[9px] font-mono">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}
