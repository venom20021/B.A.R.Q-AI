import { useState, useRef, useCallback } from 'react'

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
 * Hook to send a chat message and receive a streaming SSE response from the backend.
 * Each token is received individually through the onToken callback,
 * allowing real-time display and TTS playback.
 */
export function useStreamingChat(options: StreamingChatOptions = {}): StreamingChatResult {
  const [isStreaming, setIsStreaming] = useState(false)
  const [fullText, setFullText] = useState('')
  const abortRef = useRef<AbortController | null>(null)

  const send = useCallback(async (message: string): Promise<void> => {
    // Cancel any previous stream
    if (abortRef.current) abortRef.current.abort()

    const controller = new AbortController()
    abortRef.current = controller
    setIsStreaming(true)
    setFullText('')

    try {
      const baseUrl = 'http://127.0.0.1:8956'
      const response = await fetch(`${baseUrl}/voice/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message, language: 'en' }),
        signal: controller.signal,
      })

      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let accumulatedText = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Parse SSE events from buffer
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') {
              // Stream complete
              break
            }
            try {
              const parsed = JSON.parse(data)
              if (parsed.type === 'token') {
                const token = parsed.text || ''
                accumulatedText += token
                setFullText(accumulatedText)
                options.onToken?.(token)
              } else if (parsed.type === 'audio') {
                options.onAudio?.(parsed.audio_base64 || '')
              } else if (parsed.type === 'error') {
                options.onError?.(parsed.message || 'Stream error')
              }
            } catch {
              // Skip malformed JSON
            }
          }
        }
      }

      setFullText(accumulatedText)
      options.onComplete?.(accumulatedText)
    } catch (err) {
      if ((err as Error).name === 'AbortError') return
      const msg = (err as Error).message || 'Stream error'
      options.onError?.(msg)
    } finally {
      setIsStreaming(false)
      abortRef.current = null
    }
  }, [options])

  const cancel = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
    setIsStreaming(false)
  }, [])

  return { send, cancel, isStreaming, fullText }
}
