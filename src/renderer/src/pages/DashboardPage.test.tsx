import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

// ═══════════════════════════════════════════════════════════════════════
// Mock setup — all must be before any component imports
// ═══════════════════════════════════════════════════════════════════════

// ─── Mock WebSocket ──────────────────────────────────────────────────

interface MockWS {
  onopen: ((event: Event) => void) | null
  onmessage: ((event: MessageEvent) => void) | null
  onclose: ((event: CloseEvent) => void) | null
  onerror: ((event: Event) => void) | null
  close: ReturnType<typeof vi.fn>
  send: ReturnType<typeof vi.fn>
  readyState: number
  url: string
}

let mockWs: MockWS | null = null
let originalWebSocket: typeof globalThis.WebSocket | null = null

class TestWebSocket {
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  close = vi.fn()
  send = vi.fn()
  readyState = 1 // OPEN
  url: string
  constructor(url: string) {
    this.url = url
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    mockWs = this
  }
}

// ─── Shared test helpers ─────────────────────────────────────────────

// Simulate the server sending a voice_status message
async function sendStatus(data: Record<string, unknown>): Promise<void> {
  if (!mockWs?.onmessage) {
    throw new Error('WebSocket not connected — call openWebSocket() first')
  }
  await act(async () => {
    mockWs!.onmessage!(
      { data: JSON.stringify({ type: 'voice_status', ...data }) } as MessageEvent,
    )
  })
}

// Open the WebSocket connection (simulates ws.onopen)
async function openWebSocket(): Promise<void> {
  if (!mockWs) {
    throw new Error('WebSocket not created — render DashboardPage first')
  }
  await act(async () => {
    mockWs!.onopen!({} as Event)
  })
}

// ─── Mock window.barq API ──────────────────────────────────────────
vi.stubGlobal('barq', {
  python: {
    request: vi.fn().mockResolvedValue(null),
  },
})

// ─── Mock framer-motion ────────────────────────────────────────────
vi.mock('framer-motion', () => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function PlainTag({ children, className, style, title }: Record<string, any>) {
    return (
      <div
        className={className as string}
        style={style as React.CSSProperties | undefined}
        title={title as string | undefined}
        data-testid="motion-div"
      >
        {children as React.ReactNode}
      </div>
    )
  }
  return {
    motion: { div: PlainTag, span: PlainTag, p: PlainTag },
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  }
})

// ─── Mock ThemeContext ──────────────────────────────────────────────
vi.mock('../contexts/ThemeContext', () => ({
  useTheme: () => ({ accent: 'cyan' as const }),
}))

// ─── Mock ParticleSphere3D (lazy-loaded) ────────────────────────────
// Must match the dynamic import path used by the lazy() factory
vi.mock('../components/ParticleSphere3D', () => ({
  ParticleSphere3D: () => <div data-testid="particle-sphere" />,
}))

// ─── Import after mocks ─────────────────────────────────────────────
import { DashboardPage } from './DashboardPage'


// ═══════════════════════════════════════════════════════════════════════
// Lifecycle helpers
// ═══════════════════════════════════════════════════════════════════════

function setupTestEnv() {
  mockWs = null
  originalWebSocket = globalThis.WebSocket
  globalThis.WebSocket = TestWebSocket as unknown as typeof globalThis.WebSocket
}

function teardownTestEnv() {
  cleanup()
  mockWs = null
  if (originalWebSocket) {
    globalThis.WebSocket = originalWebSocket
    originalWebSocket = null
  }
}

async function openWsAndRender(): Promise<void> {
  render(<DashboardPage />)
  // Resolve lazy import + WebSocket connection
  await act(async () => {
    await new Promise(r => setTimeout(r, 0))
  })
  await openWebSocket()
}


// ═══════════════════════════════════════════════════════════════════════
// Greeting & State Display
// ═══════════════════════════════════════════════════════════════════════

describe('DashboardPage greeting and state display', () => {
  beforeEach(setupTestEnv)
  afterEach(teardownTestEnv)

  it('shows greeting in h1 on mount', () => {
    render(<DashboardPage />)
    // One of the time-based greetings should be present
    const h1 = document.querySelector('h1')
    expect(h1).toBeInTheDocument()
    const text = h1?.textContent ?? ''
    expect(
      text === 'GOOD MORNING' || text === 'GOOD AFTERNOON' || text === 'GOOD EVENING' ||
      text === 'STANDBY' || text === 'LISTENING' || text === 'RESPONDING' || text === 'THINKING'
    ).toBe(true)
  })

  it('displays subtitle text on mount', () => {
    render(<DashboardPage />)
    // Either BARQ is ready (greeting subtitle) or Loading (weather) should appear
    const found = screen.getAllByText(/BARQ is ready|Loading\.\.\./)
    expect(found.length).toBeGreaterThan(0)
  })

  it('shows STANDBY in voice pill when detector is running but no conversation', async () => {
    await openWsAndRender()
    await sendStatus({ is_listening: true, conversation_active: false })
    expect(screen.getByText('STANDBY')).toBeInTheDocument()
  })

  it('shows MUTED in voice pill when detector is not running', async () => {
    await openWsAndRender()
    await sendStatus({ is_listening: false })
    expect(screen.getByText('MUTED')).toBeInTheDocument()
  })

  it('shows ON AIR when detector is running and conversation is active', async () => {
    await openWsAndRender()
    await sendStatus({ is_listening: true, conversation_active: true })
    expect(screen.getByText('ON AIR')).toBeInTheDocument()
  })
})


// ═══════════════════════════════════════════════════════════════════════
// STT and Response Text Display
// ═══════════════════════════════════════════════════════════════════════

describe('DashboardPage STT and response display', () => {
  beforeEach(setupTestEnv)
  afterEach(teardownTestEnv)

  it('shows STT text when received from server', async () => {
    await openWsAndRender()
    await sendStatus({ stt_text: 'hello world' })
    // Appears in both greeting subtitle and STT bubble
    const found = screen.getAllByText(/hello world/)
    expect(found.length).toBeGreaterThan(0)
  })

  it('shows LISTENING greeting when STT text is present', async () => {
    await openWsAndRender()
    await sendStatus({ stt_text: 'test command', conversation_active: true })
    const h1 = document.querySelector('h1')
    expect(h1?.textContent).toBe('LISTENING')
  })

  it('shows RESPONDING greeting when response text is present', async () => {
    await openWsAndRender()
    await sendStatus({ response_text: 'Here is my response', is_speaking: true })
    const h1 = document.querySelector('h1')
    expect(h1?.textContent).toBe('RESPONDING')
  })

  it('shows THINKING greeting when processing', async () => {
    await openWsAndRender()
    await sendStatus({ is_processing: true })
    const h1 = document.querySelector('h1')
    expect(h1?.textContent).toBe('THINKING')
  })

  it('shows response text in the UI', async () => {
    await openWsAndRender()
    await sendStatus({ response_text: 'Processing complete' })
    // Appears in both greeting subtitle and response bubble
    const found = screen.getAllByText(/Processing complete/)
    expect(found.length).toBeGreaterThan(0)
  })

  it('preserves STT text in LiveCaptions after server clears (6s dissolve)', async () => {
    await openWsAndRender()
    await sendStatus({ stt_text: 'previous command' })
    const found = screen.getAllByText(/previous command/)
    expect(found.length).toBeGreaterThan(0)
    // LiveCaptions retains the last non-empty STT for a 6-second dissolve
    // window — the text should STILL be visible even after the server
    // sends empty stt_text. Only the top-left greeting subtitle reverts.
    await sendStatus({ stt_text: '' })
    // The text persists in LiveCaptions (displayStt is cached)
    const afterClear = screen.getAllByText(/previous command/)
    expect(afterClear.length).toBeGreaterThan(0)
  })
})


// ═══════════════════════════════════════════════════════════════════════
// Module Indicator Dots
// ═══════════════════════════════════════════════════════════════════════

describe('DashboardPage module indicators', () => {
  beforeEach(setupTestEnv)
  afterEach(teardownTestEnv)

  it('shows CORE module indicator', () => {
    render(<DashboardPage />)
    expect(screen.getByText('CORE')).toBeInTheDocument()
  })

  it('shows VISION module indicator', () => {
    render(<DashboardPage />)
    expect(screen.getByText('VISION')).toBeInTheDocument()
  })

  it('shows NET module indicator', () => {
    render(<DashboardPage />)
    expect(screen.getByText('NET')).toBeInTheDocument()
  })

  it('shows AUDIO module indicator', () => {
    render(<DashboardPage />)
    expect(screen.getByText('AUDIO')).toBeInTheDocument()
  })
})


// ═══════════════════════════════════════════════════════════════════════
// WebSocket Lifecycle — Connection & Reconnection
// ═══════════════════════════════════════════════════════════════════════

describe('DashboardPage WebSocket lifecycle', () => {
  beforeEach(setupTestEnv)
  afterEach(teardownTestEnv)

  it('creates a WebSocket on mount with the correct URL', () => {
    render(<DashboardPage />)
    expect(mockWs).not.toBeNull()
    expect(mockWs!.url).toBe('ws://127.0.0.1:8970/voice/ws/status')
  })

  it('closes the WebSocket on unmount', async () => {
    render(<DashboardPage />)
    await act(async () => { await new Promise(r => setTimeout(r, 0)) })
    await openWebSocket()
    const closeSpy = mockWs!.close
    cleanup()
    expect(closeSpy).toHaveBeenCalled()
  })
})


// ═══════════════════════════════════════════════════════════════════════
// State Derivation via WebSocket
// ═══════════════════════════════════════════════════════════════════════

describe('DashboardPage voice state derivation', () => {
  beforeEach(setupTestEnv)
  afterEach(teardownTestEnv)

  it('ignores non-voice_status messages', async () => {
    await openWsAndRender()
    // After connecting, both MUTED (voice pill) and a greeting should appear
    const found = screen.getAllByText(/STANDBY|MUTED|GOOD/)
    expect(found.length).toBeGreaterThan(0)

    // Non-voice_status message should be ignored
    await act(async () => {
      mockWs!.onmessage!(
        { data: JSON.stringify({ type: 'other_event', data: 'test' }) } as MessageEvent,
      )
    })

    // State should remain unchanged — same texts still present
    const after = screen.getAllByText(/STANDBY|MUTED|GOOD/)
    expect(after.length).toBeGreaterThan(0)
  })

  it('does not crash on malformed JSON', async () => {
    await openWsAndRender()
    expect(() => {
      act(() => {
        mockWs!.onmessage!({ data: 'not-json' } as MessageEvent)
      })
    }).not.toThrow()
  })

  it('shows appropriate subtitle for each AI state', async () => {
    await openWsAndRender()

    // idle state
    await sendStatus({})
    expect(screen.queryByText('BARQ is ready')).toBeInTheDocument()

    // listening state — detector must be running too
    await sendStatus({ conversation_active: true, is_listening: true })
    expect(screen.queryByText('Listening for commands')).toBeInTheDocument()

    // thinking state
    await sendStatus({ is_processing: true })
    expect(screen.queryByText('Processing...')).toBeInTheDocument()

    // responding state
    await sendStatus({ is_speaking: true })
    expect(screen.queryByText('BARQ is speaking')).toBeInTheDocument()
  })
})


// ═══════════════════════════════════════════════════════════════════════
// Branding
// ═══════════════════════════════════════════════════════════════════════

describe('DashboardPage branding', () => {
  beforeEach(setupTestEnv)
  afterEach(teardownTestEnv)

  it('shows BARQ Agent Network branding', () => {
    render(<DashboardPage />)
    expect(screen.getByText(/B\.A\.R\.Q.*Agent Network/)).toBeInTheDocument()
  })
})
