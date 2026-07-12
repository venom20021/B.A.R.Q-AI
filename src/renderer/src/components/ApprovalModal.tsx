import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ShieldOff, AlertTriangle, Check, X, Terminal } from 'lucide-react'
import { api } from '../utils/api'

interface PendingApproval {
  command: string
  tier: 'warn' | 'dangerous'
  tier_description: string
}

export function ApprovalModal(): JSX.Element {
  const [pending, setPending] = useState<PendingApproval | null>(null)
  const [isResolving, setIsResolving] = useState(false)

  // Listen for approval-required events from the backend
  useEffect(() => {
    const handler = (e: CustomEvent<PendingApproval>): void => {
      setPending(e.detail)
    }
    window.addEventListener('barq:approval-required', handler as EventListener)
    return () => window.removeEventListener('barq:approval-required', handler as EventListener)
  }, [])

  const handleApprove = useCallback(async () => {
    if (!pending) return
    setIsResolving(true)
    try {
      // Approve via the command approve endpoint
      await api('/voice/command/approve', { command: pending.command, tier: pending.tier })
      // Execute the approved command
      await api('/voice/command/execute', { command: pending.command })
    } catch { /* ignore */ }
    setIsResolving(false)
    setPending(null)
  }, [pending])

  const handleDeny = useCallback(() => {
    setPending(null)
  }, [])

  // Keyboard shortcut: Enter = approve, Escape = deny
  useEffect(() => {
    if (!pending) return
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Enter' && !isResolving) void handleApprove()
      if (e.key === 'Escape') handleDeny()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [pending, isResolving, handleApprove, handleDeny])

  return (
    <AnimatePresence>
      {pending && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm"
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{
              opacity: 1,
              scale: 1,
              // Subtle vibration effect for dangerous commands
              x: pending.tier === 'dangerous' ? [0, -2, 2, -1, 1, 0] : 0,
            }}
            transition={{ duration: 0.4, ease: 'easeOut' }}
            className={`relative w-[420px] rounded-2xl border-2 p-6 ${
              pending.tier === 'dangerous'
                ? 'border-red-500/40 bg-red-950/30 shadow-[0_0_40px_rgba(239,68,68,0.15)]'
                : 'border-amber-500/30 bg-amber-950/20 shadow-[0_0_30px_rgba(245,158,11,0.1)]'
            } backdrop-blur-2xl`}
          >
            {/* Icon */}
            <div className={`w-12 h-12 rounded-full mx-auto mb-4 flex items-center justify-center ${
              pending.tier === 'dangerous'
                ? 'bg-red-500/20'
                : 'bg-amber-500/20'
            }`}>
              {pending.tier === 'dangerous' ? (
                <ShieldOff className="w-6 h-6 text-red-400" />
              ) : (
                <AlertTriangle className="w-6 h-6 text-amber-400" />
              )}
            </div>

            {/* Title */}
            <h3 className={`text-center text-sm font-orbitron font-bold tracking-wider mb-2 ${
              pending.tier === 'dangerous' ? 'text-red-300' : 'text-amber-300'
            }`}>
              {pending.tier === 'dangerous' ? 'DANGEROUS COMMAND' : 'MODERATE RISK COMMAND'}
            </h3>

            {/* Command display */}
            <div className="bg-void-900/60 rounded-lg p-3 mb-3 border border-cyan-500/10">
              <div className="flex items-center gap-2 mb-1">
                <Terminal className="w-3.5 h-3.5 text-cyan-300" />
                <span className="text-[10px] font-share-tech text-dim-400 uppercase tracking-wider">Command</span>
              </div>
              <code className="text-sm font-mono text-ghost/90 block break-all">{pending.command}</code>
            </div>

            {/* Description */}
            <p className="text-xs font-exo text-dim-400 text-center mb-6">
              {pending.tier_description}
            </p>

            {/* Buttons */}
            <div className="flex gap-3">
              <button
                onClick={handleDeny}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-xs font-rajdhani font-bold uppercase tracking-wider border border-red-500/30 text-red-300 bg-red-500/10 hover:bg-red-500/20 transition-all"
              >
                <X className="w-4 h-4" />
                Deny
              </button>
              <button
                onClick={handleApprove}
                disabled={isResolving}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-xs font-rajdhani font-bold uppercase tracking-wider border border-emerald-500/30 text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/20 disabled:opacity-40 transition-all"
              >
                {isResolving ? (
                  <span className="w-4 h-4 border-2 border-emerald-300/30 border-t-emerald-300 rounded-full animate-spin" />
                ) : (
                  <Check className="w-4 h-4" />
                )}
                Allow
              </button>
            </div>

            {/* Keyboard hint */}
            <p className="text-[10px] font-exo text-dim-500 text-center mt-3">
              Press <kbd className="px-1 py-0.5 rounded bg-void-700/60 text-dim-300 font-mono text-[10px]">Enter</kbd> to allow ·{' '}
              <kbd className="px-1 py-0.5 rounded bg-void-700/60 text-dim-300 font-mono text-[10px]">Esc</kbd> to deny
            </p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
