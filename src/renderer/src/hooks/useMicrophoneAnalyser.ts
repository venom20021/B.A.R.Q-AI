import { useRef, useState, useCallback, useEffect } from 'react'

export interface MicrophoneAnalyser {
  /** Whether the microphone is currently active */
  isActive: boolean
  /** Error message if mic access was denied/failed */
  error: string | null
  /** Start capturing microphone audio */
  start: () => Promise<void>
  /** Stop capturing and release resources */
  stop: () => void
  /** Ref to the AnalyserNode — read `.current` in animation loop */
  analyserRef: React.RefObject<AnalyserNode | null>
  /** Ref to the pre-allocated Uint8Array — written each frame by the analyser */
  dataArrayRef: React.RefObject<Uint8Array | null>
}

export function useMicrophoneAnalyser(): MicrophoneAnalyser {
  const [isActive, setIsActive] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const streamRef = useRef<MediaStream | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const dataArrayRef = useRef<Uint8Array | null>(null)
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null)

  const start = useCallback(async () => {
    try {
      // Request mic access
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // Create AudioContext and analyser
      const audioCtx = new AudioContext()
      audioCtxRef.current = audioCtx

      const source = audioCtx.createMediaStreamSource(stream)
      sourceRef.current = source

      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 256 // 128 frequency bins for smooth 48-bar mapping
      analyser.smoothingTimeConstant = 0.8 // smooth transitions
      source.connect(analyser)
      analyserRef.current = analyser

      // Pre-allocate data array
      dataArrayRef.current = new Uint8Array(analyser.frequencyBinCount)

      setIsActive(true)
      setError(null)
    } catch (err) {
      const msg =
        err instanceof DOMException && err.name === 'NotAllowedError'
          ? 'Microphone access denied'
          : 'Microphone unavailable'
      setError(msg)
      setIsActive(false)
    }
  }, [])

  const stop = useCallback(() => {
    setIsActive(false)
    setError(null)

    // Stop all media tracks
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null

    // Close audio context
    audioCtxRef.current?.close()
    audioCtxRef.current = null

    sourceRef.current = null
    analyserRef.current = null
    dataArrayRef.current = null
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop())
      audioCtxRef.current?.close()
    }
  }, [])

  return {
    isActive,
    error,
    start,
    stop,
    analyserRef,
    dataArrayRef,
  }
}
