/**
 * Per-brain "last selected node" memory for the Knowledge Graph page.
 *
 * Keeps the entity id that was last opened in each brain's details panel so
 * the panel can be restored automatically when the user returns to that
 * brain.  Persisted to localStorage so the memory also survives app restarts.
 *
 * All helpers are pure (they return new maps instead of mutating), keeping
 * them trivially unit-testable; only load/save touch localStorage.
 */

const STORAGE_KEY = 'barq.brain.lastSelected'

/** Map of brain type → last selected entity id. */
export type BrainSelectionMemory = Record<string, string>

/** Read the stored memory, tolerating malformed/absent data. */
export function loadLastSelected(): BrainSelectionMemory {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const map: BrainSelectionMemory = {}
      for (const [brain, id] of Object.entries(parsed as Record<string, unknown>)) {
        if (typeof id === 'string' && id.trim()) {
          map[brain] = id
        }
      }
      return map
    }
  } catch {
    // malformed JSON or storage unavailable — start fresh
  }
  return {}
}

/** Persist the memory to localStorage (best-effort). */
export function saveLastSelected(memory: BrainSelectionMemory): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(memory))
  } catch {
    // storage may be unavailable (private mode / disk full) — best-effort only
  }
}

/** Return a new memory with the entity recorded for a brain. */
export function rememberSelection(
  memory: BrainSelectionMemory,
  brain: string,
  entityId: string,
): BrainSelectionMemory {
  if (!brain || !entityId) return memory
  // Short-circuit when nothing changes so restore paths don't churn the map.
  if (memory[brain] === entityId) return memory
  return { ...memory, [brain]: entityId }
}

/** Return a new memory with the brain's entry removed (same ref if absent). */
export function forgetSelection(
  memory: BrainSelectionMemory,
  brain: string,
): BrainSelectionMemory {
  if (!brain || !(brain in memory)) return memory
  const next = { ...memory }
  delete next[brain]
  return next
}

/**
 * Decide whether a brain's remembered node can be restored from the loaded
 * graph.  Returns ``null`` when nothing is remembered, otherwise the entity id
 * plus whether it still exists in the graph (so callers can drop stale memory).
 */
export function resolveRestoreTarget(
  nodeIds: readonly string[],
  memory: BrainSelectionMemory,
  brain: string,
): { id: string; missing: boolean } | null {
  const rememberedId = memory[brain]
  if (!rememberedId) return null
  return nodeIds.includes(rememberedId)
    ? { id: rememberedId, missing: false }
    : { id: rememberedId, missing: true }
}
