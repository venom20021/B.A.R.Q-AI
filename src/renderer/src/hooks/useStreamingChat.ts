import { useState, useRef, useCallback, useEffect } from 'react'

interface StreamingChatOptions {
  onToken?: (token: string) => void
  onAudio?: (audioBase64: string) => void
  onComplete?: (fullText: string) => void
  onError?: (error: string) => void
}

interface StreamingChatResult {
  send: (message: string) => void
  cancel: () => void
  isStreaming: boolean
  fullText: string
}

/**
 * Hook to send a chat message and receive a streaming SSE response.
 *
 * Uses the IPC bridge (main process HTTP) instead of direct fetch()
 * to avoid CORS issues in cloud/remote mode.
 *
 * The flow:
 *   renderer → IPC invoke → main process fetch (Node.js) → backend SSE
 *   backend SSE → main process parse → IPC send event → renderer callback
 */
export function useStreamingChat(options: StreamingChatOptions = {}): StreamingChatResult {
  const [isStreaming, setIsStreaming] = useState(false)
  const [fullText, setFullText] = useState('')
  const streamIdRef = useRef<string | null>(null)
  const removeListenerRef = useRef<(() => void) | null>(null)
  const accumulatedRef = useRef('')

  // ── Clean up event listener ───────────────────────────────
  const cleanupListener = useCallback(() => {
    if (removeListenerRef.current) {
      removeListenerRef.current()
      removeListenerRef.current = null
    }
  }, [])

  // ── Clean up on unmount ───────────────────────────────────
  useEffect(() => {
    return () => {
      if (streamIdRef.current && window.barq?.voice?.chatStreamCancel) {
        window.barq.voice.chatStreamCancel(streamIdRef.current)
      }
      cleanupListener()
    }
  }, [cleanupListener])

  // ── Send message ──────────────────────────────────────────
  const send = useCallback(async (message: string): Promise<void> => {
    // Cancel any previous stream first
    if (streamIdRef.current && window.barq?.voice?.chatStreamCancel) {
      window.barq.voice.chatStreamCancel(streamIdRef.current)
    }
    streamIdRef.current = null
    cleanupListener()

    setIsStreaming(true)
    setFullText('')
    accumulatedRef.current = ''

    // Listen for streaming events from the main process
    const removeListener = window.barq?.voice?.onStreamEvent?.((event) => {
      if (!event || !event.streamId) return

      // Ignore events from other streams
      if (event.streamId !== streamIdRef.current) return

      switch (event.type) {
        case 'token': {
          accumulatedRef.current += event.text || ''
          setFullText(accumulatedRef.current)
          options.onToken?.(event.text || '')
          break
        }
        case 'audio':
          options.onAudio?.(event.audio_base64 || '')
          break
        case 'done':
          setIsStreaming(false)
          options.onComplete?.(accumulatedRef.current)
          cleanupListener()
          break
        case 'error':
          setIsStreaming(false)
          options.onError?.(event.message || 'Stream error')
          cleanupListener()
          break
      }
    })

    removeListenerRef.current = removeListener ?? null

    // Start the stream via IPC bridge (main process handles the HTTP request)
    try {
      const result = await window.barq?.voice?.chatStreamStart?.(message)
      if (result && result.data?.streamId) {
        streamIdRef.current = result.data.streamId
      } else {
        throw new Error('Failed to start stream')
      }
    } catch (err) {
      setIsStreaming(false)
      const msg = (err as Error).message || 'Failed to start stream'
      options.onError?.(msg)
      cleanupListener()
    }
  }, [options, cleanupListener])

  // ── Cancel streaming ─────────────────────────────────────
  const cancel = useCallback(() => {
    if (streamIdRef.current && window.barq?.voice?.chatStreamCancel) {
      window.barq.voice.chatStreamCancel(streamIdRef.current)
    }
    streamIdRef.current = null
    setIsStreaming(false)
    cleanupListener()
  }, [cleanupListener])

  return { send, cancel, isStreaming, fullText }
}
