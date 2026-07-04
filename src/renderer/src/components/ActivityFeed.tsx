import { motion } from 'framer-motion'
import { Briefcase, Video, BarChart3, Settings, type LucideIcon } from 'lucide-react'
import { formatDistanceToNow } from '../utils/time'

export interface Activity {
  id: string
  type: 'job' | 'content' | 'analytics' | 'system'
  title: string
  description: string
  timestamp: Date
}

interface ActivityFeedProps {
  activities: Activity[]
}

const typeConfig: Record<
  Activity['type'],
  { icon: LucideIcon; accent: string; dotColor: string; label: string }
> = {
  job: {
    icon: Briefcase,
    accent: 'border-l-cyan-500',
    dotColor: 'bg-cyan-300 shadow-glow-cyan-sm',
    label: 'JOB',
  },
  content: {
    icon: Video,
    accent: 'border-l-holographic',
    dotColor: 'bg-holographic shadow-glow-purple',
    label: 'CONTENT',
  },
  analytics: {
    icon: BarChart3,
    accent: 'border-l-neural',
    dotColor: 'bg-neural shadow-glow-green',
    label: 'ANALYTICS',
  },
  system: {
    icon: Settings,
    accent: 'border-l-dim',
    dotColor: 'bg-dim',
    label: 'SYSTEM',
  },
}

function formatTime(date: Date): string {
  return formatDistanceToNow(date)
}

export function ActivityFeed({ activities }: ActivityFeedProps): JSX.Element {
  if (activities.length === 0) {
    return (
      <div className="glass-card text-center py-12">
        <p className="text-sm font-rajdhani text-dim-400">No recent activity</p>
      </div>
    )
  }

  return (
    <div className="glass-card">
      <div className="flex items-center justify-between mb-5">
        <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">
          ACTIVITY FEED
        </h3>
        <span className="text-hud font-share-tech text-dim-400">
          {activities.length} events
        </span>
      </div>

      <div className="relative">
        {/* Timeline line */}
        <div className="absolute left-[11px] top-2 bottom-2 w-px bg-gradient-to-b from-cyan-500/20 via-cyan-500/10 to-transparent" />

        <div className="space-y-3">
          {activities.map((activity, i) => {
            const cfg = typeConfig[activity.type]
            const Icon = cfg.icon
            return (
              <motion.div
                key={activity.id}
                initial={{ opacity: 0, x: -15 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.25, delay: i * 0.05 }}
                className={`relative flex items-start gap-4 pl-8 border-l-2 ${cfg.accent} border-l-transparent`}
              >
                {/* Timeline dot */}
                <div className={`absolute left-[-5px] top-1.5 w-2.5 h-2.5 rounded-full ${cfg.dotColor} ring-2 ring-void-700`} />

                {/* Icon */}
                <div className="flex-shrink-0 mt-0.5">
                  <Icon className={`w-4 h-4 ${
                    activity.type === 'job' ? 'text-cyan-300' :
                    activity.type === 'content' ? 'text-holographic' :
                    activity.type === 'analytics' ? 'text-neural' :
                    'text-dim-400'
                  }`} />
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-hud font-share-tech uppercase tracking-wider text-dim-500">
                      {cfg.label}
                    </span>
                    <span className="text-hud font-share-tech text-dim-500">
                      {formatTime(activity.timestamp)}
                    </span>
                  </div>
                  <p className="text-sm font-rajdhani font-semibold text-ghost mt-0.5">
                    {activity.title}
                  </p>
                  <p className="text-xs font-exo text-dim-400 mt-0.5 truncate">
                    {activity.description}
                  </p>
                </div>
              </motion.div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
