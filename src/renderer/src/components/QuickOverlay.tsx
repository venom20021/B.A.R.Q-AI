import { useState, useEffect, useRef, useCallback, type KeyboardEvent } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Command, Mic, History, ArrowUpRight } from 'lucide-react'

interface QuickOverlayProps {
  isVisible: boolean
  onClose: () => void
  position: { x: number; y: number }
  recentCommands: string[]
}

export function QuickOverlay({
  isVisible,
  onClose,
  position,
  recentCommands,
}: QuickOverlayProps): JSX.Element | null {
  const [input, setInput] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (isVisible && inputRef.current) {
      inputRef.current.focus()
      setInput('')
    }
  }, [isVisible])

  const handleSubmit = useCallback((): void => {
    if (input.trim()) {
      window.dispatchEvent(
        new CustomEvent('barq:quick-command', { detail: { command: input.trim() } }),
      )
      setInput('')
      onClose()
    }
  }, [input, onClose])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>): void => {
      if (e.key === 'Enter') handleSubmit()
      if (e.key === 'Escape') onClose()
    },
    [handleSubmit, onClose],
  )

  if (!isVisible) return null

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-[60]"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: -10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: -10 }}
          transition={{ duration: 0.15 }}
          onClick={(e) => e.stopPropagation()}
          className="absolute w-[360px] rounded-xl overflow-hidden shadow-2xl shadow-black/50"
          style={{
            left: Math.min(position.x, window.innerWidth - 380),
            top: Math.min(position.y, window.innerHeight - 450),
          }}
        >
          {/* Unified dark void glass panel */}
          <div className="relative bg-void-800/90 backdrop-blur-2xl border border-cyan-500/10 shadow-glass holo-border">
            {/* Glowing top border accent */}
            <div className="absolute top-0 left-4 right-4 h-px bg-gradient-to-r from-transparent via-cyan-400/40 to-transparent" />

            {/* Scanline overlay */}
            <div className="absolute inset-0 pointer-events-none opacity-[0.015]"
              style={{
                backgroundImage: 'repeating-linear-gradient(transparent 0px, transparent 2px, rgba(0,240,255,0.03) 2px, rgba(0,240,255,0.03) 4px)',
              }}
            />

            {/* Input section */}
            <div className="relative p-4 border-b border-cyan-500/10">
            <div className="flex items-center gap-3">
              <Command className="w-5 h-5 text-cyan-300 flex-shrink-0" />
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type a command..."
                className="flex-1 bg-transparent text-sm text-ghost placeholder-dim-400 font-exo outline-none"
              />
              <button
                onClick={handleSubmit}
                disabled={!input.trim()}
                className="p-1.5 rounded-md hover:bg-cyan-500/10 text-dim-400 hover:text-cyan-300 transition-colors disabled:opacity-30"
              >
                <ArrowUpRight className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Content */}
          <div className="p-3 space-y-2 max-h-[320px] overflow-y-auto scroll-cyan">
            {/* Recent commands */}
            {recentCommands.length > 0 && (
              <div>
                <div className="flex items-center gap-1.5 mb-2 px-2">
                  <History className="w-3 h-3 text-dim-400" />
                  <span className="text-hud font-share-tech text-dim-400 uppercase tracking-wider">
                    Recent
                  </span>
                </div>
                <div className="space-y-0.5">
                  {recentCommands.map((cmd, i) => (
                    <button
                      key={i}
                      onClick={() => {
                        window.dispatchEvent(
                          new CustomEvent('barq:quick-command', { detail: { command: cmd } }),
                        )
                        onClose()
                      }}
                      className="w-full text-left px-3 py-2 rounded-lg text-sm font-exo text-dim-300 hover:text-ghost hover:bg-cyan-500/5 transition-colors"
                    >
                      {cmd}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Quick hints */}
            <div className="pt-2 border-t border-cyan-500/8">
              <div className="grid grid-cols-2 gap-1.5">
                {[
                  { label: 'Scan Jobs', cmd: 'scan jobs' },
                  { label: 'Open Files', cmd: 'open files' },
                  { label: 'Check Weather', cmd: 'weather London' },
                  { label: 'Show Trends', cmd: 'show trends' },
                  { label: 'Create Note', cmd: 'create note' },
                  { label: 'System Status', cmd: 'system status' },
                ].map((hint) => (
                  <button
                    key={hint.label}
                    onClick={() => {
                      window.dispatchEvent(
                        new CustomEvent('barq:quick-command', {
                          detail: { command: hint.cmd },
                        }),
                      )
                      onClose()
                    }}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-rajdhani font-semibold
                             text-dim-300 hover:text-cyan-300 hover:bg-cyan-500/5 transition-colors border border-transparent hover:border-cyan-500/15"
                  >
                    <Mic className="w-3 h-3 flex-shrink-0" />
                    {hint.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Keyboard hint */}
            <div className="flex items-center justify-center gap-3 pt-1">
              <kbd className="text-hud font-share-tech text-dim-500 bg-void-800/50 px-1.5 py-0.5 rounded border border-dim-500/15">
                ↑↓
              </kbd>
              <span className="text-hud font-share-tech text-dim-500">navigate</span>
              <kbd className="text-hud font-share-tech text-dim-500 bg-void-800/50 px-1.5 py-0.5 rounded border border-dim-500/15">
                esc
              </kbd>
              <span className="text-hud font-share-tech text-dim-500">close</span>
            </div>
          </div>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
