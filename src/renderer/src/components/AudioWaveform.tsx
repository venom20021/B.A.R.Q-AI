import { useEffect, useRef } from 'react'
import type { MicrophoneAnalyser } from '../hooks/useMicrophoneAnalyser'

interface AudioWaveformProps {
  isActive?: boolean
  analyser?: Pick<MicrophoneAnalyser, 'analyserRef' | 'dataArrayRef'>
}

export function AudioWaveform({ isActive = false, analyser }: AudioWaveformProps): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animRef = useRef<number>(0)
  const timeRef = useRef(0)
  const analyserRef = useRef(analyser)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    const w = 300
    const h = 80
    canvas.width = w * dpr
    canvas.height = h * dpr
    ctx.scale(dpr, dpr)

    const BAR_COUNT = 48
    const BIN_COUNT = 128 // fftSize=256 gives 128 bins
    const barWidth = (w - 40) / BAR_COUNT
    const barGap = 1.5

    // Pre-compute logarithmic bin mapping: map 128 bins -> 48 bars
    // Lower bars get fewer bins, higher bars get more (log scale)
    const binGroups: number[][] = Array.from({ length: BAR_COUNT }, () => [])
    for (let b = 0; b < BIN_COUNT; b++) {
      const normalizedB = b / BIN_COUNT // 0..1
      // Logarithmic mapping: barIndex = log2(1 + normalizedB * (2^BAR_COUNT - 1))
      const logIndex = Math.log2(1 + normalizedB * (Math.pow(2, BAR_COUNT) - 1))
      const barIndex = Math.min(Math.floor(logIndex), BAR_COUNT - 1)
      binGroups[barIndex].push(b)
    }

    // Smoothed amplitudes (0..1) per bar
    const amplitudes = new Float32Array(BAR_COUNT)
    const targets = new Float32Array(BAR_COUNT)

    const animate = (timestamp: number): void => {
      const dt = timestamp - timeRef.current
      timeRef.current = timestamp
      const delta = Math.min(dt, 33) / 16

      ctx.clearRect(0, 0, w, h)

      if (isActive && analyserRef.current?.analyserRef.current && analyserRef.current?.dataArrayRef.current) {
        // Read real frequency data from the microphone
        const micNode = analyserRef.current.analyserRef.current!
        const freqData = analyserRef.current.dataArrayRef.current!
        micNode.getByteFrequencyData(freqData as Uint8Array<ArrayBuffer>)

        // Map 128 bins to 48 bars using the pre-computed groups
        for (let i = 0; i < BAR_COUNT; i++) {
          const bins = binGroups[i]
          let sum = 0
          for (const binIdx of bins) {
            sum += freqData[binIdx]
          }
          const average = sum / bins.length
          // Normalize from 0..255 to 0..1 with a noise floor
          targets[i] = Math.max(0.02, average / 255)
        }
      } else if (isActive) {
        // Mic requested but not yet available — show gentle activity
        const t = timeRef.current * 0.002
        for (let i = 0; i < BAR_COUNT; i++) {
          targets[i] =
            0.05 + Math.sin(t + i * 0.3) * 0.03 + Math.sin(t * 0.7 + i * 0.15) * 0.02
        }
      } else {
        // Idle — subtle ambient movement
        const t = timeRef.current * 0.0005
        for (let i = 0; i < BAR_COUNT; i++) {
          targets[i] = 0.04 + Math.sin(t + i * 0.5) * 0.02 + Math.random() * 0.01
        }
      }

      // Smooth interpolation for natural feel
      const lerpFactor = isActive ? 0.2 : 0.06
      for (let i = 0; i < BAR_COUNT; i++) {
        amplitudes[i] += (targets[i] - amplitudes[i]) * lerpFactor * delta
      }

      // Draw bars
      const startX = 20
      const centerY = h / 2

      for (let i = 0; i < BAR_COUNT; i++) {
        const amp = amplitudes[i]
        const barH = amp * (h * 0.7)
        const x = startX + i * (barWidth + barGap)
        const y = centerY - barH / 2

        const intensity = 0.3 + amp * 0.7
        const r = Math.round(10 + (1 - intensity) * 20)
        const g = Math.round(180 + intensity * 75)
        const b = Math.round(200 + intensity * 55)

        // Rounded bar with glow
        ctx.beginPath()
        ctx.roundRect(x, y, barWidth, barH, [barWidth / 2, barWidth / 2, barWidth / 2, barWidth / 2])
        ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${0.5 + amp * 0.5})`
        ctx.fill()

        // Brighter core
        ctx.beginPath()
        ctx.roundRect(x + 0.5, y + barH * 0.15, Math.max(barWidth - 1, 1), barH * 0.7, [1, 1, 1, 1])
        ctx.fillStyle = `rgba(${Math.min(r + 40, 255)}, ${g}, ${b}, ${0.3 + amp * 0.6})`
        ctx.fill()
      }

      animRef.current = requestAnimationFrame(animate)
    }

    timeRef.current = performance.now()
    animRef.current = requestAnimationFrame(animate)

    return () => cancelAnimationFrame(animRef.current)
  }, [isActive])

  // Keep analyser ref in sync without triggering effect re-runs
  analyserRef.current = analyser

  return (
    <canvas
      ref={canvasRef}
      style={{ width: 300, height: 80 }}
      className="pointer-events-none"
    />
  )
}
