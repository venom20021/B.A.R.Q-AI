import { useState, useEffect, useCallback, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Terminal, AlertTriangle, ShieldOff, X } from 'lucide-react'

interface ActionEntry {
  id: number
  action: string
  description: string
  severity: 'info' | 'warning' | 'danger'
  created_at: string
}

interface FloatingActionLogProps {
  pollInterval?: number // ms between polls, default 5000
}

export function FloatingActionLog({ pollInterval = 5000 }: FloatingActionLogProps): JSX.Element {
  const [actions, setActions] = useState<ActionEntry[]>([])
  const [isExpanded, setIsExpanded] = useState(false)
  const [hasUnread, setHasUnread] = useState(false)
  const prevCountRef = useRef(0)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetchActions = useCallback(async () => {
    try {
      // Use the preload bridge method which unwraps the IPC envelope
      const resp = await window.barq?.voice.actionLog.recent(10)
      if (resp?.success && resp.data) {
        const data = resp.data as { actions: ActionEntry[] }
        const entries = data.actions || []
        if (entries.length > prevCountRef.current) {
          // New action arrived
          setActions(entries)
          if (!isExpanded) setHasUnread(true)
          // Auto-dismiss after 5s
          if (timeoutRef.current) clearTimeout(timeoutRef.current)
          timeoutRef.current = setTimeout(() => {
            setActions([])
            setHasUnread(false)
          }, 5000)
        } else {
          setActions(entries)
        }
        prevCountRef.current = entries.length
      }
    } catch { /* ignore */ }
  }, [isExpanded])

  // Poll for new actions
  useEffect(() => {
    void fetchActions()
    const interval = setInterval(fetchActions, pollInterval)
    return () => {
      clearInterval(interval)
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [fetchActions, pollInterval])

  const severityConfig = {
    info: {
      icon: Terminal,
      border: 'border-cyan-500/20',
      bg: 'bg-cyan-500/8',
      dot: 'bg-cyan-400',
    },
    warning: {
      icon: AlertTriangle,
      border: 'border-amber-500/20',
      bg: 'bg-amber-500/8',
      dot: 'bg-amber-400',
    },
    danger: {
      icon: ShieldOff,
      border: 'border-red-500/20',
      bg: 'bg-red-500/8',
      dot: 'bg-red-400',
    },
  }

  return (
    <>
      {/* Bell indicator when there are unread actions */}
      {hasUnread && !isExpanded && actions.length > 0 && (
        <motion.button
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          onClick={() => { setIsExpanded(true); setHasUnread(false) }}
          className="fixed bottom-6 right-6 z-40 w-10 h-10 rounded-full bg-cyan-500/15 border border-cyan-500/30 flex items-center justify-center shadow-glow-cyan-sm"
        >
          <Terminal className="w-4 h-4 text-cyan-300" />
          <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping" />
        </motion.button>
      )}

      {/* Floating action log panel */}
      <AnimatePresence>
        {(isExpanded || actions.length > 0) && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.95 }}
            className="fixed bottom-20 right-6 z-40 w-80 max-h-72 overflow-hidden rounded-xl border border-cyan-500/15 bg-void-900/85 backdrop-blur-xl shadow-2xl"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-3 py-2 border-b border-cyan-500/10">
              <div className="flex items-center gap-2">
                <Terminal className="w-3.5 h-3.5 text-cyan-300" />
                <span className="text-[10px] font-share-tech text-ghost/60 uppercase tracking-wider">Action Log</span>
              </div>
              <button
                onClick={() => { setIsExpanded(false); setActions([]) }}
                className="p-1 rounded hover:bg-cyan-500/10 transition-colors"
              >
                <X className="w-3 h-3 text-dim-400" />
              </button>
            </div>

            {/* Action entries */}
            <div className="overflow-y-auto max-h-56 scroll-cyan p-2 space-y-1">
              {actions.length === 0 ? (
                <p className="text-[10px] font-exo text-dim-500 text-center py-3">No recent actions</p>
              ) : (
                actions.map((entry) => {
                  const cfg = severityConfig[entry.severity] || severityConfig.info
                  const Icon = cfg.icon
                  return (
                    <motion.div
                      key={entry.id}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      className={`flex items-start gap-2.5 px-2.5 py-2 rounded-lg ${cfg.bg} ${cfg.border} border`}
                    >
                      <Icon className={`w-3.5 h-3.5 mt-0.5 flex-shrink-0 ${
                        entry.severity === 'danger' ? 'text-red-400' :
                        entry.severity === 'warning' ? 'text-amber-400' : 'text-cyan-300'
                      }`} />
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-rajdhani font-semibold text-ghost/80 truncate">
                          {entry.description}
                        </p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-[10px] font-exo text-dim-500">{entry.action}</span>
                          <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
                        </div>
                      </div>
                    </motion.div>
                  )
                })
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
