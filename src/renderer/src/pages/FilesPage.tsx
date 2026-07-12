import { useState, useEffect, useCallback } from 'react'
import { FolderOpen, Search, Upload, Download, SortAsc, Loader2, File as FileIcon, FileText, Image as ImageIcon, FileCode } from 'lucide-react'
import { motion } from 'framer-motion'
import { api } from '../utils/api'

const extIcons: Record<string, typeof FileIcon> = {
  txt: FileText,
  md: FileText,
  pdf: FileText,
  doc: FileText,
  docx: FileText,
  png: ImageIcon,
  jpg: ImageIcon,
  jpeg: ImageIcon,
  gif: ImageIcon,
  svg: ImageIcon,
  ts: FileCode,
  tsx: FileCode,
  js: FileCode,
  jsx: FileCode,
  py: FileCode,
  json: FileCode,
  yml: FileCode,
  yaml: FileCode,
  html: FileCode,
  css: FileCode,
}

const formatSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function FilesPage(): JSX.Element {
  const [cwd, setCwd] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [files, setFiles] = useState<{ name: string; path: string; size_bytes: number; modified_at: number }[]>([])
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)

  const fetchSystemInfo = useCallback(async () => {
    try {
      const info = await api<{ cwd?: string; platform?: string; hostname?: string }>('/system/status')
      if (info?.cwd) setCwd(info.cwd)
    } catch { /* ignore */ }
  }, [])

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) return
    setSearching(true)
    try {
      const data = await api<{ results?: { name: string; path: string; size_bytes: number; modified_at: number }[] }>(`/system/file/search?query=${encodeURIComponent(searchQuery)}&directory=${encodeURIComponent(cwd || '.')}`)
      if (data?.results) setFiles(data.results)
    } catch { /* ignore */ }
    setSearching(false)
  }, [searchQuery, cwd])

  useEffect(() => {
    const init = async () => {
      await fetchSystemInfo()
      setLoading(false)
    }
    init()
  }, [fetchSystemInfo])

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">FILES</h1>
          <p className="text-sm font-rajdhani text-dim-400 mt-1">
            Browse, search, and organize your files with voice
          </p>
        </div>
        <button className="btn-cyan flex items-center gap-2">
          <Upload className="w-4 h-4" />
          Upload
        </button>
      </motion.div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-dim-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search files by name or content..."
            className="input-cyan w-full pl-10"
          />
        </div>
        <button onClick={handleSearch} disabled={searching} className="btn-glass flex items-center gap-2">
          {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          Search
        </button>
        <button className="btn-glass flex items-center gap-2">
          <SortAsc className="w-4 h-4" />
          Sort
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="glass-card-hover cursor-pointer col-span-2 min-h-[300px] overflow-y-auto scroll-cyan">
          {loading ? (
            <div className="flex items-center justify-center h-[300px]">
              <Loader2 className="w-5 h-5 text-cyan-300 animate-spin" />
            </div>
          ) : files.length > 0 ? (
            <div className="divide-y divide-cyan-500/5">
              {files.map((file) => {
                const ext = file.name.split('.').pop()?.toLowerCase() || ''
                const Icon = extIcons[ext] || FileIcon
                return (
                  <div key={file.path} className="flex items-center gap-3 px-4 py-2.5 hover:bg-void-700/50 transition-colors">
                    <Icon className="w-4 h-4 text-dim-400 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-rajdhani font-semibold text-ghost truncate">{file.name}</p>
                      <p className="text-xs font-exo text-dim-500 truncate">{file.path}</p>
                    </div>
                    <span className="text-xs font-share-tech text-dim-500">{formatSize(file.size_bytes)}</span>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="flex items-center justify-center h-[300px]">
              <div className="text-center">
                <FolderOpen className="w-12 h-12 text-dim-500 mx-auto mb-3" />
                <p className="text-dim-400 text-sm font-exo">
                  {searchQuery ? 'No files match your search' : 'Search for files to browse'}
                </p>
                {cwd && (
                  <p className="text-hud font-share-tech text-dim-500 mt-2">{cwd}</p>
                )}
              </div>
            </div>
          )}
        </div>
        <div className="glass-card space-y-4">
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Quick Actions</h3>
          <div className="space-y-2">
            <button className="w-full text-left btn-ghost-cyan text-sm flex items-center gap-2">
              <Download className="w-4 h-4" /> Downloads
            </button>
            <button className="w-full text-left btn-ghost-cyan text-sm flex items-center gap-2">
              <FolderOpen className="w-4 h-4" /> Documents
            </button>
            <button className="w-full text-left btn-ghost-cyan text-sm flex items-center gap-2">
              <FolderOpen className="w-4 h-4" /> Desktop
            </button>
          </div>
          <div className="pt-3 border-t border-cyan-500/8">
            <h4 className="text-hud font-share-tech text-dim-500 font-medium mb-2 tracking-wider uppercase">Drop Zones</h4>
            <div className="space-y-1.5">
              <div className="text-xs font-exo text-dim-400 bg-void-700/50 px-3 py-2 rounded-lg border border-cyan-500/5">PDFs → Documents/PDFs</div>
              <div className="text-xs font-exo text-dim-400 bg-void-700/50 px-3 py-2 rounded-lg border border-cyan-500/5">Images → Pictures</div>
              <div className="text-xs font-exo text-dim-400 bg-void-700/50 px-3 py-2 rounded-lg border border-cyan-500/5">Downloads &gt;7d → Archive</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
