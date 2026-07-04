import {
  BarChart3,
  TrendingUp,
  Users,
  Eye,
  DollarSign,
  MousePointerClick,
  Briefcase,
  Search,
  Crosshair,
  Send,
  Award
} from 'lucide-react'
import { motion } from 'framer-motion'
import { StatCard } from '../components/StatCard'

export function AnalyticsPage(): JSX.Element {
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">ANALYTICS</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">
          Track your career progress and content performance
        </p>
      </motion.div>

      {/* Career Analytics */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0 }}
      >
        <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-4 flex items-center gap-2">
          <Briefcase className="w-5 h-5 text-cyan-300" />
          Career Funnel
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <StatCard title="Jobs Scanned" value="1,247" icon={Search} accent="cyan" />
          <StatCard title="Matches Found" value="89" icon={Crosshair} accent="cyan" />
          <StatCard title="Applications" value="23" icon={Send} accent="green" />
          <StatCard title="Interviews" value="5" icon={Users} accent="plasma" />
          <StatCard title="Offers" value="2" icon={Award} accent="green" />
        </div>
      </motion.div>

      {/* Social Analytics */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-4 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-cyan-300" />
          Social Performance
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard title="Total Views" value="45.2K" icon={Eye} trend={{ value: 32, isPositive: true }} accent="cyan" />
          <StatCard title="Total Engagement" value="3,891" icon={MousePointerClick} trend={{ value: 18, isPositive: true }} accent="green" />
          <StatCard title="Followers Gained" value="247" icon={Users} trend={{ value: 45, isPositive: true }} accent="plasma" />
          <StatCard title="Revenue" value="$847" icon={DollarSign} trend={{ value: 22, isPositive: true }} />
        </div>
      </motion.div>

      {/* Platform Breakdown */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="glass-card"
      >
        <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider mb-4">Platform Breakdown</h3>
        <div className="space-y-4">
          {[
            { name: 'YouTube', followers: 1240, views: 28200, revenue: 420 },
            { name: 'TikTok', followers: 3420, views: 12500, revenue: 180 },
            { name: 'Instagram', followers: 1890, views: 3500, revenue: 120 },
            { name: 'Twitter/X', followers: 560, views: 1000, revenue: 127 }
          ].map((platform) => (
            <div
              key={platform.name}
              className="flex items-center justify-between py-3 border-b border-cyan-500/10 last:border-0"
            >
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 bg-void-700/80 rounded-lg flex items-center justify-center text-xs font-jetbrains font-bold text-cyan-300 border border-cyan-500/10">
                  {platform.name[0]}
                </div>
                <div>
                  <p className="text-sm font-rajdhani font-semibold text-ghost">{platform.name}</p>
                  <p className="text-xs font-exo text-dim-400">{platform.followers.toLocaleString()} followers</p>
                </div>
              </div>
              <div className="flex items-center gap-8">
                <div className="text-right">
                  <p className="text-sm font-rajdhani font-semibold text-ghost">{platform.views.toLocaleString()}</p>
                  <p className="text-xs font-exo text-dim-400">Views</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-rajdhani font-semibold text-neural">${platform.revenue}</p>
                  <p className="text-xs font-exo text-dim-400">Revenue</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  )
}
