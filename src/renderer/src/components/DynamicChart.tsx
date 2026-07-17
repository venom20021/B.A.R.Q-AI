/**
 * DynamicChart — Renders any Recharts chart from a JSON schema.
 *
 * Uses a registry-based pattern (no if/else chains) to map `schema.type`
 * to the correct Recharts components, making it extensible for new chart types.
 */

import { useId } from 'react'
import {
  BarChart, Bar, LineChart, Line, AreaChart, Area, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  type BarProps, type LineProps, type AreaProps,
} from 'recharts'
import { motion } from 'framer-motion'

// ─── Schema Types ───────────────────────────────────────────────────────

export interface DynamicChartConfig {
  xKey?: string
  yKey?: string
  nameKey?: string
  valueKey?: string
  xLabel?: string
  yLabel?: string
  color?: string
  colors?: string[]
  stacked?: boolean
  showLegend?: boolean
  showGrid?: boolean
  height?: number
}

export interface DynamicChartSchema {
  type: 'BarChart' | 'LineChart' | 'PieChart' | 'AreaChart' | 'RadialBarChart'
  title: string
  data: Record<string, unknown>[]
  config: DynamicChartConfig
}

interface DynamicChartProps {
  schema: DynamicChartSchema
}

// ─── Default palette for multi-series ──────────────────────────────────

const DEFAULT_COLORS = [
  '#6366f1', '#818cf8', '#a5b4fc', '#34d399', '#6ee7b7',
  '#fbbf24', '#fcd34d', '#f472b6', '#fb923c', '#a78bfa',
  '#2dd4bf', '#22d3ee', '#60a5fa', '#c084fc', '#e879f9',
]

function getColor(index: number, customColors?: string[]): string {
  const palette = (customColors && customColors.length > 0) ? customColors : DEFAULT_COLORS
  return palette[index % palette.length]
}

// ─── Custom Tooltip ────────────────────────────────────────────────────

function ChartTooltip({ active, payload, label }: {
  active?: boolean
  payload?: { name: string; value: number; color: string }[]
  label?: string
}): JSX.Element | null {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="rounded-xl bg-black/90 backdrop-blur-xl border border-white/10 shadow-2xl px-4 py-3">
      <p className="text-xs font-sans font-medium text-white/50 mb-1.5">{label}</p>
      {payload.map((entry, i) => (
        <div key={i} className="flex items-center gap-2 text-sm font-sans">
          <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: entry.color }} />
          <span className="text-white/70">{entry.name}: </span>
          <span className="text-white font-medium">{typeof entry.value === 'number' ? entry.value.toLocaleString() : entry.value}</span>
        </div>
      ))}
    </div>
  )
}

// ─── Component Registry ────────────────────────────────────────────────

/**
 * Each registry entry renders the chart content *inside* a <ResponsiveContainer>.
 * The function receives parsed config & data and returns JSX children.
 */
type ChartRenderer = (cfg: RequiredConfig, data: Record<string, unknown>[]) => React.ReactNode

interface RequiredConfig extends DynamicChartConfig {
  xKey: string
  yKey: string
  nameKey: string
  valueKey: string
  showLegend: boolean
  showGrid: boolean
}

function parseConfig(config: DynamicChartConfig): RequiredConfig {
  return {
    xKey: config.xKey ?? 'name',
    yKey: config.yKey ?? 'value',
    nameKey: config.nameKey ?? 'name',
    valueKey: config.valueKey ?? 'value',
    color: config.color,
    colors: config.colors,
    stacked: config.stacked,
    xLabel: config.xLabel,
    yLabel: config.yLabel,
    showLegend: config.showLegend ?? true,
    showGrid: config.showGrid ?? true,
    height: config.height,
  }
}

const chartRegistry: Record<string, ChartRenderer> = {
  BarChart: (cfg, data) => {
    const allKeys = Object.keys(data[0] ?? {}).filter(k => k !== cfg.xKey && typeof data[0]?.[k] === 'number')
    const singleKey = allKeys[0] ?? cfg.yKey
    const isStacked = cfg.stacked && allKeys.length > 1
    return (
      <>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
        <XAxis
          dataKey={cfg.xKey}
          tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }}
          axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
          tickLine={false}
          label={cfg.xLabel ? { value: cfg.xLabel, position: 'insideBottom', offset: -4, fill: 'rgba(255,255,255,0.2)', fontSize: 10 } : undefined}
        />
        <YAxis
          tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          label={cfg.yLabel ? { value: cfg.yLabel, angle: -90, position: 'insideLeft', fill: 'rgba(255,255,255,0.2)', fontSize: 10, style: { textAnchor: 'middle' } } : undefined}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
        {cfg.showLegend && <Legend wrapperStyle={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }} />}
        {isStacked ? (
          allKeys.map((key, i) => (
            <Bar
              key={key}
              dataKey={key}
              stackId="stack"
              fill={getColor(i, cfg.colors)}
              radius={[4, 4, 0, 0]}
              maxBarSize={40}
            />
          ))
        ) : singleKey ? (
          <Bar
            dataKey={singleKey}
            fill={cfg.color ?? getColor(0, cfg.colors)}
            radius={[6, 6, 0, 0]}
            maxBarSize={50}
          />
        ) : null}
      </>
    )
  },

  LineChart: (cfg, data) => {
    const allKeys = Object.keys(data[0] ?? {}).filter(k => k !== cfg.xKey && typeof data[0]?.[k] === 'number')
    const singleKey = allKeys[0] ?? cfg.yKey
    return (
      <>
        {cfg.showGrid && <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />}
        <XAxis
          dataKey={cfg.xKey}
          tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }}
          axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip content={<ChartTooltip />} />
        {cfg.showLegend && <Legend wrapperStyle={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }} />}
        {singleKey ? (
          <Line
            type="monotone"
            dataKey={singleKey}
            stroke={cfg.color ?? getColor(0, cfg.colors)}
            strokeWidth={2}
            dot={{ fill: cfg.color ?? getColor(0, cfg.colors), r: 3, strokeWidth: 0 }}
            activeDot={{ r: 5, fill: cfg.color ?? getColor(0, cfg.colors) }}
          />
        ) : allKeys.map((key, i) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            stroke={getColor(i, cfg.colors)}
            strokeWidth={2}
            dot={{ r: 3, strokeWidth: 0 }}
            activeDot={{ r: 5 }}
          />
        ))}
      </>
    )
  },

  AreaChart: (cfg, data) => {
    const allKeys = Object.keys(data[0] ?? {}).filter(k => k !== cfg.xKey && typeof data[0]?.[k] === 'number')
    const singleKey = allKeys[0] ?? cfg.yKey
    return (
      <>
        {cfg.showGrid && <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />}
        <XAxis
          dataKey={cfg.xKey}
          tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }}
          axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 11 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip content={<ChartTooltip />} />
        {cfg.showLegend && <Legend wrapperStyle={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }} />}
        {singleKey ? (
          <Area
            type="monotone"
            dataKey={singleKey}
            stroke={cfg.color ?? getColor(0, cfg.colors)}
            fill={cfg.color ?? getColor(0, cfg.colors)}
            fillOpacity={0.15}
            strokeWidth={2}
          />
        ) : allKeys.map((key, i) => (
          <Area
            key={key}
            type="monotone"
            dataKey={key}
            stroke={getColor(i, cfg.colors)}
            fill={getColor(i, cfg.colors)}
            fillOpacity={0.1}
            strokeWidth={2}
          />
        ))}
      </>
    )
  },

  PieChart: (cfg, data) => {
    return (
      <>
        <Pie
          data={data}
          dataKey={cfg.valueKey}
          nameKey={cfg.nameKey}
          cx="50%"
          cy="50%"
          innerRadius={60}
          outerRadius={100}
          paddingAngle={2}
        >
          {data.map((_, i) => (
            <Cell key={`cell-${i}`} fill={getColor(i, cfg.colors)} />
          ))}
        </Pie>
        <Tooltip content={<ChartTooltip />} />
        {cfg.showLegend && (
          <Legend
            wrapperStyle={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}
            formatter={(value: string) => (
              <span className="text-white/60 text-xs font-sans">{value}</span>
            )}
          />
        )}
      </>
    )
  },

  RadialBarChart: (cfg, data) => {
    // For simplicity, RadialBar uses BarChart rendering as fallback
    return chartRegistry.BarChart(cfg, data)
  },
}

// ─── Main Component ────────────────────────────────────────────────────

export function DynamicChart({ schema }: DynamicChartProps): JSX.Element {
  const id = useId()
  const cfg = parseConfig(schema.config)
  const renderer = chartRegistry[schema.type]
  const defaultHeight = schema.type === 'PieChart' ? 280 : 220

  if (!renderer) {
    return (
      <div className="flex items-center justify-center h-40 text-white/30 text-sm font-sans italic">
        Unsupported chart type: {schema.type}
      </div>
    )
  }

  if (!schema.data || schema.data.length === 0) {
    return (
      <div className="flex items-center justify-center h-40 text-white/30 text-sm font-sans italic">
        No data available
      </div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      className="w-full"
    >
      <ResponsiveContainer
        width="100%"
        height={cfg.height ?? defaultHeight}
        key={`${id}-${schema.type}`}
      >
        {/* We dynamically call the registry function and wrap in appropriate chart container */}
        <>
          {schema.type === 'BarChart' && (
            <BarChart data={schema.data} margin={{ top: 8, right: 8, left: -8, bottom: 4 }}>
              {renderer(cfg, schema.data)}
            </BarChart>
          )}
          {schema.type === 'LineChart' && (
            <LineChart data={schema.data} margin={{ top: 8, right: 8, left: -8, bottom: 4 }}>
              {renderer(cfg, schema.data)}
            </LineChart>
          )}
          {schema.type === 'AreaChart' && (
            <AreaChart data={schema.data} margin={{ top: 8, right: 8, left: -8, bottom: 4 }}>
              {renderer(cfg, schema.data)}
            </AreaChart>
          )}
          {schema.type === 'PieChart' && (
            <PieChart margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
              {renderer(cfg, schema.data)}
            </PieChart>
          )}
          {schema.type === 'RadialBarChart' && (
            <BarChart data={schema.data} margin={{ top: 8, right: 8, left: -8, bottom: 4 }}>
              {renderer(cfg, schema.data)}
            </BarChart>
          )}
        </>
      </ResponsiveContainer>
    </motion.div>
  )
}
