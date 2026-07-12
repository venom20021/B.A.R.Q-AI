import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api, apiRaw } from './api'

// ─── Mock window.barq.python.request ─────────────────────────────────

const mockPythonRequest = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  Object.defineProperty(window, 'barq', {
    value: {
      python: {
        request: mockPythonRequest,
      },
    },
    configurable: true,
    writable: true,
  })
})

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).barq
})

// ═══════════════════════════════════════════════════════════════════════
// api() — typed helper with unwrapping
// ═══════════════════════════════════════════════════════════════════════

describe('api()', () => {
  it('returns the response for a GET request (no data)', async () => {
    mockPythonRequest.mockResolvedValue({ status: 'ok', version: '2.0' })

    const result = await api('/health')

    expect(mockPythonRequest).toHaveBeenCalledWith('/health', undefined)
    expect(result).toEqual({ status: 'ok', version: '2.0' })
  })

  it('sends data as POST body when data is provided', async () => {
    mockPythonRequest.mockResolvedValue({ result: 'success' })

    const result = await api('/agent/execute', { goal: 'test' })

    expect(mockPythonRequest).toHaveBeenCalledWith('/agent/execute', { goal: 'test' })
    expect(result).toEqual({ result: 'success' })
  })

  it('unwraps { success: true, data: T } responses', async () => {
    mockPythonRequest.mockResolvedValue({
      success: true,
      data: { items: ['a', 'b'] },
    })

    const result = await api<{ items: string[] }>('/memory/memory')

    expect(result).toEqual({ items: ['a', 'b'] })
  })

  it('returns undefined for { success: false } responses', async () => {
    mockPythonRequest.mockResolvedValue({
      success: false,
      error: 'Not authorized',
    })

    const result = await api('/voice/status')

    expect(result).toBeUndefined()
  })

  it('returns undefined for { success: true, data: null }', async () => {
    mockPythonRequest.mockResolvedValue({
      success: true,
      data: null,
    })

    const result = await api('/voice/status')

    expect(result).toBeUndefined()
  })

  it('returns undefined for { success: true } with no data field', async () => {
    mockPythonRequest.mockResolvedValue({
      success: true,
    })

    const result = await api('/voice/status')

    expect(result).toBeUndefined()
  })

  it('returns undefined when python.request throws', async () => {
    mockPythonRequest.mockRejectedValue(new Error('Network error'))

    const result = await api('/voice/status')

    expect(result).toBeUndefined()
  })

  it('returns undefined when window.barq is undefined', async () => {
    delete (window as unknown as Record<string, unknown>).barq

    const result = await api('/voice/status')

    expect(result).toBeUndefined()
  })

  it('returns undefined when window.barq.python is undefined', async () => {
    Object.defineProperty(window, 'barq', {
      value: {},
      configurable: true,
      writable: true,
    })

    const result = await api('/voice/status')

    expect(result).toBeUndefined()
  })

  it('preserves generic return type when response is not wrapped', async () => {
    interface VoiceStatus {
      is_listening: boolean
      language: string
    }
    mockPythonRequest.mockResolvedValue({
      is_listening: true,
      language: 'en',
    })

    const result = await api<VoiceStatus>('/voice/status')

    expect(result).toEqual({ is_listening: true, language: 'en' })
  })

  it('handles numeric/primitive responses (not wrapped)', async () => {
    mockPythonRequest.mockResolvedValue(42)

    const result = await api('/numeric-endpoint')

    expect(result).toBe(42)
  })

  it('sends undefined data as undefined (GET)', async () => {
    mockPythonRequest.mockResolvedValue(null)

    await api('/health')

    expect(mockPythonRequest).toHaveBeenCalledWith('/health', undefined)
  })

  it('passes empty object as request body when explicitly provided', async () => {
    mockPythonRequest.mockResolvedValue({ status: 'stopped' })

    await api('/voice/stop', {})

    expect(mockPythonRequest).toHaveBeenCalledWith('/voice/stop', {})
  })

  it('passes { method: DELETE } through for DELETE requests', async () => {
    mockPythonRequest.mockResolvedValue({ deleted: true })

    await api('/notes/5', { method: 'DELETE' })

    // The bridge interprets { method: 'DELETE' } — api() passes it through
    expect(mockPythonRequest).toHaveBeenCalledWith('/notes/5', { method: 'DELETE' })
  })
})


// ═══════════════════════════════════════════════════════════════════════
// apiRaw() — raw response helper (no unwrapping)
// ═══════════════════════════════════════════════════════════════════════

describe('apiRaw()', () => {
  it('returns the raw response without unwrapping', async () => {
    mockPythonRequest.mockResolvedValue({
      success: true,
      data: { items: ['a', 'b'] },
    })

    const result = await apiRaw('/memory/memory')

    // apiRaw does NOT unwrap — returns the full object as-is
    expect(result).toEqual({ success: true, data: { items: ['a', 'b'] } })
  })

  it('returns the raw response for simple objects', async () => {
    mockPythonRequest.mockResolvedValue({ status: 'ok' })

    const result = await apiRaw('/health')

    expect(result).toEqual({ status: 'ok' })
  })

  it('returns undefined when python.request throws', async () => {
    mockPythonRequest.mockRejectedValue(new Error('Network error'))

    const result = await apiRaw('/system/status')

    expect(result).toBeUndefined()
  })

  it('returns undefined when window.barq is undefined', async () => {
    delete (window as unknown as Record<string, unknown>).barq

    const result = await apiRaw('/voice/status')

    expect(result).toBeUndefined()
  })

  it('sends data as POST when provided', async () => {
    mockPythonRequest.mockResolvedValue({ result: 'ok' })

    await apiRaw('/system/terminal/run', { command: 'ls' })

    expect(mockPythonRequest).toHaveBeenCalledWith('/system/terminal/run', { command: 'ls' })
  })

  it('handles array responses', async () => {
    const items = [{ id: 1 }, { id: 2 }]
    mockPythonRequest.mockResolvedValue(items)

    const result = await apiRaw('/items')

    expect(result).toEqual(items)
  })
})
