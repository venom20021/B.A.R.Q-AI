import { useState, useCallback, useRef, useEffect } from 'react'
import { api as apiFn } from '../utils/api'

// ─── Types ──────────────────────────────────────────────────────────────

export type UseApiState = 'idle' | 'loading' | 'success' | 'error'

export interface UseApiResult<T> {
  /** The successfully fetched data, or `undefined` before first success. */
  data: T | undefined
  /** Current lifecycle state: idle → loading → success | error */
  state: UseApiState
  /** Convenience boolean — true when state === 'loading' */
  loading: boolean
  /** Error message string when state === 'error', otherwise `null`. */
  error: string | null
  /** Error object when state === 'error', or `null`. */
  errorObject: Error | null
  /** Manually trigger execution. Overrides `data` from options if provided. */
  execute: (overrideData?: Record<string, unknown>) => Promise<T | undefined>
  /** Reset all state back to idle defaults. */
  reset: () => void
  /** True after the first successful execution (stays true even on re-fetches). */
  hasData: boolean
}

export interface UseApiOptions<T = Record<string, unknown>> {
  /**
   * Payload data sent as the JSON body.
   * When provided, the bridge sends a POST; otherwise a GET.
   * Can be overridden at call-time via `execute(overrideData)`.
   */
  data?: Record<string, unknown>
  /**
   * Whether to fire the request immediately on mount (and when `deps` change).
   * @default true
   */
  immediate?: boolean
  /** Callback fired on successful response with typed data. */
  onSuccess?: (data: T) => void
  /** Callback fired on error. Receives the error message string. */
  onError?: (message: string) => void
  /**
   * Optional debounce (in ms) applied to automatic re-fetches driven by `deps`.
   * Manual `execute()` calls are never debounced.
   * @default 0
   */
  debounceMs?: number
  /** Dependencies that trigger an automatic re-fetch when changed. */
  deps?: React.DependencyList
  /**
   * When `true`, suppresses state updates after unmount (avoids React warnings).
   * The hook already internally guards against this.
   */
  keepAlive?: boolean
}

// ─── Hook ────────────────────────────────────────────────────────────────

/**
 * React hook wrapping the `api()` helper with built-in loading, error, and
 * data state management.
 *
 * @param endpoint  API endpoint path (e.g. `/voice/status`)
 * @param options   Configuration for auto-execution, callbacks, debouncing
 *
 * @example
 *   const { data, loading, error, execute } = useApi<VoiceStatus>('/voice/status')
 *
 *   // Manual trigger with override data
 *   const handleSubmit = useCallback(() => execute({ city: 'Tokyo' }), [execute])
 */
export function useApi<T = Record<string, unknown>>(
  endpoint: string,
  options: UseApiOptions<T> = {} as UseApiOptions<T>,
): UseApiResult<T> {
  const {
    data: defaultData,
    immediate = true,
    onSuccess,
    onError,
    debounceMs = 0,
    deps = [],
    keepAlive,
  } = options

  // ── State ────────────────────────────────────────────────────────────
  const [data, setData] = useState<T | undefined>(undefined)
  const [state, setState] = useState<UseApiState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [errorObject, setErrorObject] = useState<Error | null>(null)
  const [hasData, setHasData] = useState(false)

  // ── Refs for lifecycle safety ───────────────────────────────────────
  const mountedRef = useRef(true)
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const latestPromiseRef = useRef<Promise<T | undefined> | null>(null)

  // Cleanup on unmount
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
      }
    }
  }, [])

  // ── Core execute function ───────────────────────────────────────────
  const execute = useCallback(
    async (overrideData?: Record<string, unknown>): Promise<T | undefined> => {
      // Debounce guard — if a debounce is pending, cancel it for manual calls
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
        debounceTimerRef.current = null
      }

      setState('loading')
      setError(null)
      setErrorObject(null)

      const payload = overrideData !== undefined ? overrideData : defaultData
      const promise = apiFn<T>(endpoint, payload)
      latestPromiseRef.current = promise

      try {
        const result = await promise
        // Guard against stale responses
        if (latestPromiseRef.current !== promise) return result
        if (!mountedRef.current && !keepAlive) return result

        if (result !== undefined) {
          setData(result)
          setHasData(true)
          setState('success')
          setError(null)
          setErrorObject(null)
          onSuccess?.(result)
        } else {
          setState('error')
          const msg = `Empty response from ${endpoint}`
          setError(msg)
          setErrorObject(new Error(msg))
          onError?.(msg)
        }
        return result
      } catch (err) {
        if (latestPromiseRef.current !== promise) return undefined
        if (!mountedRef.current && !keepAlive) return undefined

        const msg =
          err instanceof Error ? err.message : `Request to ${endpoint} failed`
        setState('error')
        setError(msg)
        setErrorObject(err instanceof Error ? err : new Error(String(err)))
        onError?.(msg)
        return undefined
      }
    },
    [endpoint, defaultData, onSuccess, onError, keepAlive],
  )

  // ── Reset ────────────────────────────────────────────────────────────
  const reset = useCallback(() => {
    setData(undefined)
    setState('idle')
    setError(null)
    setErrorObject(null)
    setHasData(false)
  }, [])

  // ── Automatic execution ─────────────────────────────────────────────
  useEffect(() => {
    if (!immediate) return

    if (debounceMs > 0) {
      debounceTimerRef.current = setTimeout(() => {
        void execute()
      }, debounceMs)
      return () => {
        if (debounceTimerRef.current) {
          clearTimeout(debounceTimerRef.current)
        }
      }
    }

    void execute()
  }, [immediate, debounceMs, endpoint, ...deps])

  return {
    data,
    state,
    loading: state === 'loading',
    error,
    errorObject,
    execute,
    reset,
    hasData,
  }
}
