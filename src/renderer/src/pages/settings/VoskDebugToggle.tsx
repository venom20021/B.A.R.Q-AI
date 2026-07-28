import { useState, useEffect, useCallback } from 'react'
import { Loader2 } from 'lucide-react'

// ── Vosk Debug Logs Toggle ────────────────────────────────────────────

export function VoskDebugToggle(): JSX.Element {
  const [enabled, setEnabled] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    ;(async () => {
      try {
        const resp = await window.barq?.debug.getVoskLogs()
        if (resp?.success && resp.data) {
          const data = resp.data as { enabled: boolean }
          setEnabled(data.enabled)
        }
      } catch {
        /* ignore */
      }
      setLoading(false)
    })()
  }, [])

  const handleToggle = useCallback(async () => {
    const newVal = !enabled
    setEnabled(newVal)
    try {
      await window.barq?.debug.setVoskLogs(newVal)
    } catch {
      setEnabled(!newVal) // revert on error
    }
  }, [enabled])

  if (loading) {
    return <Loader2 className="w-4 h-4 animate-spin text-cyan-300" />
  }

  return (
    <button
      onClick={handleToggle}
      className={`relative w-9 h-5 rounded-full transition-colors ${enabled ? 'bg-cyan-500' : 'bg-dim-500/30'}`}
    >
      <span className={`absolute top-[2px] w-4 h-4 bg-white rounded-full transition-transform ${enabled ? 'translate-x-[18px]' : 'translate-x-[2px]'}`} />
    </button>
  )
}
