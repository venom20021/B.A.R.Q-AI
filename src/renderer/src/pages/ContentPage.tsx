import { useState } from 'react'
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

const sampleIdeas: ContentIdea[] = [
  {
    id: '1',
    topic: 'Top 5 AI Tools for Productivity in 2025',
    platform: 'YouTube',
    format: 'Video Essay',
    status: 'scripted',
    score: 88
  },
  {
    id: '2',
    topic: 'Why Remote Work is Here to Stay',
    platform: 'TikTok',
    format: 'Short',
    status: 'ready',
    score: 92
  },
  {
    id: '3',
    topic: 'How I Automated My Job Search',
    platform: 'Instagram',
    format: 'Reel',
    status: 'idea',
    score: 76
  }
]

const statusConfig: Record<ContentIdea['status'], { icon: typeof Lightbulb; color: string; bg: string }> = {
  idea: { icon: Lightbulb, color: 'text-dim-400', bg: 'bg-void-700' },
  scripted: { icon: FileText, color: 'text-cyan-300', bg: 'bg-cyan-500/10' },
  rendering: { icon: Loader2, color: 'text-plasma', bg: 'bg-plasma-500/10' },
  ready: { icon: Play, color: 'text-neural', bg: 'bg-neural-500/10' },
  posted: { icon: CheckCircle, color: 'text-dim-400', bg: 'bg-void-700' },
}

export function ContentPage(): JSX.Element {
  const [selectedIdea, setSelectedIdea] = useState<string | null>(null)

  const handleGenerateScript = async (topic: string): Promise<void> => {
    await window.barq?.social.generateScript(topic, 'short')
  }

  const handleRender = async (scriptId: string): Promise<void> => {
    await window.barq?.social.renderVideo(scriptId)
  }

  const handlePost = async (videoId: string): Promise<void> => {
    await window.barq?.social.post(videoId, ['youtube', 'tiktok', 'instagram'])
  }

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
        <button className="btn-cyan flex items-center gap-2">
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
        {[
          { label: 'Trend Research', icon: Globe, count: 24, active: true },
          { label: 'Scripting', icon: FileText, count: 8, active: true },
          { label: 'Rendering', icon: Video, count: 3, active: true },
          { label: 'Ready to Post', icon: Play, count: 5, active: true },
          { label: 'Published', icon: CheckCircle, count: 12, active: false }
        ].map((stage) => {
          const Icon = stage.icon
          return (
            <div
              key={stage.label}
              className={`glass-card text-center transition-all duration-200 ${
                stage.active ? 'hover:border-cyan-500/20' : 'opacity-50'
              }`}
            >
              <Icon className="w-5 h-5 mx-auto mb-2 text-dim-400" />
              <p className="text-hud font-share-tech text-dim-400 uppercase tracking-wider">{stage.label}</p>
              <p className="text-xl font-orbitron font-bold text-ghost mt-1">{stage.count}</p>
            </div>
          )
        })}
      </motion.div>

      {/* Content Ideas */}
      <div className="space-y-4">
        <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Content Ideas</h3>
        {sampleIdeas.map((idea, i) => {
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
                    <span className={`font-semibold ${
                      idea.score >= 85 ? 'text-neural' : 'text-plasma'
                    }`}>
                      Score: {idea.score}
                    </span>
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
    </div>
  )
}
