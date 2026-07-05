import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react'

export type AccentColor = 'cyan' | 'purple' | 'amber' | 'red'

interface ThemeContextValue {
  accent: AccentColor
  setAccent: (color: AccentColor) => void
}

const ThemeContext = createContext<ThemeContextValue>({
  accent: 'purple',
  setAccent: () => {},
})

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext)
}

// ─── Color Palettes ────────────────────────────────────────────────────────
// Matches Tailwind's shade scale for the accent color.
// a200 = light accent, a300 = medium-light, a400 = primary, a500 = bold, a600 = dark

interface Palette {
  '--a200': string; '--a300': string; '--a400': string; '--a500': string; '--a600': string;
  '--a200-rgb': string; '--a300-rgb': string; '--a400-rgb': string; '--a500-rgb': string;
}

const palettes: Record<AccentColor, Palette> = {
  cyan: {
    '--a200': '#33f5ff', '--a300': '#00f0ff', '--a400': '#00e6e6', '--a500': '#00b3b3', '--a600': '#008080',
    '--a200-rgb': '51,245,255', '--a300-rgb': '0,240,255', '--a400-rgb': '0,230,230', '--a500-rgb': '0,179,179',
  },
  purple: {
    '--a200': '#e9d5ff', '--a300': '#d8b4fe', '--a400': '#c084fc', '--a500': '#a855f7', '--a600': '#9333ea',
    '--a200-rgb': '233,213,255', '--a300-rgb': '216,180,254', '--a400-rgb': '192,132,252', '--a500-rgb': '168,85,247',
  },
  amber: {
    '--a200': '#fde68a', '--a300': '#fcd34d', '--a400': '#fbbf24', '--a500': '#f59e0b', '--a600': '#d97706',
    '--a200-rgb': '253,230,138', '--a300-rgb': '252,211,77', '--a400-rgb': '251,191,36', '--a500-rgb': '245,158,11',
  },
  red: {
    '--a200': '#fecaca', '--a300': '#fca5a5', '--a400': '#f87171', '--a500': '#ef4444', '--a600': '#dc2626',
    '--a200-rgb': '254,202,202', '--a300-rgb': '252,165,165', '--a400-rgb': '248,113,113', '--a500-rgb': '239,68,68',
  },
}

export function getAccentHex(accent: AccentColor, shade: keyof Palette): string {
  return palettes[accent][shade]
}

export function getAccentRGB(accent: AccentColor, shade: '--a400-rgb' | '--a500-rgb'): string {
  return palettes[accent][shade]
}

// ─── ThemeProvider ─────────────────────────────────────────────────────────

const STYLE_ID = 'barq-accent-override'

export function ThemeProvider({ children }: { children: ReactNode }): JSX.Element {
  const [accent, setAccentState] = useState<AccentColor>('purple')

  const setAccent = useCallback((color: AccentColor) => {
    setAccentState(color)
  }, [])

  // Apply CSS variables and inject override stylesheet
  useEffect(() => {
    const root = document.documentElement
    const p = palettes[accent]

    root.setAttribute('data-accent', accent)

    // Set CSS custom properties
    for (const [key, value] of Object.entries(p)) {
      root.style.setProperty(key, value)
    }

    // Inject/update stylesheet overriding the most common Tailwind accent classes
    const css = `
[data-accent] [class*="text-cyan-200"]:not([class*="text-cyan-200/"]) { color: var(--a200) !important; }
[data-accent] [class*="text-cyan-300"]:not([class*="text-cyan-300/"]) { color: var(--a300) !important; }
[data-accent] [class*="text-cyan-400"] { color: var(--a400) !important; }
[data-accent] [class*="text-cyan-500"] { color: var(--a500) !important; }
[data-accent] [class*="text-cyan-600"] { color: var(--a600) !important; }

[data-accent] [class*="text-purple-200"]:not([class*="text-purple-200/"]) { color: var(--a200) !important; }
[data-accent] [class*="text-purple-300"]:not([class*="text-purple-300/"]) { color: var(--a300) !important; }
[data-accent] [class*="text-purple-400"]:not([class*="text-purple-400/"]) { color: var(--a400) !important; }
[data-accent] [class*="text-purple-500"]:not([class*="text-purple-500/"]) { color: var(--a500) !important; }
[data-accent] [class*="text-purple-400/80"] { color: rgba(var(--a400-rgb), 0.8) !important; }
[data-accent] [class*="text-purple-400/70"] { color: rgba(var(--a400-rgb), 0.7) !important; }
[data-accent] [class*="text-purple-400/60"] { color: rgba(var(--a400-rgb), 0.6) !important; }
[data-accent] [class*="text-purple-400/50"] { color: rgba(var(--a400-rgb), 0.5) !important; }
[data-accent] [class*="text-purple-300/80"] { color: rgba(var(--a300-rgb), 0.8) !important; }
[data-accent] [class*="text-purple-300/60"] { color: rgba(var(--a300-rgb), 0.6) !important; }
[data-accent] [class*="text-purple-300/50"] { color: rgba(var(--a300-rgb), 0.5) !important; }

[data-accent] [class*="border-cyan-500/"] { border-color: rgba(var(--a500-rgb), 0.15) !important; }
[data-accent] [class*="border-cyan-400/"] { border-color: rgba(var(--a400-rgb), 0.2) !important; }
[data-accent] [class*="border-purple-500/"] { border-color: rgba(var(--a500-rgb), 0.15) !important; }

[data-accent] [class*="bg-cyan-500/"] { background-color: rgba(var(--a500-rgb), 0.15) !important; }
[data-accent] [class*="bg-cyan-400/"] { background-color: rgba(var(--a400-rgb), 0.15) !important; }
[data-accent] [class*="bg-purple-500/"] { background-color: rgba(var(--a500-rgb), 0.15) !important; }
[data-accent] [class*="bg-purple-400/"] { background: rgba(var(--a400-rgb), 0.6) !important; }

[data-accent] [class*="from-cyan-400"] { --tw-gradient-from: var(--a400) !important; }
[data-accent] [class*="to-cyan-600"] { --tw-gradient-to: var(--a600) !important; }

[data-accent] [class*="shadow-glow-cyan"] { box-shadow: 0 0 20px rgba(var(--a400-rgb), 0.3) !important; }
[data-accent] [class*="shadow-glow-purple"] { box-shadow: 0 0 20px rgba(var(--a400-rgb), 0.3) !important; }
[data-accent] [class*="shadow-glow-red"] { box-shadow: 0 0 20px rgba(var(--a500-rgb), 0.3) !important; }
[data-accent] [class*="shadow-glow-cyan-sm"] { box-shadow: 0 0 10px rgba(var(--a400-rgb), 0.2) !important; }

[data-accent] [class*="hover:border-cyan-500/"]:hover { border-color: rgba(var(--a500-rgb), 0.15) !important; }
[data-accent] [class*="hover:bg-cyan-500/"]:hover { background-color: rgba(var(--a500-rgb), 0.05) !important; }
[data-accent] [class*="hover:text-cyan-300"]:hover { color: var(--a300) !important; }
[data-accent] [class*="hover:border-purple-500/"]:hover { border-color: rgba(var(--a500-rgb), 0.5) !important; }
`

    let styleEl = document.getElementById(STYLE_ID) as HTMLStyleElement
    if (!styleEl) {
      styleEl = document.createElement('style')
      styleEl.id = STYLE_ID
      document.head.appendChild(styleEl)
    }
    styleEl.textContent = css
  }, [accent])

  return (
    <ThemeContext.Provider value={{ accent, setAccent }}>
      {children}
    </ThemeContext.Provider>
  )
}
