import { useState, useEffect, useCallback, startTransition } from 'react'
import { api } from '../utils/api'
import {
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
  const [careerData, setCareerData] = useState<{
    jobsScanned: number
    matchesFound: number
    applications: number
    interviews: number
    offers: number
  } | null>(null)

  const [socialData, setSocialData] = useState<{
    totalViews: number
    totalEngagement: number
    followersGained: number
    revenue: number
  } | null>(null)

  const [platforms, setPlatforms] = useState<{
    name: string
    followers: number
    views: number
    revenue: number
  }[]>([])

  const fetchAnalytics = useCallback(async () => {
    const [careerResp, socialResp] = await Promise.all([
      api<{ funnel?: Record<string, number> }>('/analytics/career'),
      api<{ overview?: { platforms?: { platform: string; followers: number; views: number; revenue: number; engagement?: number }[]; total_revenue?: number } }>('/analytics/social'),
    ])

    // Parse career data
    const funnel = careerResp?.funnel
    if (funnel) {
      setCareerData({
        jobsScanned: funnel['jobs_scanned'] ?? 0,
        matchesFound: funnel['matches_found'] ?? 0,
        applications: funnel['applications'] ?? 0,
        interviews: funnel['interviews'] ?? 0,
        offers: funnel['offers'] ?? 0,
      })
    }

    // Parse social data
    const overview = socialResp?.overview
    const plats = overview?.platforms ?? []
    setSocialData({
      totalViews: plats.reduce((s, p) => s + (p.views ?? 0), 0),
      totalEngagement: plats.reduce((s, p) => s + (p.engagement ?? 0), 0),
      followersGained: plats.reduce((s, p) => s + (p.followers ?? 0), 0),
      revenue: overview?.total_revenue ?? 0,
    })
    setPlatforms(plats.map((p) => ({
      name: p.platform,
      followers: p.followers ?? 0,
      views: p.views ?? 0,
      revenue: p.revenue ?? 0,
    })))
  }, [])

  useEffect(() => {
    startTransition(() => { void fetchAnalytics() })
  }, [fetchAnalytics])

  const fmt = (n: number): string =>
    n >= 1000 ? `${(n / 1000).toFixed(1)}K` : String(n)

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
          <StatCard title="Jobs Scanned" value={fmt(careerData?.jobsScanned ?? 0)} icon={Search} accent="cyan" />
          <StatCard title="Matches Found" value={fmt(careerData?.matchesFound ?? 0)} icon={Crosshair} accent="cyan" />
          <StatCard title="Applications" value={fmt(careerData?.applications ?? 0)} icon={Send} accent="green" />
          <StatCard title="Interviews" value={fmt(careerData?.interviews ?? 0)} icon={Users} accent="plasma" />
          <StatCard title="Offers" value={fmt(careerData?.offers ?? 0)} icon={Award} accent="green" />
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
          <StatCard title="Total Views" value={fmt(socialData?.totalViews ?? 0)} icon={Eye} trend={{ value: 32, isPositive: true }} accent="cyan" />
          <StatCard title="Total Engagement" value={fmt(socialData?.totalEngagement ?? 0)} icon={MousePointerClick} trend={{ value: 18, isPositive: true }} accent="green" />
          <StatCard title="Followers Gained" value={fmt(socialData?.followersGained ?? 0)} icon={Users} trend={{ value: 45, isPositive: true }} accent="plasma" />
          <StatCard title="Revenue" value={`$${fmt(socialData?.revenue ?? 0)}`} icon={DollarSign} trend={{ value: 22, isPositive: true }} />
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
          {platforms.length === 0 ? (
            <p className="text-sm font-rajdhani text-dim-400 text-center py-4">
              No platform data yet. Connect your social accounts to see analytics.
            </p>
          ) : (
            platforms.map((platform) => (
              <div
                key={platform.name}
                className="flex items-center justify-between py-3 border-b border-cyan-500/10 last:border-0"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 bg-void-700/80 rounded-lg flex items-center justify-center text-xs font-jetbrains font-bold text-cyan-300 border border-cyan-500/10">
                    {platform.name[0].toUpperCase()}
                  </div>
                  <div>
                    <p className="text-sm font-rajdhani font-semibold text-ghost">{platform.name}</p>
                    <p className="text-xs font-exo text-dim-400">{fmt(platform.followers)} followers</p>
                  </div>
                </div>
                <div className="flex items-center gap-8">
                  <div className="text-right">
                    <p className="text-sm font-rajdhani font-semibold text-ghost">{fmt(platform.views)}</p>
                    <p className="text-xs font-exo text-dim-400">Views</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-rajdhani font-semibold text-neural">${platform.revenue}</p>
                    <p className="text-xs font-exo text-dim-400">Revenue</p>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </motion.div>
    </div>
  )
}
