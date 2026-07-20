/**
 * Integration-style tests for the api() helper that simulate the full
 * Electron IPC bridge → Python backend data flow that was broken in
 * the JobsPage.tsx "0 jobs loaded" bug.
 *
 * The IPC handler (src/main/ipc.ts) wraps Python backend responses as:
 *   { success: true, data: <raw backend response> }
 *
 * api() then unwraps this envelope, returning just the <raw backend response>.
 *
 * Callers MUST access fields on the unwrapped response directly —
 * NOT try to unwrap a second `.data` layer.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api } from './api'

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

describe('api() integration scenarios (simulates IPC -> Python flow)', () => {
  // ── Scenario: GET /jobs/matches (the "0 jobs loaded" bug) ──────────
  //
  // The IPC handler wraps the Python response in { success: true, data: ... }
  // api() unwraps it, returning the inner { matches: [...] } object.
  // The caller then accesses resp.matches directly.

  it('fetches job matches through the IPC bridge correctly', async () => {
    // Simulate what the IPC handler returns when the Python backend
    // responds with { matches: [...] }
    const backendResponse = {
      matches: [
        {
          id: 1,
          title: 'Senior Dev',
          company: 'TechCorp',
          match_score: 4.5,
          match_percentage: 90,
          pros: '["Remote","Stock options"]',
          cons: '["On-call rotation"]',
          reasoning: 'Great fit',
          source: 'linkedin',
        },
      ],
    }

    // The IPC handler wraps it: { success: true, data: backendResponse }
    mockPythonRequest.mockResolvedValue({
      success: true,
      data: backendResponse,
    })

    // --- THIS IS THE PATTERN USED IN JOBS PAGE (now fixed) ---
    const resp = await api<{ matches?: Record<string, unknown>[] }>(
      '/jobs/matches?limit=50',
    )

    // Verify the request went through
    expect(mockPythonRequest).toHaveBeenCalledWith('/jobs/matches?limit=50', undefined)

    // The critical assertion: resp IS the matches object directly,
    // NOT wrapped in { data: { matches: ... } }.
    // Access resp.matches — NOT resp.data.matches.
    const matches = resp?.matches ?? []
    expect(matches).toHaveLength(1)
    expect(matches[0].title).toBe('Senior Dev')
    expect(matches[0].company).toBe('TechCorp')
    expect(matches[0].match_percentage).toBe(90)
  })

  it('returns empty array when no matches exist', async () => {
    mockPythonRequest.mockResolvedValue({
      success: true,
      data: { matches: [] },
    })

    const resp = await api<{ matches?: Record<string, unknown>[] }>(
      '/jobs/matches?limit=50',
    )

    const matches = resp?.matches ?? []
    expect(matches).toEqual([])
  })

  // ── Scenario: POST /jobs/scan with {} (the "infinite scanning" bug) ─
  //
  // Previously, api('/jobs/scan') was called with no data, which sent a GET.
  // The fix was to call api('/jobs/scan', {}) to force POST.
  // This test verifies the POST flow works end-to-end.

  it('triggers a job scan via POST when empty object is passed', async () => {
    const backendResponse = {
      status: 'started',
      message: 'Scan started in background',
    }

    // IPC handler wraps it
    mockPythonRequest.mockResolvedValue({
      success: true,
      data: backendResponse,
    })

    // --- THIS IS THE FIXED PATTERN ---
    // Pass {} to force the bridge to send POST instead of GET
    const resp = await api<{ status?: string; message?: string }>(
      '/jobs/scan',
      {},
    )

    // Critical: empty object {} is truthy, so the bridge sends POST
    expect(mockPythonRequest).toHaveBeenCalledWith('/jobs/scan', {})

    // Response should be the unwrapped backend response
    expect(resp?.status).toBe('started')
    expect(resp?.message).toContain('background')
  })

  // ── Scenario: GET /jobs/scan/progress (polling) ──────────────────

  it('polls scan progress correctly through the IPC bridge', async () => {
    const progressResponse = {
      status: 'scanning',
      phase: 'Searching listings',
      phase_index: 1,
      total_phases: 4,
      progress_pct: 35,
      boards_total: 25,
      boards_scanned: 9,
      jobs_found: 42,
      message: 'Found 42 jobs across 9 boards',
      started_at: 1_000_000,
      elapsed_seconds: 3.2,
    }

    mockPythonRequest.mockResolvedValue({
      success: true,
      data: progressResponse,
    })

    const resp = await api<Record<string, unknown>>('/jobs/scan/progress')

    // Direct field access — no .data nesting
    expect(resp?.status).toBe('scanning')
    expect(resp?.progress_pct).toBe(35)
    expect(resp?.jobs_found).toBe(42)
    expect(resp?.elapsed_seconds).toBe(3.2)
  })

  // ── Scenario: GET /jobs/resume (resume info) ─────────────────────

  it('fetches resume info with direct field access', async () => {
    const resumeResponse = {
      exists: true,
      parsed: {
        full_name: 'John Doe',
        skills_count: 12,
      },
      char_count: 1500,
    }

    mockPythonRequest.mockResolvedValue({
      success: true,
      data: resumeResponse,
    })

    const resp = await api<{
      exists?: boolean
      parsed?: { full_name?: string; skills_count?: number }
      char_count?: number
    }>('/jobs/resume')

    // Direct field access — this was incorrectly using
    // (d.parsed as Record<string, unknown>)?.full_name before
    expect(resp?.exists).toBe(true)
    expect(resp?.parsed?.full_name).toBe('John Doe')
    expect(resp?.parsed?.skills_count).toBe(12)
    expect(resp?.char_count).toBe(1500)
  })

  // ── Scenario: Scanning is already running (no duplicate scans) ───

  it('handles already_running scan status correctly', async () => {
    mockPythonRequest.mockResolvedValue({
      success: true,
      data: {
        status: 'already_running',
        message: 'A scan is already in progress',
        progress: {
          status: 'scanning',
          phase: 'Searching listings',
          progress_pct: 60,
        },
      },
    })

    const resp = await api<{
      status?: string
      message?: string
      progress?: Record<string, unknown>
    }>('/jobs/scan', {})

    expect(resp?.status).toBe('already_running')
    expect(resp?.progress?.progress_pct).toBe(60)
  })

  // ── Scenario: Backend unreachable (simulate bridge failure) ──────

  it('gracefully handles backend being unreachable', async () => {
    mockPythonRequest.mockRejectedValue(new Error('Connection refused'))

    const resp = await api('/jobs/matches?limit=50')

    expect(resp).toBeUndefined()
  })
})
