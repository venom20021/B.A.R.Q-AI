/**
 * Hook that persists React state across component unmount/remount cycles.
 *
 * Problem: When navigating between SPA routes, React unmounts the page component
 * and all its `useState` values are lost. On return, the component remounts fresh.
 *
 * Solution: Stores state in a global Map (keyed by a unique string) so it survives
 * component unmounting. The Map lives as long as the page is loaded (entire SPA session).
 *
 * @param key  Unique key for this state variable (e.g. "JobsPage.activeTab")
 * @param initial  Default value if no stored state exists
 * @returns  Same signature as useState — [value, setValue]
 *
 * @example
 *   // Before: const [jobs, setJobs] = useState<Job[]>([])
 *   // After:  const [jobs, setJobs] = usePersistentState<Job[]>('JobsPage.jobs', [])
 */

import { useState, useCallback } from 'react'

// ─── Global state registry (survives component unmount) ───────────────

const _registry = new Map<string, unknown>()

// ─── Hook ──────────────────────────────────────────────────────────────

export function usePersistentState<T>(
  key: string,
  initial: T,
): [T, (value: T | ((prev: T) => T)) => void] {
  // Initialize from registry if available, otherwise use initial
  const [state, setState] = useState<T>(() => {
    if (_registry.has(key)) {
      return _registry.get(key) as T
    }
    return initial
  })

  const setPersistentState = useCallback(
    (value: T | ((prev: T) => T)): void => {
      setState((prev) => {
        const next = typeof value === 'function'
          ? (value as (prev: T) => T)(prev)
          : value
        _registry.set(key, next)
        return next
      })
    },
    [key],
  )

  return [state, setPersistentState]
}

/**
 * Clear a specific key from the global state registry.
 * Useful for "reset" actions.
 */
export function clearPersistentState(key: string): void {
  _registry.delete(key)
}

/**
 * Clear ALL persistent state (e.g. on full app reset).
 */
export function clearAllPersistentState(): void {
  _registry.clear()
}
