import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { Clock, TrendingUp, Calculator, Globe, Wand2, Code, Play, Square, RotateCcw, Loader2, Trash2, GripVertical } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { api } from '../utils/api'

// ─── Types ─────────────────────────────────────────────────────────────────

interface SpawnedWidget {
  id: string
  type: 'timer' | 'calculator' | 'weather' | 'stocks'
  title: string
  accent: string
}

interface WeatherData {
  city: string
  temperature_c: number
  description: string
}

// ─── Widget Defs ───────────────────────────────────────────────────────────

const widgetDefs = [
  { icon: Clock, accent: 'text-emerald-400', title: 'Timer', desc: 'Countdown / stopwatch widget', type: 'timer' as const },
  { icon: Calculator, accent: 'text-purple-400', title: 'Calculator', desc: 'Desktop calculator widget', type: 'calculator' as const },
  { icon: Globe, accent: 'text-cyan-300', title: 'Weather', desc: 'Current weather widget', type: 'weather' as const },
  { icon: TrendingUp, accent: 'text-rose-400', title: 'Stock Ticker', desc: 'Live market prices', type: 'stocks' as const },
]

// ─── Inline Timer ──────────────────────────────────────────────────────────

function TimerWidget({ accent, onClose }: { accent: string; onClose: () => void }): JSX.Element {
  const [seconds, setSeconds] = useState(0)
  const [running, setRunning] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (running) {
      intervalRef.current = setInterval(() => setSeconds(s => s + 1), 1000)
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [running])

  const formatTime = (s: number): string => {
    const m = Math.floor(s / 60)
    const sec = s % 60
    return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
  }

  const handleReset = () => { setRunning(false); setSeconds(0) }

  return (
    <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
      className="bg-zinc-900/90 backdrop-blur-md rounded-xl border border-zinc-800 p-4 flex flex-col items-center gap-3 shadow-xl"
    >
      <div className="flex items-center justify-between w-full">
        <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">Timer</span>
        <button onClick={onClose} className="p-1 rounded text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors">
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
      <div className="text-3xl font-mono font-bold tracking-wider" style={{ color: accent.replace('text-', '') === 'emerald-400' ? '#34D399' : '#A855F7' }}>
        {formatTime(seconds)}
      </div>
      <div className="flex items-center gap-2">
        {running ? (
          <button onClick={() => setRunning(false)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500/15 text-amber-400 border border-amber-500/20 text-xs font-medium hover:bg-amber-500/25 transition-colors">
            <Square className="w-3 h-3" /> Stop
          </button>
        ) : (
          <button onClick={() => setRunning(true)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 text-xs font-medium hover:bg-emerald-500/25 transition-colors">
            <Play className="w-3 h-3" /> Start
          </button>
        )}
        <button onClick={handleReset} className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors">
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
      </div>
    </motion.div>
  )
}

// ─── Inline Calculator ─────────────────────────────────────────────────────

function CalculatorWidget({ onClose }: { onClose: () => void }): JSX.Element {
  const [display, setDisplay] = useState('0')
  const [prevValue, setPrevValue] = useState<number | null>(null)
  const [operator, setOperator] = useState<string | null>(null)
  const [waitingForOperand, setWaitingForOperand] = useState(false)

  const inputDigit = useCallback((digit: string) => {
    if (waitingForOperand) { setDisplay(digit); setWaitingForOperand(false) }
    else { setDisplay(prev => prev === '0' ? digit : prev + digit) }
  }, [waitingForOperand])

  const inputDecimal = useCallback(() => {
    if (waitingForOperand) { setDisplay('0.'); setWaitingForOperand(false); return }
    if (!display.includes('.')) setDisplay(prev => prev + '.')
  }, [waitingForOperand, display])

  const clearAll = useCallback(() => { setDisplay('0'); setPrevValue(null); setOperator(null); setWaitingForOperand(false) }, [])

  const performOperation = useCallback((nextOperator: string) => {
    const current = parseFloat(display)
    if (prevValue === null) { setPrevValue(current) }
    else if (operator) {
      const prev = prevValue
      let result = 0
      switch (operator) {
        case '+': result = prev + current; break
        case '-': result = prev - current; break
        case '*': result = prev * current; break
        case '/': result = prev / current; break
        default: result = current
      }
      setDisplay(String(result))
      setPrevValue(result)
    }
    setWaitingForOperand(true)
    setOperator(nextOperator === '=' ? null : nextOperator)
  }, [display, prevValue, operator])

  const btnClass = "p-2 rounded-lg text-xs font-mono font-semibold transition-all duration-150 active:scale-95"
  const numBtn = `${btnClass} bg-zinc-800/80 text-zinc-200 hover:bg-zinc-700/80 border border-zinc-700/50`
  const opBtn = `${btnClass} bg-violet-500/15 text-violet-300 hover:bg-violet-500/25 border border-violet-500/20`
  const eqBtn = `${btnClass} bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 border border-cyan-500/20`
  const fnBtn = `${btnClass} bg-zinc-800/50 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/50 border border-zinc-700/30`

  return (
    <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
      className="bg-zinc-900/90 backdrop-blur-md rounded-xl border border-zinc-800 p-4 shadow-xl"
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">Calculator</span>
        <button onClick={onClose} className="p-1 rounded text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors">
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
      <div className="bg-zinc-950 rounded-lg px-3 py-2 mb-3 border border-zinc-800">
        <div className="text-right text-xl font-mono font-bold text-zinc-100 tracking-tight tabular-nums overflow-x-auto whitespace-nowrap">{display}</div>
      </div>
      <div className="grid grid-cols-4 gap-1.5">
        <button onClick={clearAll} className={fnBtn}>C</button>
        <button onClick={() => inputDigit('-')} className={fnBtn}>±</button>
        <button onClick={() => inputDigit('%')} className={fnBtn}>%</button>
        <button onClick={() => performOperation('/')} className={opBtn}>÷</button>
        <button onClick={() => inputDigit('7')} className={numBtn}>7</button>
        <button onClick={() => inputDigit('8')} className={numBtn}>8</button>
        <button onClick={() => inputDigit('9')} className={numBtn}>9</button>
        <button onClick={() => performOperation('*')} className={opBtn}>×</button>
        <button onClick={() => inputDigit('4')} className={numBtn}>4</button>
        <button onClick={() => inputDigit('5')} className={numBtn}>5</button>
        <button onClick={() => inputDigit('6')} className={numBtn}>6</button>
        <button onClick={() => performOperation('-')} className={opBtn}>−</button>
        <button onClick={() => inputDigit('1')} className={numBtn}>1</button>
        <button onClick={() => inputDigit('2')} className={numBtn}>2</button>
        <button onClick={() => inputDigit('3')} className={numBtn}>3</button>
        <button onClick={() => performOperation('+')} className={opBtn}>+</button>
        <button onClick={() => inputDigit('0')} className={`${numBtn} col-span-2`}>0</button>
        <button onClick={inputDecimal} className={numBtn}>.</button>
        <button onClick={() => performOperation('=')} className={eqBtn}>=</button>
      </div>
    </motion.div>
  )
}

// ─── Inline Weather ────────────────────────────────────────────────────────

function WeatherWidget({ onClose }: { onClose: () => void }): JSX.Element {
  const [weather, setWeather] = useState<WeatherData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      try {
        const data = await api('/web/weather?city=London')
        if (data && typeof data === 'object') {
          const d = data as Record<string, unknown>
          setWeather({
            city: (d.city as string) ?? 'London',
            temperature_c: Number(d.temperature_c ?? 0),
            description: (d.description as string) ?? '',
          })
        }
      } catch { /* ignore */ }
      setLoading(false)
    })()
  }, [])

  return (
    <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
      className="bg-zinc-900/90 backdrop-blur-md rounded-xl border border-zinc-800 p-4 shadow-xl"
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">Weather</span>
        <button onClick={onClose} className="p-1 rounded text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors">
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
      {loading ? (
        <div className="flex items-center justify-center py-6"><Loader2 className="w-5 h-5 text-cyan-400 animate-spin" /></div>
      ) : weather ? (
        <div className="flex flex-col items-center gap-1">
          <span className="text-3xl font-mono font-bold text-cyan-300">{Math.round(weather.temperature_c)}°</span>
          <span className="text-xs font-mono text-zinc-400 uppercase tracking-wider">{weather.city}</span>
          <span className="text-[10px] font-mono text-zinc-500">{weather.description}</span>
        </div>
      ) : (
        <div className="text-center py-4 text-xs font-mono text-zinc-600">Weather unavailable</div>
      )}
    </motion.div>
  )
}

// ─── Inline Stock Ticker ────────────────────────────────────────────────────

const MOCK_STOCKS = [
  { symbol: 'AAPL', price: 218.45, change: '+1.23%', up: true },
  { symbol: 'GOOGL', price: 175.89, change: '-0.45%', up: false },
  { symbol: 'MSFT', price: 425.22, change: '+0.89%', up: true },
  { symbol: 'TSLA', price: 248.60, change: '+2.15%', up: true },
  { symbol: 'NVDA', price: 880.35, change: '-1.02%', up: false },
]

function StockTickerWidget({ onClose }: { onClose: () => void }): JSX.Element {
  return (
    <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }}
      className="bg-zinc-900/90 backdrop-blur-md rounded-xl border border-zinc-800 p-4 shadow-xl"
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-mono text-zinc-500 uppercase tracking-wider">Stocks</span>
        <button onClick={onClose} className="p-1 rounded text-zinc-600 hover:text-red-400 hover:bg-red-500/10 transition-colors">
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
      <div className="space-y-1.5">
        {MOCK_STOCKS.map(s => (
          <div key={s.symbol} className="flex items-center justify-between px-2 py-1.5 rounded-lg bg-zinc-800/40 hover:bg-zinc-800/60 transition-colors">
            <span className="text-xs font-mono font-semibold text-zinc-300">{s.symbol}</span>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono tabular-nums text-zinc-100">${s.price.toFixed(2)}</span>
              <span className={`text-[10px] font-mono ${s.up ? 'text-emerald-400' : 'text-red-400'}`}>{s.change}</span>
            </div>
          </div>
        ))}
      </div>
      <p className="text-[9px] font-mono text-zinc-600 text-center mt-2">Delayed · Demo data</p>
    </motion.div>
  )
}

// ─── Widget Forge: Render user HTML/JSX as an iframe preview ───────────────

function WidgetForgePreview({ code }: { code: string }): JSX.Element {
  const iframeRef = useRef<HTMLIFrameElement>(null)

  const blobUrl = useMemo(() => {
    const html = `<!DOCTYPE html><html><head><style>
      * { margin: 0; padding: 0; box-sizing: border-box; }
      body { background: #18181b; color: #e4e4e7; font-family: monospace; display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 16px; font-size: 13px; }
    </style></head><body>${code}</body></html>`
    const blob = new Blob([html], { type: 'text/html' })
    return URL.createObjectURL(blob)
  }, [code])

  useEffect(() => {
    return () => URL.revokeObjectURL(blobUrl)
  }, [blobUrl])

  return <iframe ref={iframeRef} src={blobUrl} className="w-full h-full rounded-lg bg-zinc-950" title="Widget Preview" />
}

// ─── Main Page ─────────────────────────────────────────────────────────────

export function WidgetsPage(): JSX.Element {
  const [spawned, setSpawned] = useState<SpawnedWidget[]>([])
  const [forgeCode, setForgeCode] = useState('<div style="text-align:center"><h3 style="color:#34D399">Hello Widget!</h3><p style="color:#71717a;margin-top:8px">Edit the code →</p></div>')
  const [showForgePreview, setShowForgePreview] = useState(false)
  const nextId = useRef(1)

  const spawnWidget = useCallback((def: typeof widgetDefs[0]) => {
    setSpawned(prev => [...prev, { id: `widget-${nextId.current++}`, type: def.type, title: def.title, accent: def.accent }])
  }, [])

  const removeWidget = useCallback((id: string) => {
    setSpawned(prev => prev.filter(w => w.id !== id))
  }, [])

  const renderWidget = (w: SpawnedWidget) => {
    switch (w.type) {
      case 'timer': return <TimerWidget accent={w.accent} onClose={() => removeWidget(w.id)} />
      case 'calculator': return <CalculatorWidget onClose={() => removeWidget(w.id)} />
      case 'weather': return <WeatherWidget onClose={() => removeWidget(w.id)} />
      case 'stocks': return <StockTickerWidget onClose={() => removeWidget(w.id)} />
    }
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20">
            <Wand2 className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">WIDGETS & UI</h1>
            <p className="text-sm font-rajdhani text-dim-400 mt-0.5">Floating widgets, live coding, and desktop customization</p>
          </div>
        </div>
      </motion.div>

      {/* ── Widget Cards ──────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {widgetDefs.map((w, i) => {
          const Icon = w.icon
          return (
            <motion.div key={w.title} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}
              className="bg-zinc-900/60 backdrop-blur-sm rounded-xl border border-zinc-800/60 hover:border-zinc-700/60 p-5 text-center transition-all duration-300 group"
            >
              <Icon className={`w-8 h-8 ${w.accent} mx-auto mb-3`} />
              <h3 className="text-sm font-rajdhani font-semibold text-zinc-200">{w.title}</h3>
              <p className="text-xs font-exo text-zinc-500 mt-1 mb-4">{w.desc}</p>
              <button onClick={() => spawnWidget(w)} 
                className="px-4 py-1.5 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 text-xs font-rajdhani font-semibold hover:bg-cyan-500/20 transition-all duration-200"
              >
                Spawn
              </button>
            </motion.div>
          )
        })}
      </div>

      {/* ── Spawned Widgets ────────────────────────────────────────────── */}
      <AnimatePresence>
        {spawned.length > 0 && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <h3 className="text-xs font-orbitron font-bold text-zinc-400 tracking-wider mb-3 flex items-center gap-2">
              <GripVertical className="w-3 h-3" />
              Active Widgets ({spawned.length})
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {spawned.map(w => (
                <div key={w.id}>{renderWidget(w)}</div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Widget Forge ──────────────────────────────────────────────── */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
        className="bg-zinc-900/60 backdrop-blur-sm rounded-xl border border-zinc-800/60 p-5"
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Code className="w-5 h-5 text-cyan-300" />
            <h3 className="text-sm font-orbitron font-bold text-zinc-200 tracking-wider">Widget Forge</h3>
          </div>
          <button onClick={() => setShowForgePreview(p => !p)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800/60 text-zinc-400 border border-zinc-700/50 text-xs font-mono hover:bg-zinc-700/60 hover:text-zinc-200 transition-all duration-200"
          >
            {showForgePreview ? <Code className="w-3 h-3" /> : <Globe className="w-3 h-3" />}
            {showForgePreview ? 'Code' : 'Preview'}
          </button>
        </div>
        <p className="text-xs font-exo text-zinc-500 mb-4">Write custom HTML to render as a widget. Edit the code and see a live preview.</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-zinc-950/80 rounded-lg border border-zinc-800/60">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-zinc-800/40">
              <span className="w-2 h-2 rounded-full bg-red-500/60" />
              <span className="w-2 h-2 rounded-full bg-yellow-500/60" />
              <span className="w-2 h-2 rounded-full bg-green-500/60" />
              <span className="text-[9px] font-mono text-zinc-600 ml-2">widget.html</span>
            </div>
            <textarea
              value={forgeCode}
              onChange={(e) => setForgeCode(e.target.value)}
              className="w-full bg-transparent text-zinc-300 text-xs font-mono p-3 min-h-[160px] resize-none outline-none placeholder:text-zinc-700 leading-relaxed"
              placeholder="<!-- Write HTML here -->"
              spellCheck={false}
            />
          </div>
          <div className="bg-zinc-950/80 rounded-lg border border-zinc-800/60 min-h-[200px] overflow-hidden">
            <div className="flex items-center gap-2 px-3 py-2 border-b border-zinc-800/40">
              <Globe className="w-3 h-3 text-cyan-500/60" />
              <span className="text-[9px] font-mono text-zinc-600">Preview</span>
            </div>
            <WidgetForgePreview code={forgeCode} />
          </div>
        </div>
      </motion.div>
    </div>
  )
}
