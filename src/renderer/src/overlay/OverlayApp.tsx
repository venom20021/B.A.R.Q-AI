import { useEffect, useState, useCallback, useRef } from 'react'
import { OverlayClock } from './OverlayClock'
import { OverlayWeather } from './OverlayWeather'
import { OverlayStats } from './OverlayStats'
import { OverlayStocks } from './OverlayStocks'

// Inline type to avoid cross-entry import from preload
interface OverlayUpdatePayload {
  weather?: {
    city: string
    temperature_c: number
    description: string
    icon: string
    humidity: number
    loaded: boolean
  } | null
  stats?: {
    cpu_percent: number
    memory: { used_gb: number; total_gb: number; percent: number }
    disk: { used_gb: number; total_gb: number; percent: number }
    hostname: string
    uptime: string
    loaded: boolean
  } | null
  stocks?: {
    ticker: string
    company: string
    current_price: number
    change_percent: number
    loaded: boolean
  } | null
}

const EMPTY_WEATHER = { city: '', temperature_c: 0, description: '', icon: '', humidity: 0, loaded: false }
const EMPTY_STATS = { cpu_percent: 0, memory: { used_gb: 0, total_gb: 0, percent: 0 }, disk: { used_gb: 0, total_gb: 0, percent: 0 }, hostname: '', uptime: '', loaded: false }
const EMPTY_STOCKS = { ticker: '---', company: '', current_price: 0, change_percent: 0, loaded: false }

export function OverlayApp(): JSX.Element {
  const [weather, setWeather] = useState(EMPTY_WEATHER)
  const [stats, setStats] = useState(EMPTY_STATS)
  const [stocks, setStocks] = useState(EMPTY_STOCKS)

  const handleUpdate = useCallback((data: OverlayUpdatePayload) => {
    if (data.weather) setWeather(data.weather)
    if (data.stats) setStats(data.stats)
    if (data.stocks) setStocks(data.stocks)
  }, [])

  useEffect(() => {
    // Listen for data pushed from main process
    const overlayApi = (window as unknown as { overlay?: { onUpdate: (cb: (data: OverlayUpdatePayload) => void) => void; onToggle: (cb: (v: boolean) => void) => void; refresh: () => void; removeAllListeners: (c: string) => void } }).overlay
    if (overlayApi) {
      overlayApi.onUpdate(handleUpdate)

      // Request initial data via IPC bridge
      overlayApi.refresh()
    }

    return () => {
      if (overlayApi) {
        overlayApi.removeAllListeners('overlay:update')
      }
    }
  }, [handleUpdate])

  const overlayApi = (window as unknown as {
    overlay?: {
      hide: () => void
      openMain: () => void
      moveBy: (deltaX: number, deltaY: number) => void
    }
  }).overlay

  // ─── Custom drag support ────────────────────────────────────────────────
  const dragState = useRef<{ lastScreenX: number; lastScreenY: number } | null>(null)

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    // Only left button, not on close button
    if (e.button !== 0 || (e.target as HTMLElement).closest('.overlay-close-btn')) return

    e.preventDefault()

    // Track the last screen position for incremental delta calculation
    dragState.current = {
      lastScreenX: e.screenX,
      lastScreenY: e.screenY,
    }

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (!dragState.current) return
      // Calculate delta from last mouse position (incremental)
      const deltaX = moveEvent.screenX - dragState.current.lastScreenX
      const deltaY = moveEvent.screenY - dragState.current.lastScreenY
      dragState.current.lastScreenX = moveEvent.screenX
      dragState.current.lastScreenY = moveEvent.screenY

      // Send incremental delta to main process which adds it to window position
      if (overlayApi?.moveBy) {
        overlayApi.moveBy(deltaX, deltaY)
      }
    }

    const handleMouseUp = () => {
      dragState.current = null
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [overlayApi])

  const handleClose = useCallback(() => {
    overlayApi?.hide()
  }, [overlayApi])

  const handleDoubleClick = useCallback(() => {
    overlayApi?.openMain()
  }, [overlayApi])

  return (
    <div
      className="overlay-container"
      onMouseDown={handleMouseDown}
      onDoubleClick={handleDoubleClick}
    >
      {/* Drag handle area */}
      <div className="overlay-drag-handle">
        <div className="drag-handle-dots">
          <span /><span /><span />
        </div>
      </div>

      {/* Close button */}
      <button className="overlay-close-btn" onClick={handleClose} title="Hide overlay">
        ✕
      </button>

      {/* Widgets */}
      <OverlayClock />
      <OverlayWeather weather={weather} />
      <OverlayStats stats={stats} />
      <OverlayStocks stocks={stocks} />
    </div>
  )
}
