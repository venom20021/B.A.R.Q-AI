import { useCallback, useRef } from 'react'

/**
 * Hook that provides functions to play synthesized notification sounds
 * using the Web Audio API. No audio files needed — tones are generated
 * programmatically with a sci-fi / BARQ-appropriate feel.
 */
export function useNotificationSound(): {
  playChime: () => void
  playUrgent: () => void
} {
  const audioCtxRef = useRef<AudioContext | null>(null)

  const getCtx = useCallback((): AudioContext => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new AudioContext()
    }
    // Resume if suspended (browsers require user gesture first)
    if (audioCtxRef.current.state === 'suspended') {
      void audioCtxRef.current.resume()
    }
    return audioCtxRef.current
  }, [])

  /** Soft, gentle chime for normal notifications — a clean sine tone with a subtle shimmer */
  const playChime = useCallback((): void => {
    try {
      const ctx = getCtx()
      const now = ctx.currentTime

      // Main tone — bright sine at ~1047Hz (C6)
      const osc = ctx.createOscillator()
      osc.type = 'sine'
      osc.frequency.setValueAtTime(1047, now)
      osc.frequency.exponentialRampToValueAtTime(880, now + 0.35)

      // Subtle shimmer — a quiet overtone at 2x frequency
      const shimmer = ctx.createOscillator()
      shimmer.type = 'sine'
      shimmer.frequency.setValueAtTime(2093, now)
      shimmer.frequency.exponentialRampToValueAtTime(1760, now + 0.3)

      // Gain envelope — quick attack, smooth fade
      const gain = ctx.createGain()
      gain.gain.setValueAtTime(0, now)
      gain.gain.linearRampToValueAtTime(0.08, now + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.45)

      // Shimmer is quieter
      const shimmerGain = ctx.createGain()
      shimmerGain.gain.setValueAtTime(0, now)
      shimmerGain.gain.linearRampToValueAtTime(0.03, now + 0.02)
      shimmerGain.gain.exponentialRampToValueAtTime(0.001, now + 0.35)

      osc.connect(gain)
      gain.connect(ctx.destination)
      shimmer.connect(shimmerGain)
      shimmerGain.connect(ctx.destination)

      osc.start(now)
      osc.stop(now + 0.5)
      shimmer.start(now + 0.01)
      shimmer.stop(now + 0.4)
    } catch {
      // Silently fail — audio is non-critical
    }
  }, [getCtx])

  /** Urgent tone for priority notifications — double pulse with a darker timbre */
  const playUrgent = useCallback((): void => {
    try {
      const ctx = getCtx()
      const now = ctx.currentTime

      // First pulse — lower, more intense
      const osc1 = ctx.createOscillator()
      osc1.type = 'square'
      osc1.frequency.setValueAtTime(440, now)
      osc1.frequency.exponentialRampToValueAtTime(660, now + 0.12)

      // Second pulse — rising slightly
      const osc2 = ctx.createOscillator()
      osc2.type = 'square'
      osc2.frequency.setValueAtTime(520, now + 0.15)
      osc2.frequency.exponentialRampToValueAtTime(780, now + 0.27)

      // Noise burst for texture
      const bufferSize = ctx.sampleRate * 0.1
      const noiseBuffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate)
      const data = noiseBuffer.getChannelData(0)
      for (let i = 0; i < bufferSize; i++) {
        data[i] = Math.random() * 2 - 1
      }
      const noise = ctx.createBufferSource()
      noise.buffer = noiseBuffer

      // Gain envelope
      const gain = ctx.createGain()
      gain.gain.setValueAtTime(0, now)
      gain.gain.linearRampToValueAtTime(0.1, now + 0.01)
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12)
      gain.gain.setValueAtTime(0, now + 0.13)
      gain.gain.linearRampToValueAtTime(0.1, now + 0.15)
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35)

      // Noise gain — subtle
      const noiseGain = ctx.createGain()
      noiseGain.gain.setValueAtTime(0.02, now)
      noiseGain.gain.exponentialRampToValueAtTime(0.001, now + 0.08)

      osc1.connect(gain)
      osc2.connect(gain)
      gain.connect(ctx.destination)
      noise.connect(noiseGain)
      noiseGain.connect(ctx.destination)

      osc1.start(now)
      osc1.stop(now + 0.14)
      osc2.start(now + 0.15)
      osc2.stop(now + 0.3)
      noise.start(now)
      noise.stop(now + 0.1)
    } catch {
      // Silently fail — audio is non-critical
    }
  }, [getCtx])

  return { playChime, playUrgent }
}
