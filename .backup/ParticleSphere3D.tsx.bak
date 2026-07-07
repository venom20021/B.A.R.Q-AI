import { useRef, useMemo, useCallback, useEffect, Component, type MutableRefObject } from 'react'
import type { ReactNode } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import type { Group, Mesh, Points, MeshBasicMaterial } from 'three'
// Import specific Three.js values instead of namespace import to avoid bundling issues
import { AdditiveBlending, DoubleSide, CanvasTexture } from 'three'
import { Grid } from '@react-three/drei'

// ─── Error Boundary — prevents 3D sphere crash from blanking the whole dashboard

interface ErrorBoundaryState {
  hasError: boolean
}

class CanvasErrorBoundary extends Component<{ children: ReactNode; fallback?: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true }
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="w-[280px] h-[280px] flex items-center justify-center">
          <div className="w-8 h-8 border-2 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin" />
        </div>
      )
    }
    return this.props.children
  }
}

// ─── Voice Reactivity Config ───────────────────────────────────────────

const IDLE_ROTATION_SPEED = 0.08
const SPEAKING_ROTATION_SPEED = 0.25
const IDLE_WOBBLE_SPEED = 0.025
const SPEAKING_WOBBLE_SPEED = 0.05
const IDLE_WOBBLE_AMPLITUDE = 0.08
const SPEAKING_WOBBLE_AMPLITUDE = 0.18
const IDLE_PULSE_AMPLITUDE = 0.01
const SPEAKING_PULSE_AMPLITUDE = 0.035
const IDLE_PULSE_FREQ = 0.5
const SPEAKING_PULSE_FREQ = 1.2
const RING_IDLE_SPEED = 0.04
const RING_SPEAKING_SPEED = 0.12

// ─── Mouse Tracking Config ─────────────────────────────────────────────

const MOUSE_SPRING = 0.06       // lerp factor per frame — lower = smoother
const MOUSE_MAX_ANGLE = 0.35    // max rotation offset in radians (~20°)

// ─── Parallax Depth Config ────────────────────────────────────────────

const PARALLAX_STRENGTH = 0.25  // max X/Y shift for surface particles (units)
const PARALLAX_DEPTH_MIN = 0.75 // innermost particle radius fraction
const PARALLAX_DEPTH_MAX = 1.0  // outermost particle radius fraction

// ─── Color Transition Config ────────────────────────────────────────────

const COLOR_LERP_RATE = 0.03    // per-frame lerp factor for theme color transitions (~2.5s to converge)

// ─── Types ──────────────────────────────────────────────────────────────

export type ThemeColor = 'cyan' | 'purple' | 'amber' | 'red'

interface ThemePalette {
  primary: string
  primaryHex: string
  particle: [number, number, number]  // RGB base for inner core
  particleOuterBoost: [number, number, number]  // RGB boost for outer particles
  ringOpacity: number
}

const THEMES: Record<ThemeColor, ThemePalette> = {
  cyan: {
    primary: '#00E5FF',
    primaryHex: '#00E5FF',
    particle: [0.0, 0.7, 0.85],
    particleOuterBoost: [0.15, 0.3, 0.15],
    ringOpacity: 0.2,
  },
  purple: {
    primary: '#A855F7',
    primaryHex: '#A855F7',
    particle: [0.45, 0.15, 0.85],
    particleOuterBoost: [0.25, 0.0, 0.15],
    ringOpacity: 0.18,
  },
  amber: {
    primary: '#F59E0B',
    primaryHex: '#F59E0B',
    particle: [0.85, 0.5, 0.05],
    particleOuterBoost: [0.15, 0.2, 0.0],
    ringOpacity: 0.2,
  },
  red: {
    primary: '#EF4444',
    primaryHex: '#EF4444',
    particle: [0.85, 0.15, 0.1],
    particleOuterBoost: [0.15, 0.0, 0.0],
    ringOpacity: 0.2,
  },
}

// ─── Constants ──────────────────────────────────────────────────────────

const PARTICLE_COUNT = 30000
const SPHERE_RADIUS = 2.0

// ─── Density Config ────────────────────────────────────────────────────

const DENSITY_POWER = 5.0         // power distribution: >1 clusters particles toward inner core

// ─── Inner Particle Field ───────────────────────────────────────────────

function ParticleField({ activeTheme, isSpeaking, mouseTarget }: {
  activeTheme: ThemeColor
  isSpeaking: boolean
  mouseTarget: MutableRefObject<{ x: number; y: number }>
}): JSX.Element {
  const groupRef = useRef<Group>(null!)
  const pointsRef = useRef<Points>(null!)

  // Refs to avoid stale closure in useFrame
  const speakingRef = useRef(isSpeaking)
  speakingRef.current = isSpeaking

  // Spring-damped mouse offset — smoothly follows the mouse
  const mouseOffset = useRef({ x: 0, y: 0 })

  const theme = THEMES[activeTheme]

  // Per-particle depth values (0.75–1.0) and a ref to the original rest positions
  const depthFactorsRef = useRef<Float32Array>(null!)
  const restPositionsRef = useRef<Float32Array>(null!)

  // ─── Stable geometry — generated once ──────────────────────────
  const { positions, sizes } = useMemo(() => {
    const pos = new Float32Array(PARTICLE_COUNT * 3)
    const sz = new Float32Array(PARTICLE_COUNT)
    const depths = new Float32Array(PARTICLE_COUNT)

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      // Fibonacci sphere distribution for even spread
      const goldenRatio = (1 + Math.sqrt(5)) / 2
      const theta = 2 * Math.PI * i / goldenRatio
      const phi = Math.acos(1 - 2 * (i + 0.5) / PARTICLE_COUNT)
      // Power-weighted distribution: most particles cluster near the inner
      // radius (dense core), thinning out toward the surface (scattered edge)
      const t = Math.pow(Math.random(), DENSITY_POWER)
      const r = SPHERE_RADIUS * (PARALLAX_DEPTH_MIN + t * (PARALLAX_DEPTH_MAX - PARALLAX_DEPTH_MIN))

      const x = r * Math.sin(phi) * Math.cos(theta)
      const y = r * Math.sin(phi) * Math.sin(theta)
      const z = r * Math.cos(phi)

      pos[i * 3] = x
      pos[i * 3 + 1] = y
      pos[i * 3 + 2] = z

      // Store depth ratio for parallax
      depths[i] = r / SPHERE_RADIUS

      // Size gradient: inner particles larger (bright core), outer smaller
      const depthFraction = (depths[i] - PARALLAX_DEPTH_MIN) / (PARALLAX_DEPTH_MAX - PARALLAX_DEPTH_MIN)
      sz[i] = (0.30 - depthFraction * 0.23) + Math.random() * 0.06
    }

    // Store refs for useFrame
    restPositionsRef.current = new Float32Array(pos)
    depthFactorsRef.current = depths

    return { positions: pos, sizes: sz }
  }, [])  // ⬅️ empty deps — stable for the lifetime of the component

  // ─── Particle colors (recomputed on theme change) ──────────────
  const colors = useMemo(() => {
    const col = new Float32Array(PARTICLE_COUNT * 3)
    const [rBase, gBase, bBase] = theme.particle
    const [rBoost, gBoost, bBoost] = theme.particleOuterBoost
    const depths = depthFactorsRef.current
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const depth = depths[i]  // 0.75–1.0
      col[i * 3] = rBase + (1 - depth) * rBoost
      col[i * 3 + 1] = gBase + (1 - depth) * gBoost
      col[i * 3 + 2] = bBase + (1 - depth) * bBoost
    }
    return col
  }, [activeTheme])

  // ─── Animated color buffer — lerps toward `colors` each frame ──
  // Stable Float32Array reference passed to the buffer attribute;
  // mutated in-place each frame so R3F never re-uploads the buffer.
  const colorBufferRef = useRef<Float32Array | null>(null)
  const targetColorsRef = useRef<Float32Array>(colors)
  if (!colorBufferRef.current) {
    colorBufferRef.current = new Float32Array(colors)
  }
  targetColorsRef.current = colors

  // ─── Soft bokeh texture — generated once ─────────────────────
  // Canvas-based radial gradient creates a soft circle texture.
  // When thousands of these overlap with additive blending, they
  // naturally form a glowing energy cloud.
  const softTexture = useMemo(() => {
    const size = 64
    const canvas = document.createElement('canvas')
    canvas.width = size
    canvas.height = size
    const ctx = canvas.getContext('2d')!
    const cx = size / 2, cy = size / 2, r = size / 2
    const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, r)
    gradient.addColorStop(0, 'rgba(255,255,255,1)')
    gradient.addColorStop(0.2, 'rgba(255,255,255,0.9)')
    gradient.addColorStop(0.5, 'rgba(255,255,255,0.4)')
    gradient.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, size, size)
    const tex = new CanvasTexture(canvas)
    tex.needsUpdate = true
    return tex
  }, [])

  // Animation loop — voice-reactive + mouse-tracking + parallax depth + line reactivity
  useFrame((state) => {
    const t = state.clock.elapsedTime
    const isSpoke = speakingRef.current

    // Speed multipliers — 3× faster when speaking
    const rotSpeed = isSpoke ? SPEAKING_ROTATION_SPEED : IDLE_ROTATION_SPEED
    const wobbleSpeed = isSpoke ? SPEAKING_WOBBLE_SPEED : IDLE_WOBBLE_SPEED
    const wobbleAmp = isSpoke ? SPEAKING_WOBBLE_AMPLITUDE : IDLE_WOBBLE_AMPLITUDE
    const pulseAmp = isSpoke ? SPEAKING_PULSE_AMPLITUDE : IDLE_PULSE_AMPLITUDE
    const pulseFreq = isSpoke ? SPEAKING_PULSE_FREQ : IDLE_PULSE_FREQ

    // Spring-damped mouse tracking
    const target = mouseTarget.current
    const offset = mouseOffset.current
    offset.x += (target.x - offset.x) * MOUSE_SPRING
    offset.y += (target.y - offset.y) * MOUSE_SPRING

    if (groupRef.current) {
      // Base rotation: auto-rotation + voice reactivity
      const baseY = t * rotSpeed
      const baseX = Math.sin(t * wobbleSpeed) * wobbleAmp

      // Mouse offset adds on top with spring damping
      groupRef.current.rotation.y = baseY + offset.x * MOUSE_MAX_ANGLE
      groupRef.current.rotation.x = baseX + offset.y * MOUSE_MAX_ANGLE
    }

    // Parallax depth displacement — surface particles shift more than deep ones
    if (pointsRef.current && restPositionsRef.current && depthFactorsRef.current) {
      const geometry = pointsRef.current.geometry
      const posAttr = geometry.attributes.position
      if (posAttr) {
        const posArray = posAttr.array as Float32Array
        const rest = restPositionsRef.current
        const depths = depthFactorsRef.current
        const depthRange = PARALLAX_DEPTH_MAX - PARALLAX_DEPTH_MIN

        for (let i = 0; i < PARTICLE_COUNT; i++) {
          // Normalize depth to 0 (inner) → 1 (surface)
          const depthFactor = (depths[i] - PARALLAX_DEPTH_MIN) / depthRange
          const i3 = i * 3
          // Shift X/Y: surface = full offset, deep = nearly static
          posArray[i3] = rest[i3] + offset.x * depthFactor * PARALLAX_STRENGTH
          posArray[i3 + 1] = rest[i3 + 1] + offset.y * depthFactor * PARALLAX_STRENGTH
          posArray[i3 + 2] = rest[i3 + 2]
        }
        posAttr.needsUpdate = true
      }
    }

    // Pulse particle size — larger amplitude and faster frequency when speaking
    if (pointsRef.current) {
      const geometry = pointsRef.current.geometry
      const sizeAttr = geometry.attributes.size
      if (sizeAttr) {
        const array = sizeAttr.array as Float32Array
        for (let i = 0; i < PARTICLE_COUNT; i++) {
          const depthFraction = (depthFactorsRef.current[i] - PARALLAX_DEPTH_MIN) / (PARALLAX_DEPTH_MAX - PARALLAX_DEPTH_MIN)
          const base = (0.30 - depthFraction * 0.23) + (i % 3) * 0.04
          array[i] = base + Math.sin(t * pulseFreq + i * 0.1) * pulseAmp
        }
        sizeAttr.needsUpdate = true
      }
    }

    // Smooth color transition — lerp toward target on theme change
    if (colorBufferRef.current && targetColorsRef.current && pointsRef.current) {
      const cur = colorBufferRef.current
      const tgt = targetColorsRef.current
      const colorAttr = pointsRef.current.geometry.attributes.color
      if (colorAttr && colorAttr.array === cur) {
        let dirty = false
        for (let i = 0; i < cur.length; i++) {
          const diff = tgt[i] - cur[i]
          if (Math.abs(diff) > 0.001) {
            cur[i] += diff * COLOR_LERP_RATE
            dirty = true
          }
        }
        if (dirty) colorAttr.needsUpdate = true
      }
    }
  })

  return (
    <group ref={groupRef}>
      {/* Particle points */}
      <points ref={pointsRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            count={PARTICLE_COUNT}
            array={positions}
            itemSize={3}
          />
          <bufferAttribute
            attach="attributes-size"
            count={PARTICLE_COUNT}
            array={sizes}
            itemSize={1}
          />
          <bufferAttribute
            attach="attributes-color"
            count={PARTICLE_COUNT}
            array={colorBufferRef.current}
            itemSize={3}
          />
        </bufferGeometry>
        <pointsMaterial
          size={0.06}
          sizeAttenuation
          transparent
          opacity={1}
          vertexColors
          depthWrite={false}
          blending={AdditiveBlending}
          map={softTexture}
        />
      </points>
    </group>
  )
}

// ─── Outer Ring Segments ────────────────────────────────────────────────

const RING_BOOST_MULTIPLIER = 6    // peak speed multiplier on theme switch
const RING_BOOST_DECAY = 0.04       // per-frame decay toward 1.0 (~1.5s to settle)

function Rings({ activeTheme, isSpeaking }: { activeTheme: ThemeColor; isSpeaking: boolean }): JSX.Element {
  const ring1Ref = useRef<Mesh>(null!)
  const ring2Ref = useRef<Mesh>(null!)

  const speakingRef = useRef(isSpeaking)
  speakingRef.current = isSpeaking

  const theme = THEMES[activeTheme]

  // Speed boost on theme change
  const prevThemeRef = useRef(activeTheme)
  const speedBoostRef = useRef(1)  // multiplier, decays from 6 → 1
  if (prevThemeRef.current !== activeTheme) {
    prevThemeRef.current = activeTheme
    speedBoostRef.current = RING_BOOST_MULTIPLIER
  }

  // Accumulated rotation (delta-based to avoid jumps on speed change)
  const ringRotationRef = useRef({ z: 0, x: 0 })

  // Animated ring color — lerps toward target each frame
  const currentRgbRef = useRef<{ r: number; g: number; b: number } | null>(null)
  const targetRgbRef = useRef({ r: 0, g: 0, b: 0 })

  // Parse target from current theme
  const tgtR = parseInt(theme.primary.slice(1, 3), 16) / 255
  const tgtG = parseInt(theme.primary.slice(3, 5), 16) / 255
  const tgtB = parseInt(theme.primary.slice(5, 7), 16) / 255

  if (!currentRgbRef.current) {
    currentRgbRef.current = { r: tgtR, g: tgtG, b: tgtB }
  }
  targetRgbRef.current = { r: tgtR, g: tgtG, b: tgtB }

  useFrame((_state, delta) => {
    const baseSpeed = speakingRef.current ? RING_SPEAKING_SPEED : RING_IDLE_SPEED

    // Decay speed boost toward 1.0
    if (speedBoostRef.current > 1.001) {
      speedBoostRef.current += (1 - speedBoostRef.current) * RING_BOOST_DECAY
    } else {
      speedBoostRef.current = 1
    }

    const speed = baseSpeed * speedBoostRef.current

    // Accumulate rotation with current speed (delta-based = smooth)
    ringRotationRef.current.z += delta * speed
    ringRotationRef.current.x += delta * speed * 0.75

    if (ring1Ref.current) ring1Ref.current.rotation.z = ringRotationRef.current.z
    if (ring2Ref.current) ring2Ref.current.rotation.x = ringRotationRef.current.x

    // Lerp ring color toward target
    if (currentRgbRef.current) {
      const cur = currentRgbRef.current
      const tgt = targetRgbRef.current
      const dr = tgt.r - cur.r
      const dg = tgt.g - cur.g
      const db = tgt.b - cur.b
      if (Math.abs(dr) > 0.001 || Math.abs(dg) > 0.001 || Math.abs(db) > 0.001) {
        cur.r += dr * COLOR_LERP_RATE
        cur.g += dg * COLOR_LERP_RATE
        cur.b += db * COLOR_LERP_RATE

        const mat1 = ring1Ref.current?.material as MeshBasicMaterial | undefined
        const mat2 = ring2Ref.current?.material as MeshBasicMaterial | undefined
        if (mat1?.color) { mat1.color.r = cur.r; mat1.color.g = cur.g; mat1.color.b = cur.b }
        if (mat2?.color) { mat2.color.r = cur.r; mat2.color.g = cur.g; mat2.color.b = cur.b }
      }
    }
  })

  return (
    <group>
      {/* Horizontal ring */}
      <mesh ref={ring1Ref} rotation={[Math.PI / 2, 0, 0]}>
        <ringGeometry args={[SPHERE_RADIUS * 1.15, SPHERE_RADIUS * 1.18, 128]} />
        <meshBasicMaterial
          transparent
          opacity={theme.ringOpacity}
          side={DoubleSide}
          depthWrite={false}
        />
      </mesh>

      {/* Vertical ring */}
      <mesh ref={ring2Ref}>
        <ringGeometry args={[SPHERE_RADIUS * 1.25, SPHERE_RADIUS * 1.27, 128]} />
        <meshBasicMaterial
          transparent
          opacity={theme.ringOpacity * 0.7}
          side={DoubleSide}
          depthWrite={false}
        />
      </mesh>
    </group>
  )
}

// ─── CSS Glow Effect (replaces WebGL bloom — avoids WebGL context loss) ─

function useCSSGlow(containerRef: React.RefObject<HTMLDivElement | null>, isSpeaking: boolean, themeColor: string) {
  const currentIntensity = useRef(0.3)
  const speakingRef = useRef(isSpeaking)
  speakingRef.current = isSpeaking

  // Animated glow color — lerps toward target
  const currentRgbRef = useRef<{ r: number; g: number; b: number } | null>(null)
  const targetRgbRef = useRef({ r: 0, g: 0, b: 0 })

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    // Parse target from hex
    const tgtR = parseInt(themeColor.slice(1, 3), 16) / 255
    const tgtG = parseInt(themeColor.slice(3, 5), 16) / 255
    const tgtB = parseInt(themeColor.slice(5, 7), 16) / 255

    // Initialize current on first mount
    if (!currentRgbRef.current) {
      currentRgbRef.current = { r: tgtR, g: tgtG, b: tgtB }
    }
    targetRgbRef.current = { r: tgtR, g: tgtG, b: tgtB }

    let rafId: number
    let startTime = performance.now()

    const animate = (now: number) => {
      const t = (now - startTime) / 1000
      const speaking = speakingRef.current

      // Idle breathing: ~0.35–0.45 (boosted for brighter core)
      const idleTarget = 0.4 + Math.sin(t * 0.5) * 0.05
      // Speaking pulse: ~0.65–0.95
      const target = speaking
        ? 0.8 + Math.sin(t * 2.0) * 0.15
        : idleTarget

      // Spring-damped interpolation
      const curInt = currentIntensity.current
      const nextInt = curInt + (target - curInt) * 0.08
      currentIntensity.current = nextInt

      // Lerp color toward target
      if (currentRgbRef.current) {
        const cur = currentRgbRef.current
        const tgt = targetRgbRef.current
        const dr = tgt.r - cur.r
        const dg = tgt.g - cur.g
        const db = tgt.b - cur.b
        if (Math.abs(dr) > 0.001) cur.r += dr * COLOR_LERP_RATE
        if (Math.abs(dg) > 0.001) cur.g += dg * COLOR_LERP_RATE
        if (Math.abs(db) > 0.001) cur.b += db * COLOR_LERP_RATE
      }

      // Apply as CSS filter — drop-shadow creates a bloom-like glow
      const glowSize = 8 + nextInt * 22  // 8px at min, ~30px at max
      const alpha = 0.3 + nextInt * 0.4  // 0.44 at min, ~0.68 at max
      const rgb = currentRgbRef.current!
      el.style.filter = `drop-shadow(0 0 ${glowSize}px rgba(${Math.round(rgb.r * 255)},${Math.round(rgb.g * 255)},${Math.round(rgb.b * 255)},${alpha.toFixed(3)}) ) brightness(${1 + nextInt * 0.2})`

      rafId = requestAnimationFrame(animate)
    }

    rafId = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(rafId)
  }, [containerRef, themeColor])
}

// ─── Perspective Grid Floor ─────────────────────────────────────────────

function PerspectiveGrid({ activeTheme }: { activeTheme: ThemeColor }): JSX.Element {
  const theme = THEMES[activeTheme]
  return (
    <Grid
      position={[0, -1.85, 0]}
      args={[10, 10]}
      cellSize={0.4}
      cellThickness={0.6}
      cellColor="#6b21a8"
      sectionSize={2}
      sectionThickness={1}
      sectionColor={theme.primary}
      fadeDistance={6}
      fadeStrength={1.5}
      infiniteGrid
      followCamera={false}
    />
  )
}

// ─── Main Export ────────────────────────────────────────────────────────

export function ParticleSphere3D({ activeTheme = 'cyan', isSpeaking = false, showGrid = false }: { activeTheme?: ThemeColor; isSpeaking?: boolean; showGrid?: boolean }): JSX.Element {
  // Track mouse position normalized to [-1, 1] relative to canvas center
  const mouseTarget = useRef({ x: 0, y: 0 })
  const containerRef = useRef<HTMLDivElement>(null)
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return
    // Normalize: -1 (left/top) to +1 (right/bottom)
    mouseTarget.current.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
    mouseTarget.current.y = -(((e.clientY - rect.top) / rect.height) * 2 - 1)
  }, [])

  const handleMouseLeave = useCallback(() => {
    // Slowly spring back to center
    mouseTarget.current.x = 0
    mouseTarget.current.y = 0
  }, [])

  // CSS glow animation — replaces WebGL Bloom which causes context loss on Electron/macOS
  const theme = THEMES[activeTheme]
  useCSSGlow(containerRef, isSpeaking, theme.primary)

  // Safety net for WebGL context loss (Electron/macOS GPU edge cases)
  const handleCanvasCreated = useCallback((state: any) => {
    const gl = state.gl
    const canvas = gl.domElement as HTMLCanvasElement

    const onContextLost = (e: Event) => {
      e.preventDefault()
    }

    canvas.addEventListener('webglcontextlost', onContextLost)
    return () => canvas.removeEventListener('webglcontextlost', onContextLost)
  }, [])

  return (
    <div
      ref={containerRef}
      className="w-[340px] h-[340px] rounded-full"
      style={{
        maskImage: 'radial-gradient(circle at center, black 80%, transparent 100%)',
        WebkitMaskImage: 'radial-gradient(circle at center, black 80%, transparent 100%)',
      }}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
    >
      <CanvasErrorBoundary>
        <Canvas
          camera={{ position: [0, 0, 4.5], fov: 50 }}
          dpr={[1, 1.5]}
          gl={{
            antialias: true,
            alpha: false,
            powerPreference: 'high-performance',
            failIfMajorPerformanceCaveat: false,
          }}
          onCreated={handleCanvasCreated}
          style={{ width: '100%', height: '100%' }}
        >
          <ParticleField activeTheme={activeTheme} isSpeaking={isSpeaking} mouseTarget={mouseTarget} />
          <Rings activeTheme={activeTheme} isSpeaking={isSpeaking} />
          {showGrid && <PerspectiveGrid activeTheme={activeTheme} />}
        </Canvas>
      </CanvasErrorBoundary>
    </div>
  )
}
