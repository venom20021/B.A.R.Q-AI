import { useRef, useMemo, useState, useCallback, useEffect, Component } from 'react'
import { Zap, FileText, Link } from 'lucide-react'
import type { ReactNode, MutableRefObject } from 'react'
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber'
import type { Group, Mesh, Points } from 'three'
import { AdditiveBlending, DoubleSide, CanvasTexture, Vector3, type MeshBasicMaterial } from 'three'
import { Html, QuadraticBezierLine, OrbitControls } from '@react-three/drei'

// ─── Error Boundary ────────────────────────────────────────────────────

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
        <div className="w-full h-full flex items-center justify-center">
          <div className="w-8 h-8 border-2 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin" />
        </div>
      )
    }
    return this.props.children
  }
}

// ─── Types ─────────────────────────────────────────────────────────────

export type AIState = 'idle' | 'listening' | 'thinking' | 'responding'

export type QualityLevel = 'ultra' | 'high' | 'medium' | 'low' | 'potato'

export interface TransferSparkData {
  id: string
  from: [number, number, number]
  to: [number, number, number]
  color: string
  progress: number // 0-1
}

export interface TemporalLogEntry {
  id: string
  timestamp: number
  text: string
  icon?: string
}

// ─── Agent Node Data ───────────────────────────────────────────────────

interface AgentNodeData {
  id: string
  label: string
  color: string
  position: [number, number, number]
  description: string
}

const AGENT_NODES: AgentNodeData[] = [
  { id: 'strategist', label: 'Strategist', color: '#00E5FF', position: [5.0, 1.8, 1.0], description: 'Planning & Strategy' },
  { id: 'researcher', label: 'Researcher', color: '#A855F7', position: [2.0, 4.5, 2.0], description: 'Deep Research' },
  { id: 'chief-of-staff', label: 'Chief of Staff', color: '#FBBF24', position: [-3.5, 4.0, 1.5], description: 'Coordination' },
  { id: 'finance', label: 'Finance', color: '#34D399', position: [-5.5, 0.0, -1.0], description: 'Budget & Tracking' },
  { id: 'memory', label: 'Memory', color: '#F472B6', position: [-3.0, -3.8, 2.0], description: 'Context & Recall' },
  { id: 'vision', label: 'Vision', color: '#60A5FA', position: [3.5, -3.5, 2.5], description: 'Computer Vision' },
  { id: 'analytics', label: 'Analytics', color: '#FB923C', position: [0.5, -5.5, -1.5], description: 'Data Insights' },
  { id: 'coding', label: 'Coding', color: '#2DD4BF', position: [1.5, 5.0, -2.0], description: 'Code Generation' },
]

// ─── Quality Presets ───────────────────────────────────────────────────

export const QUALITY_PRESETS: Record<QualityLevel, { label: string; particles: number; description: string }> = {
  ultra:  { label: 'Ultra',   particles: 40000, description: 'High-end desktops' },
  high:   { label: 'High',    particles: 20000, description: 'Default — recommended' },
  medium: { label: 'Medium',  particles: 10000, description: 'Mid-range systems' },
  low:    { label: 'Low',     particles: 5000,  description: 'Integrated GPUs' },
  potato: { label: 'Potato',  particles: 1500,  description: 'Minimum performance' },
}

// ─── Constants ─────────────────────────────────────────────────────────

const SPHERE_RADIUS = 2.8
const WAKE_EASE_RATE = 0.035
const WAKE_MIN_SCALE = 0.02

// ─── Particle Data Generator ───────────────────────────────────────────

interface ParticleData {
  positions: Float32Array
  sizes: Float32Array
  colors: Float32Array
}

function generateParticleData(particleCount: number): ParticleData {
  const pos = new Float32Array(particleCount * 3)
  const sz = new Float32Array(particleCount)
  const col = new Float32Array(particleCount * 3)
  for (let i = 0; i < particleCount; i++) {
    const goldenRatio = (1 + Math.sqrt(5)) / 2
    const theta = 2 * Math.PI * i / goldenRatio
    const phi = Math.acos(1 - 2 * (i + 0.5) / particleCount)
    const t = Math.pow(Math.random(), 4.0)
    const r = SPHERE_RADIUS * (0.75 + t * 0.25)
    pos[i * 3] = r * Math.sin(phi) * Math.cos(theta)
    pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta)
    pos[i * 3 + 2] = r * Math.cos(phi)
    sz[i] = (0.28 - t * 0.20) + Math.random() * 0.05

    const normalizedDepth = (r / SPHERE_RADIUS - 0.75) / 0.25
    const isInner = normalizedDepth < 0.5
    if (isInner) {
      col[i * 3] = 0.3 + Math.random() * 0.4
      col[i * 3 + 1] = 0.8 + Math.random() * 0.5
      col[i * 3 + 2] = 1.0
    } else {
      const fade = (normalizedDepth - 0.5) * 2
      col[i * 3] = 0.1 * (1 - fade)
      col[i * 3 + 1] = 0.4 * (1 - fade * 0.5)
      col[i * 3 + 2] = 0.7 * (1 - fade * 0.3)
    }
  }
  return { positions: pos, sizes: sz, colors: col }
}

// ─── Soft Particle Texture ─────────────────────────────────────────────

function useSoftTexture(): CanvasTexture {
  return useMemo(() => {
    const size = 64
    const canvas = document.createElement('canvas')
    canvas.width = size; canvas.height = size
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
}

// ─── Cyan Particle Core ────────────────────────────────────────────────

function ParticleCore({ particleCount }: { particleCount: number }): JSX.Element {
  "use no memo"
  const groupRef = useRef<Group>(null!)
  const pointsRef = useRef<Points>(null!)
  const wakeProgressRef = useRef(0)
  const wakeDoneRef = useRef(false)

  // Regenerate particle data when count changes
  const particleData = useMemo(() => generateParticleData(particleCount), [particleCount])
  const colors = particleData.colors
  const softTexture = useSoftTexture()

  useFrame((state) => {
    const t = state.clock.elapsedTime
    if (!wakeDoneRef.current) {
      wakeProgressRef.current += (1 - wakeProgressRef.current) * WAKE_EASE_RATE
      if (wakeProgressRef.current > 0.999) { wakeProgressRef.current = 1; wakeDoneRef.current = true }
    }
    const wakeScale = WAKE_MIN_SCALE + wakeProgressRef.current * (1 - WAKE_MIN_SCALE)
    if (groupRef.current) {
      groupRef.current.rotation.y = t * 0.06
      groupRef.current.rotation.x = Math.sin(t * 0.02) * 0.05
      groupRef.current.scale.setScalar(wakeScale)
    }
    if (pointsRef.current) {
      const sizeAttr = pointsRef.current.geometry.attributes.size
      if (sizeAttr) {
        const array = sizeAttr.array as Float32Array
        const pulse = 1 + Math.sin(t * 0.3) * 0.03
        const sizes = particleData.sizes
        for (let i = 0; i < particleCount; i++) array[i] = sizes[i] * pulse
        sizeAttr.needsUpdate = true
      }
    }
  })

  return (
    <group ref={groupRef}>
      <points ref={pointsRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" count={particleCount} array={particleData.positions} itemSize={3} />
          <bufferAttribute attach="attributes-size" count={particleCount} array={particleData.sizes} itemSize={1} />
          <bufferAttribute attach="attributes-color" count={particleCount} array={colors} itemSize={3} />
        </bufferGeometry>
        <pointsMaterial size={0.06} sizeAttenuation transparent opacity={0.95} vertexColors depthWrite={false} blending={AdditiveBlending} map={softTexture} />
      </points>
    </group>
  )
}

// ─── Gold Orbiting Ring ────────────────────────────────────────────────

function GoldRing(): JSX.Element {
  const ringRef = useRef<Group>(null!)
  useFrame((state) => {
    if (ringRef.current) {
      ringRef.current.rotation.y = state.clock.elapsedTime * 0.15
      ringRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.05) * 0.1
    }
  })
  return (
    <group ref={ringRef}>
      <mesh rotation={[Math.PI / 2.5, 0, 0]}>
        <torusGeometry args={[SPHERE_RADIUS * 1.45, 0.035, 32, 96]} />
        <meshBasicMaterial color="#FBBF24" transparent opacity={0.6} side={DoubleSide} depthWrite={false} />
      </mesh>
      <mesh rotation={[Math.PI / 2.5, 0.3, 0]}>
        <torusGeometry args={[SPHERE_RADIUS * 1.45, 0.08, 16, 96]} />
        <meshBasicMaterial color="#FBBF24" transparent opacity={0.12} side={DoubleSide} depthWrite={false} />
      </mesh>
      <mesh rotation={[Math.PI / 3, Math.PI / 4, 0]}>
        <torusGeometry args={[SPHERE_RADIUS * 1.35, 0.02, 24, 80]} />
        <meshBasicMaterial color="#FDE68A" transparent opacity={0.3} side={DoubleSide} depthWrite={false} />
      </mesh>
    </group>
  )
}

// ─── Resource Ring (telemetry) ─────────────────────────────────────────

function ResourceRing({ systemLoad }: { systemLoad: number }): JSX.Element {
  const ringRef = useRef<Group>(null!)
  const matRef = useRef<MeshBasicMaterial>(null!)

  useFrame((state) => {
    if (!ringRef.current || !matRef.current) return
    const normalizedLoad = systemLoad / 100
    const speed = 0.025 + normalizedLoad * 0.025
    ringRef.current.rotation.y += speed
    ringRef.current.rotation.x = Math.sin(state.clock.elapsedTime * 0.08) * 0.06
    const opacity = 0.1 + normalizedLoad * 0.2
    matRef.current.opacity = Math.min(opacity, 0.3)
    const r = 0.05 + normalizedLoad * 0.5
    const g = 0.3 + normalizedLoad * 0.5
    const b = 0.8 - normalizedLoad * 0.4
    matRef.current.color.setRGB(r, g, b)
  })

  return (
    <group ref={ringRef}>
      <mesh rotation={[Math.PI / 2.2, 0, 0]}>
        <torusGeometry args={[SPHERE_RADIUS * 1.65, 0.005, 16, 80]} />
        <meshBasicMaterial ref={matRef} color="#4FC3F7" transparent opacity={0.15} side={DoubleSide} depthWrite={false} />
      </mesh>
    </group>
  )
}

// ─── Transfer Spark ────────────────────────────────────────────────────

function TransferSpark({ spark }: { spark: TransferSparkData }): JSX.Element {
  const meshRef = useRef<Mesh>(null!)

  const mid = useMemo(() => {
    const start = new Vector3(...spark.from)
    const end = new Vector3(...spark.to)
    const m = new Vector3().addVectors(start, end).multiplyScalar(0.5)
    const dir = new Vector3().copy(end).normalize()
    m.add(dir.multiplyScalar(1.2))
    return m
  }, [spark.from, spark.to])

  useFrame(() => {
    if (!meshRef.current) return
    const t = spark.progress
    const p0 = new Vector3(...spark.from)
    const p1 = mid
    const p2 = new Vector3(...spark.to)
    const pos = new Vector3()
    pos.x = (1 - t) ** 2 * p0.x + 2 * (1 - t) * t * p1.x + t ** 2 * p2.x
    pos.y = (1 - t) ** 2 * p0.y + 2 * (1 - t) * t * p1.y + t ** 2 * p2.y
    pos.z = (1 - t) ** 2 * p0.z + 2 * (1 - t) * t * p1.z + t ** 2 * p2.z
    meshRef.current.position.copy(pos)
    const pulse = 0.5 + Math.sin(t * 20) * 0.3
    meshRef.current.scale.setScalar(pulse)
  })

  return (
    <mesh ref={meshRef}>
      <sphereGeometry args={[0.06, 8, 8]} />
      <meshBasicMaterial color={spark.color} transparent opacity={0.9} blending={AdditiveBlending} depthWrite={false} />
    </mesh>
  )
}

// ─── Camera Controller ─────────────────────────────────────────────────

const DEFAULT_POSITION = new Vector3(0, 0, 9)
const DEFAULT_TARGET = new Vector3(0, 0, 0)
const CAMERA_LERP_SPEED = 0.035
const CAMERA_SETTLE_THRESHOLD = 0.15

function CameraController({
  focusTargetRef,
  activeAgent,
}: {
  focusTargetRef: MutableRefObject<Vector3 | null>
  activeAgent: string | null
}): JSX.Element {
  const { camera } = useThree()
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const controlsRef = useRef<any>(null!)
  const animatingRef = useRef(false)

  useFrame(() => {
    const controls = controlsRef.current
    if (!controls) return

    if (activeAgent && focusTargetRef.current) {
      animatingRef.current = true
      controls.enabled = false
      const targetPos = focusTargetRef.current
      controls.target.lerp(targetPos, CAMERA_LERP_SPEED)
      const offset = targetPos.clone().add(new Vector3(4, 0.5, 4))
      camera.position.lerp(offset, CAMERA_LERP_SPEED)
    } else if (animatingRef.current) {
      controls.target.lerp(DEFAULT_TARGET, CAMERA_LERP_SPEED)
      camera.position.lerp(DEFAULT_POSITION, CAMERA_LERP_SPEED)
      const settled = camera.position.distanceTo(DEFAULT_POSITION) < CAMERA_SETTLE_THRESHOLD
      if (settled) {
        controls.enabled = true
        animatingRef.current = false
      }
    }
    controls.update()
  })

  return (
    <OrbitControls
      ref={controlsRef}
      enablePan={false}
      enableZoom={true}
      minDistance={3}
      maxDistance={25}
      zoomSpeed={1.2}
      rotateSpeed={0.8}
      dampingFactor={0.08}
      enableDamping
    />
  )
}

// ─── Agent Node ────────────────────────────────────────────────────────

function AgentNode({
  node,
  onSelect,
  focusTargetRef,
  isActive,
  onContextMenu,
  activeRadialMenu,
  onCloseRadialMenu,
  onRadialAction,
}: {
  node: AgentNodeData
  onSelect: (label: string, worldPos: Vector3) => void
  focusTargetRef: MutableRefObject<Vector3 | null>
  isActive: boolean
  onContextMenu: (label: string) => void
  activeRadialMenu: string | null
  onCloseRadialMenu: () => void
  onRadialAction: (label: string, action: 'quick-execute' | 'view-details' | 'share-link') => void
}): JSX.Element {
  const nodeRef = useRef<Mesh>(null!)
  const glowRef = useRef<Mesh>(null!)
  const startPos = useMemo(() => new Vector3(...node.position), [node.position])
  // eslint-disable-next-line react-hooks/purity
  const floatOffset = useRef(Math.random() * Math.PI * 2)
  const [hovered, setHovered] = useState(false)
  const hoveredRef = useRef(false)
  const isRadialOpen = activeRadialMenu === node.label

  const mid = useMemo(() => {
    const start = new Vector3(0, 0, 0)
    const end = new Vector3(...node.position)
    const m = new Vector3().addVectors(start, end).multiplyScalar(0.5)
    const dir = new Vector3().copy(end).normalize()
    m.add(dir.multiplyScalar(1.2))
    return m
  }, [node.position])

  useFrame((state) => {
    const t = state.clock.elapsedTime
    const float = Math.sin(t * 0.5 + floatOffset.current) * 0.2
    const isHovered = hoveredRef.current
    const pulseActive = isActive && !isHovered
    const activePulse = pulseActive ? 1 + Math.sin(t * 3) * 0.2 : 0

    if (nodeRef.current) {
      nodeRef.current.position.y = startPos.y + float
      const breath = Math.sin(t * 0.8 + floatOffset.current) * 0.08
      nodeRef.current.scale.setScalar(1 + breath + (isHovered ? 0.6 : 0) + activePulse * 0.3)
    }
    if (glowRef.current) {
      glowRef.current.position.y = startPos.y + float
      const breath = Math.sin(t * 0.6 + floatOffset.current) * 0.15
      glowRef.current.scale.setScalar(1 + breath + (isHovered ? 1.2 : 0) + activePulse * 1.0)
      const mat = glowRef.current.material as MeshBasicMaterial
      const baseOpacity = isActive ? 0.35 : 0.15
      mat.opacity = isHovered ? 0.4 : baseOpacity + (pulseActive ? Math.sin(t * 3) * 0.15 : 0)
    }
  })

  const handlePointerOver = useCallback(() => {
    setHovered(true); hoveredRef.current = true; document.body.style.cursor = 'pointer'
  }, [])
  const handlePointerOut = useCallback(() => {
    setHovered(false); hoveredRef.current = false; document.body.style.cursor = 'default'
  }, [])
  const handleClick = useCallback((e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation()
    onCloseRadialMenu()
    const worldPos = new Vector3()
    e.object.getWorldPosition(worldPos)
    focusTargetRef.current = worldPos
    onSelect(node.label, worldPos)
  }, [node.label, onSelect, focusTargetRef, onCloseRadialMenu])
  const handleContextMenu = useCallback((e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation()
    e.nativeEvent.preventDefault()
    onContextMenu(node.label)
  }, [node.label, onContextMenu])

  useEffect(() => {
    return () => { document.body.style.cursor = 'default' }
  }, [])

  return (
    <group>
      {/* Invisible hit area */}
      <mesh
        position={node.position}
        onPointerOver={handlePointerOver}
        onPointerOut={handlePointerOut}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
      >
        <sphereGeometry args={[0.35, 8, 8]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>

      {/* Glow */}
      <mesh ref={glowRef} position={node.position}>
        <sphereGeometry args={[0.25, 16, 16]} />
        <meshBasicMaterial color={node.color} transparent opacity={0.15} depthWrite={false} />
      </mesh>

      {/* Node sphere */}
      <mesh ref={nodeRef} position={node.position}>
        <sphereGeometry args={[0.12, 16, 16]} />
        <meshBasicMaterial color={node.color} transparent opacity={0.9} depthWrite={false} />
      </mesh>

      {/* Connecting line */}
      <QuadraticBezierLine
        start={[0, 0, 0]} end={node.position} mid={[mid.x, mid.y, mid.z]}
        color={node.color} lineWidth={isActive ? 2.5 : hovered ? 2 : 1}
        transparent opacity={isActive ? 0.85 : hovered ? 0.7 : 0.3} dashed={false}
      />

      {/* Label */}
      <Html
        position={[node.position[0] + 0.5, node.position[1] + 0.1, node.position[2]]}
        center={false}
        style={{
          pointerEvents: 'none', userSelect: 'none',
          transition: 'opacity 0.3s, transform 0.3s',
          opacity: isActive ? 1 : hovered ? 1 : 0.85,
          transform: isActive || hovered ? 'translateX(2px)' : 'translateX(0)',
        }}
        zIndexRange={[1, 10]}
      >
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full flex-shrink-0"
            style={{
              backgroundColor: node.color,
              boxShadow: isActive ? `0 0 20px ${node.color}` : hovered ? `0 0 12px ${node.color}` : `0 0 6px ${node.color}`,
              transition: 'box-shadow 0.3s',
            }}
          />
          <div className="flex flex-col">
            <span className={`font-sans font-medium leading-tight tracking-wide ${isActive ? 'text-[14px]' : hovered ? 'text-[13px]' : 'text-[11px]'}`}
              style={{
                color: node.color,
                textShadow: isActive ? `0 0 24px ${node.color}` : hovered ? `0 0 16px ${node.color}80` : `0 0 8px ${node.color}40`,
                transition: 'text-shadow 0.3s, font-size 0.3s',
              }}
            >{node.label}</span>
            <span className={`font-sans leading-tight ${isActive ? 'text-white/70 text-[10px]' : hovered ? 'text-white/60 text-[9px]' : 'text-white/40 text-[8px]'}`}
              style={{ transition: 'color 0.3s, font-size 0.3s' }}
            >{node.description}</span>
          </div>
        </div>
      </Html>

      {/* ── Radial Quick-Action Menu (right-click) ───────────────── */}
      {isRadialOpen && (
        <Html
          position={[node.position[0], node.position[1] - 1.0, node.position[2]]}
          center
          zIndexRange={[10, 20]}
        >
          <div className="flex items-center gap-4">              {([Zap, FileText, Link] as const).map((Icon, i) => (
              <button
                key={['Zap', 'FileText', 'Link'][i]}
                className="w-7 h-7 flex items-center justify-center text-white/40 hover:bg-white/5 hover:text-cyan-300 rounded-full transition-all duration-200"
                title={['Quick Execute', 'View Details', 'Share Link'][i]}
                onClick={(e) => { e.stopPropagation(); onCloseRadialMenu(); onRadialAction(node.label, ['quick-execute', 'view-details', 'share-link'][i] as 'quick-execute' | 'view-details' | 'share-link') }}
              >
                <Icon className="w-3.5 h-3.5" />
              </button>
            ))}
          </div>
        </Html>
      )}
    </group>
  )
}

// ─── Node Constellation ────────────────────────────────────────────────

function NodeConstellation({
  onSelectAgent,
  focusTargetRef,
  activeAgent,
  onContextMenu,
  activeRadialMenu,
  onCloseRadialMenu,
  onRadialAction,
}: {
  onSelectAgent: (label: string) => void
  focusTargetRef: MutableRefObject<Vector3 | null>
  activeAgent: string | null
  onContextMenu: (label: string) => void
  activeRadialMenu: string | null
  onCloseRadialMenu: () => void
  onRadialAction: (label: string, action: 'quick-execute' | 'view-details' | 'share-link') => void
}): JSX.Element {
  const groupRef = useRef<Group>(null!)

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y = state.clock.elapsedTime * 0.1
    }
  })

  return (
    <group ref={groupRef}>
      {AGENT_NODES.map((node) => (
        <AgentNode
          key={node.id}
          node={node}
          onSelect={onSelectAgent}
          focusTargetRef={focusTargetRef}
          isActive={activeAgent === node.label}
          onContextMenu={onContextMenu}
          activeRadialMenu={activeRadialMenu}
          onCloseRadialMenu={onCloseRadialMenu}
          onRadialAction={onRadialAction}
        />
      ))}
    </group>
  )
}

// ─── Main Scene ────────────────────────────────────────────────────────

function AgentNetworkScene({
  activeAgent,
  onSelectAgent,
  focusTargetRef,
  systemLoad,
  activeTransfers,
  onContextMenu,
  activeRadialMenu,
  onCloseRadialMenu,
  onRadialAction,
  particleCount,
}: {
  activeAgent: string | null
  onSelectAgent: (label: string) => void
  focusTargetRef: MutableRefObject<Vector3 | null>
  systemLoad: number
  activeTransfers: TransferSparkData[]
  onContextMenu: (label: string) => void
  activeRadialMenu: string | null
  onCloseRadialMenu: () => void
  onRadialAction: (label: string, action: 'quick-execute' | 'view-details' | 'share-link') => void
  particleCount: number
}): JSX.Element {
  return (
    <>
      <CameraController focusTargetRef={focusTargetRef} activeAgent={activeAgent} />
      <ambientLight intensity={0.5} />
      <ParticleCore particleCount={particleCount} />
      <ResourceRing systemLoad={systemLoad} />
      <GoldRing />
      <NodeConstellation
        onSelectAgent={onSelectAgent}
        focusTargetRef={focusTargetRef}
        activeAgent={activeAgent}
        onContextMenu={onContextMenu}
        activeRadialMenu={activeRadialMenu}
        onCloseRadialMenu={onCloseRadialMenu}
        onRadialAction={onRadialAction}
      />
      {activeTransfers.map((spark) => (
        <TransferSpark key={spark.id} spark={spark} />
      ))}
    </>
  )
}

// ─── Main Export ────────────────────────────────────────────────────────

export function ParticleSphere3D({
  activeTheme: _activeTheme,
  aiState: _aiState,
  audioAmplitude: _audioAmplitude,
  showGrid: _showGrid,
  micMuted: _micMuted,
  sttText: _sttText,
  tokenBurst: _tokenBurst,
  activeAgent,
  onSelectAgent,
  focusTargetRef,
  onReturnToCore,
  systemLoad = 0,
  activeTransfers = [],
  onContextMenu,
  activeRadialMenu = null,
  onCloseRadialMenu,
  onRadialAction,
  quality = 'high',
}: {
  activeTheme?: string
  aiState?: AIState
  audioAmplitude?: number
  showGrid?: boolean
  micMuted?: boolean
  sttText?: string
  tokenBurst?: number
  activeAgent: string | null
  onSelectAgent: (label: string) => void
  focusTargetRef: MutableRefObject<Vector3 | null>
  onReturnToCore?: () => void
  systemLoad?: number
  activeTransfers?: TransferSparkData[]
  onContextMenu?: (label: string) => void
  activeRadialMenu?: string | null
  onCloseRadialMenu?: () => void
  onRadialAction?: (label: string, action: 'quick-execute' | 'view-details' | 'share-link') => void
  quality?: QualityLevel
}): JSX.Element {
  const particleCount = QUALITY_PRESETS[quality]?.particles ?? 20000
  return (
    <div className="w-full h-full">
      <CanvasErrorBoundary>
        <Canvas
          camera={{ position: [0, 0, 9], fov: 45 }}
          dpr={quality === 'ultra' ? [1, 2] : quality === 'high' ? [1, 1.5] : quality === 'medium' ? [0.9, 1.25] : quality === 'low' ? [0.75, 1] : [0.75, 1]}
          gl={{
            antialias: quality !== 'potato',
            alpha: true,
            powerPreference: 'high-performance',
            failIfMajorPerformanceCaveat: false,
          }}
          style={{ width: '100%', height: '100%', background: 'transparent' }}
          onPointerMissed={onReturnToCore}
        >
          <AgentNetworkScene
            activeAgent={activeAgent}
            onSelectAgent={onSelectAgent}
            focusTargetRef={focusTargetRef}
            systemLoad={systemLoad}
            activeTransfers={activeTransfers}
            onContextMenu={onContextMenu ?? (() => {})}
            activeRadialMenu={activeRadialMenu}
            onCloseRadialMenu={onCloseRadialMenu ?? (() => {})}
            onRadialAction={onRadialAction ?? (() => {})}
            particleCount={particleCount}
          />
        </Canvas>
      </CanvasErrorBoundary>
    </div>
  )
}

export type { AgentNodeData }
export { AGENT_NODES }
