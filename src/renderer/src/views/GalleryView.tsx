import { useState } from 'react'
import { motion } from 'framer-motion'
import { ImageIcon, Sparkles, Loader2 } from 'lucide-react'

const SAMPLE_GALLERY = [
  { id: 1, prompt: 'Neon cyberpunk city', url: 'https://image.pollinations.ai/prompt/Neon%20cyberpunk%20city%20dark%20aesthetic', date: '2026-07-04' },
  { id: 2, prompt: 'Abstract quantum field', url: 'https://image.pollinations.ai/prompt/Abstract%20quantum%20energy%20field%20teal', date: '2026-07-04' },
  { id: 3, prompt: 'Mystical forest', url: 'https://image.pollinations.ai/prompt/Mystical%20dark%20forest%20with%20cyan%20lights', date: '2026-07-03' },
]

export default function GalleryView(): JSX.Element {
  const [prompt, setPrompt] = useState('')
  const [generating, setGenerating] = useState(false)
  const [images, setImages] = useState(SAMPLE_GALLERY)

  const generate = async () => {
    if (!prompt.trim() || generating) return
    setGenerating(true)
    try {
      const resp = await window.barq?.python.request('/web/images/generate', {
        method: 'POST',
        body: JSON.stringify({ prompt: prompt.trim(), style: 'auto' }),
        headers: { 'Content-Type': 'application/json' },
      })
      if (resp && typeof resp === 'object') {
        const d = resp as { image_url?: string }
        if (d.image_url) {
          setImages(prev => [{ id: Date.now(), prompt: prompt.trim(), url: d.image_url!, date: new Date().toISOString().slice(0, 10) }, ...prev])
          setPrompt('')
        }
      }
    } catch { /* ignore */ }
    setGenerating(false)
  }

  return (
    <div className="h-full flex flex-col p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-emerald-500/15 flex items-center justify-center">
            <ImageIcon className="w-4 h-4 text-emerald-400" />
          </div>
          <div>
            <h2 className="text-sm font-orbitron font-bold text-zinc-100 tracking-wider">GALLERY</h2>
            <p className="text-[10px] font-mono text-zinc-500">{images.length} generations</p>
          </div>
        </div>
      </div>

      <div className="flex gap-2 mb-6">
        <input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && generate()}
          placeholder="Describe an image to generate..."
          className="flex-1 px-4 py-2 bg-zinc-900/60 border border-white/5 rounded-lg text-xs font-mono text-zinc-300 placeholder-zinc-600 focus:outline-none focus:border-emerald-500/30 focus:shadow-[0_0_10px_rgba(16,185,129,0.1)] transition-all"
        />
        <button
          onClick={generate}
          disabled={generating || !prompt.trim()}
          className="flex items-center gap-1.5 px-4 py-2 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-lg text-[11px] font-bold tracking-wider uppercase hover:bg-emerald-500/20 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {generating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
          Generate
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {images.map((img, i) => (
            <motion.div
              key={img.id}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.05 }}
              className="group relative rounded-xl overflow-hidden border border-white/5 bg-zinc-900/40 aspect-square cursor-pointer hover:border-emerald-500/20 transition-all"
              onClick={() => window.open(img.url, '_blank')}
            >
              <img
                src={img.url}
                alt={img.prompt}
                className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
                loading="lazy"
              />
              <div className="absolute inset-x-0 bottom-0 p-2 bg-gradient-to-t from-black/80 to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
                <p className="text-[9px] font-mono text-zinc-300 truncate">{img.prompt}</p>
                <p className="text-[8px] font-mono text-zinc-500">{img.date}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  )
}
