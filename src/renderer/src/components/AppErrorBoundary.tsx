import { Component } from 'react'
import { AlertTriangle, Home, RefreshCw, RotateCcw } from 'lucide-react'
import type { ErrorInfo, ReactNode } from 'react'

// ─── App-wide Error Boundary ────────────────────────────────────────────
//
// Catches render-time crashes anywhere below it so a broken page shows a
// recovery screen instead of a blank window.  Used at two levels:
//   1. `main.tsx` — wraps the whole <App /> (last-resort net for crashes in
//      providers or the router itself).  'screen' variant covers the window.
//   2. `App.tsx`  — wraps the <Routes> content area ('inline' variant) so the
//      sidebar/navbar survive a page crash.  `resetKey` clears the crash on
//      navigation and `onReset` lets the user jump back to the dashboard.
//
// Note: like all error boundaries, this catches render/lifecycle errors only —
// not errors thrown inside event handlers or async callbacks.

interface AppErrorBoundaryProps {
  children: ReactNode
  /** When this value changes, a crashed boundary resets itself (e.g. route path). */
  resetKey?: string
  /** Renders a "Back to dashboard" action — typically navigate('/dashboard'). */
  onReset?: () => void
  /** 'screen' covers the whole window; 'inline' fills the content area. */
  variant?: 'screen' | 'inline'
  /** Optional title shown on the recovery screen. */
  title?: string
}

interface AppErrorBoundaryState {
  hasError: boolean
  error: Error | null
  prevResetKey?: string
}

export class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): Partial<AppErrorBoundaryState> {
    return { hasError: true, error }
  }

  static getDerivedStateFromProps(
    props: AppErrorBoundaryProps,
    state: AppErrorBoundaryState,
  ): Partial<AppErrorBoundaryState> | null {
    if (state.prevResetKey !== props.resetKey) {
      return { prevResetKey: props.resetKey, hasError: false, error: null }
    }
    return null
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Always surface the crash to the console for diagnosis.
    console.error('[AppErrorBoundary] Render crash caught:', error, errorInfo)
    // Notify the Electron main process if it's listening (e.g. for logging).
    try {
      window.dispatchEvent(
        new CustomEvent('barq:renderer-error', {
          detail: { message: error.message, stack: error.stack },
        }),
      )
    } catch {
      // dispatching is best-effort only
    }
  }

  private handleTryAgain = (): void => {
    this.setState({ hasError: false, error: null })
  }

  private handleReload = (): void => {
    window.location.reload()
  }

  render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children
    }

    const { variant = 'screen', onReset, title } = this.props
    const errorMessage = (this.state.error?.message ?? 'Unknown render error').slice(0, 220)

    const wrapperClass =
      variant === 'screen'
        ? 'fixed inset-0 z-[999] flex items-center justify-center bg-[radial-gradient(ellipse_at_center,#18181b_0%,#000_70%)] p-6'
        : 'w-full h-full flex items-center justify-center p-6'

    return (
      <div className={wrapperClass} role="alert" aria-live="assertive">
        <div className="relative w-full max-w-md rounded-2xl border border-white/10 bg-zinc-950/80 p-8 text-center shadow-2xl backdrop-blur-xl">
          {/* Icon with soft red glow */}
          <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full border border-red-500/30 bg-red-500/10 shadow-[0_0_28px_rgba(239,68,68,0.18)]">
            <AlertTriangle className="h-6 w-6 text-red-400" />
          </div>

          <h2 className="text-lg font-semibold text-white">
            {title ?? 'Something went wrong'}
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-zinc-400">
            The app hit an unexpected error while rendering this view. Your data is
            safe — try again, or reload the app.
          </p>

          {/* Error detail — helpful for diagnosing in a local desktop app */}
          <div className="mt-4 rounded-lg border border-red-500/20 bg-black/40 px-3 py-2 text-left">
            <p className="truncate font-mono text-[11px] leading-relaxed text-red-300/70">
              {errorMessage}
            </p>
          </div>

          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <button
              onClick={this.handleTryAgain}
              className="inline-flex items-center gap-2 rounded-lg border border-cyan-400/40 bg-cyan-500/15 px-4 py-2 text-sm font-medium text-cyan-300 transition-all hover:scale-[1.02] hover:bg-cyan-500/25 hover:text-cyan-200 active:scale-[0.98]"
            >
              <RotateCcw className="h-4 w-4" />
              Try again
            </button>

            {onReset && (
              <button
                onClick={onReset}
                className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm text-zinc-300 transition-all hover:scale-[1.02] hover:bg-white/10 active:scale-[0.98]"
              >
                <Home className="h-4 w-4" />
                Back to dashboard
              </button>
            )}

            <button
              onClick={this.handleReload}
              className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm text-zinc-300 transition-all hover:scale-[1.02] hover:bg-white/10 active:scale-[0.98]"
            >
              <RefreshCw className="h-4 w-4" />
              Reload app
            </button>
          </div>
        </div>
      </div>
    )
  }
}

export default AppErrorBoundary
