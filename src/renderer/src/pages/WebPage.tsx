import { useState, useCallback } from 'react'
import { Globe, Music, TrendingUp, CloudSun, Map, Image as ImageIcon, Loader2, ExternalLink } from 'lucide-react'
import { motion } from 'framer-motion'

export function WebPage(): JSX.Element {
  const [url, setUrl] = useState('')
  const [browseResult, setBrowseResult] = useState('')
  const [browsing, setBrowsing] = useState(false)
  const [ticker, setTicker] = useState('')
  const [stockData, setStockData] = useState<{ company?: string; current_price?: number; change_percent?: number } | null>(null)
  const [stockLoading, setStockLoading] = useState(false)
  const [city, setCity] = useState('')
  const [weather, setWeather] = useState<{ temperature_c?: number; description?: string; humidity?: number } | null>(null)
  const [weatherLoading, setWeatherLoading] = useState(false)
  const [imagePrompt, setImagePrompt] = useState('')
  const [imageUrl, setImageUrl] = useState('')
  const [generating, setGenerating] = useState(false)

  const handleBrowse = useCallback(async () => {
    if (!url.trim()) return
    setBrowsing(true)
    try {
      const resp = await window.barq?.python.request('/web/browse', {
        method: 'POST',
        body: JSON.stringify({ url: url.startsWith('http') ? url : `https://${url}`, action: 'navigate' }),
        headers: { 'Content-Type': 'application/json' },
      })
      if (resp && typeof resp === 'object') {
        const data = resp as { title?: string; body_text?: string; status?: string }
        setBrowseResult(data.title || data.body_text || data.status || 'No content')
      }
    } catch {
      setBrowseResult('Browse failed')
    }
    setBrowsing(false)
  }, [url])

  const handleStock = useCallback(async () => {
    if (!ticker.trim()) return
    setStockLoading(true)
    setStockData(null)
    try {
      const resp = await window.barq?.python.request(`/web/stocks/${encodeURIComponent(ticker.toUpperCase())}`)
      if (resp && typeof resp === 'object') setStockData(resp as typeof stockData)
    } catch { /* ignore */ }
    setStockLoading(false)
  }, [ticker])

  const handleWeather = useCallback(async () => {
    if (!city.trim()) return
    setWeatherLoading(true)
    setWeather(null)
    try {
      const resp = await window.barq?.python.request(`/web/weather?city=${encodeURIComponent(city)}`)
      if (resp && typeof resp === 'object') setWeather(resp as typeof weather)
    } catch { /* ignore */ }
    setWeatherLoading(false)
  }, [city])

  const handleGenerate = useCallback(async () => {
    if (!imagePrompt.trim()) return
    setGenerating(true)
    setImageUrl('')
    try {
      const resp = await window.barq?.python.request('/web/images/generate', {
        method: 'POST',
        body: JSON.stringify({ prompt: imagePrompt, style: 'auto' }),
        headers: { 'Content-Type': 'application/json' },
      })
      if (resp && typeof resp === 'object') {
        const data = resp as { image_url?: string; status?: string }
        if (data.image_url) setImageUrl(data.image_url)
      }
    } catch { /* ignore */ }
    setGenerating(false)
  }, [imagePrompt])

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">WEB & MEDIA</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">Browser agent, Spotify, stocks, weather, maps, and image generation</p>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {/* Web Agent */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card-hover">
          <Globe className="w-5 h-5 text-cyan-300 mb-3" />
          <h3 className="text-sm font-rajdhani font-semibold text-ghost mb-1">Web Agent</h3>
          <p className="text-xs font-exo text-dim-400">Browse, click, fill forms, scrape — all by voice</p>
          <div className="mt-3 flex gap-2">
            <input type="text" value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleBrowse()} placeholder="URL or search query..." className="input-cyan flex-1 text-sm" />
            <button onClick={handleBrowse} disabled={browsing} className="btn-cyan text-sm">{browsing ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Go'}</button>
          </div>
          {browseResult && <p className="text-xs font-exo text-dim-400 mt-2 truncate">{browseResult}</p>}
        </motion.div>

        {/* Spotify */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="glass-card-hover">
          <Music className="w-5 h-5 text-neural mb-3" />
          <h3 className="text-sm font-rajdhani font-semibold text-ghost mb-1">Spotify Control</h3>
          <p className="text-xs font-exo text-dim-400 mb-3">Say: &quot;Play some music&quot; or &quot;Skip track&quot;</p>
          <div className="flex gap-2">
            {['play', 'pause', 'skip'].map((action) => (
              <button key={action} onClick={async () => { await window.barq?.python.request('/web/spotify', { method: 'POST', body: JSON.stringify({ action }), headers: { 'Content-Type': 'application/json' } }) }} className="btn-ghost-cyan text-xs capitalize">{action}</button>
            ))}
          </div>
        </motion.div>

        {/* Stocks */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="glass-card-hover">
          <TrendingUp className="w-5 h-5 text-plasma mb-3" />
          <h3 className="text-sm font-rajdhani font-semibold text-ghost mb-1">Stock Market</h3>
          <p className="text-xs font-exo text-dim-400">Enter a ticker symbol below</p>
          <div className="mt-3 flex gap-2">
            <input type="text" value={ticker} onChange={(e) => setTicker(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleStock()} placeholder="Ticker (e.g., AAPL)" className="input-cyan flex-1 text-sm" />
            <button onClick={handleStock} disabled={stockLoading} className="btn-glass text-sm">{stockLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Search'}</button>
          </div>
          {stockData && (
            <div className="mt-2 text-xs font-exo">
              <span className="text-ghost">{stockData.company}</span>
              <span className="text-dim-400 ml-2">${stockData.current_price?.toFixed(2)}</span>
              <span className={`ml-1 ${stockData.change_percent && stockData.change_percent >= 0 ? 'text-neural' : 'text-red-400'}`}>
                {stockData.change_percent != null ? `${(stockData.change_percent >= 0 ? '+' : '')}${(stockData.change_percent * 100).toFixed(2)}%` : ''}
              </span>
            </div>
          )}
        </motion.div>

        {/* Weather */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="glass-card-hover">
          <CloudSun className="w-5 h-5 text-cyan-300 mb-3" />
          <h3 className="text-sm font-rajdhani font-semibold text-ghost mb-1">Weather</h3>
          <p className="text-xs font-exo text-dim-400">Check current conditions</p>
          <div className="mt-3 flex gap-2">
            <input type="text" value={city} onChange={(e) => setCity(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleWeather()} placeholder="City name..." className="input-cyan flex-1 text-sm" />
            <button onClick={handleWeather} disabled={weatherLoading} className="btn-glass text-sm">{weatherLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Check'}</button>
          </div>
          {weather && (
            <div className="mt-2 text-xs font-exo">
              <span className="text-ghost">{weather.temperature_c?.toFixed(1)}°C</span>
              <span className="text-dim-400 ml-2 capitalize">{weather.description}</span>
              <span className="text-dim-500 ml-2">Humidity: {weather.humidity}%</span>
            </div>
          )}
        </motion.div>

        {/* Maps */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="glass-card-hover">
          <Map className="w-5 h-5 text-plasma mb-3" />
          <h3 className="text-sm font-rajdhani font-semibold text-ghost mb-1">Maps</h3>
          <p className="text-xs font-exo text-dim-400">Say: &quot;Show map of Tokyo&quot; or &quot;Directions to airport&quot;</p>
        </motion.div>

        {/* Image Generation */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }} className="glass-card-hover">
          <ImageIcon className="w-5 h-5 text-holographic mb-3" />
          <h3 className="text-sm font-rajdhani font-semibold text-ghost mb-1">Image Generation</h3>
          <p className="text-xs font-exo text-dim-400">Generate images from descriptions</p>
          <div className="mt-3 flex gap-2">
            <input type="text" value={imagePrompt} onChange={(e) => setImagePrompt(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleGenerate()} placeholder="Image description..." className="input-cyan flex-1 text-sm" />
            <button onClick={handleGenerate} disabled={generating} className="btn-cyan text-sm">{generating ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Generate'}</button>
          </div>
          {imageUrl && (
            <a href={imageUrl} target="_blank" rel="noopener noreferrer" className="mt-2 flex items-center gap-1 text-xs font-exo text-neural hover:underline">
              <ExternalLink className="w-3 h-3" /> View Image
            </a>
          )}
        </motion.div>
      </div>
    </div>
  )
}
