import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Download, RefreshCw, Rocket, X, AlertTriangle } from 'lucide-react'

// Structural mirror of the UpdateState union broadcast by the main process on
// `update:status` (see src/main/updater.ts). Kept local so this component is
// self-contained; it matches the type from window.barq.updater.onStatus.
type UpdateStatus =
  | { state: 'dev' }
  | { state: 'idle' }
  | { state: 'checking' }
  | { state: 'available'; version: string }
  | { state: 'not-available'; version?: string }
  | { state: 'downloading'; percent: number }
  | { state: 'downloaded'; version: string }
  | { state: 'error'; message: string }

/**
 * UpdateToast — subscribes to the auto-updater status channel
 * (barq.updater.onStatus) and surfaces a compact glass toast when an update
 * is being downloaded or is ready to install.
 *
 * Visible states:
 *  - available    → "Update vX downloading…" (autoDownload is on)
 *  - downloading  → progress bar with percent
 *  - downloaded   → Restart-to-install button + dismiss
 *  - error        → failure message + Try Again + dismiss
 *
 * Silent states (dev, idle, checking, not-available) render nothing.
 */

const toastVariants = {
  initial: { opacity: 0, y: 20, scale: 0.95 },
  animate: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: 20, scale: 0.95 },
}

export function UpdateToast(): JSX.Element {
  const [status, setStatus] = useState<UpdateStatus | null>(null)
  const [restarting, setRestarting] = useState(false)

  useEffect(() => {
    if (!window.barq?.updater?.onStatus) return
    const unsubscribe = window.barq.updater.onStatus((next) => setStatus(next))
    return () => {
      if (typeof unsubscribe === 'function') unsubscribe()
    }
  }, [])

  const dismiss = useCallback(() => setStatus(null), [])

  const handleRestart = useCallback(async () => {
    setRestarting(true)
    try {
      const res = await window.barq?.updater?.restartToInstall?.()
      // The main process resolves with { success: false } instead of
      // rejecting (e.g. dev mode / failure) — restore the button then.
      if (!res?.success) setRestarting(false)
    } catch {
      setRestarting(false)
    }
  }, [])

  const handleCheckAgain = useCallback(async () => {
    try {
      await window.barq?.updater?.checkForUpdates?.()
    } catch {
      // ignored — the error toast stays visible
    }
  }, [])

  // Whether we currently have anything worth showing.
  const show =
    status?.state === 'available' ||
    status?.state === 'downloading' ||
    status?.state === 'downloaded' ||
    status?.state === 'error'

  let content: JSX.Element | null = null

  if (status?.state === 'downloaded') {
    content = (
      <motion.div
        key="update-ready"
        variants={toastVariants}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={{ duration: 0.25, ease: 'easeOut' }}
        className="fixed bottom-6 right-6 z-40 w-80 overflow-hidden rounded-xl bg-void-900/80 backdrop-blur-2xl border border-white/[0.06] shadow-2xl"
        role="status"
      >
        {/* Header bar */}
        <div className="h-1 bg-gradient-to-r from-emerald-400 via-emerald-500 to-cyan-400 shadow-glow-cyan-sm" />

        <div className="p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Rocket className="w-4 h-4 text-emerald-300" />
              <span className="text-xs font-share-tech text-ghost/60 uppercase tracking-wider">
                Update Ready
              </span>
            </div>
            <button
              onClick={dismiss}
              className="p-1 rounded hover:bg-emerald-500/10 transition-colors"
              aria-label="Dismiss update notice"
            >
              <X className="w-3 h-3 text-dim-400" />
            </button>
          </div>

          <div>
            <p className="text-sm font-exo text-ghost">
              BARQ v{status.version} downloaded
            </p>
            <p className="text-[11px] font-exo text-dim-500 mt-0.5">
              Restart to apply the update.
            </p>
          </div>

          <button
            onClick={() => { void handleRestart() }}
            disabled={restarting}
            className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-gradient-to-r from-emerald-500/20 to-cyan-500/20 border border-emerald-400/30 text-emerald-200 text-xs font-share-tech uppercase tracking-wider hover:from-emerald-500/30 hover:to-cyan-500/30 hover:border-emerald-300/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${restarting ? 'animate-spin' : ''}`} />
            {restarting ? 'Restarting…' : 'Restart & Install'}
          </button>
        </div>
      </motion.div>
    )
  } else if (status?.state === 'error') {
    content = (
      <motion.div
        key="update-error"
        variants={toastVariants}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={{ duration: 0.25, ease: 'easeOut' }}
        className="fixed bottom-6 right-6 z-40 w-80 overflow-hidden rounded-xl bg-void-900/80 backdrop-blur-2xl border border-white/[0.06] shadow-2xl"
        role="alert"
      >
        <div className="h-1 bg-gradient-to-r from-amber-400 via-orange-500 to-red-500" />

        <div className="p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-300" />
              <span className="text-xs font-share-tech text-ghost/60 uppercase tracking-wider">
                Update Failed
              </span>
            </div>
            <button
              onClick={dismiss}
              className="p-1 rounded hover:bg-amber-500/10 transition-colors"
              aria-label="Dismiss update error"
            >
              <X className="w-3 h-3 text-dim-400" />
            </button>
          </div>

          <p className="text-xs font-exo text-dim-400 leading-relaxed">
            {status.message || 'Something went wrong while checking for updates.'}
          </p>

          <button
            onClick={() => { void handleCheckAgain() }}
            className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-400/30 text-amber-200 text-xs font-share-tech uppercase tracking-wider hover:bg-amber-500/20 transition-all"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Try Again
          </button>
        </div>
      </motion.div>
    )
  } else if (status?.state === 'available' || status?.state === 'downloading') {
    const percent = status.state === 'downloading' ? Math.round(status.percent) : 0
    const indeterminate = status.state === 'available'

    content = (
      <motion.div
        key="update-progress"
        variants={toastVariants}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={{ duration: 0.25, ease: 'easeOut' }}
        className="fixed bottom-6 right-6 z-40 w-80 overflow-hidden rounded-xl bg-void-900/80 backdrop-blur-2xl border border-white/[0.06] shadow-2xl"
        role="status"
      >
        {/* Header bar */}
        <div className="h-1 bg-gradient-to-r from-cyan-400 via-cyan-500 to-cyan-400 shadow-glow-cyan-sm" />

        <div className="p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Download className="w-4 h-4 text-cyan-300" />
              <span className="text-xs font-share-tech text-ghost/60 uppercase tracking-wider">
                {indeterminate ? 'Update Found' : 'Downloading'}
              </span>
            </div>
            <button
              onClick={dismiss}
              className="p-1 rounded hover:bg-cyan-500/10 transition-colors"
              aria-label="Dismiss update notice"
            >
              <X className="w-3 h-3 text-dim-400" />
            </button>
          </div>

          <div>
            <p className="text-sm font-exo text-ghost">
              {indeterminate
                ? `BARQ v${status.version} is downloading…`
                : `Downloading update… ${percent}%`}
            </p>
            <p className="text-[11px] font-exo text-dim-500 mt-0.5">
              {indeterminate
                ? 'Preparing the update in the background.'
                : 'You can keep working — it installs on restart.'}
            </p>
          </div>

          {/* Progress bar */}
          <div className="h-1.5 rounded-full bg-void-700/60 overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{
                width: indeterminate ? '40%' : `${Math.min(percent, 100)}%`,
              }}
              transition={
                indeterminate
                  ? { repeat: Infinity, repeatType: 'reverse', duration: 1.2, ease: 'easeInOut' }
                  : { duration: 0.4, ease: 'easeOut' }
              }
              className="h-full rounded-full bg-cyan-500 shadow-[0_0_8px_rgba(6,182,212,0.5)]"
            />
          </div>
        </div>
      </motion.div>
    )
  }

  return (
    <AnimatePresence>
      {show && content}
    </AnimatePresence>
  )
}
