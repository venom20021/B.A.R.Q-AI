import { useState, useEffect, useRef, useCallback, startTransition } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { User, Bot } from 'lucide-react'

interface LiveCaptionsProps {
  /** Live STT text from the voice pipeline (interim and final) */
  sttText: string
  /** Accumulated AI response text being streamed token-by-token */
  responseText: string
  /** Whether the AI is currently speaking (playing TTS) */
  isSpeaking: boolean
  /** Whether the AI is processing/thinking */
  isProcessing: boolean
  /** Whether conversation mode is active */
  conversationActive: boolean
}

// Note: `isListening` prop is accepted by callers but unused internally (kept for API consistency)

/**
 * LiveCaptions — a sleek glassmorphic overlay floating at the bottom-center
 * of the screen, above the microphone pill indicator.
 *
 * Displays two lines:
 * 1. User's spoken words (from STT) — subtle, muted italics
 * 2. AI's streaming response — bold, high-contrast cyan
 *
 * Auto-dissolves after 6 seconds of inactivity (no new STT or response text).
 * Uses AnimatePresence for smooth mount/unmount transitions.
 */
export function LiveCaptions({
  sttText,
  responseText,
  isSpeaking,
  isProcessing,
  conversationActive,
}: LiveCaptionsProps): JSX.Element {
  const [visible, setVisible] = useState(false)
  const [displayStt, setDisplayStt] = useState('')
  const [displayResponse, setDisplayResponse] = useState('')
  const [showCursor, setShowCursor] = useState(false)
  const dissolveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── Track the last seen STT for dissolve logic ────────────────────
  const lastSttRef = useRef('')
  const lastResponseRef = useRef('')
  const hasContentRef = useRef(false)

  const scheduleDissolve = useCallback(() => {
    if (dissolveTimer.current) clearTimeout(dissolveTimer.current)
    dissolveTimer.current = setTimeout(() => {
      setVisible(false)
      setDisplayStt('')
      setDisplayResponse('')
      hasContentRef.current = false
    }, 6000)
  }, [])

  const cancelDissolve = useCallback(() => {
    if (dissolveTimer.current) clearTimeout(dissolveTimer.current)
  }, [])

  // ── Sync STT text ─────────────────────────────────────────────────
  useEffect(() => {
    if (sttText) {
      cancelDissolve()
      startTransition(() => {
        setDisplayStt(sttText)
        setVisible(true)
      })
      lastSttRef.current = sttText
      hasContentRef.current = true
    }
  }, [sttText, cancelDissolve])

  // ── Sync response text ────────────────────────────────────────────
  useEffect(() => {
    if (responseText) {
      cancelDissolve()
      startTransition(() => {
        setDisplayResponse(responseText)
        setVisible(true)
        setShowCursor(true)
      })
      lastResponseRef.current = responseText
      hasContentRef.current = true
    } else {
      startTransition(() => {
        setShowCursor(false)
      })
    }
  }, [responseText, cancelDissolve])

  // ── Show captions when conversation becomes active (Listening indicator) ─
  useEffect(() => {
    if (conversationActive && !isProcessing) {
      startTransition(() => {
        setVisible(true)
      })
      hasContentRef.current = true
    }
  }, [conversationActive, isProcessing])

  // ── Start dissolve when processing finishes ───────────────────────
  useEffect(() => {
    // When the AI finishes its turn (not speaking, not processing, but
    // we still have response text displayed), begin the 6s countdown.
    if (!isSpeaking && !isProcessing && hasContentRef.current) {
      scheduleDissolve()
    }
  }, [isSpeaking, isProcessing, scheduleDissolve])

  // ── Cleanup timer on unmount ──────────────────────────────────────
  useEffect(() => {
    return () => {
      if (dissolveTimer.current) clearTimeout(dissolveTimer.current)
    }
  }, [])

  // ── Don't render if nothing to show ───────────────────────────────
  // (visible gates the AnimatePresence, but also skip if truly empty)
  if (!visible && !sttText && !responseText && !conversationActive) {
    return <></>
  }

  return (
    <AnimatePresence mode="wait">
      {visible && (displayStt || displayResponse || (conversationActive && !isProcessing)) && (
       <motion.div
          key="live-captions"
          // 1. Add x: "-50%" to all animation states
          initial={{ opacity: 0, y: 16, x: "-50%", scale: 0.95 }}
          animate={{ opacity: 1, y: 0, x: "-50%", scale: 1 }}
          exit={{ opacity: 0, y: 12, x: "-50%", scale: 0.95 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
          // 2. Remove -translate-x-1/2 from the Tailwind classes
          className="fixed bottom-40 left-1/2 z-[70] w-full max-w-xl pointer-events-none"
        >
          <div className="mx-4 backdrop-blur-md backdrop-blur-sm border border-white/10 rounded-2xl px-6 py-4 shadow-2xl shadow-black/30">
            {/* ── User speech line ──────────────────────────────── */}
            {displayStt && (
              <div className="flex items-start gap-2.5 mb-1.5">
                <User className="w-3.5 h-3.5 mt-0.5 shrink-0 text-cyan-400/50" />
                <p className="text-sm text-slate-300 leading-relaxed italic font-sans">
                  &ldquo;{displayStt}&rdquo;
                </p>
              </div>
            )}

            {/* ── AI response line ──────────────────────────────── */}
            {displayResponse && (
              <div className="flex items-start gap-2.5">
                <Bot className="w-3.5 h-3.5 mt-0.5 shrink-0 text-emerald-400/60" />
                <p className="text-base font-medium text-cyan-50 leading-relaxed font-sans">
                  {displayResponse}
                  {showCursor && (
                    <motion.span
                      className="inline-block w-0.5 h-4 ml-0.5 bg-cyan-300/80 align-text-bottom"
                      animate={{ opacity: [1, 0] }}
                      transition={{ duration: 0.6, repeat: Infinity, ease: 'easeInOut' }}
                    />
                  )}
                </p>
              </div>
            )}

            {/* ── Thinking indicator (no response yet) ─────────── */}
            {!displayResponse && isProcessing && (
              <div className="flex items-center gap-2.5">
                <Bot className="w-3.5 h-3.5 mt-0.5 shrink-0 text-emerald-400/60" />
                <div className="flex gap-1">
                  <motion.span
                    className="w-1.5 h-1.5 rounded-full bg-emerald-400/60"
                    animate={{ opacity: [0.3, 1, 0.3] }}
                    transition={{ duration: 1.2, repeat: Infinity, delay: 0 }}
                  />
                  <motion.span
                    className="w-1.5 h-1.5 rounded-full bg-emerald-400/60"
                    animate={{ opacity: [0.3, 1, 0.3] }}
                    transition={{ duration: 1.2, repeat: Infinity, delay: 0.2 }}
                  />
                  <motion.span
                    className="w-1.5 h-1.5 rounded-full bg-emerald-400/60"
                    animate={{ opacity: [0.3, 1, 0.3] }}
                    transition={{ duration: 1.2, repeat: Infinity, delay: 0.4 }}
                  />
                </div>
              </div>
            )}

            {/* ── Listening indicator (no STT yet) ─────────────── */}
            {!displayStt && !displayResponse && conversationActive && !isProcessing && (
              <div className="flex items-center gap-2.5">
                <span className="relative flex w-2 h-2 shrink-0">
                  <span className="animate-ping absolute inset-0 rounded-full bg-cyan-400 opacity-50" />
                  <span className="relative rounded-full w-2 h-2 bg-cyan-400" />
                </span>
                <span className="text-xs font-sans text-slate-400 italic">
                  Listening...
                </span>
              </div>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
