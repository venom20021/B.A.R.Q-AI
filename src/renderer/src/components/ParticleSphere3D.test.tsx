import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

// ─── Mock @react-three/fiber ────────────────────────────────────────────
vi.mock('@react-three/fiber', () => ({
  Canvas: () => <div data-testid="r3f-canvas" />,
  useFrame: vi.fn(),
}))

// ─── Mock three.js ──────────────────────────────────────────────────────
vi.mock('three', () => {
  const mockVec = (x = 0, y = 0, z = 0) => ({
    x, y, z,
    set: vi.fn(),
    add: vi.fn(() => mockVec(x, y, z)),
    addVectors: vi.fn(() => mockVec()),
    multiplyScalar: vi.fn(() => mockVec(x, y, z)),
    copy: vi.fn(() => mockVec(x, y, z)),
    normalize: vi.fn(() => mockVec(x, y, z)),
    clone: vi.fn(() => mockVec(x, y, z)),
    lerp: vi.fn(),
    length: vi.fn(() => 1),
  })
  // Regular function so it can be called with 'new'
  function Vector3(x?: number, y?: number, z?: number) {
    return mockVec(x, y, z)
  }
  return {
    AdditiveBlending: 0,
    DoubleSide: 0,
    CanvasTexture: vi.fn(() => ({ needsUpdate: false })),
    MathUtils: { lerp: vi.fn() },
    Vector3,
  }
})

// ─── Mock @react-three/drei ─────────────────────────────────────────────
vi.mock('@react-three/drei', () => ({
  Html: ({ children }: { children: React.ReactNode }) => <div data-testid="html-label">{children}</div>,
  QuadraticBezierLine: () => null,
  OrbitControls: () => null,
}))

// ─── Helper: default required props ─────────────────────────────────────
const defaultProps = {
  activeAgent: null,
  onSelectAgent: vi.fn(),
  focusTargetRef: { current: null },
}
import { ParticleSphere3D, type AIState, AGENT_NODES } from './ParticleSphere3D'

// ═══════════════════════════════════════════════════════════════════════
// Agent Node Data
// ═══════════════════════════════════════════════════════════════════════

describe('AGENT_NODES data', () => {
  it('has exactly 8 agent nodes', () => {
    expect(AGENT_NODES).toHaveLength(8)
  })

  it('each node has required fields', () => {
    for (const node of AGENT_NODES) {
      expect(node.id).toBeTruthy()
      expect(node.label).toBeTruthy()
      expect(node.color).toBeTruthy()
      expect(node.position).toHaveLength(3)
      expect(node.description).toBeTruthy()
    }
  })

  it('nodes cover diverse specialties', () => {
    const labels = AGENT_NODES.map(n => n.label)
    expect(labels).toContain('Strategist')
    expect(labels).toContain('Researcher')
    expect(labels).toContain('Chief of Staff')
    expect(labels).toContain('Memory')
    expect(labels).toContain('Coding')
  })
})

// ═══════════════════════════════════════════════════════════════════════
// Smoke Tests
// ═══════════════════════════════════════════════════════════════════════

describe('ParticleSphere3D rendering', () => {
  it('renders without crashing with default props', () => {
    const { container } = render(<ParticleSphere3D {...defaultProps} />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it('renders in idle state', () => {
    const { container } = render(<ParticleSphere3D {...defaultProps} aiState="idle" />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it('renders in listening state', () => {
    const { container } = render(<ParticleSphere3D {...defaultProps} aiState="listening" />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it('renders in thinking state', () => {
    const { container } = render(<ParticleSphere3D {...defaultProps} aiState="thinking" />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it('renders in responding state', () => {
    const { container } = render(<ParticleSphere3D {...defaultProps} aiState="responding" />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it('renders with sttText prop', () => {
    const { container } = render(<ParticleSphere3D {...defaultProps} sttText="hello" />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it('renders with audioAmplitude prop', () => {
    const { container } = render(<ParticleSphere3D {...defaultProps} audioAmplitude={0.5} />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it('renders with micMuted prop', () => {
    const { container } = render(<ParticleSphere3D {...defaultProps} micMuted />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it('renders multiple instances independently', () => {
    const { container } = render(
      <div>
        <ParticleSphere3D {...defaultProps} aiState="idle" />
        <ParticleSphere3D {...defaultProps} aiState="listening" />
      </div>,
    )
    const r3fCanvases = container.querySelectorAll('[data-testid="r3f-canvas"]')
    expect(r3fCanvases).toHaveLength(2)
  })

  it('all props set simultaneously', () => {
    const { container } = render(
      <ParticleSphere3D
        {...defaultProps}
        activeTheme="purple"
        aiState="thinking"
        audioAmplitude={0.75}
        micMuted={false}
        sttText="test speech"
      />,
    )
    expect(container.firstChild).toBeInTheDocument()
  })
})

// ═══════════════════════════════════════════════════════════════════════
// AIState Type
// ═══════════════════════════════════════════════════════════════════════

describe('AIState type shape', () => {
  it('accepts all valid state strings', () => {
    const valid: AIState[] = ['idle', 'listening', 'thinking', 'responding']
    for (const s of valid) {
      render(<ParticleSphere3D {...defaultProps} aiState={s} />)
      // No crash = pass
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════
// Edge Cases
// ═══════════════════════════════════════════════════════════════════════

describe('edge cases', () => {
  it('handles empty sttText', () => {
    const { container } = render(<ParticleSphere3D {...defaultProps} sttText="" />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it('handles audioAmplitude=0', () => {
    const { container } = render(<ParticleSphere3D {...defaultProps} audioAmplitude={0} />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it('handles audioAmplitude=1.0', () => {
    const { container } = render(<ParticleSphere3D {...defaultProps} audioAmplitude={1.0} />)
    expect(container.firstChild).toBeInTheDocument()
  })

  it('renders without any props (just required)', () => {
    const { container } = render(<ParticleSphere3D {...defaultProps} />)
    expect(container.firstChild).toBeInTheDocument()
  })
})
