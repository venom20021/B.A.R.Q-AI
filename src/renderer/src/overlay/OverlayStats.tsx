type StatsData = {
  cpu_percent: number
  memory: { used_gb: number; total_gb: number; percent: number }
  disk: { used_gb: number; total_gb: number; percent: number }
  hostname: string
  uptime: string
  loaded: boolean
} | null | undefined

interface OverlayStatsProps {
  stats: StatsData
}

function barClass(percent: number): string {
  if (percent > 85) return 'high'
  if (percent > 65) return 'med'
  if (percent > 40) return 'low'
  return 'cyan'
}

export function OverlayStats({ stats }: OverlayStatsProps): JSX.Element {
  if (!stats || !stats.loaded) {
    return (
      <div className="widget-panel stats-widget">
        <div className="widget-label">System</div>
        <div className="widget-loading">
          <div className="widget-loading-dot" />
          <div className="widget-loading-dot" />
          <div className="widget-loading-dot" />
        </div>
      </div>
    )
  }

  const cpuPct = Math.min(stats.cpu_percent, 100)
  const memPct = Math.min(stats.memory.percent, 100)
  const diskPct = Math.min(stats.disk.percent, 100)

  return (
    <div className="widget-panel stats-widget">
      <div className="widget-label">{stats.hostname}</div>

      <div className="stat-row">
        <span className="stat-label">CPU</span>
        <div className="stat-bar-bg">
          <div className={`stat-bar-fill ${barClass(cpuPct)}`} style={{ width: `${cpuPct}%` }} />
        </div>
        <span className="stat-value">{cpuPct}%</span>
      </div>

      <div className="stat-row">
        <span className="stat-label">RAM</span>
        <div className="stat-bar-bg">
          <div className={`stat-bar-fill ${barClass(memPct)}`} style={{ width: `${memPct}%` }} />
        </div>
        <span className="stat-value">{stats.memory.used_gb.toFixed(1)}G</span>
      </div>

      <div className="stat-row">
        <span className="stat-label">DSK</span>
        <div className="stat-bar-bg">
          <div className={`stat-bar-fill ${barClass(diskPct)}`} style={{ width: `${diskPct}%` }} />
        </div>
        <span className="stat-value">{stats.disk.used_gb.toFixed(0)}G</span>
      </div>
    </div>
  )
}
