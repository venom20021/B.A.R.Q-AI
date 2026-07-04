import { useEffect, useRef, useState } from 'react'

/* ─── Wolf Head Geometry ─────────────────────────────────────────────── */

// Key points defining the wolf head silhouette (normalized 0..1 coordinates)
// Origin is center of the head, facing forward
interface Point {
  x: number
  y: number
}

// Ear tips, snout, cheek lines, jaw, eye positions, etc.
const WOLF_HEAD: Point[] = [
  // Left ear outer
  { x: -0.32, y: -0.9 },
  { x: -0.22, y: -0.55 },
  // Left ear inner
  { x: -0.18, y: -0.6 },
  { x: -0.24, y: -0.85 },
  // Left brow ridge
  { x: -0.35, y: -0.5 },
  { x: -0.2, y: -0.45 },
  { x: -0.05, y: -0.4 },
  // Snout left
  { x: -0.15, y: -0.3 },
  { x: -0.08, y: -0.15 },
  { x: 0, y: -0.08 },
  // Snout right
  { x: 0.08, y: -0.15 },
  { x: 0.15, y: -0.3 },
  // Right brow ridge
  { x: 0.05, y: -0.4 },
  { x: 0.2, y: -0.45 },
  { x: 0.35, y: -0.5 },
  // Right ear inner
  { x: 0.24, y: -0.85 },
  { x: 0.18, y: -0.6 },
  // Right ear outer
  { x: 0.22, y: -0.55 },
  { x: 0.32, y: -0.9 },
]

// Seam lines — glowing cybernetic paths across the face
interface SeamLine {
  points: number[] // indices into WOLF_HEAD or extra points
  extraPoints?: Point[]
}

const SEAM_LINES: SeamLine[] = [
  // Forehead center seam
  { points: [0, 1, 4, 6, 7, 8, 9, 10, 11, 13, 15, 16, 17] },
  // Left cheek seam
  { points: [0, 4, 0] },
  // Right cheek seam
  { points: [17, 13, 17] },
  // Eye socket left
  { points: [3, 5], extraPoints: [{ x: -0.28, y: -0.38 }] },
  // Eye socket right
  { points: [14, 16], extraPoints: [{ x: 0.28, y: -0.38 }] },
  // Jaw line
  { points: [4, 7, 8, 9, 10, 11, 13] },
  // Snout center
  { points: [8, 9, 10] },
]

/* ─── Theme Colors ────────────────────────────────────────────────────── */

interface WolfTheme {
  outline: string
  seam: string
  seamGlow: string
  eyeOuter: string
  eyePupil: string
  eyeGlow: string
}

const THEMES: Record<string, WolfTheme> = {
  cyan: {
    outline: '#00E5FF',
    seam: '#00E5FF',
    seamGlow: '0, 229, 255',
    eyeOuter: '#00E5FF',
    eyePupil: '#FFFFFF',
    eyeGlow: '0, 229, 255',
  },
  gold: {
    outline: '#FFD700',
    seam: '#FFD700',
    seamGlow: '255, 215, 0',
    eyeOuter: '#FFD700',
    eyePupil: '#FFE4B5',
    eyeGlow: '255, 215, 0',
  },
}

/* ─── Component ────────────────────────────────────────────────────────── */

interface GuardianWolfProps {
  fullscreen?: boolean
  className?: string
  theme?: 'cyan' | 'gold'
  size?: number
}

export function GuardianWolf({
  fullscreen = false,
  className = '',
  theme = 'cyan',
  size = 300,
}: GuardianWolfProps): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const animRef = useRef<number>(0)
  const timeRef = useRef(0)
  const mouseRef = useRef({ x: -9999, y: -9999 })
  const hoverLabelRef = useRef('')
  const [tooltip, setTooltip] = useState<{ text: string; x: number; y: number } | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let w = size
    let h = size

    const resize = (): void => {
      if (fullscreen && container) {
        w = container.clientWidth
        h = container.clientHeight
      } else {
        w = size
        h = size
      }
      const dpr = window.devicePixelRatio || 1
      canvas.width = w * dpr
      canvas.height = h * dpr
      canvas.style.width = `${w}px`
      canvas.style.height = `${h}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    resize()

    // ── Mouse tracking for particle hover effects ──
    const handleMouseMove = (e: MouseEvent): void => {
      const rect = canvas.getBoundingClientRect()
      mouseRef.current = {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      }
    }
    const handleMouseLeave = (): void => {
      mouseRef.current = { x: -9999, y: -9999 }
      hoverLabelRef.current = ''
      setTooltip(null)
    }
    canvas.addEventListener('mousemove', handleMouseMove)
    canvas.addEventListener('mouseleave', handleMouseLeave)

    let resizeObserver: ResizeObserver | null = null
    if (fullscreen && container) {
      resizeObserver = new ResizeObserver(() => resize())
      resizeObserver.observe(container)
    }

    const colors = THEMES[theme] ?? THEMES.cyan
    const cx = w / 2
    const cy = h / 2
    const scale = Math.min(w, h) * 0.35

    // Transform wolf point from normalized to canvas coordinates
    const transform = (p: Point): { x: number; y: number } => ({
      x: cx + p.x * scale,
      y: cy + p.y * scale,
    })

    // Scatter particles (float around the wolf)
    const wolfParticles: {
      x: number
      y: number
      vx: number
      vy: number
      size: number
      alpha: number
      life: number
      maxLife: number
      pulse: number
    }[] = Array.from({ length: 25 }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.4,
      vy: -0.1 - Math.random() * 0.2,
      size: 0.8 + Math.random() * 2,
      alpha: 0.15 + Math.random() * 0.35,
      life: 1,
      maxLife: 4 + Math.random() * 6,
      pulse: Math.random() * Math.PI * 2,
    }))

    const animate = (timestamp: number): void => {
      const dt = timestamp - timeRef.current
      timeRef.current = timestamp
      const delta = Math.min(dt, 33) / 16

      ctx.clearRect(0, 0, w, h)

      // ── Pure black background ──
      ctx.fillStyle = '#000000'
      ctx.fillRect(0, 0, w, h)

      // ── Breathing/pulsing animation ──
      const breath = Math.sin(timestamp * 0.001) * 0.015 + 1
      const pulsePhase = Math.sin(timestamp * 0.002) * 0.5 + 0.5

      ctx.save()
      ctx.translate(cx, cy)
      ctx.scale(breath, breath)
      ctx.translate(-cx, -cy)

      // ── Draw seam lines (cybernetic glow paths) ──
      SEAM_LINES.forEach((seam, idx) => {
        const seamPulse = Math.sin(timestamp * 0.0015 + idx * 0.8) * 0.3 + 0.7

        ctx.beginPath()
        const pts = seam.points.map((i) => transform(WOLF_HEAD[i]))
        const extra = seam.extraPoints?.map((p) => transform(p)) ?? []

        ctx.moveTo(pts[0].x, pts[0].y)
        for (let i = 1; i < pts.length; i++) {
          ctx.lineTo(pts[i].x, pts[i].y)
        }
        for (const ep of extra) {
          ctx.lineTo(ep.x, ep.y)
        }

        // Outer glow
        ctx.strokeStyle = `rgba(${colors.seamGlow}, ${0.08 * seamPulse})`
        ctx.lineWidth = 4
        ctx.stroke()

        // Main seam line
        ctx.beginPath()
        ctx.moveTo(pts[0].x, pts[0].y)
        for (let i = 1; i < pts.length; i++) {
          ctx.lineTo(pts[i].x, pts[i].y)
        }
        for (const ep of extra) {
          ctx.lineTo(ep.x, ep.y)
        }
        ctx.strokeStyle = `rgba(${colors.seamGlow}, ${0.3 * seamPulse})`
        ctx.lineWidth = 1.5
        ctx.stroke()

        // Bright core
        ctx.beginPath()
        ctx.moveTo(pts[0].x, pts[0].y)
        for (let i = 1; i < pts.length; i++) {
          ctx.lineTo(pts[i].x, pts[i].y)
        }
        for (const ep of extra) {
          ctx.lineTo(ep.x, ep.y)
        }
        ctx.strokeStyle = `rgba(${colors.seamGlow}, ${0.6 * seamPulse})`
        ctx.lineWidth = 0.5
        ctx.stroke()
      })

      // ── Draw head outline (angular geometric silhouette) ──
      ctx.beginPath()
      const headPts = WOLF_HEAD.map((p) => transform(p))
      ctx.moveTo(headPts[0].x, headPts[0].y)
      // Connect in order: left ear outer → left ear inner → left brow → snout → right brow → right ear inner → right ear outer
      const outlineOrder = [0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 15, 17, 18]
      for (const idx of outlineOrder) {
        ctx.lineTo(headPts[idx].x, headPts[idx].y)
      }
      ctx.closePath()

      // Glow behind outline
      ctx.strokeStyle = `rgba(${colors.seamGlow}, 0.1)`
      ctx.lineWidth = 6
      ctx.stroke()

      // Main outline
      ctx.strokeStyle = `rgba(${colors.seamGlow}, 0.25)`
      ctx.lineWidth = 1.5
      ctx.stroke()

      // ── Eyes ──
      const eyeLeft = { x: cx - 0.22 * scale, y: cy - 0.35 * scale }
      const eyeRight = { x: cx + 0.22 * scale, y: cy - 0.35 * scale }
      const eyeGlowSize = 8 + pulsePhase * 6

      // Left eye glow
      const lGlow = ctx.createRadialGradient(eyeLeft.x, eyeLeft.y, 0, eyeLeft.x, eyeLeft.y, eyeGlowSize)
      lGlow.addColorStop(0, `rgba(${colors.eyeGlow}, ${0.3 + pulsePhase * 0.3})`)
      lGlow.addColorStop(0.5, `rgba(${colors.eyeGlow}, ${0.1 * pulsePhase})`)
      lGlow.addColorStop(1, `rgba(${colors.eyeGlow}, 0)`)
      ctx.beginPath()
      ctx.arc(eyeLeft.x, eyeLeft.y, eyeGlowSize, 0, Math.PI * 2)
      ctx.fillStyle = lGlow
      ctx.fill()

      // Right eye glow
      const rGlow = ctx.createRadialGradient(eyeRight.x, eyeRight.y, 0, eyeRight.x, eyeRight.y, eyeGlowSize)
      rGlow.addColorStop(0, `rgba(${colors.eyeGlow}, ${0.3 + pulsePhase * 0.3})`)
      rGlow.addColorStop(0.5, `rgba(${colors.eyeGlow}, ${0.1 * pulsePhase})`)
      rGlow.addColorStop(1, `rgba(${colors.eyeGlow}, 0)`)
      ctx.beginPath()
      ctx.arc(eyeRight.x, eyeRight.y, eyeGlowSize, 0, Math.PI * 2)
      ctx.fillStyle = rGlow
      ctx.fill()

      // Left eye pupil (sharp, angular)
      ctx.beginPath()
      const eyeSize = 2.5 + pulsePhase * 1.5
      // Diamond-shaped pupil
      ctx.moveTo(eyeLeft.x, eyeLeft.y - eyeSize)
      ctx.lineTo(eyeLeft.x + eyeSize * 0.7, eyeLeft.y)
      ctx.lineTo(eyeLeft.x, eyeLeft.y + eyeSize)
      ctx.lineTo(eyeLeft.x - eyeSize * 0.7, eyeLeft.y)
      ctx.closePath()
      ctx.fillStyle = colors.eyePupil
      ctx.fill()

      // Right eye pupil
      ctx.beginPath()
      ctx.moveTo(eyeRight.x, eyeRight.y - eyeSize)
      ctx.lineTo(eyeRight.x + eyeSize * 0.7, eyeRight.y)
      ctx.lineTo(eyeRight.x, eyeRight.y + eyeSize)
      ctx.lineTo(eyeRight.x - eyeSize * 0.7, eyeRight.y)
      ctx.closePath()
      ctx.fillStyle = colors.eyePupil
      ctx.fill()

      // Inner eye dot (bright center)
      ctx.beginPath()
      ctx.arc(eyeLeft.x, eyeLeft.y, eyeSize * 0.3, 0, Math.PI * 2)
      ctx.fillStyle = '#FFFFFF'
      ctx.fill()

      ctx.beginPath()
      ctx.arc(eyeRight.x, eyeRight.y, eyeSize * 0.3, 0, Math.PI * 2)
      ctx.fillStyle = '#FFFFFF'
      ctx.fill()

      ctx.restore()

      // ── Scatter particles around the wolf ──
      const mx = mouseRef.current.x
      const my = mouseRef.current.y
      const HOVER_DIST = 35
      let anyHovered = false
      let hoveredLabel = ''
      let hoveredX = 0
      let hoveredY = 0

      wolfParticles.forEach((p) => {
        p.x += p.vx * delta
        p.y += p.vy * delta
        p.life -= delta / (p.maxLife * 60)
        p.pulse += delta * 0.04

        if (p.life <= 0 || p.y < -10 || p.y > h + 10 || p.x < -10 || p.x > w + 10) {
          p.x = Math.random() * w
          p.y = h + 5 + Math.random() * 30
          p.vx = (Math.random() - 0.5) * 0.5
          p.vy = -(0.15 + Math.random() * 0.35)
          p.life = 1
          p.maxLife = 4 + Math.random() * 6
          p.alpha = 0.15 + Math.random() * 0.35
        }

        // ── Hover effect ──
        const dx = p.x - mx
        const dy = p.y - my
        const dist = Math.sqrt(dx * dx + dy * dy)
        const hoverBoost = dist < HOVER_DIST ? 1 + (1 - dist / HOVER_DIST) * 3 : 1

        if (dist < HOVER_DIST && !anyHovered) {
          anyHovered = true
          hoveredLabel = 'Digital Ember'
          hoveredX = p.x
          hoveredY = p.y - 12
        }

        const flicker = Math.sin(p.pulse) * 0.3 + 0.7
        const alpha = Math.min(p.alpha * p.life * flicker * hoverBoost, 1)
        const sizeBoost = p.size * (1 + (hoverBoost - 1) * 0.5)

        // Glow
        const glowRad = sizeBoost * 3 * hoverBoost
        const sGlow = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, glowRad)
        sGlow.addColorStop(0, `rgba(${colors.seamGlow}, ${alpha * Math.min(0.4 * hoverBoost, 1)})`)
        sGlow.addColorStop(0.5, `rgba(${colors.seamGlow}, ${alpha * 0.1 * hoverBoost})`)
        sGlow.addColorStop(1, `rgba(${colors.seamGlow}, 0)`)
        ctx.beginPath()
        ctx.arc(p.x, p.y, glowRad, 0, Math.PI * 2)
        ctx.fillStyle = sGlow
        ctx.fill()

        // Core dot
        ctx.beginPath()
        ctx.arc(p.x, p.y, sizeBoost, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(${colors.seamGlow}, ${alpha * 0.8})`
        ctx.fill()

        // Extra bright ring when hovered
        if (dist < HOVER_DIST) {
          ctx.beginPath()
          ctx.arc(p.x, p.y, sizeBoost * 2, 0, Math.PI * 2)
          ctx.strokeStyle = `rgba(255, 255, 255, ${0.25 * (1 - dist / HOVER_DIST) * hoverBoost})`
          ctx.lineWidth = 1
          ctx.stroke()
        }
      })

      if (anyHovered && hoverLabelRef.current !== hoveredLabel) {
        hoverLabelRef.current = hoveredLabel
        setTooltip({ text: hoveredLabel, x: hoveredX, y: hoveredY })
      } else if (!anyHovered && hoverLabelRef.current !== '') {
        hoverLabelRef.current = ''
        setTooltip(null)
      }

      animRef.current = requestAnimationFrame(animate)
    }

    timeRef.current = performance.now()
    animRef.current = requestAnimationFrame(animate)

    return () => {
      cancelAnimationFrame(animRef.current)
      canvas.removeEventListener('mousemove', handleMouseMove)
      canvas.removeEventListener('mouseleave', handleMouseLeave)
      if (resizeObserver) resizeObserver.disconnect()
    }
  }, [fullscreen, size, theme])

  const wolfTooltipColors = THEMES[theme]
  const wolfTooltipRgb = wolfTooltipColors?.seamGlow ?? '0, 229, 255'
  const wolfTooltipHex = wolfTooltipColors?.seam ?? '#00E5FF'

  return (
    <div ref={containerRef} className={fullscreen ? 'w-full h-full relative' : 'relative'}>
      <canvas ref={canvasRef} className={className} />
      {/* Particle tooltip overlay */}
      {tooltip && (
        <div
          className="absolute pointer-events-none z-10 px-2 py-1 rounded text-[8px] font-share-tech tracking-wider uppercase whitespace-nowrap"
          style={{
            left: tooltip.x,
            top: tooltip.y,
            color: '#FFFFFF',
            background: `rgba(${wolfTooltipRgb}, 0.12)`,
            border: `1px solid rgba(${wolfTooltipRgb}, 0.25)`,
            boxShadow: `0 0 12px rgba(${wolfTooltipRgb}, 0.15)`,
            backdropFilter: 'blur(4px)',
            transform: 'translate(-50%, -100%)',
          }}
        >
          <span style={{ color: wolfTooltipHex }}>✦</span> {tooltip.text}
        </div>
      )}
    </div>
  )
}
