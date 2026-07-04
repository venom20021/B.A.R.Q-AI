import { useState, useCallback, useEffect, useRef } from 'react'
import { GuardianWolf } from '../components/GuardianWolf'
import { ArcReactor } from '../components/ArcReactor'
import { ArcMonitorPanel } from '../components/ArcMonitorPanel'
import { AiChatPanel } from '../components/AiChatPanel'

type DisplayMode = 'default' | 'split' | 'wolf'
type ThemeMode = 'cyan' | 'gold'

const MODE_LABELS: Record<DisplayMode, { label: string; icon: string }> = {
  default: { label: 'Reactor', icon: '⚡' },
  split: { label: 'Split', icon: '⬜' },
  wolf: { label: 'Wolf', icon: '🐺' },
}

/** Format seconds as a human-readable duration string. */
function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

export function DashboardPage(): JSX.Element {
  const [displayMode, setDisplayMode] = useState<DisplayMode>('default')
  const [theme, setTheme] = useState<ThemeMode>('cyan')

  // ── Live stats for quick-action cards ──────────────────────────────

  const [voiceCmd, setVoiceCmd] = useState('-')
  const [jobsScan, setJobsScan] = useState('-')
  const [scripts, setScripts] = useState('-')

  // Scan progress state
  const [scanProgress, setScanProgress] = useState<{ pct: number; phase: string } | null>(null)
  // Content generation progress state
  const [contentProgress, setContentProgress] = useState<{ pct: number; phase: string } | null>(null)
  // Voice listening state
  const [voiceListening, setVoiceListening] = useState(false)

  // Track mount time for session uptime
  const uptimeStartRef = useRef(Date.now())
  const [uptime, setUptime] = useState('0s')

  // ── Weather data ───────────────────────────────────────────────────

  const [weather, setWeather] = useState<{
    temp: number
    feels: number
    description: string
    emoji: string
  } | null>(null)

  const fetchDashboardData = useCallback(async () => {
    // Fetch stats
    try {
      const results = await Promise.allSettled([
        window.barq?.python.request('/voice/status') ?? Promise.resolve(undefined),
        window.barq?.python.request('/jobs/status') ?? Promise.resolve(undefined),
        window.barq?.python.request('/social/status') ?? Promise.resolve(undefined),
      ])

      const voiceResp = results[0].status === 'fulfilled' ? results[0].value : undefined
      const jobsResp = results[1].status === 'fulfilled' ? results[1].value : undefined
      const socialResp = results[2].status === 'fulfilled' ? results[2].value : undefined

      const pipeline = (socialResp as
        { success?: boolean; data?: { pipeline?: Record<string, number> } } | undefined
      )?.data?.pipeline

      setVoiceCmd(String(
        (voiceResp as
          { success?: boolean; data?: { recent_commands?: unknown[] } } | undefined
        )?.data?.recent_commands?.length ?? 0
      ))
      setJobsScan(String(
        (jobsResp as
          { success?: boolean; data?: { total_jobs_scanned?: number } } | undefined
        )?.data?.total_jobs_scanned ?? 0
      ))
      setScripts(String(
        pipeline?.['draft_scripts'] ?? pipeline?.['scripts'] ?? 0
      ))
    } catch {
      // keep showing previous values
    }

    // Fetch weather
    try {
      const resp = await window.barq?.python.request('/web/weather?city=London')
      const d = (resp as { success?: boolean; data?: {
        temperature_c: number; feels_like_c: number; description: string; icon: string
      } } | undefined)?.data
      if (d) {
        const desc = d.description.toLowerCase()
        const isNight = d.icon?.endsWith('n')
        let emoji = '🌡'
        if (desc.includes('thunder')) emoji = '⛈'
        else if (desc.includes('rain') || desc.includes('drizzle')) emoji = '🌧'
        else if (desc.includes('snow')) emoji = '❄'
        else if (desc.includes('mist') || desc.includes('fog') || desc.includes('haze')) emoji = '🌫'
        else if (desc.includes('cloud')) emoji = isNight ? '☁' : '⛅'
        else if (desc.includes('clear') || desc.includes('sunny')) emoji = isNight ? '🌙' : '☀'

        setWeather({ temp: Math.round(d.temperature_c), feels: Math.round(d.feels_like_c), description: d.description, emoji })
      }
    } catch {
      // weather unavailable
    }
  }, [])

  // ── Scan progress polling (frequent, 2-second interval) ────────────

  const fetchScanProgress = useCallback(async () => {
    try {
      const resp = await window.barq?.python.request('/jobs/scan/progress')
      if (resp && typeof resp === 'object') {
        const p = resp as { status?: string; progress_pct?: number; phase?: string; message?: string }
        if (p.status === 'scanning' || p.status === 'evaluating') {
          setScanProgress({
            pct: p.progress_pct ?? 0,
            phase: p.phase || p.message || 'Scanning...',
          })
        } else if (p.status === 'complete') {
          // Briefly show 100% then revert to idle
          setScanProgress({ pct: 100, phase: 'Complete' })
          setTimeout(() => setScanProgress(null), 5000)
        } else {
          setScanProgress(null)
        }
      }
    } catch {
      // scan progress unavailable — just show idle state
    }
  }, [])

  // ── Trigger job scan ───────────────────────────────────────────────

  const handleScanNow = useCallback(async () => {
    try {
      const resp = await window.barq?.python.request('/jobs/scan', { method: 'POST' })
      if (resp && typeof resp === 'object') {
        const r = resp as { status?: string }
        if (r.status === 'started') {
          // Immediately trigger a progress fetch so the UI shows the scanning state
          fetchScanProgress()
        }
      }
    } catch {
      // scan trigger failed
    }
  }, [fetchScanProgress])

  // ── Voice status polling (every 2 seconds for real-time indicator) ─

  const fetchVoiceStatus = useCallback(async () => {
    try {
      const resp = await window.barq?.python.request('/voice/status')
      if (resp && typeof resp === 'object') {
        const v = resp as { is_listening?: boolean; data?: { is_listening?: boolean } }
        // Handle both wrapped and unwrapped response shapes
        const isListening = v.is_listening ?? v.data?.is_listening ?? false
        setVoiceListening(isListening)
      }
    } catch {
      // voice status unavailable
    }
  }, [])

  // ── Content generation progress polling (2-second interval) ────────

  const fetchContentProgress = useCallback(async () => {
    try {
      const resp = await window.barq?.python.request('/social/generation/progress')
      if (resp && typeof resp === 'object') {
        const p = resp as { status?: string; progress_pct?: number; phase?: string; message?: string }
        if (p.status === 'scripting' || p.status === 'rendering' || p.status === 'posting') {
          setContentProgress({
            pct: p.progress_pct ?? 0,
            phase: p.message || p.phase || 'Generating...',
          })
        } else if (p.status === 'complete') {
          setContentProgress({ pct: 100, phase: 'Complete' })
          setTimeout(() => setContentProgress(null), 5000)
        } else if (p.status === 'error') {
          setContentProgress(null)
        } else {
          setContentProgress(null)
        }
      }
    } catch {
      // content progress unavailable
    }
  }, [])

  // Fetch on mount and poll every 30 seconds
  useEffect(() => {
    fetchDashboardData()
    const interval = setInterval(fetchDashboardData, 30_000)
    return () => clearInterval(interval)
  }, [fetchDashboardData])

  // Scan progress polling — every 2 seconds while dashboard is mounted
  useEffect(() => {
    fetchScanProgress()
    const interval = setInterval(fetchScanProgress, 2000)
    return () => clearInterval(interval)
  }, [fetchScanProgress])

  // Content generation progress polling — every 2 seconds
  useEffect(() => {
    fetchContentProgress()
    const interval = setInterval(fetchContentProgress, 2000)
    return () => clearInterval(interval)
  }, [fetchContentProgress])

  // Voice status polling — every 2 seconds
  useEffect(() => {
    fetchVoiceStatus()
    const interval = setInterval(fetchVoiceStatus, 2000)
    return () => clearInterval(interval)
  }, [fetchVoiceStatus])

  // Session uptime — ticks every second
  useEffect(() => {
    const timer = setInterval(() => {
      setUptime(formatUptime((Date.now() - uptimeStartRef.current) / 1000))
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  const isWolf = displayMode === 'wolf'
  const isSplit = displayMode === 'split'

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === 'cyan' ? 'gold' : 'cyan'))
  }, [])

  const handleKeyDown = useCallback((e: KeyboardEvent): void => {
    if (e.key === '1') setDisplayMode('default')
    else if (e.key === '2') setDisplayMode('split')
    else if (e.key === '3') setDisplayMode('wolf')
  }, [])

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  return (
    <div className="h-full w-full bg-[#0A0A0F] relative overflow-hidden">
      {/* Background layers */}
      {isWolf ? (
        <div className="absolute inset-0 z-0">
          <GuardianWolf fullscreen theme={theme} />
        </div>
      ) : isSplit ? (
        <div className="absolute inset-0 z-0 flex">
          <div className="w-1/2">
            <ArcReactor fullscreen theme={theme} />
          </div>
          <div className="w-1/2">
            <GuardianWolf fullscreen theme={theme} />
          </div>
        </div>
      ) : (
        <div className="absolute inset-0 z-0">
          <ArcReactor fullscreen theme={theme} />
        </div>
      )}

      {/* Content overlay */}
      <div className="relative z-10 h-full flex flex-col">
        {/* Mode toggle header */}
        <div className="flex items-center justify-between px-6 py-2 border-b border-[#00E5FF]/8">
          {/* Mode toggle buttons */}
          <div className="flex items-center gap-1">
            {(Object.entries(MODE_LABELS) as [DisplayMode, { label: string; icon: string }][]).map(
              ([mode, { label, icon }]) => (
                <button
                  key={mode}
                  onClick={() => setDisplayMode(mode)}
                  className={`flex items-center gap-1 px-2.5 py-1 rounded text-[9px] font-share-tech tracking-wider uppercase transition-all duration-200 ${
                    displayMode === mode
                      ? 'bg-[#00E5FF]/12 text-[#00E5FF] shadow-[0_0_8px_rgba(0,229,255,0.15)]'
                      : 'text-[#00E5FF]/30 hover:text-[#00E5FF]/60 hover:bg-[#00E5FF]/5'
                  }`}
                >
                  <span className="text-[11px]">{icon}</span>
                  <span>{mode === 'default' ? '①' : mode === 'split' ? '②' : '③'}</span>
                </button>
              ),
            )}
          </div>

          {/* Theme toggle */}
          <button
            onClick={toggleTheme}
            className="flex items-center gap-1.5 px-2 py-1 rounded text-[9px] font-share-tech tracking-wider uppercase transition-all duration-200 text-[#00E5FF]/30 hover:text-[#00E5FF]/60 hover:bg-[#00E5FF]/5"
          >
            <span>{theme === 'cyan' ? '❄' : '☀'}</span>
            <span>{theme === 'cyan' ? 'CYAN' : 'GOLD'}</span>
          </button>
        </div>

        {/* Main content area */}
        <div className="flex-1 flex items-stretch px-4 pb-4 gap-2">
          {/* LEFT: Monitor panel with left-side stats */}
          {!isWolf && (
            <ArcMonitorPanel
              side="left"
              quickActions={[
                {
                  label: 'VOICE CMD',
                  value: voiceCmd,
                  subtitle: 'recent cmds',
                  status: {
                    active: voiceListening,
                    label: voiceListening ? 'LISTENING' : 'IDLE',
                  },
                },
                {
                  label: 'JOBS SCAN',
                  value: scanProgress ? `${scanProgress.pct}%` : jobsScan,
                  subtitle: scanProgress ? scanProgress.phase : 'total scanned',
                  progress: scanProgress ?? undefined,
                  onAction: scanProgress ? undefined : handleScanNow,
                },
              ]}
            />
          )}

          {/* CENTER: Empty — just the background reactor/wolf visible */}
          <div className="flex-1" />

          {/* RIGHT: Monitor panel with right-side stats + weather */}
          {!isWolf && (
            <ArcMonitorPanel
              side="right"
              quickActions={[
                {
                  label: 'SCRIPTS',
                  value: contentProgress ? `${contentProgress.pct}%` : scripts,
                  subtitle: contentProgress ? contentProgress.phase : 'generated',
                  progress: contentProgress ?? undefined,
                },
                { label: 'UPTIME', value: uptime, subtitle: 'session' },
              ]}
              weather={weather}
            />
          )}
        </div>
      </div>

      <AiChatPanel />
    </div>
  )
}
