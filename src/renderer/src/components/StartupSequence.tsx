import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

interface StatusLine {
  text: string
  type: 'success' | 'info' | 'warn'
}

const statusLines: StatusLine[] = [
  { text: 'Initializing neural core...', type: 'info' },
  { text: 'Voice engine online', type: 'success' },
  { text: 'Ollama inference connected', type: 'success' },
  { text: 'Memory banks loaded', type: 'success' },
  { text: 'Calibrating audio pipeline...', type: 'info' },
  { text: 'Scheduler active', type: 'success' },
  { text: 'Database synchronized', type: 'success' },
  { text: 'All systems nominal', type: 'success' },
]

interface StartupSequenceProps {
  onComplete: () => void
}

export function StartupSequence({ onComplete }: StartupSequenceProps): JSX.Element {
  const [phase, setPhase] = useState<'logo' | 'init' | 'status' | 'ready'>('logo')
  const [visibleStatuses, setVisibleStatuses] = useState<number>(0)
  const [initText, setInitText] = useState('')
  const initMessage = 'INITIALIZING NEURAL SYSTEMS'

  // Phase 1: Logo glitch (0.8s)
  useEffect(() => {
    const t = setTimeout(() => setPhase('init'), 800)
    return () => clearTimeout(t)
  }, [])

  // Phase 2: Typewriter INITIALIZING text (1.5s)
  useEffect(() => {
    if (phase !== 'init') return
    let i = 0
    const interval = setInterval(() => {
      i++
      setInitText(initMessage.slice(0, i))
      if (i >= initMessage.length) {
        clearInterval(interval)
        setTimeout(() => setPhase('status'), 400)
      }
    }, 60)
    return () => clearInterval(interval)
  }, [phase])

  // Phase 3: Status lines appear one by one
  useEffect(() => {
    if (phase !== 'status') return
    if (visibleStatuses >= statusLines.length) {
      setTimeout(() => setPhase('ready'), 500)
      return
    }
    const t = setTimeout(
      () => setVisibleStatuses((p) => p + 1),
      visibleStatuses === 0 ? 300 : 200,
    )
    return () => clearTimeout(t)
  }, [phase, visibleStatuses])

  // Phase 4: Done
  useEffect(() => {
    if (phase !== 'ready') return
    const t = setTimeout(onComplete, 600)
    return () => clearTimeout(t)
  }, [phase, onComplete])

  const handleSkip = useCallback((): void => {
    onComplete()
  }, [onComplete])

  return (
    <motion.div
      className="fixed inset-0 z-[100] bg-[#0A0A0F] flex flex-col items-center justify-center"
      exit={{ opacity: 0 }}
      transition={{ duration: 0.5 }}
    >
      {/* Skip hint */}
      <button
        onClick={handleSkip}
        className="absolute top-6 right-6 text-hud font-share-tech text-dim-400 hover:text-ghost transition-colors"
      >
        SKIP &gt;&gt;
      </button>

      {/* Phase 1: Logo */}
      <AnimatePresence mode="wait">
        {phase === 'logo' && (
          <motion.div
            key="logo"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="text-center"
          >
            <motion.h1
              className="text-6xl font-orbitron font-bold text-cyan-300 tracking-widest"
              animate={{ x: [0, -3, 3, -2, 2, 0] }}
              transition={{ duration: 0.3, delay: 0.4 }}
            >
              BARQ
            </motion.h1>
            <motion.div
              className="mt-4 w-32 h-px mx-auto bg-gradient-to-r from-transparent via-cyan-400 to-transparent"
              animate={{ opacity: [0.2, 1, 0.2] }}
              transition={{ duration: 0.6, repeat: Infinity }}
            />
          </motion.div>
        )}

        {/* Phase 2: INITIALIZING */}
        {phase === 'init' && (
          <motion.div
            key="init"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center"
          >
            <p className="text-xl font-share-tech text-cyan-300 tracking-[0.3em]">
              {initText}
              <motion.span
                animate={{ opacity: [1, 0] }}
                transition={{ duration: 0.5, repeat: Infinity }}
                className="text-cyan-400"
              >
                _
              </motion.span>
            </p>
          </motion.div>
        )}

        {/* Phase 3: Status lines */}
        {phase === 'status' && (
          <motion.div
            key="status"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="w-96"
          >
            <p className="text-xs font-share-tech text-dim-400 tracking-[0.2em] mb-6 uppercase">
              System Diagnostics
            </p>
            <div className="space-y-2">
              {statusLines.map((line, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -10 }}
                  animate={
                    i < visibleStatuses
                      ? { opacity: 1, x: 0 }
                      : { opacity: 0, x: -10 }
                  }
                  transition={{ duration: 0.2 }}
                  className="flex items-center gap-3"
                >
                  {i < visibleStatuses ? (
                    line.type === 'success' ? (
                      <span className="text-neural text-hud font-share-tech">[OK]</span>
                    ) : (
                      <span className="text-cyan-300 text-hud font-share-tech">[..]</span>
                    )
                  ) : (
                    <span className="text-dim-500 text-hud font-share-tech">[--]</span>
                  )}
                  <span
                    className={`text-sm font-rajdhani ${
                      i < visibleStatuses
                        ? line.type === 'success'
                          ? 'text-neural'
                          : 'text-cyan-300'
                        : 'text-dim-500'
                    }`}
                  >
                    {line.text}
                  </span>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}

        {/* Phase 4: BARQ online */}
        {phase === 'ready' && (
          <motion.div
            key="ready"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.4 }}
            className="text-center"
          >
            <motion.div
              animate={{ opacity: [1, 0.6, 1] }}
              transition={{ duration: 2, repeat: Infinity }}
            >
              <h1 className="text-4xl font-orbitron font-bold text-cyan-300 tracking-widest">
                BARQ
              </h1>
              <p className="mt-3 text-lg font-rajdhani font-semibold text-neural">
                Online. Ready.
              </p>
            </motion.div>
            <div className="mt-6 w-48 h-px mx-auto bg-gradient-to-r from-transparent via-neural to-transparent" />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Bottom loading bar */}
      <div className="absolute bottom-12 left-1/2 -translate-x-1/2 w-64">
        <div className="h-px bg-dim-500/30 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-gradient-to-r from-cyan-400 via-holographic to-cyan-400"
            initial={{ width: '0%' }}
            animate={
              phase === 'ready'
                ? { width: '100%', opacity: [1, 0] }
                : { width: phase === 'logo' ? '15%' : phase === 'init' ? '45%' : '80%' }
            }
            transition={phase === 'ready' ? { duration: 0.4 } : { duration: 0.5 }}
          />
        </div>
        <p className="mt-2 text-center text-hud font-share-tech text-dim-500">
          {phase === 'logo' && 'BOOTING'}
          {phase === 'init' && 'LOADING KERNEL'}
          {phase === 'status' && 'MOUNTING MODULES'}
          {phase === 'ready' && 'READY'}
        </p>
      </div>
    </motion.div>
  )
}
