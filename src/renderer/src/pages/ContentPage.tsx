import { useState, useEffect, useCallback } from 'react'
import { Video, Lightbulb, FileText, Globe, Play, CheckCircle, Loader2 } from 'lucide-react'
import { motion } from 'framer-motion'

interface ContentIdea {
  id: string
  topic: string
  platform: string
  format: string
  status: 'idea' | 'scripted' | 'rendering' | 'ready' | 'posted'
  score: number
}

const statusConfig: Record<ContentIdea['status'], { icon: typeof Lightbulb; color: string; bg: string }> = {
  idea: { icon: Lightbulb, color: 'text-dim-400', bg: 'bg-void-700' },
  scripted: { icon: FileText, color: 'text-cyan-300', bg: 'bg-cyan-500/10' },
  rendering: { icon: Loader2, color: 'text-plasma', bg: 'bg-plasma-500/10' },
  ready: { icon: Play, color: 'text-neural', bg: 'bg-neural-500/10' },
  posted: { icon: CheckCircle, color: 'text-dim-400', bg: 'bg-void-700' },
}

export function ContentPage(): JSX.Element {
  const [loading, setLoading] = useState(true)
  const [pipelineCounts, setPipelineCounts] = useState<Record<string, number>>({})
  const [scripts, setScripts] = useState<ContentIdea[]>([])
  const [selectedIdea, setSelectedIdea] = useState<string | null>(null)

  const fetchPipeline = useCallback(async () => {
    setLoading(true)
    try {
      const [pipelineResp, scriptsResp] = await Promise.allSettled([
        window.barq?.python.request('/social/pipeline') ?? Promise.resolve(undefined),
        window.barq?.python.request('/social/scripts?limit=50') ?? Promise.resolve(undefined),
      ])

      const pipeline = (pipelineResp.status === 'fulfilled' ? pipelineResp.value : undefined) as
        { success?: boolean; data?: { pipeline?: Record<string, number> } } | undefined
      setPipelineCounts(pipeline?.data?.pipeline ?? {})

      const scriptsData = (scriptsResp.status === 'fulfilled' ? scriptsResp.value : undefined) as
        { success?: boolean; data?: { scripts?: Record<string, unknown>[] } } | undefined
      const rawScripts = scriptsData?.data?.scripts ?? []
      setScripts(rawScripts.slice(0, 20).map((s, i) => ({
        id: String(s['id'] ?? i),
        topic: String(s['title'] ?? s['topic'] ?? 'Untitled'),
        platform: String(s['platform'] ?? 'YouTube'),
        format: String(s['format'] ?? 'Short'),
        status: (s['status'] === 'draft' ? 'scripted' : s['status'] === 'rendering' ? 'rendering' : s['status'] === 'rendered' ? 'ready' : 'idea') as ContentIdea['status'],
        score: Number(s['score'] ?? 0),
      })))
    } catch {
      setPipelineCounts({})
      setScripts([])
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchPipeline()
  }, [fetchPipeline])

  const handleGenerateScript = async (topic: string): Promise<void> => {
    await window.barq?.social.generateScript(topic, 'short')
    await fetchPipeline()
  }

  const handleRender = async (scriptId: string): Promise<void> => {
    await window.barq?.social.renderVideo(scriptId)
    await fetchPipeline()
  }

  const handlePost = async (videoId: string): Promise<void> => {
    await window.barq?.social.post(videoId, ['youtube', 'tiktok', 'instagram'])
    await fetchPipeline()
  }

  const stageLabels = [
    { label: 'Trend Research', icon: Globe, key: 'trends' },
    { label: 'Scripting', icon: FileText, key: 'draft_scripts' },
    { label: 'Rendering', icon: Video, key: 'rendering' },
    { label: 'Ready to Post', icon: Play, key: 'completed' },
    { label: 'Published', icon: CheckCircle, key: 'posted' },
  ]

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">CONTENT STUDIO</h1>
          <p className="text-sm font-rajdhani text-dim-400 mt-1">
            AI-powered content creation pipeline from trend to post
          </p>
        </div>
        <button
          onClick={() => handleGenerateScript('trending topic')}
          className="btn-cyan flex items-center gap-2"
        >
          <Lightbulb className="w-4 h-4" />
          Generate Ideas
        </button>
      </motion.div>

      {/* Pipeline Overview */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="grid grid-cols-5 gap-3"
      >
        {stageLabels.map((stage) => {
          const Icon = stage.icon
          const count = pipelineCounts[stage.key] ?? 0
          return (
            <div
              key={stage.label}
              className={`glass-card text-center transition-all duration-200 ${
                count > 0 ? 'hover:border-cyan-500/20' : 'opacity-50'
              }`}
            >
              <Icon className="w-5 h-5 mx-auto mb-2 text-dim-400" />
              <p className="text-hud font-share-tech text-dim-400 uppercase tracking-wider">{stage.label}</p>
              <p className="text-xl font-orbitron font-bold text-ghost mt-1">{count}</p>
            </div>
          )
        })}
      </motion.div>

      {/* Content Ideas / Scripts */}
      <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">
        {scripts.length > 0 ? 'Scripts & Ideas' : 'Generated Scripts'}
      </h3>
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-6 h-6 text-cyan-300 animate-spin" />
          <span className="ml-3 text-sm font-rajdhani text-dim-400">Loading pipeline...</span>
        </div>
      ) : scripts.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-sm font-rajdhani text-dim-400">
            No content yet. Click "Generate Ideas" to start creating.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {scripts.map((idea, i) => {
            const StatusIcon = statusConfig[idea.status].icon
            const sCfg = statusConfig[idea.status]
            const isSelected = selectedIdea === idea.id

            return (
              <motion.div
                key={idea.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                onClick={() => setSelectedIdea(idea.id)}
                className={`glass-card-hover cursor-pointer ${
                  isSelected ? 'border-cyan-500/30 shadow-glow-cyan-sm' : ''
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="space-y-2 flex-1">
                    <div className="flex items-center gap-3">
                      <h3 className="text-base font-rajdhani font-semibold text-ghost">{idea.topic}</h3>
                      <div className={`p-1.5 rounded-lg ${sCfg.bg}`}>
                        <StatusIcon className={`w-4 h-4 ${sCfg.color} ${idea.status === 'rendering' ? 'animate-spin' : ''}`} />
                      </div>
                    </div>
                    <div className="flex items-center gap-3 text-sm font-exo text-dim-400">
                      <span className="badge-cyan text-hud">{idea.platform}</span>
                      <span>{idea.format}</span>
                      {idea.score > 0 && (
                        <span className={`font-semibold ${
                          idea.score >= 85 ? 'text-neural' : 'text-plasma'
                        }`}>
                          Score: {idea.score}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  {isSelected && (
                    <div className="flex items-center gap-2 ml-4">
                      {idea.status === 'idea' && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleGenerateScript(idea.topic)
                          }}
                          className="btn-cyan text-sm"
                        >
                          Generate Script
                        </button>
                      )}
                      {idea.status === 'scripted' && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleRender(idea.id)
                          }}
                          className="btn-glass text-sm"
                        >
                          Render Video
                        </button>
                      )}
                      {idea.status === 'ready' && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handlePost(idea.id)
                          }}
                          className="btn-cyan text-sm"
                        >
                          Post Now
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </motion.div>
            )
          })}
        </div>
      )}
    </div>
  )
}
