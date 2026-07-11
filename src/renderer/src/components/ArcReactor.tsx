import { useEffect, useRef, useState, memo } from 'react'

/* ─── Theme Colors ───────────────────────────────────────────────────── */

interface ReactorThemeColors {
  plasma: string
  plasmaRgb: string
  core: string
  ring: string
  ringDark: string
  arc: string
  arcRgb: string
  glow: string
  glowRgb: string
  segment: string
  segmentGlow: string
}

const THEMES: Record<string, ReactorThemeColors> = {
  cyan: {
    plasma: '#00E5FF',
    plasmaRgb: '0, 229, 255',
    core: '#FFFFFF',
    ring: '#0A2A3A',
    ringDark: '#051520',
    arc: '#00E5FF',
    arcRgb: '0, 229, 255',
    glow: '0, 229, 255',
    glowRgb: '0, 229, 255',
    segment: '#00B8D4',
    segmentGlow: '0, 184, 212',
  },
  gold: {
    plasma: '#FFD700',
    plasmaRgb: '255, 215, 0',
    core: '#FFE4B5',
    ring: '#2A1A00',
    ringDark: '#150D00',
    arc: '#FFD700',
    arcRgb: '255, 215, 0',
    glow: '255, 215, 0',
    glowRgb: '255, 215, 0',
    segment: '#FFA000',
    segmentGlow: '255, 160, 0',
  },
}

/* ─── Particle (floating energy motes) ───────────────────────────────── */

interface EnergyMote {
  x: number
  y: number
  baseX: number
  baseY: number
  size: number
  speed: number
  phase: number
  opacity: number
  driftX: number
  driftY: number
}

function generateMotes(w: number, h: number, count: number): EnergyMote[] {
  return Array.from({ length: count }, () => ({
    x: Math.random() * w,
    y: Math.random() * h,
    baseX: Math.random() * w,
    baseY: Math.random() * h,
    size: 0.3 + Math.random() * 1.2,
    speed: 0.05 + Math.random() * 0.2,
    phase: Math.random() * Math.PI * 2,
    opacity: 0.1 + Math.random() * 0.3,
    driftX: (Math.random() - 0.5) * 0.2,
    driftY: (Math.random() - 0.5) * 0.2,
  }))
}

/* ─── Electric Arc (jumping between segments) ────────────────────────── */

interface ElectricArc {
  fromAngle: number
  toAngle: number
  life: number
  maxLife: number
  intensity: number
  segments: { x: number; y: number }[]
}

function generateArcSegment(
  cx: number,
  cy: number,
  innerR: number,
  outerR: number,
  fromAngle: number,
  toAngle: number,
  _complexity: number,
): { x: number; y: number }[] {
  const pts: { x: number; y: number }[] = []
  const steps = 4 + Math.floor(Math.random() * 6)
  const midR = (innerR + outerR) / 2
  const spread = (outerR - innerR) * 0.6

  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    const angle = fromAngle + (toAngle - fromAngle) * t
    const rJitter = (Math.random() - 0.5) * spread
    const r = midR + rJitter
    pts.push({
      x: cx + Math.cos(angle) * r,
      y: cy + Math.sin(angle) * r,
    })
  }
  return pts
}

/* ─── Component ──────────────────────────────────────────────────────── */

interface ArcReactorProps {
  fullscreen?: boolean
  className?: string
  theme?: 'cyan' | 'gold'
  isSpeaking?: boolean
  micLevel?: number
}

export const ArcReactor = memo(function ArcReactor({
  fullscreen = false,
  className = '',
  theme = 'cyan',
  isSpeaking = false,
  micLevel = 0,
}: ArcReactorProps): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const animRef = useRef<number>(0)
  const timeRef = useRef(0)
  const rotationRef = useRef(0)
  const mouseRef = useRef({ x: -9999, y: -9999 })
  const hoverLabelRef = useRef('')
  const [tooltip, setTooltip] = useState<{ text: string; x: number; y: number } | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let w = 500
    let h = 500

    const resize = (): void => {
      if (fullscreen && container) {
        w = container.clientWidth
        h = container.clientHeight
      } else {
        w = 500
        h = 500
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

    const colors = THEMES[theme]

    // Background motes
    const motes = generateMotes(w, h, 40)

    // Foreground scatter particles (more visible, float across the screen)
    const scatterParticles: {
      x: number
      y: number
      vx: number
      vy: number
      size: number
      alpha: number
      life: number
      maxLife: number
      pulse: number
    }[] = Array.from({ length: 30 }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.5,
      vy: -0.1 - Math.random() * 0.3,
      size: 1 + Math.random() * 2.5,
      alpha: 0.2 + Math.random() * 0.5,
      life: 1,
      maxLife: 3 + Math.random() * 5,
      pulse: Math.random() * Math.PI * 2,
    }))

    // Reactor geometry (responsive to canvas size)
    const getReactorSize = (): number => Math.min(w, h) * 0.266
    const getCenterX = (): number => w / 2
    const getCenterY = (): number => h * 0.42

    // Animated arcs
    let electricArcs: ElectricArc[] = []
    let nextArcTime = 0.5 + Math.random() * 1.5

    const animate = (timestamp: number): void => {
      const dt = timestamp - timeRef.current
      timeRef.current = timestamp
      const delta = Math.min(dt, 33) / 16

      rotationRef.current += delta * 0.003

      const cx = getCenterX()
      const cy = getCenterY()
      const ringRadius = getReactorSize()
      const innerRadius = ringRadius * 0.35
      const coreRadius = ringRadius * 0.18
      const ringWidth = ringRadius - innerRadius
      const numSegments = 8
      const segmentAngle = (Math.PI * 2) / numSegments
      const gapAngle = segmentAngle * 0.08

      ctx.clearRect(0, 0, w, h)
      ctx.fillStyle = '#000000'
      ctx.fillRect(0, 0, w, h)

      // ── Draw background energy motes ──
      const time = timeRef.current * 0.0003
      motes.forEach((m) => {
        m.x = m.baseX + Math.sin(time * m.speed + m.phase) * 40 + m.driftX
        m.y = m.baseY + Math.cos(time * m.speed * 0.7 + m.phase * 1.3) * 30 + m.driftY

        ctx.beginPath()
        ctx.arc(m.x, m.y, m.size, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(${colors.plasmaRgb}, ${m.opacity * 0.3})`
        ctx.fill()
      })

      // ── Foreground scatter particles (drift upward, fade in/out) ──
      const mx = mouseRef.current.x
      const my = mouseRef.current.y
      const HOVER_DIST = 35
      let anyHovered = false
      let hoveredLabel = ''
      let hoveredX = 0
      let hoveredY = 0

      scatterParticles.forEach((p) => {
        p.x += p.vx * delta
        p.y += p.vy * delta
        p.life -= delta / (p.maxLife * 60)
        p.pulse += delta * 0.03

        if (p.life <= 0 || p.y < -10 || p.y > h + 10 || p.x < -10 || p.x > w + 10) {
          p.x = Math.random() * w
          p.y = h + 5 + Math.random() * 20
          p.vx = (Math.random() - 0.5) * 0.6
          p.vy = -(0.2 + Math.random() * 0.4)
          p.life = 1
          p.maxLife = 3 + Math.random() * 5
          p.alpha = 0.2 + Math.random() * 0.4
        }

        // ── Hover effect: closer = bigger glow ──
        const dx = p.x - mx
        const dy = p.y - my
        const dist = Math.sqrt(dx * dx + dy * dy)
        const hoverBoost = dist < HOVER_DIST ? 1 + (1 - dist / HOVER_DIST) * 3 : 1

        if (dist < HOVER_DIST && !anyHovered) {
          anyHovered = true
          hoveredLabel = 'Plasma Mote'
          hoveredX = p.x
          hoveredY = p.y - 12
        }

        const flicker = Math.sin(p.pulse) * 0.3 + 0.7
        const alpha = Math.min(p.alpha * p.life * flicker * hoverBoost, 1)
        const sizeBoost = p.size * (1 + (hoverBoost - 1) * 0.5)

        // Glow
        const glowRad = sizeBoost * 4 * hoverBoost
        const sGlow = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, glowRad)
        sGlow.addColorStop(0, `rgba(${colors.plasmaRgb}, ${alpha * Math.min(0.5 * hoverBoost, 1)})`)
        sGlow.addColorStop(0.5, `rgba(${colors.plasmaRgb}, ${alpha * 0.15 * hoverBoost})`)
        sGlow.addColorStop(1, `rgba(${colors.plasmaRgb}, 0)`)
        ctx.beginPath()
        ctx.arc(p.x, p.y, glowRad, 0, Math.PI * 2)
        ctx.fillStyle = sGlow
        ctx.fill()

        // Core dot
        ctx.beginPath()
        ctx.arc(p.x, p.y, sizeBoost, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(${colors.plasmaRgb}, ${alpha})`
        ctx.fill()

        // Extra bright ring when hovered
        if (dist < HOVER_DIST) {
          ctx.beginPath()
          ctx.arc(p.x, p.y, sizeBoost * 2, 0, Math.PI * 2)
          ctx.strokeStyle = `rgba(255, 255, 255, ${0.3 * (1 - dist / HOVER_DIST) * hoverBoost})`
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

      ctx.save()
      ctx.translate(cx, cy)
      ctx.rotate(rotationRef.current)

      // ── Draw the outer ring shadow (3D depth) ──
      ctx.beginPath()
      ctx.arc(2, 3, ringRadius + ringWidth * 0.15, 0, Math.PI * 2)
      ctx.fillStyle = 'rgba(0, 0, 0, 0.4)'
      ctx.fill()

      // ── Draw outer ring base ──
      ctx.beginPath()
      ctx.arc(0, 0, ringRadius + ringWidth * 0.1, 0, Math.PI * 2)
      const outerRingGrad = ctx.createRadialGradient(0, -ringRadius * 0.3, 0, 0, 0, ringRadius + ringWidth * 0.1)
      outerRingGrad.addColorStop(0, '#1A2A3A')
      outerRingGrad.addColorStop(0.5, colors.ring)
      outerRingGrad.addColorStop(1, colors.ringDark)
      ctx.fillStyle = outerRingGrad
      ctx.fill()

      // ── Draw the 8 segments with flowing arcs ──
      for (let i = 0; i < numSegments; i++) {
        const startAngle = i * segmentAngle + gapAngle / 2
        const endAngle = (i + 1) * segmentAngle - gapAngle / 2
        const midAngle = (startAngle + endAngle) / 2

        // Segment background (dark)
        ctx.beginPath()
        ctx.arc(0, 0, ringRadius, startAngle, endAngle)
        ctx.arc(0, 0, innerRadius, endAngle, startAngle, true)
        ctx.closePath()
        ctx.fillStyle = `rgba(10, 30, 50, 0.6)`
        ctx.fill()

        // Segment border glow
        ctx.beginPath()
        ctx.arc(0, 0, ringRadius, startAngle, endAngle)
        ctx.arc(0, 0, innerRadius, endAngle, startAngle, true)
        ctx.closePath()
        ctx.strokeStyle = `rgba(${colors.plasmaRgb}, 0.15)`
        ctx.lineWidth = 0.5
        ctx.stroke()

        // ── Flowing plasma arc inside each segment ──
        const arcPhase = (timestamp * 0.0008 + i * 0.8) % (Math.PI * 2)
        const arcIntensity = Math.sin(arcPhase) * 0.5 + 0.5

        // Multiple arc curves for each segment
        for (let a = 0; a < 3; a++) {
          const offset = a * 0.3
          const t = (i + offset) / numSegments + timestamp * 0.0004
          const r1 = innerRadius + (ringRadius - innerRadius) * (0.15 + (Math.sin(t * Math.PI * 2) * 0.5 + 0.5) * 0.7)
          const r2 = innerRadius + (ringRadius - innerRadius) * (0.85 - (Math.sin(t * Math.PI * 2 + 1.5) * 0.5 + 0.5) * 0.7)
          const spreadAngle = segmentAngle * 0.7

          const a1 = midAngle - spreadAngle / 2 + Math.sin(t * 3 + i) * 0.08
          const a2 = midAngle + spreadAngle / 2 + Math.cos(t * 2.5 + i * 1.3) * 0.08

          ctx.beginPath()
          for (let p = 0; p <= 20; p++) {
            const progress = p / 20
            const angle = a1 + (a2 - a1) * progress
            const r = r1 + (r2 - r1) * progress
            const x = Math.cos(angle) * r
            const y = Math.sin(angle) * r
            if (p === 0) ctx.moveTo(x, y)
            else ctx.lineTo(x, y)
          }

          const arcAlpha = (0.3 + arcIntensity * 0.5) * (1 - a * 0.2)
          ctx.strokeStyle = `rgba(${colors.plasmaRgb}, ${arcAlpha})`
          ctx.lineWidth = 2 - a * 0.5
          ctx.stroke()
        }

        // ── Inner glow at the segment's inner edge (flowing toward core) ──
        const innerFlow = Math.sin(timestamp * 0.001 + i * 1.2) * 0.5 + 0.5
        const flowRadius = innerRadius + (ringRadius - innerRadius) * innerFlow * 0.3
        const flowAngle = midAngle + Math.sin(timestamp * 0.0005 + i * 0.7) * 0.1

        ctx.beginPath()
        ctx.arc(
          Math.cos(flowAngle) * flowRadius,
          Math.sin(flowAngle) * flowRadius,
          2 + innerFlow * 2,
          0,
          Math.PI * 2,
        )
        ctx.fillStyle = `rgba(${colors.plasmaRgb}, ${0.3 + innerFlow * 0.5})`
        ctx.fill()
      }

      // ── Electric arcs jumping between segments ──
      // Manage arc spawning
      nextArcTime -= delta * 0.016
      if (nextArcTime <= 0) {
        const fromSeg = Math.floor(Math.random() * numSegments)
        let toSeg = fromSeg
        while (toSeg === fromSeg) toSeg = Math.floor(Math.random() * numSegments)

        const fromAngle = (fromSeg + 0.5) * segmentAngle
        const toAngle = (toSeg + 0.5) * segmentAngle

        electricArcs.push({
          fromAngle,
          toAngle,
          life: 1,
          maxLife: 0.3 + Math.random() * 0.5,
          intensity: 0.4 + Math.random() * 0.6,
          segments: generateArcSegment(0, 0, innerRadius, ringRadius, fromAngle, toAngle, 0.5 + Math.random() * 0.5),
        })
        nextArcTime = 0.3 + Math.random() * 1.2
      }

      // Draw and update arcs
      electricArcs = electricArcs.filter((arc) => {
        arc.life -= delta / (arc.maxLife * 60)
        if (arc.life <= 0) return false

        const alpha = arc.life * arc.intensity
        ctx.beginPath()
        ctx.moveTo(arc.segments[0].x, arc.segments[0].y)
        for (let i = 1; i < arc.segments.length; i++) {
          ctx.lineTo(arc.segments[i].x, arc.segments[i].y)
        }
        ctx.strokeStyle = `rgba(${colors.arcRgb}, ${alpha * 0.8})`
        ctx.lineWidth = 1.5 * arc.life
        ctx.stroke()

        // Arc glow
        ctx.beginPath()
        ctx.moveTo(arc.segments[0].x, arc.segments[0].y)
        for (let i = 1; i < arc.segments.length; i++) {
          ctx.lineTo(arc.segments[i].x, arc.segments[i].y)
        }
        ctx.strokeStyle = `rgba(${colors.arcRgb}, ${alpha * 0.3})`
        ctx.lineWidth = 4 * arc.life
        ctx.stroke()

        return true
      })

      // ── Inner ring glow (between segments and core) ──
      ctx.beginPath()
      ctx.arc(0, 0, innerRadius, 0, Math.PI * 2)
      const innerRingGrad = ctx.createRadialGradient(0, 0, innerRadius * 0.3, 0, 0, innerRadius)
      innerRingGrad.addColorStop(0, `rgba(${colors.plasmaRgb}, 0)`)
      innerRingGrad.addColorStop(0.7, `rgba(${colors.plasmaRgb}, 0.05)`)
      innerRingGrad.addColorStop(1, `rgba(${colors.plasmaRgb}, 0.15)`)
      ctx.fillStyle = innerRingGrad
      ctx.fill()

      // ── Core glow (large outer glow) ──
      const corePulse = Math.sin(timestamp * 0.0015) * 0.15 + 0.85
      const coreGlowRadius = coreRadius * 3.5 * corePulse
      const coreGlow = ctx.createRadialGradient(0, 0, 0, 0, 0, coreGlowRadius)
      coreGlow.addColorStop(0, `rgba(${colors.plasmaRgb}, ${0.3 * corePulse})`)
      coreGlow.addColorStop(0.2, `rgba(${colors.plasmaRgb}, ${0.15 * corePulse})`)
      coreGlow.addColorStop(0.5, `rgba(${colors.plasmaRgb}, ${0.05 * corePulse})`)
      coreGlow.addColorStop(1, `rgba(${colors.plasmaRgb}, 0)`)
      ctx.beginPath()
      ctx.arc(0, 0, coreGlowRadius, 0, Math.PI * 2)
      ctx.fillStyle = coreGlow
      ctx.fill()

      // ── Core (bright center) ──
      const coreBrightness = 0.7 + Math.sin(timestamp * 0.002) * 0.3
      ctx.beginPath()
      ctx.arc(0, 0, coreRadius, 0, Math.PI * 2)
      const coreGrad = ctx.createRadialGradient(0, 0, 0, 0, 0, coreRadius)
      coreGrad.addColorStop(0, colors.core)
      coreGrad.addColorStop(0.3, `rgba(${colors.plasmaRgb}, ${0.9 * coreBrightness})`)
      coreGrad.addColorStop(0.7, `rgba(${colors.plasmaRgb}, ${0.5 * coreBrightness})`)
      coreGrad.addColorStop(1, `rgba(${colors.plasmaRgb}, 0.2)`)
      ctx.fillStyle = coreGrad
      ctx.fill()

      // ── Core inner bright spot ──
      ctx.beginPath()
      ctx.arc(0, 0, coreRadius * 0.3, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(255, 255, 255, ${0.6 * coreBrightness})`
      ctx.fill()

      ctx.restore()

      // ── Outer glow around the entire reactor ──
      const outerGlowRadius = ringRadius + ringWidth * 0.5
      const outerGlow2 = ctx.createRadialGradient(cx, cy, ringRadius * 0.5, cx, cy, outerGlowRadius)
      outerGlow2.addColorStop(0, `rgba(${colors.plasmaRgb}, ${0.06 * corePulse})`)
      outerGlow2.addColorStop(0.7, `rgba(${colors.plasmaRgb}, ${0.02 * corePulse})`)
      outerGlow2.addColorStop(1, `rgba(${colors.plasmaRgb}, 0)`)
      ctx.beginPath()
      ctx.arc(cx, cy, outerGlowRadius, 0, Math.PI * 2)
      ctx.fillStyle = outerGlow2
      ctx.fill()

      // ── Voice-reactive waveform between reactor and subtitle ──
      const waveformY = cy + ringRadius + ringWidth * 0.5 + 8
      const waveformW = ringRadius * 1.2
      const waveformH = 14
      const waveformStartX = cx - waveformW / 2

      // Generate waveform bars that react to speaking
      const waveformBars = 32
      const barW = waveformW / waveformBars - 1
      const barGap = 1

      ctx.save()
      for (let i = 0; i < waveformBars; i++) {
        let barH: number
        if (isSpeaking) {
          // Active speaking — reactive waveform based on micLevel + sin for variety
          const t = timestamp * 0.005 + i * 0.4
          const react = micLevel * 0.8 + Math.sin(t) * 0.2 + Math.sin(t * 2.3 + i * 0.7) * 0.15
          barH = Math.max(1, react * waveformH)
        } else {
          // Idle — gentle ambient pulse
          const t = timestamp * 0.0008 + i * 0.3
          barH = Math.max(1, (Math.sin(t) * 0.3 + 0.5) * 3)
        }

        const x = waveformStartX + i * (barW + barGap)
        const y = waveformY + (waveformH - barH) / 2
        const alpha = 0.4 + (barH / waveformH) * 0.6

        ctx.beginPath()
        ctx.roundRect(x, y, barW, barH, [barW / 2, barW / 2, barW / 2, barW / 2])
        ctx.fillStyle = `rgba(${colors.plasmaRgb}, ${alpha})`
        ctx.fill()

        // Bright core line for active speaking
        if (isSpeaking && barH > 3) {
          ctx.beginPath()
          ctx.roundRect(x + 0.3, y + 1, Math.max(barW - 0.6, 1), barH - 2, [1, 1, 1, 1])
          ctx.fillStyle = `rgba(${colors.plasmaRgb}, ${alpha * 0.7})`
          ctx.fill()
        }
      }
      ctx.restore()

      // ── Subtitle between reactor and BARQ text ──
      const textY = cy + ringRadius + ringWidth * 0.5 + 30
      const textGlowPulse = Math.sin(timestamp * 0.001) * 0.3 + 0.7

      ctx.save()
      ctx.font = `${Math.round(ringRadius * 0.08)}px "Share Tech Mono", monospace`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      ctx.fillStyle = `rgba(${colors.plasmaRgb}, ${0.4 * textGlowPulse})`
      ctx.fillText('ARC REACTOR · ONLINE', cx, textY)
      ctx.restore()

      // ── BARQ Text below reactor ──
      const barqY = textY + Math.round(ringRadius * 0.2)
      ctx.save()
      ctx.shadowColor = `rgba(${colors.plasmaRgb}, ${0.6 * textGlowPulse})`
      ctx.shadowBlur = 30 + Math.sin(timestamp * 0.0015) * 10
      ctx.font = `bold ${Math.round(ringRadius * 0.45)}px "Orbitron", sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      ctx.fillStyle = colors.core
      ctx.fillText('BARQ', cx, barqY)
      ctx.shadowBlur = 0

      ctx.font = `bold ${Math.round(ringRadius * 0.45)}px "Orbitron", sans-serif`
      ctx.fillStyle = `rgba(${colors.plasmaRgb}, ${0.4 * textGlowPulse})`
      ctx.fillText('BARQ', cx, barqY)
      ctx.restore()

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
  }, [fullscreen, theme, isSpeaking, micLevel])

  const tooltipColors = THEMES[theme]
  const tooltipRgb = tooltipColors?.plasmaRgb ?? '0, 229, 255'
  const tooltipHex = tooltipColors?.plasma ?? '#00E5FF'

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
            background: `rgba(${tooltipRgb}, 0.12)`,
            border: `1px solid rgba(${tooltipRgb}, 0.25)`,
            boxShadow: `0 0 12px rgba(${tooltipRgb}, 0.15)`,
            backdropFilter: 'blur(4px)',
            transform: 'translate(-50%, -100%)',
          }}
        >
          <span style={{ color: tooltipHex }}>✦</span> {tooltip.text}
        </div>
      )}
    </div>
  )
})
