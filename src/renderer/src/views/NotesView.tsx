import { useState, useEffect, useCallback, startTransition, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { StickyNote, Search, Plus, Trash2, Pin, Edit3, X, Save, Loader2, Tag, Calendar, AlignLeft, Eye } from 'lucide-react'
import { api } from '../utils/api'

// ─── Types ─────────────────────────────────────────────────────────────────

interface Note {
  id: number
  title: string
  content: string
  tags: string[]
  pinned?: boolean
  color?: string
  created_at: string
}

// ─── Simple Markdown Renderer ─────────────────────────────────────────────

function renderMarkdown(text: string): string {
  if (!text) return ''
  let html = text
    // Headers
    .replace(/^### (.+)$/gm, '<h3 class="text-sm font-semibold text-emerald-300 mt-3 mb-1">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="text-base font-bold text-zinc-100 mt-4 mb-1">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 class="text-lg font-bold text-zinc-100 mt-4 mb-2">$1</h1>')
    // Bold & italic
    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-zinc-200 font-semibold">$1</strong>')
    .replace(/\*(.+?)\*/g, '<em class="text-zinc-300 italic">$1</em>')
    // Code blocks
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-zinc-950/80 rounded-lg p-3 my-2 overflow-x-auto"><code class="text-[11px] font-mono text-emerald-300">$2</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="bg-zinc-800/60 px-1 py-0.5 rounded text-[11px] font-mono text-cyan-300">$1</code>')
    // Unordered lists
    .replace(/^- (.+)$/gm, '<li class="text-xs text-zinc-400 ml-4 list-disc">$1</li>')
    // Ordered lists
    .replace(/^\d+\. (.+)$/gm, '<li class="text-xs text-zinc-400 ml-4 list-decimal">$1</li>')
    // Horizontal rule
    .replace(/^---$/gm, '<hr class="border-zinc-800 my-3" />')
    // Line breaks
    .replace(/\n/g, '<br />')
  return html
}

// ─── Notes View ───────────────────────────────────────────────────────────

export default function NotesView({ glassPanel }: { glassPanel: string }): JSX.Element {
  const [notes, setNotes] = useState<Note[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [editingNote, setEditingNote] = useState<Note | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editContent, setEditContent] = useState('')
  const [editTags, setEditTags] = useState('')
  const [saving, setSaving] = useState(false)
  const [selectedTag, setSelectedTag] = useState<string | null>(null)
  const [previewMode, setPreviewMode] = useState(false)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newContent, setNewContent] = useState('')
  const [newTags, setNewTags] = useState('')
  const [creating, setCreating] = useState(false)

  const fetchNotes = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await api<{ notes?: Note[] }>('/notes')
      if (resp?.notes) setNotes(resp.notes)
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  const createNote = useCallback(async () => {
    if (!newTitle.trim()) return
    setCreating(true)
    try {
      const tagArr = newTags.split(',').map(t => t.trim()).filter(Boolean)
      const resp = await api<{ note?: Note }>('/notes', { title: newTitle, content: newContent, tags: tagArr })
      if (resp?.note) setNotes(prev => [resp.note!, ...prev])
      else await fetchNotes()
      setNewTitle('')
      setNewContent('')
      setNewTags('')
      setShowCreateForm(false)
    } catch { /* ignore */ }
    setCreating(false)
  }, [newTitle, newContent, newTags, fetchNotes])

  const deleteNote = useCallback(async (id: number) => {
    try {
      await api(`/notes/${id}`, { method: 'DELETE' })
      setNotes(prev => prev.filter(n => n.id !== id))
      if (editingNote?.id === id) setEditingNote(null)
    } catch { /* ignore */ }
  }, [editingNote])

  const togglePin = useCallback(async (note: Note) => {
    try {
      await api(`/notes/${note.id}`, { pinned: !note.pinned })
      setNotes(prev => prev.map(n => n.id === note.id ? { ...n, pinned: !n.pinned } : n))
    } catch { /* ignore */ }
  }, [])

  const saveEdit = useCallback(async () => {
    if (!editingNote) return
    setSaving(true)
    try {
      const tagArr = editTags.split(',').map(t => t.trim()).filter(Boolean)
      const resp = await api<{ note?: Note }>(`/notes/${editingNote.id}`, {
        title: editTitle,
        content: editContent,
        tags: tagArr,
      })
      if (resp?.note) {
        setNotes(prev => prev.map(n => n.id === editingNote.id ? resp.note! : n))
        setEditingNote(resp.note)
      } else {
        setNotes(prev => prev.map(n => n.id === editingNote.id ? { ...n, title: editTitle, content: editContent, tags: tagArr } : n))
      }
    } catch { /* ignore */ }
    setSaving(false)
  }, [editingNote, editTitle, editContent, editTags])

  // Open edit modal
  const openEdit = useCallback((note: Note) => {
    setEditingNote(note)
    setEditTitle(note.title)
    setEditContent(note.content)
    setEditTags((note.tags || []).join(', '))
    setPreviewMode(false)
  }, [])

  useEffect(() => { startTransition(() => { void fetchNotes() }) }, [fetchNotes])

  // All unique tags
  const allTags = useMemo(() => {
    const tagSet = new Set<string>()
    notes.forEach(n => (n.tags || []).forEach(t => tagSet.add(t)))
    return [...tagSet].sort()
  }, [notes])

  // Filtered + searched notes
  const filtered = useMemo(() => {
    let result = notes
    if (selectedTag) result = result.filter(n => n.tags?.includes(selectedTag))
    if (search) {
      const q = search.toLowerCase()
      result = result.filter(n =>
        n.title.toLowerCase().includes(q) || n.content.toLowerCase().includes(q)
      )
    }
    // Pinned first, then by date
    return result.sort((a, b) => {
      if (a.pinned && !b.pinned) return -1
      if (!a.pinned && b.pinned) return 1
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })
  }, [notes, search, selectedTag])

  return (
    <div className={`h-full ${glassPanel} p-6 overflow-y-auto`}>
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-4">
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
            <input value={search} onChange={(e) => setSearch(e.target.value)}
              placeholder="Search notes..."
              className="w-48 pl-8 pr-3 py-1.5 bg-zinc-900/60 border border-white/5 rounded-lg text-xs font-mono text-zinc-300 placeholder-zinc-600 focus:outline-none focus:border-emerald-500/30 focus:shadow-[0_0_10px_rgba(16,185,129,0.1)] transition-all"
            />
          </div>
          <button onClick={() => setShowCreateForm(p => !p)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-lg text-[11px] font-bold tracking-wider uppercase hover:bg-emerald-500/20 transition-all"
          >
            {showCreateForm ? <X className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
            {showCreateForm ? 'Cancel' : 'New'}
          </button>
        </div>
      </div>

      {/* ── Tag filters ─────────────────────────────────────────────────── */}
      {allTags.length > 0 && (
        <div className="flex items-center gap-1.5 mb-4 overflow-x-auto pb-1">
          <Tag className="w-3 h-3 text-zinc-600 shrink-0" />
          <button onClick={() => setSelectedTag(null)}
            className={`whitespace-nowrap px-2 py-1 rounded text-[10px] font-mono transition-all ${
              !selectedTag ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-zinc-800/40 text-zinc-500 hover:text-zinc-300 border border-transparent'
            }`}
          >
            All
          </button>
          {allTags.map(tag => (
            <button key={tag} onClick={() => setSelectedTag(tag === selectedTag ? null : tag)}
              className={`whitespace-nowrap px-2 py-1 rounded text-[10px] font-mono transition-all ${
                selectedTag === tag ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-zinc-800/40 text-zinc-500 hover:text-zinc-300 border border-transparent'
              }`}
            >
              {tag} <span className="text-zinc-600">({notes.filter(n => n.tags?.includes(tag)).length})</span>
            </button>
          ))}
        </div>
      )}

      {/* ── Create Form ─────────────────────────────────────────────────── */}
      <AnimatePresence>
        {showCreateForm && (
          <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
            className="mb-4 bg-zinc-900/80 backdrop-blur-sm rounded-xl border border-emerald-500/20 p-4 space-y-3"
          >
            <input value={newTitle} onChange={e => setNewTitle(e.target.value)}
              placeholder="Note title..." autoFocus
              className="w-full bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-sm font-rajdhani text-zinc-200 outline-none focus:border-emerald-500/40 transition-colors placeholder:text-zinc-600"
            />
            <textarea value={newContent} onChange={e => setNewContent(e.target.value)}
              placeholder="Write your note..."
              rows={3}
              className="w-full bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs font-mono text-zinc-300 outline-none focus:border-emerald-500/40 transition-colors placeholder:text-zinc-600 resize-none"
            />
            <input value={newTags} onChange={e => setNewTags(e.target.value)}
              placeholder="Tags: ideas, work, personal"
              className="w-full bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-[10px] font-mono text-zinc-400 outline-none focus:border-emerald-500/40 transition-colors placeholder:text-zinc-600"
            />
            <button onClick={createNote} disabled={creating || !newTitle.trim()}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 text-xs font-rajdhani font-semibold hover:bg-emerald-500/25 transition-all disabled:opacity-40"
            >
              {creating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              Create Note
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Notes Grid ──────────────────────────────────────────────────── */}
      {loading ? (
        <div className="flex items-center justify-center h-48">
          <div className="w-5 h-5 border-2 border-emerald-500/30 border-t-emerald-400 rounded-full animate-spin" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-48 text-zinc-600">
          <StickyNote className="w-10 h-10 mb-3 opacity-30" />
          <p className="text-xs font-mono">
            {search || selectedTag ? 'No matching notes' : 'No notes yet — click + to create one'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((note, i) => (
            <motion.div key={note.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }}
              className={`group relative rounded-xl border bg-zinc-900/40 backdrop-blur-sm p-4 hover:border-emerald-500/15 transition-all cursor-pointer ${
                note.pinned ? 'border-emerald-500/20 ring-1 ring-emerald-500/20' : 'border-white/5'
              }`}
              onClick={() => openEdit(note)}
            >
              {/* Pin indicator */}
              {note.pinned && <Pin className="absolute top-2 right-8 w-3 h-3 text-emerald-400/50" />}

              {/* Action buttons */}
              <div className="absolute top-2 right-2 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-all">
                <span onClick={(e) => { e.stopPropagation(); togglePin(note) }}
                  className="p-1 rounded text-zinc-500 hover:text-emerald-400 hover:bg-emerald-500/10 transition-all cursor-pointer"
                >
                  <Pin className="w-3 h-3" />
                </span>
                <span onClick={(e) => { e.stopPropagation(); openEdit(note) }}
                  className="p-1 rounded text-zinc-500 hover:text-cyan-400 hover:bg-cyan-500/10 transition-all cursor-pointer"
                >
                  <Edit3 className="w-3 h-3" />
                </span>
                <span onClick={(e) => { e.stopPropagation(); deleteNote(note.id) }}
                  className="p-1 rounded text-zinc-500 hover:text-red-400 hover:bg-red-500/10 transition-all cursor-pointer"
                >
                  <Trash2 className="w-3 h-3" />
                </span>
              </div>

              {/* Note content */}
              <h3 className="text-sm font-semibold text-zinc-200 mb-1.5 truncate pr-12">{note.title || 'Untitled'}</h3>
              <p className="text-[11px] font-mono text-zinc-500 line-clamp-3 leading-relaxed">{note.content || 'No content'}</p>

              {/* Tags */}
              {note.tags && note.tags.length > 0 && (
                <div className="flex gap-1 mt-2 flex-wrap">
                  {note.tags.slice(0, 3).map((tag, j) => (
                    <span key={j} onClick={(e) => { e.stopPropagation(); setSelectedTag(tag) }}
                      className="px-1.5 py-0.5 bg-emerald-500/8 text-emerald-400/70 rounded text-[9px] font-mono hover:bg-emerald-500/15 hover:text-emerald-300 cursor-pointer transition-all"
                    >
                      {tag}
                    </span>
                  ))}
                  {note.tags.length > 3 && (
                    <span className="text-[9px] font-mono text-zinc-600">+{note.tags.length - 3}</span>
                  )}
                </div>
              )}

              {/* Date */}
              <div className="flex items-center gap-1 mt-2">
                <Calendar className="w-2.5 h-2.5 text-zinc-600" />
                <span className="text-[9px] font-mono text-zinc-600">{new Date(note.created_at).toLocaleDateString()}</span>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {/* ── Edit Modal ──────────────────────────────────────────────────── */}
      <AnimatePresence>
        {editingNote && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
            onClick={(e) => { if (e.target === e.currentTarget) { setEditingNote(null); setPreviewMode(false) } }}
          >
            <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
              className="w-full max-w-xl bg-zinc-900/95 backdrop-blur-xl rounded-2xl border border-zinc-800/80 shadow-2xl mx-4 overflow-hidden"
            >
              {/* Edit header */}
              <div className="flex items-center justify-between px-5 py-3 border-b border-zinc-800/60">
                <div className="flex items-center gap-2">
                  <StickyNote className="w-4 h-4 text-emerald-400" />
                  <span className="text-xs font-orbitron font-bold text-zinc-200 tracking-wider">EDIT NOTE</span>
                </div>
                <div className="flex items-center gap-1">
                  <button onClick={() => setPreviewMode(p => !p)}
                    className={`p-1.5 rounded transition-all ${previewMode ? 'text-emerald-400 bg-emerald-500/10' : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40'}`}
                    title={previewMode ? 'Edit' : 'Preview'}
                  >
                    {previewMode ? <AlignLeft className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  </button>
                  <button onClick={() => { setEditingNote(null); setPreviewMode(false) }}
                    className="p-1.5 rounded text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40 transition-all"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {/* Edit/preview body */}
              <div className="p-5 space-y-3">
                {previewMode ? (
                  <div className="min-h-[200px] max-h-[400px] overflow-y-auto px-1">
                    <h2 className="text-base font-orbitron font-bold text-zinc-100 mb-2">{editTitle || 'Untitled'}</h2>
                    <div className="text-xs leading-relaxed [&>br]:content-['']" dangerouslySetInnerHTML={{ __html: renderMarkdown(editContent) }} />
                  </div>
                ) : (
                  <>
                    <input value={editTitle} onChange={e => setEditTitle(e.target.value)}
                      className="w-full bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-sm font-rajdhani text-zinc-200 outline-none focus:border-emerald-500/40 transition-colors"
                      placeholder="Title"
                    />
                    <textarea value={editContent} onChange={e => setEditContent(e.target.value)}
                      rows={8}
                      className="w-full bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-xs font-mono text-zinc-300 outline-none focus:border-emerald-500/40 transition-colors resize-none"
                      placeholder="Write your note in Markdown..."
                    />
                    <input value={editTags} onChange={e => setEditTags(e.target.value)}
                      className="w-full bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2 text-[10px] font-mono text-zinc-400 outline-none focus:border-emerald-500/40 transition-colors"
                      placeholder="Tags: work, ideas, personal"
                    />
                  </>
                )}
              </div>

              {/* Edit footer */}
              <div className="flex items-center justify-between px-5 py-3 border-t border-zinc-800/60 bg-zinc-900/60">
                <button onClick={() => togglePin(editingNote)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-mono transition-all ${
                    editingNote.pinned
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40'
                  }`}
                >
                  <Pin className={`w-3 h-3 ${editingNote.pinned ? 'fill-emerald-400/30' : ''}`} />
                  {editingNote.pinned ? 'Pinned' : 'Pin'}
                </button>
                <div className="flex items-center gap-2">
                  <button onClick={() => { setEditingNote(null); setPreviewMode(false) }}
                    className="px-3 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-zinc-200 transition-all"
                  >
                    Cancel
                  </button>
                  <button onClick={saveEdit} disabled={saving}
                    className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 text-xs font-rajdhani font-semibold hover:bg-emerald-500/25 transition-all disabled:opacity-40"
                  >
                    {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    Save
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
