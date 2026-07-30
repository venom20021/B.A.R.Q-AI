import { useState, useCallback, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Plane,
  Youtube,
  Newspaper,
  Bell,
  Globe,
  X,
  ExternalLink,
  Clock,
  Eye,
} from 'lucide-react'
import type { RichContent, FlightContent, YouTubeContent, NewsContent, ReminderContent, GenericContent } from './DynamicContentTypes'

// ─── Props ──────────────────────────────────────────────────────────────────

interface DynamicContentPanelProps {
  content: RichContent | null
  onDismiss: () => void
}

// ─── Helpers ────────────────────────────────────────────────────────────────

const TAB_ICONS: Record<string, React.ReactNode> = {
  flights: <Plane className="w-3.5 h-3.5" />,
  youtube: <Youtube className="w-3.5 h-3.5" />,
  news: <Newspaper className="w-3.5 h-3.5" />,
  reminders: <Bell className="w-3.5 h-3.5" />,
  generic: <Globe className="w-3.5 h-3.5" />,
}

const TAB_LABELS: Record<string, string> = {
  flights: 'Flights',
  youtube: 'YouTube',
  news: 'News',
  reminders: 'Reminders',
  generic: 'Info',
}

function formatDuration(seconds: string): string {
  const secs = parseInt(seconds, 10)
  if (isNaN(secs)) return seconds
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatViews(views: string): string {
  const n = parseInt(views.replace(/[^0-9]/g, ''), 10)
  if (isNaN(n)) return views
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return views
}

// ─── Card Renderers ─────────────────────────────────────────────────────────

function FlightCard({ result }: { result: FlightContent['results'][0] }): JSX.Element {
  return (
    <div className="flex items-center gap-3 p-3 rounded-xl bg-white/[0.04] border border-white/[0.06] hover:bg-white/[0.07] hover:border-white/[0.10] transition-all duration-200 group">
      <div className="shrink-0 w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center">
        <Plane className="w-4 h-4 text-cyan-400/70" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium text-white/90 truncate">{result.airline}</span>
          <span className="text-sm font-semibold text-emerald-400 whitespace-nowrap">{result.price}</span>
        </div>
        <div className="flex items-center gap-2 mt-0.5 text-xs text-white/50">
          <span>{result.departure} → {result.arrival}</span>
          <span className="w-1 h-1 rounded-full bg-white/20" />
          <span>{result.duration}</span>
          <span className="w-1 h-1 rounded-full bg-white/20" />
          <span>{result.stops}</span>
        </div>
      </div>
      {result.link && (
        <a
          href={result.link}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 p-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity hover:bg-white/10"
        >
          <ExternalLink className="w-3.5 h-3.5 text-white/40" />
        </a>
      )}
    </div>
  )
}

function YouTubeCard({ video }: { video: YouTubeContent['results'][0] }): JSX.Element {
  return (
    <a
      href={video.url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-start gap-3 p-3 rounded-xl bg-white/[0.04] border border-white/[0.06] hover:bg-white/[0.07] hover:border-white/[0.10] transition-all duration-200 group"
    >
      {video.thumbnail ? (
        <img
          src={video.thumbnail}
          alt={video.title}
          className="shrink-0 w-20 h-14 rounded-lg object-cover bg-zinc-800"
        />
      ) : (
        <div className="shrink-0 w-20 h-14 rounded-lg bg-zinc-800 flex items-center justify-center">
          <Youtube className="w-5 h-5 text-red-400/50" />
        </div>
      )}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-white/90 leading-snug line-clamp-2 group-hover:text-cyan-300 transition-colors">
          {video.title}
        </p>
        <div className="flex items-center gap-2 mt-1.5 text-xs text-white/50">
          <span className="truncate">{video.channel}</span>
          <span className="w-1 h-1 rounded-full bg-white/20" />
          <span className="flex items-center gap-1">
            <Eye className="w-3 h-3" />
            {formatViews(video.views)}
          </span>
          {video.duration && (
            <>
              <span className="w-1 h-1 rounded-full bg-white/20" />
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                {formatDuration(video.duration)}
              </span>
            </>
          )}
        </div>
      </div>
    </a>
  )
}

function NewsCard({ article }: { article: NewsContent['results'][0] }): JSX.Element {
  return (
    <a
      href={article.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block p-3 rounded-xl bg-white/[0.04] border border-white/[0.06] hover:bg-white/[0.07] hover:border-white/[0.10] transition-all duration-200 group"
    >
      <p className="text-sm font-medium text-white/90 leading-snug group-hover:text-cyan-300 transition-colors">
        {article.title}
      </p>
      <div className="flex items-center gap-2 mt-1.5 text-xs text-white/50">
        <span>{article.source}</span>
        {article.published && (
          <>
            <span className="w-1 h-1 rounded-full bg-white/20" />
            <span>{article.published}</span>
          </>
        )}
      </div>
      {article.snippet && (
        <p className="text-xs text-white/40 mt-1.5 line-clamp-2 leading-relaxed">
          {article.snippet}
        </p>
      )}
    </a>
  )
}

function ReminderCard({ item }: { item: ReminderContent['results'][0] }): JSX.Element {
  const dueDate = new Date(item.due_at)
  const isOverdue = dueDate < new Date()
  const formatted = dueDate.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })

  return (
    <div className="flex items-start gap-3 p-3 rounded-xl bg-white/[0.04] border border-white/[0.06]">
      <div className={`shrink-0 w-8 h-8 rounded-lg flex items-center justify-center ${
        isOverdue ? 'bg-red-500/10' : 'bg-amber-500/10'
      }`}>
        <Bell className={`w-4 h-4 ${isOverdue ? 'text-red-400' : 'text-amber-400'}`} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-white/90">{item.title}</p>
        {item.message && (
          <p className="text-xs text-white/50 mt-0.5">{item.message}</p>
        )}
        <p className={`text-xs mt-1 ${isOverdue ? 'text-red-400/70' : 'text-white/40'}`}>
          {isOverdue ? 'Overdue — ' : ''}{formatted}
        </p>
      </div>
    </div>
  )
}

function GenericCard({ item }: { item: GenericContent['items'][0] }): JSX.Element {
  return (
    <div className="flex items-start gap-3 p-3 rounded-xl bg-white/[0.04] border border-white/[0.06]">
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium text-white/90">{item.label}</span>
          <span className="text-sm font-semibold text-cyan-400 whitespace-nowrap">{item.value}</span>
        </div>
        {item.detail && (
          <p className="text-xs text-white/50 mt-0.5">{item.detail}</p>
        )}
      </div>
    </div>
  )
}

// ─── Main Component ─────────────────────────────────────────────────────────

export function DynamicContentPanel({ content, onDismiss }: DynamicContentPanelProps): JSX.Element {
  const panelRef = useRef<HTMLDivElement>(null)

  // Dismiss on Escape key
  useEffect(() => {
    if (!content) return
    const handler = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onDismiss()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [content, onDismiss])

  // ─── Render content by type ──────────────────────────────────────────────

  const renderContent = (): JSX.Element | null => {
    if (!content) return null

    switch (content.type) {
      case 'flights': {
        const fc = content as FlightContent
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2 px-1 mb-3">
              <Plane className="w-4 h-4 text-cyan-400" />
              <span className="text-sm text-white/70">
                {fc.origin} → {fc.destination}
              </span>
              <span className="text-xs text-white/40 ml-auto">
                {fc.date}
              </span>
            </div>
            {fc.results.map((r, i) => (
              <FlightCard key={i} result={r} />
            ))}
            {fc.summary && (
              <p className="text-xs text-white/40 italic px-1 pt-2 border-t border-white/[0.06]">
                💬 {fc.summary}
              </p>
            )}
          </div>
        )
      }

      case 'youtube': {
        const yc = content as YouTubeContent
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2 px-1 mb-3">
              <Youtube className="w-4 h-4 text-red-400" />
              <span className="text-sm text-white/70">
                Search: "{yc.query}"
              </span>
            </div>
            {yc.results.map((v, i) => (
              <YouTubeCard key={i} video={v} />
            ))}
            {yc.summary && (
              <p className="text-xs text-white/40 italic px-1 pt-2 border-t border-white/[0.06]">
                💬 {yc.summary}
              </p>
            )}
          </div>
        )
      }

      case 'news': {
        const nc = content as NewsContent
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2 px-1 mb-3">
              <Newspaper className="w-4 h-4 text-blue-400" />
              <span className="text-sm text-white/70">
                Topic: {nc.topic}
              </span>
            </div>
            {nc.results.map((a, i) => (
              <NewsCard key={i} article={a} />
            ))}
            {nc.summary && (
              <p className="text-xs text-white/40 italic px-1 pt-2 border-t border-white/[0.06]">
                💬 {nc.summary}
              </p>
            )}
          </div>
        )
      }

      case 'reminders': {
        const rc = content as ReminderContent
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2 px-1 mb-3">
              <Bell className="w-4 h-4 text-amber-400" />
              <span className="text-sm text-white/70">
                Reminders ({rc.results.length})
              </span>
            </div>
            {rc.results.map((r) => (
              <ReminderCard key={r.id} item={r} />
            ))}
            {rc.summary && (
              <p className="text-xs text-white/40 italic px-1 pt-2 border-t border-white/[0.06]">
                💬 {rc.summary}
              </p>
            )}
          </div>
        )
      }

      case 'generic': {
        const gc = content as GenericContent
        return (
          <div className="space-y-2">
            <div className="flex items-center gap-2 px-1 mb-3">
              <Globe className="w-4 h-4 text-purple-400" />
              <span className="text-sm text-white/70">{gc.title}</span>
            </div>
            {gc.items.map((item, i) => (
              <GenericCard key={i} item={item} />
            ))}
            {gc.summary && (
              <p className="text-xs text-white/40 italic px-1 pt-2 border-t border-white/[0.06]">
                💬 {gc.summary}
              </p>
            )}
          </div>
        )
      }

      default:
        return null
    }
  }

  // ─── Nothing to show ─────────────────────────────────────────────────────

  if (!content) return <></>

  const itemCount =
    content.type === 'flights' ? (content as FlightContent).results.length :
    content.type === 'youtube' ? (content as YouTubeContent).results.length :
    content.type === 'news' ? (content as NewsContent).results.length :
    content.type === 'reminders' ? (content as ReminderContent).results.length :
    content.type === 'generic' ? (content as GenericContent).items.length :
    0

  return (
    <AnimatePresence>
      <motion.div
        ref={panelRef}
        key="dynamic-content-panel"
        initial={{ opacity: 0, y: 24, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 16, scale: 0.97 }}
        transition={{ type: 'spring', damping: 28, stiffness: 280, mass: 0.8 }}
        className="fixed bottom-[140px] left-1/2 -translate-x-1/2 z-[65] w-full max-w-xl pointer-events-auto"
      >
        {/* Panel body */}
        <div className="mx-4 backdrop-blur-xl bg-zinc-950/80 border border-white/[0.08] rounded-2xl shadow-2xl shadow-black/40 overflow-hidden">
          {/* Header bar */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-white/40 uppercase tracking-wider">
                {TAB_LABELS[content.type] || 'Results'}
              </span>
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400/80 font-medium">
                {itemCount}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={onDismiss}
                className="p-1.5 rounded-lg hover:bg-white/10 transition-colors text-white/40 hover:text-white/70"
                title="Close panel (Esc)"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Content area */}
          <div className="max-h-[50vh] overflow-y-auto p-4 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
            {renderContent()}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
