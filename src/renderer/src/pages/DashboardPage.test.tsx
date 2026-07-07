import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, cleanup, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

// ═══════════════════════════════════════════════════════════════════════
// Mock setup — all must be before any component imports
// ═══════════════════════════════════════════════════════════════════════

// ─── Mock WebSocket ──────────────────────────────────────────────────
// Use a real class so it's not affected by vi.clearAllMocks().
// Tests control the lifecycle explicitly via openWebSocket() etc.

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

const OriginalWebSocket = globalThis.WebSocket

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
    mockWs = this
    // Do NOT auto-open — tests call openWebSocket() explicitly
  }
}

// ─── Shared test helpers ─────────────────────────────────────────────

// Flush microtasks so lazy-loaded components (ParticleSphere3D) resolve
async function flushLazyImport(): Promise<void> {
  await act(async () => {})
}

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

// Close the WebSocket connection
async function closeWebSocket(): Promise<void> {
  if (!mockWs) {
    throw new Error('WebSocket not created')
  }
  await act(async () => {
    mockWs!.onclose!({ code: 1000, reason: 'test' } as CloseEvent)
  })
}

// Read derived particle sphere props from the mocked component
function getParticleProps() {
  const el = screen.queryByTestId('particle-sphere')
  if (!el) return null
  return {
    aiState: el.getAttribute('data-ai-state'),
    audioAmplitude: parseFloat(el.getAttribute('data-audio-amplitude') ?? '0'),
    micMuted: el.getAttribute('data-mic-muted') === 'true',
    sttText: el.getAttribute('data-stt-text') ?? '',
  }
}

// ─── Mock window.barq API ──────────────────────────────────────────
vi.stubGlobal('barq', {
  python: {
    request: vi.fn().mockResolvedValue(null),
  },
})

// ─── Mock framer-motion ────────────────────────────────────────────
vi.mock('framer-motion', () => {
  function PlainDiv({
    children, className, style, onClick, onMouseMove, onMouseEnter,
    onMouseLeave, onKeyDown, onChange, onMouseDown, title, role, tabIndex,
    ..._motionProps
  }: Record<string, unknown>) {
    return (
      <div
        className={className as string}
        style={style}
        onClick={onClick as React.MouseEventHandler}
        onMouseMove={onMouseMove as React.MouseEventHandler}
        onMouseEnter={onMouseEnter as React.MouseEventHandler}
        onMouseLeave={onMouseLeave as React.MouseEventHandler}
        onKeyDown={onKeyDown as React.KeyboardEventHandler}
        onChange={onChange}
        onMouseDown={onMouseDown}
        title={title as string}
        role={role as string}
        tabIndex={tabIndex as number}
      >
        {children as React.ReactNode}
      </div>
    )
  }
  function PlainSpan({ children, className, style, title, ..._mp }: Record<string, unknown>) {
    return (
      <span className={className as string} style={style} title={title as string}>
        {children as React.ReactNode}
      </span>
    )
  }
  return {
    motion: { div: PlainDiv, span: PlainSpan },
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  }
})

// ─── Mock ThemeContext ──────────────────────────────────────────────
vi.mock('../contexts/ThemeContext', () => ({
  useTheme: () => ({ accent: 'cyan' as const }),
}))

// ─── Mock ParticleSphere3D (lazy-loaded) ────────────────────────────
vi.mock('../components/ParticleSphere3D', () => ({
  ParticleSphere3D: (props: Record<string, unknown>) => (
    <div
      data-testid="particle-sphere"
      data-ai-state={props.aiState as string}
      data-audio-amplitude={String(props.audioAmplitude ?? 0)}
      data-mic-muted={String(props.micMuted ?? false)}
      data-stt-text={props.sttText as string ?? ''}
    />
  ),
}))

// ─── Import after mocks ─────────────────────────────────────────────
import { DashboardPage } from './DashboardPage'


// ═══════════════════════════════════════════════════════════════════════
// Lifecycle helpers
// ═══════════════════════════════════════════════════════════════════════

function setupTestEnv() {
  mockWs = null
  globalThis.WebSocket = TestWebSocket as unknown as typeof globalThis.WebSocket
}

function teardownTestEnv() {
  cleanup()
  mockWs = null
  globalThis.WebSocket = OriginalWebSocket
}


// ═══════════════════════════════════════════════════════════════════════
// WebSocket AI State Derivation — Core Tests
// ═══════════════════════════════════════════════════════════════════════

describe('DashboardPage WebSocket state derivation', () => {
  beforeEach(setupTestEnv)
  afterEach(teardownTestEnv)

  // ── State derivation rules ────────────────────────────────────────

  it('sets aiState="responding" when is_speaking is true', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ is_speaking: true, is_listening: true, conversation_active: true })
    expect(getParticleProps()?.aiState).toBe('responding')
  })

  it('sets aiState="thinking" when is_processing is true', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ is_processing: true, is_listening: true })
    expect(getParticleProps()?.aiState).toBe('thinking')
  })

  it('sets aiState="listening" when conversation_active is true', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ conversation_active: true, is_listening: true })
    expect(getParticleProps()?.aiState).toBe('listening')
  })

  it('sets aiState="idle" when no active flags are set', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ is_listening: true })
    expect(getParticleProps()?.aiState).toBe('idle')
  })

  // ── Priority ordering ─────────────────────────────────────────────

  it('gives speaking priority over processing', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ is_speaking: true, is_processing: true })
    expect(getParticleProps()?.aiState).toBe('responding')
  })

  it('gives processing priority over conversation_active', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ is_processing: true, conversation_active: true })
    expect(getParticleProps()?.aiState).toBe('thinking')
  })

  it('gives speaking priority over both processing and conversation_active', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ is_speaking: true, is_processing: true, conversation_active: true })
    expect(getParticleProps()?.aiState).toBe('responding')
  })

  // ── State transitions ─────────────────────────────────────────────

  it('transitions through all states: idle→listening→thinking→responding→idle', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()

    await sendStatus({})
    expect(getParticleProps()?.aiState).toBe('idle')

    await sendStatus({ conversation_active: true, is_listening: true })
    expect(getParticleProps()?.aiState).toBe('listening')

    await sendStatus({ is_processing: true })
    expect(getParticleProps()?.aiState).toBe('thinking')

    await sendStatus({ is_speaking: true })
    expect(getParticleProps()?.aiState).toBe('responding')

    await sendStatus({})
    expect(getParticleProps()?.aiState).toBe('idle')
  })

  it('ignores non-voice_status messages', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ is_speaking: true })
    expect(getParticleProps()?.aiState).toBe('responding')

    // Non-voice_status message should be ignored
    await act(async () => {
      mockWs!.onmessage!(
        { data: JSON.stringify({ type: 'other_event', data: 'test' }) } as MessageEvent,
      )
    })
    expect(getParticleProps()?.aiState).toBe('responding')
  })

  // ── Derived values ────────────────────────────────────────────────

  it('propagates stt_text to the sphere', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ stt_text: 'hello world' })
    expect(getParticleProps()?.sttText).toBe('hello world')
  })

  it('propagates mic_level as audioAmplitude to the sphere', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ mic_level: 0.75 })
    expect(getParticleProps()?.audioAmplitude).toBeCloseTo(0.75, 2)
  })

  it('maps is_listening to inverted micMuted on the sphere', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()

    await sendStatus({ is_listening: true })
    expect(getParticleProps()?.micMuted).toBe(false)

    await sendStatus({ is_listening: false })
    expect(getParticleProps()?.micMuted).toBe(true)
  })

  it('shows ON AIR when detector is running and conversation is active', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ is_listening: true, conversation_active: true })
    expect(screen.getByText('ON AIR')).toBeInTheDocument()
  })

  it('shows STANDBY when detector is running but no conversation', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ is_listening: true, conversation_active: false })
    expect(screen.getByText('STANDBY')).toBeInTheDocument()
  })

  it('shows MUTED when detector is not running', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ is_listening: false })
    expect(screen.getByText('MUTED')).toBeInTheDocument()
  })

  // ── Edge cases ────────────────────────────────────────────────────

  it('defaults to idle on empty data', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({})
    expect(getParticleProps()?.aiState).toBe('idle')
  })

  it('defaults to idle when fields are explicitly false', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ is_speaking: false, is_processing: false, conversation_active: false })
    expect(getParticleProps()?.aiState).toBe('idle')
  })

  it('handles null mic_level (defaults to 0)', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ mic_level: null })
    expect(getParticleProps()?.audioAmplitude).toBe(0)
  })

  it('handles undefined stt_text (defaults to empty string)', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({})
    expect(getParticleProps()?.sttText).toBe('')
  })

  it('does not crash on malformed JSON', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    expect(() => {
      act(() => {
        mockWs!.onmessage!({ data: 'not-json' } as MessageEvent)
      })
    }).not.toThrow()
  })

  it('resets stt_text when subsequent message omits it', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ stt_text: 'previous command' })
    expect(getParticleProps()?.sttText).toBe('previous command')

    await sendStatus({})
    expect(getParticleProps()?.sttText).toBe('')
  })

  it('resets audioAmplitude when mic_level is omitted', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ mic_level: 0.9 })
    expect(getParticleProps()?.audioAmplitude).toBeCloseTo(0.9, 2)

    await sendStatus({})
    expect(getParticleProps()?.audioAmplitude).toBe(0)
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
    expect(mockWs!.url).toBe('ws://127.0.0.1:8956/voice/ws/status')
  })

  it('closes the WebSocket on unmount', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    const closeSpy = mockWs!.close
    cleanup()
    expect(closeSpy).toHaveBeenCalled()
  })
})


// ═══════════════════════════════════════════════════════════════════════
// AI State Control Panel — Manual Override Buttons
// ═══════════════════════════════════════════════════════════════════════

describe('DashboardPage AI state manual control', () => {
  beforeEach(setupTestEnv)
  afterEach(teardownTestEnv)

  it('renders all four AI state control buttons', () => {
    render(<DashboardPage />)
    expect(screen.getByText('idle')).toBeInTheDocument()
    expect(screen.getByText('listening')).toBeInTheDocument()
    expect(screen.getByText('thinking')).toBeInTheDocument()
    expect(screen.getByText('responding')).toBeInTheDocument()
  })

  it('starts with idle state by default', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    const el = screen.queryByTestId('particle-sphere')
    if (el) {
      expect(el.getAttribute('data-ai-state')).toBe('idle')
    }
  })

  it('clicking listening button sets the sphere to listening', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    fireEvent.click(screen.getByText('listening'))
    const el = screen.queryByTestId('particle-sphere')
    if (el) {
      expect(el.getAttribute('data-ai-state')).toBe('listening')
    }
  })

  it('manual button click overrides WebSocket state', async () => {
    render(<DashboardPage />)
    await flushLazyImport()
    await openWebSocket()
    await sendStatus({ is_speaking: true })
    expect(getParticleProps()?.aiState).toBe('responding')

    fireEvent.click(screen.getByText('thinking'))
    expect(getParticleProps()?.aiState).toBe('thinking')
  })
})
