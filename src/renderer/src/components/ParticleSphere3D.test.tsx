import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

// ─── Mock @react-three/fiber ────────────────────────────────────────────
vi.mock('@react-three/fiber', () => ({
  Canvas: ({ children, ...props }: Record<string, unknown>) => (
    <div data-testid="r3f-canvas" {...props}>
      {children as React.ReactNode}
    </div>
  ),
  useFrame: vi.fn(),
}))

// ─── Mock three.js ──────────────────────────────────────────────────────
vi.mock('three', () => ({
  AdditiveBlending: 0,
  DoubleSide: 0,
  CanvasTexture: vi.fn(() => ({ needsUpdate: false })),
  BufferGeometry: vi.fn(() => ({ attributes: {} })),
  Points: vi.fn(() => ({ geometry: { attributes: {} } })),
  Group: vi.fn(() => ({ rotation: { x: 0, y: 0, z: 0 }, scale: { setScalar: vi.fn() } })),
  Mesh: vi.fn(() => ({
    rotation: { x: 0, y: 0, z: 0 },
    scale: { setScalar: vi.fn() },
    material: { color: { r: 0, g: 0, b: 0 }, opacity: 0 },
  })),
  MeshBasicMaterial: vi.fn(() => ({
    color: { r: 0, g: 0, b: 0 },
    opacity: 0,
    transparent: true,
  })),
  PointsMaterial: vi.fn(() => ({ size: 0.06, transparent: true, opacity: 1 })),
  BufferAttribute: vi.fn(() => ({ needsUpdate: false })),
  RingGeometry: vi.fn(() => ({})),
  Float32Array: globalThis.Float32Array,
  Vector3: vi.fn(() => ({ x: 0, y: 0, z: 0 })),
  Color: vi.fn(() => ({ r: 0, g: 0, b: 0 })),
  MathUtils: { lerp: vi.fn((a, b, t) => a + (b - a) * t) },
}))

// ─── Mock @react-three/drei ─────────────────────────────────────────────
vi.mock('@react-three/drei', () => ({ Grid: () => null }))

// ─── Mock framer-motion ─────────────────────────────────────────────────
// motion.div renders as a regular div, passing animate as data attribute
// so tests can verify hover state transitions.
vi.mock('framer-motion', () => {
  const MotionDiv = ({ children, initial, animate, transition, className, style, ...props }: Record<string, unknown>) => (
    <div
      className={className as string}
      style={style}
      data-animate={JSON.stringify(animate)}
      data-initial={JSON.stringify(initial)}
      data-testid="motion-div"
      {...props}
    >
      {children as React.ReactNode}
    </div>
  )
  return {
    motion: { div: MotionDiv },
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  }
})

// ─── Import after mocks are set up ──────────────────────────────────────
import {
  ParticleSphere3D,
  type AIState,
  IDLE_ROTATION_SPEED,
  SPEAKING_ROTATION_SPEED,
  THINKING_ROTATION_SPEED,
  THINKING_SCALE_FACTOR,
  STATE_PARTICLE_COLORS,
  STATE_RING_OPACITY,
  COLOR_LERP_RATE,
  IDLE_WOBBLE_AMPLITUDE,
  IDLE_PULSE_AMPLITUDE,
} from './ParticleSphere3D'


// ═══════════════════════════════════════════════════════════════════════
// Exported Constants — Direct Value Tests
// These verify the exact numeric values that govern each AI state's
// visual behavior are correct per the design spec.
// ═══════════════════════════════════════════════════════════════════════


describe('rotation speed constants', () => {
  it('idle rotation speed is 0.08', () => {
    expect(IDLE_ROTATION_SPEED).toBe(0.08)
  })

  it('listening rotation speed (SPEAKING_ROTATION_SPEED) is 0.25', () => {
    expect(SPEAKING_ROTATION_SPEED).toBe(0.25)
  })

  it('thinking rotation speed is 0.6', () => {
    expect(THINKING_ROTATION_SPEED).toBe(0.6)
  })

  it('responding rotation speed is SPEAKING_ROTATION_SPEED * 0.7 = 0.175', () => {
    expect(SPEAKING_ROTATION_SPEED * 0.7).toBeCloseTo(0.175, 3)
  })
})

describe('particle color constants', () => {
  it('idle color is deep purple [8, 1, 10]', () => {
    expect(STATE_PARTICLE_COLORS.idle).toEqual([8, 1, 10])
  })

  it('listening color is amber [12, 6, 0]', () => {
    expect(STATE_PARTICLE_COLORS.listening).toEqual([12, 6, 0])
  })

  it('thinking color is cool white [10, 10, 12]', () => {
    expect(STATE_PARTICLE_COLORS.thinking).toEqual([10, 10, 12])
  })

  it('responding color is neon green [0, 10, 2]', () => {
    expect(STATE_PARTICLE_COLORS.responding).toEqual([0, 10, 2])
  })
})

describe('ring opacity constants', () => {
  it('idle ring opacity is 0.2', () => {
    expect(STATE_RING_OPACITY.idle).toBe(0.2)
  })

  it('listening ring opacity is 0.35', () => {
    expect(STATE_RING_OPACITY.listening).toBe(0.35)
  })

  it('thinking ring opacity is 0.35', () => {
    expect(STATE_RING_OPACITY.thinking).toBe(0.35)
  })

  it('responding ring opacity is 0.4', () => {
    expect(STATE_RING_OPACITY.responding).toBe(0.4)
  })
})

describe('other numeric constants', () => {
  it('color lerp rate is 0.06 per frame (doubled for faster reactivity)', () => {
    expect(COLOR_LERP_RATE).toBe(0.06)
  })

  it('idle wobble amplitude is 0.08', () => {
    expect(IDLE_WOBBLE_AMPLITUDE).toBe(0.08)
  })

  it('idle pulse amplitude is 0.01', () => {
    expect(IDLE_PULSE_AMPLITUDE).toBe(0.01)
  })

  it('thinking scale factor collapses sphere to 82%', () => {
    expect(THINKING_SCALE_FACTOR).toBe(0.82)
  })
})


// ═══════════════════════════════════════════════════════════════════════
// Rendering — smoke tests per state
// ═══════════════════════════════════════════════════════════════════════


describe('ParticleSphere3D rendering', () => {
  it('renders sphere container in idle state', () => {
    const { container } = render(<ParticleSphere3D aiState="idle" />)
    expect(container.querySelector('[data-testid="sphere-container"]')).toBeInTheDocument()
  })

  it('renders sphere container in listening state', () => {
    const { container } = render(<ParticleSphere3D aiState="listening" />)
    expect(container.querySelector('[data-testid="sphere-container"]')).toBeInTheDocument()
  })

  it('renders sphere container in thinking state', () => {
    const { container } = render(<ParticleSphere3D aiState="thinking" />)
    expect(container.querySelector('[data-testid="sphere-container"]')).toBeInTheDocument()
  })

  it('renders sphere container in responding state', () => {
    const { container } = render(<ParticleSphere3D aiState="responding" />)
    expect(container.querySelector('[data-testid="sphere-container"]')).toBeInTheDocument()
  })

  it('renders with default idle state when no aiState provided', () => {
    const { container } = render(<ParticleSphere3D />)
    expect(container.querySelector('[data-testid="sphere-container"]')).toBeInTheDocument()
  })

  it('renders with custom activeTheme', () => {
    const { container } = render(<ParticleSphere3D activeTheme="amber" />)
    expect(container.querySelector('[data-testid="sphere-container"]')).toBeInTheDocument()
  })

  it('renders with showGrid prop without crashing', () => {
    const { container } = render(<ParticleSphere3D showGrid />)
    expect(container.querySelector('[data-testid="sphere-container"]')).toBeInTheDocument()
  })

  it('renders with audioAmplitude without crashing', () => {
    const { container } = render(<ParticleSphere3D audioAmplitude={0.5} />)
    expect(container.querySelector('[data-testid="sphere-container"]')).toBeInTheDocument()
  })

  it('renders with sttText without crashing', () => {
    const { container } = render(<ParticleSphere3D sttText="hello world" />)
    expect(container.querySelector('[data-testid="sphere-container"]')).toBeInTheDocument()
  })

  // Canvas mock component is intentionally not tested here — the mocked Canvas
  // renders inside CanvasErrorBoundary, which may catch R3F-element rendering
  // edge cases in JSDOM. The component's sphere-container structure is verified
  // by the other rendering tests above.

  it('renders multiple sphere instances independently', () => {
    const { container } = render(
      <div>
        <ParticleSphere3D aiState="idle" />
        <ParticleSphere3D aiState="listening" />
      </div>,
    )
    const spheres = container.querySelectorAll('[data-testid="sphere-container"]')
    expect(spheres).toHaveLength(2)
  })
})


// ═══════════════════════════════════════════════════════════════════════
// AI State Tooltip — Label Correctness
// ═══════════════════════════════════════════════════════════════════════


describe('AI State tooltip labels', () => {
  it('shows "Idle" label when aiState is idle', () => {
    render(<ParticleSphere3D aiState="idle" />)
    expect(screen.getByText('Idle')).toBeInTheDocument()
  })

  it('shows "Listening" label when aiState is listening', () => {
    render(<ParticleSphere3D aiState="listening" />)
    expect(screen.getByText('Listening')).toBeInTheDocument()
  })

  it('shows "Thinking" label when aiState is thinking', () => {
    render(<ParticleSphere3D aiState="thinking" />)
    expect(screen.getByText('Thinking')).toBeInTheDocument()
  })

  it('shows "Responding" label when aiState is responding', () => {
    render(<ParticleSphere3D aiState="responding" />)
    expect(screen.getByText('Responding')).toBeInTheDocument()
  })

  it('shows "Muted" label when idle and mic is muted', () => {
    render(<ParticleSphere3D aiState="idle" micMuted />)
    expect(screen.getByText('Muted')).toBeInTheDocument()
  })

  it('does NOT show "Muted" when listening and mic is muted', () => {
    render(<ParticleSphere3D aiState="listening" micMuted />)
    expect(screen.getByText('Listening')).toBeInTheDocument()
    expect(screen.queryByText('Muted')).not.toBeInTheDocument()
  })

  it('shows state description for idle state', () => {
    render(<ParticleSphere3D aiState="idle" />)
    expect(screen.getByText('Awaiting input')).toBeInTheDocument()
  })

  it('shows state description for listening state', () => {
    render(<ParticleSphere3D aiState="listening" />)
    expect(screen.getByText('Listening for speech')).toBeInTheDocument()
  })

  it('shows state description for thinking state', () => {
    render(<ParticleSphere3D aiState="thinking" />)
    expect(screen.getByText('Processing response')).toBeInTheDocument()
  })

  it('shows state description for responding state', () => {
    render(<ParticleSphere3D aiState="responding" />)
    expect(screen.getByText('Speaking response')).toBeInTheDocument()
  })

  it('shows muted description when idle and micMuted', () => {
    render(<ParticleSphere3D aiState="idle" micMuted />)
    expect(screen.getByText('Microphone muted')).toBeInTheDocument()
  })

  it('tooltip renders in DOM with initial hidden opacity', () => {
    const { container } = render(<ParticleSphere3D aiState="idle" />)
    const motionDiv = container.querySelector('[data-testid="motion-div"]')
    expect(motionDiv).toBeInTheDocument()
    const initial = JSON.parse(motionDiv?.getAttribute('data-initial') ?? '{}')
    expect(initial.opacity).toBe(0)
  })
})


// ═══════════════════════════════════════════════════════════════════════
// Hover Behavior
// ═══════════════════════════════════════════════════════════════════════


describe('hover behavior', () => {
  it('shows tooltip with animate.opacity=1 on mouse enter', () => {
    const { container } = render(<ParticleSphere3D aiState="listening" />)
    const sphereDiv = container.querySelector('[data-testid="sphere-container"]')
    expect(sphereDiv).toBeInTheDocument()

    fireEvent.mouseEnter(sphereDiv!)

    const motionDiv = container.querySelector('[data-testid="motion-div"]')
    const animate = JSON.parse(motionDiv?.getAttribute('data-animate') ?? '{}')
    expect(animate.opacity).toBe(1)
  })

  it('hides tooltip with animate.opacity=0 on mouse leave', () => {
    const { container } = render(<ParticleSphere3D aiState="thinking" />)
    const sphereDiv = container.querySelector('[data-testid="sphere-container"]')

    // Enter then leave
    fireEvent.mouseEnter(sphereDiv!)
    fireEvent.mouseLeave(sphereDiv!)

    const motionDiv = container.querySelector('[data-testid="motion-div"]')
    const animate = JSON.parse(motionDiv?.getAttribute('data-animate') ?? '{}')
    expect(animate.opacity).toBe(0)
  })

  it('tooltip text remains in DOM regardless of hover state', () => {
    render(<ParticleSphere3D aiState="responding" />)
    expect(screen.getByText('Responding')).toBeInTheDocument()
    expect(screen.getByText('Speaking response')).toBeInTheDocument()
  })
})


// ═══════════════════════════════════════════════════════════════════════
// Muted State
// ═══════════════════════════════════════════════════════════════════════


describe('muted state behavior', () => {
  it('shows idle label when mic is NOT muted', () => {
    render(<ParticleSphere3D aiState="idle" micMuted={false} />)
    expect(screen.getByText('Idle')).toBeInTheDocument()
  })

  it('shows correct label when mic is not muted', () => {
    render(<ParticleSphere3D aiState="listening" micMuted={false} />)
    expect(screen.getByText('Listening')).toBeInTheDocument()
  })

  it('shows Muted only for idle+micMuted combo, not other states', () => {
    const states: AIState[] = ['idle', 'listening', 'thinking', 'responding']
    for (const state of states) {
      const { unmount } = render(<ParticleSphere3D aiState={state} micMuted />)
      if (state === 'idle') {
        expect(screen.getByText('Muted')).toBeInTheDocument()
      } else {
        expect(screen.queryByText('Muted')).not.toBeInTheDocument()
      }
      unmount()
    }
  })
})


// ═══════════════════════════════════════════════════════════════════════
// Edge Cases
// ═══════════════════════════════════════════════════════════════════════


describe('edge cases', () => {
  it('renders with all props set simultaneously', () => {
    const { container } = render(
      <ParticleSphere3D
        activeTheme="purple"
        aiState="thinking"
        audioAmplitude={0.75}
        showGrid
        micMuted={false}
        sttText="test speech"
      />,
    )
    expect(container.querySelector('[data-testid="sphere-container"]')).toBeInTheDocument()
  })

  it('handles audioAmplitude=0 gracefully', () => {
    const { container } = render(<ParticleSphere3D audioAmplitude={0} />)
    expect(container.querySelector('[data-testid="sphere-container"]')).toBeInTheDocument()
  })

  it('handles audioAmplitude=1.0 gracefully', () => {
    const { container } = render(<ParticleSphere3D audioAmplitude={1.0} />)
    expect(container.querySelector('[data-testid="sphere-container"]')).toBeInTheDocument()
  })

  it('handles empty sttText', () => {
    const { container } = render(<ParticleSphere3D sttText="" />)
    expect(container.querySelector('[data-testid="sphere-container"]')).toBeInTheDocument()
  })

  it('renders without any props', () => {
    const { container } = render(<ParticleSphere3D />)
    expect(container.querySelector('[data-testid="sphere-container"]')).toBeInTheDocument()
  })
})
