import { describe, it, expect, beforeEach } from 'vitest'

import {
  loadLastSelected,
  saveLastSelected,
  rememberSelection,
  forgetSelection,
  resolveRestoreTarget,
  type BrainSelectionMemory,
} from './brainSelectionMemory'

const STORAGE_KEY = 'barq.brain.lastSelected'

beforeEach(() => {
  window.localStorage.clear()
})

// ─── loadLastSelected ─────────────────────────────────────────────────────

describe('loadLastSelected', () => {
  it('returns an empty map when nothing is stored', () => {
    expect(loadLastSelected()).toEqual({})
  })

  it('returns an empty map for malformed JSON', () => {
    window.localStorage.setItem(STORAGE_KEY, 'not json {')
    expect(loadLastSelected()).toEqual({})
  })

  it('returns an empty map for non-object payloads', () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([1, 2, 3]))
    expect(loadLastSelected()).toEqual({})
  })

  it('parses a stored map and drops non-string ids', () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ general: 'python', career: 'google', ai_chats: 42, empty: '' }),
    )
    expect(loadLastSelected()).toEqual({ general: 'python', career: 'google' })
  })
})

// ─── saveLastSelected (round-trip) ────────────────────────────────────────

describe('saveLastSelected', () => {
  it('persists the map so loadLastSelected round-trips it', () => {
    saveLastSelected({ general: 'python', career: 'google' })
    expect(loadLastSelected()).toEqual({ general: 'python', career: 'google' })
  })

  it('overwrites previous storage', () => {
    saveLastSelected({ general: 'python' })
    saveLastSelected({ career: 'google' })
    expect(loadLastSelected()).toEqual({ career: 'google' })
  })
})

// ─── rememberSelection ────────────────────────────────────────────────────

describe('rememberSelection', () => {
  it('records the entity for a brain', () => {
    const next = rememberSelection({}, 'general', 'python')
    expect(next).toEqual({ general: 'python' })
  })

  it('updates an existing entry without mutating the input map', () => {
    const memory: BrainSelectionMemory = { general: 'python' }
    const next = rememberSelection(memory, 'general', 'rust')
    expect(next).toEqual({ general: 'rust' })
    expect(memory).toEqual({ general: 'python' })
  })

  it('keeps other brains intact', () => {
    const next = rememberSelection({ career: 'google' }, 'general', 'python')
    expect(next).toEqual({ general: 'python', career: 'google' })
  })

  it('ignores empty brain or entity ids', () => {
    const memory: BrainSelectionMemory = { general: 'python' }
    expect(rememberSelection(memory, '', 'python')).toBe(memory)
    expect(rememberSelection(memory, 'general', '')).toBe(memory)
  })

  it('returns the same reference when the entry is unchanged', () => {
    // Restore paths re-remember the exact id already stored — no churn allowed.
    const memory: BrainSelectionMemory = { general: 'python' }
    expect(rememberSelection(memory, 'general', 'python')).toBe(memory)
  })
})

// ─── forgetSelection ──────────────────────────────────────────────────────

describe('forgetSelection', () => {
  it('removes the brain entry immutably', () => {
    const memory: BrainSelectionMemory = { general: 'python', career: 'google' }
    const next = forgetSelection(memory, 'general')
    expect(next).toEqual({ career: 'google' })
    expect(memory).toEqual({ general: 'python', career: 'google' })
  })

  it('returns the same reference when the brain has no entry', () => {
    const memory: BrainSelectionMemory = { general: 'python' }
    expect(forgetSelection(memory, 'career')).toBe(memory)
    expect(forgetSelection(memory, '')).toBe(memory)
  })

  it('does not touch other brains', () => {
    const next = forgetSelection({ general: 'python', career: 'google' }, 'general')
    expect(next).toEqual({ career: 'google' })
  })
})

// ─── resolveRestoreTarget ──────────────────────────────────────────────────

describe('resolveRestoreTarget', () => {
  it('returns null when nothing is remembered for the brain', () => {
    expect(resolveRestoreTarget(['python'], {}, 'general')).toBeNull()
    expect(resolveRestoreTarget(['python'], { career: 'google' }, 'general')).toBeNull()
  })

  it('returns the id when the remembered node exists in the graph', () => {
    expect(resolveRestoreTarget(['python', 'rust'], { general: 'python' }, 'general'))
      .toEqual({ id: 'python', missing: false })
  })

  it('flags a missing node so callers can drop stale memory', () => {
    expect(resolveRestoreTarget(['rust'], { general: 'python' }, 'general'))
      .toEqual({ id: 'python', missing: true })
  })

  it('is scoped to the requested brain', () => {
    expect(resolveRestoreTarget(['python'], { career: 'python' }, 'general')).toBeNull()
  })
})
