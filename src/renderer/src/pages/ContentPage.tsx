import { useState, useEffect, useCallback } from 'react'
import { api } from '../utils/api'
import { usePersistentState } from '../hooks/usePersistentState'
import {
  Video, Lightbulb, FileText, Globe, Play, CheckCircle, Loader2,
  Calendar, TrendingUp, Clock, Plus, X, ChevronLeft, ChevronRight,
  ExternalLink, Twitter, MessageCircle, Hash, BarChart3,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

// ─── Types ──────────────────────────────────────────────────────────────

interface ContentIdea {
  id: string
  topic: string
  platform: string
  format: string
  status: 'idea' | 'scripted' | 'rendering' | 'ready' | 'posted'
  score: number
}

interface Trend {
  id: string
  title: string
  source: string
  subreddit: string
  url: string
  score: number
  engagement: number
  fetched_at: string
  niche: string
}

interface CalendarPost {
  id: number
  video_id: number
  platform: string
  title: string
  description: string
  status: string
  scheduled_at: string
  posted_at: string
  type?: 'scheduled' | 'posted'
  video_title?: string
  script_format?: string
  topic?: string
}

interface CalendarDay {
  date: string
  posts: CalendarPost[]
  day: number
  isCurrentMonth: boolean
  isToday: boolean
}

interface CalendarData {
  year: number
  month: number
  days: Record<string, CalendarPost[]>
  total_scheduled: number
  total_posted: number
}

interface CalendarStats {
  total_scheduled: number
  total_posted: number
  scheduled_this_month: number
  platform_distribution: Record<string, number>
  videos_ready: number
  scripts_draft: number
}

// ─── Constants ──────────────────────────────────────────────────────────

const statusConfig: Record<ContentIdea['status'], { icon: typeof Lightbulb; color: string; bg: string }> = {
  idea: { icon: Lightbulb, color: 'text-dim-400', bg: 'bg-void-700' },
  scripted: { icon: FileText, color: 'text-cyan-300', bg: 'bg-cyan-500/10' },
  rendering: { icon: Loader2, color: 'text-plasma', bg: 'bg-plasma-500/10' },
  ready: { icon: Play, color: 'text-neural', bg: 'bg-neural-500/10' },
  posted: { icon: CheckCircle, color: 'text-dim-400', bg: 'bg-void-700' },
}

const PLATFORM_COLORS: Record<string, string> = {
  youtube: 'text-red-400',
  tiktok: 'text-pink-400',
  instagram: 'text-purple-400',
  twitter: 'text-sky-400',
  linkedin: 'text-blue-400',
}

const PLATFORM_ICONS: Record<string, string> = {
  youtube: '▶',
  tiktok: '♪',
  instagram: '📷',
  twitter: '𝕏',
  linkedin: 'in',
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

type Tab = 'pipeline' | 'calendar' | 'trends'

// ─── Helper Functions ────────────────────────────────────────────────────

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate()
}

function getFirstDayOfMonth(year: number, month: number): number {
  return new Date(year, month - 1, 1).getDay()
}

function getCalendarDays(year: number, month: number): CalendarDay[] {
  const daysInMonth = getDaysInMonth(year, month)
  const firstDay = getFirstDayOfMonth(year, month)
  const today = new Date()
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`

  const days: CalendarDay[] = []

  // Previous month fill
  const prevMonth = month === 1 ? 12 : month - 1
  const prevYear = month === 1 ? year - 1 : year
  const daysInPrevMonth = getDaysInMonth(prevYear, prevMonth)

  for (let i = firstDay - 1; i >= 0; i--) {
    const day = daysInPrevMonth - i
    const date = `${prevYear}-${String(prevMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    days.push({ date, posts: [], day, isCurrentMonth: false, isToday: date === todayStr })
  }

  // Current month
  for (let day = 1; day <= daysInMonth; day++) {
    const date = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    days.push({ date, posts: [], day, isCurrentMonth: true, isToday: date === todayStr })
  }

  // Next month fill
  const remaining = 42 - days.length // 6 rows × 7 days
  const nextMonth = month === 12 ? 1 : month + 1
  const nextYear = month === 12 ? year + 1 : year
  for (let day = 1; day <= remaining; day++) {
    const date = `${nextYear}-${String(nextMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    days.push({ date, posts: [], day, isCurrentMonth: false, isToday: date === todayStr })
  }

  return days
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatTime(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
}

// ─── Content Page Component ──────────────────────────────────────────────

export function ContentPage(): JSX.Element {
  const [activeTab, setActiveTab] = usePersistentState<Tab>('ContentPage.activeTab', 'pipeline')
  const [loading, setLoading] = useState(true)
  const [pipelineCounts, setPipelineCounts] = usePersistentState<Record<string, number>>('ContentPage.pipelineCounts', {})
  const [scripts, setScripts] = usePersistentState<ContentIdea[]>('ContentPage.scripts', [])
  const [selectedIdea, setSelectedIdea] = usePersistentState<string | null>('ContentPage.selectedIdea', null)

  // Calendar state
  const [calendarYear, setCalendarYear] = usePersistentState('ContentPage.calendarYear', new Date().getFullYear())
  const [calendarMonth, setCalendarMonth] = usePersistentState('ContentPage.calendarMonth', new Date().getMonth() + 1)
  const [calendarData, setCalendarData] = usePersistentState<CalendarData | null>('ContentPage.calendarData', null)
  const [calendarStats, setCalendarStats] = usePersistentState<CalendarStats | null>('ContentPage.calendarStats', null)
  const [selectedDay, setSelectedDay] = usePersistentState<string | null>('ContentPage.selectedDay', null)

  // Trends state
  const [trends, setTrends] = usePersistentState<Trend[]>('ContentPage.trends', [])
  const [trendsLoading, setTrendsLoading] = useState(false)
  const [trendSourceFilter, setTrendSourceFilter] = usePersistentState<string>('ContentPage.trendSourceFilter', 'all')

  // ─── Fetch Pipeline Data ────────────────────────────────────────────────

  const fetchPipeline = useCallback(async () => {
    setLoading(true)
    try {
      const [, pipelineResp, scriptsResp] = await Promise.allSettled([
        window.barq?.social.trends() ?? Promise.resolve(undefined),
        api('/social/pipeline') ?? Promise.resolve(undefined),
        api('/social/scripts?limit=50') ?? Promise.resolve(undefined),
      ])

      const pipelineValue = pipelineResp.status === 'fulfilled' ? pipelineResp.value : undefined
      const pipelineData = (pipelineValue as { pipeline?: Record<string, number> } | undefined)?.pipeline
        ?? (pipelineValue as { success?: boolean; data?: { pipeline?: Record<string, number> } } | undefined)?.data?.pipeline
        ?? {}
      setPipelineCounts(pipelineData)

      const scriptsValue = (scriptsResp.status === 'fulfilled' ? scriptsResp.value : undefined) as
        { scripts?: Record<string, unknown>[] } | { success?: boolean; data?: { scripts?: Record<string, unknown>[] } } | undefined
      const rawScripts = 'scripts' in (scriptsValue ?? {})
        ? (scriptsValue as { scripts?: Record<string, unknown>[] }).scripts ?? []
        : (scriptsValue as { success?: boolean; data?: { scripts?: Record<string, unknown>[] } } | undefined)?.data?.scripts ?? []

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

  // ─── Fetch Calendar Data ────────────────────────────────────────────────

  const fetchCalendar = useCallback(async (year: number, month: number) => {
    try {
      const [monthResp, statsResp] = await Promise.allSettled([
        api(`/social/calendar/month?year=${year}&month=${month}`) ?? Promise.resolve(undefined),
        api('/social/calendar/stats') ?? Promise.resolve(undefined),
      ])

      if (monthResp.status === 'fulfilled' && monthResp.value) {
        const data = (monthResp.value as { success?: boolean; data?: CalendarData } | CalendarData | undefined)
        const calendar = 'data' in (data ?? {})
          ? (data as { success?: boolean; data?: CalendarData }).data
          : data as CalendarData
        if (calendar && 'days' in calendar) {
          setCalendarData(calendar as CalendarData)
        }
      }

      if (statsResp.status === 'fulfilled' && statsResp.value) {
        const data = (statsResp.value as { success?: boolean; data?: CalendarStats } | CalendarStats | undefined)
        const stats = 'data' in (data ?? {})
          ? (data as { success?: boolean; data?: CalendarStats }).data
          : data as CalendarStats
        if (stats && 'total_scheduled' in stats) {
          setCalendarStats(stats as CalendarStats)
        }
      }
    } catch {
      // Silent fail
    }
  }, [])

  // ─── Fetch Trends ───────────────────────────────────────────────────────

  const fetchTrends = useCallback(async () => {
    setTrendsLoading(true)
    try {
      const resp = await api('/social/trends')
      const data = resp && 'data' in resp ? resp.data : resp
      const typedData = data as { trends?: Trend[] } | undefined
      if (typedData?.trends) {
        setTrends(typedData.trends)
      }
    } catch {
      setTrends([])
    }
    setTrendsLoading(false)
  }, [])

  // ─── Effects ────────────────────────────────────────────────────────────

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchPipeline()
    fetchCalendar(calendarYear, calendarMonth)
  }, [fetchPipeline, fetchCalendar, calendarYear, calendarMonth])

  // ─── Actions ────────────────────────────────────────────────────────────

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

  const handleSchedule = async (date: string): Promise<void> => {
    // Find the first ready video to schedule
    const readyItem = scripts.find(s => s.status === 'ready')
    if (!readyItem) return
    await window.barq?.social.schedule({
      video_id: Number(readyItem.id),
      platforms: ['youtube', 'tiktok'],
      scheduled_date: `${date}T12:00:00`,
      title: readyItem.topic,
    })
    await fetchCalendar(calendarYear, calendarMonth)
    setSelectedDay(null)
  }

  const navigateMonth = (delta: number): void => {
    let newMonth = calendarMonth + delta
    let newYear = calendarYear
    if (newMonth > 12) { newMonth = 1; newYear++ }
    if (newMonth < 1) { newMonth = 12; newYear-- }
    setCalendarMonth(newMonth)
    setCalendarYear(newYear)
  }

  // ─── Build Calendar Grid ────────────────────────────────────────────────

  const calendarDays = getCalendarDays(calendarYear, calendarMonth)

  // Merge calendar data into days
  if (calendarData?.days) {
    for (const day of calendarDays) {
      if (calendarData.days[day.date]) {
        day.posts = calendarData.days[day.date]
      }
    }
  }

  // ─── Tab Config ─────────────────────────────────────────────────────────

  const tabs: { id: Tab; label: string; icon: typeof Calendar }[] = [
    { id: 'pipeline', label: 'Pipeline', icon: BarChart3 },
    { id: 'calendar', label: 'Calendar', icon: Calendar },
    { id: 'trends', label: 'Trends', icon: TrendingUp },
  ]

  const stageLabels = [
    { label: 'Scripting', icon: FileText, key: 'scripts_draft' },
    { label: 'Rendering', icon: Video, key: 'videos_rendering' },
    { label: 'Scheduled', icon: Clock, key: 'posts_scheduled' },
    { label: 'Ready to Post', icon: Play, key: 'videos_ready' },
    { label: 'Published', icon: CheckCircle, key: 'posts_posted' },
  ]

  // ─── Render ─────────────────────────────────────────────────────────────

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
      </motion.div>

      {/* ─── Tab Navigation ──────────────────────────────────────────────── */}
      <div className="flex gap-1 bg-void-700/50 rounded-lg p-1 border border-dim-700/30">
        {tabs.map(tab => {
          const TabIcon = tab.icon
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              onClick={() => {
                setActiveTab(tab.id)
                if (tab.id === 'trends') fetchTrends()
              }}
              className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-rajdhani font-semibold transition-all duration-200 ${
                isActive
                  ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/20'
                  : 'text-dim-400 hover:text-ghost hover:bg-void-600/50'
              }`}
            >
              <TabIcon className="w-4 h-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* ─── Pipeline Tab ────────────────────────────────────────────────── */}
      {activeTab === 'pipeline' && (
        <>
          {/* Pipeline Overview */}
          <motion.div
            key="pipeline-cards"
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

          {/* Calendar Stats Summary */}
          {calendarStats && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="grid grid-cols-4 gap-3"
            >
              <div className="glass-card p-3 text-center">
                <p className="text-hud font-share-tech text-dim-400 uppercase tracking-wider">Scheduled</p>
                <p className="text-lg font-orbitron font-bold text-cyan-300 mt-1">{calendarStats.scheduled_this_month}</p>
                <p className="text-2xs font-rajdhani text-dim-500">this month</p>
              </div>
              <div className="glass-card p-3 text-center">
                <p className="text-hud font-share-tech text-dim-400 uppercase tracking-wider">Videos Ready</p>
                <p className="text-lg font-orbitron font-bold text-neural mt-1">{calendarStats.videos_ready}</p>
              </div>
              <div className="glass-card p-3 text-center">
                <p className="text-hud font-share-tech text-dim-400 uppercase tracking-wider">Scripts Draft</p>
                <p className="text-lg font-orbitron font-bold text-plasma mt-1">{calendarStats.scripts_draft}</p>
              </div>
              <div className="glass-card p-3 text-center">
                <p className="text-hud font-share-tech text-dim-400 uppercase tracking-wider">Platforms</p>
                <p className="text-lg font-orbitron font-bold text-ghost mt-1">
                  {Object.keys(calendarStats.platform_distribution).length}
                </p>
              </div>
            </motion.div>
          )}

          {/* Scripts List */}
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
                No content yet. Check the Trends tab to find trending topics, then generate a script.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {scripts.map((idea, i) => {
                const StatusIcon = statusConfig[idea.status].icon
                const sCfg = statusConfig[idea.status]
                const isSelected = selectedIdea === idea.id

                return (
                  <motion.div
                    key={idea.id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.04 }}
                    onClick={() => setSelectedIdea(isSelected ? null : idea.id)}
                    className={`glass-card-hover cursor-pointer transition-all ${
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
                        <motion.div
                          initial={{ opacity: 0, x: 10 }}
                          animate={{ opacity: 1, x: 0 }}
                          className="flex items-center gap-2 ml-4"
                        >
                          {idea.status === 'idea' && (
                            <button
                              onClick={(e) => { e.stopPropagation(); handleGenerateScript(idea.topic) }}
                              className="btn-cyan text-sm"
                            >
                              Generate Script
                            </button>
                          )}
                          {idea.status === 'scripted' && (
                            <button
                              onClick={(e) => { e.stopPropagation(); handleRender(idea.id) }}
                              className="btn-glass text-sm"
                            >
                              Render Video
                            </button>
                          )}
                          {idea.status === 'ready' && (
                            <>
                              <button
                                onClick={(e) => { e.stopPropagation(); handlePost(idea.id) }}
                                className="btn-cyan text-sm"
                              >
                                Post Now
                              </button>
                              <button
                                onClick={(e) => { e.stopPropagation(); setActiveTab('calendar') }}
                                className="btn-glass text-sm"
                              >
                                <Calendar className="w-3 h-3 mr-1" />
                                Schedule
                              </button>
                            </>
                          )}
                        </motion.div>
                      )}
                    </div>
                  </motion.div>
                )
              })}
            </div>
          )}
        </>
      )}

      {/* ─── Calendar Tab ────────────────────────────────────────────────── */}
      {activeTab === 'calendar' && (
        <motion.div
          key="calendar-view"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          {/* Calendar Header */}
          <div className="flex items-center justify-between">
            <button
              onClick={() => navigateMonth(-1)}
              className="p-2 rounded-lg hover:bg-void-600/50 text-dim-400 hover:text-ghost transition-all"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>

            <h2 className="text-lg font-orbitron font-bold text-ghost tracking-wider">
              {MONTH_NAMES[calendarMonth - 1]} {calendarYear}
            </h2>

            <button
              onClick={() => navigateMonth(1)}
              className="p-2 rounded-lg hover:bg-void-600/50 text-dim-400 hover:text-ghost transition-all"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>

          {/* Calendar Summary Strip */}
          {calendarStats && (
            <div className="flex items-center gap-4 text-xs font-rajdhani text-dim-400 bg-void-700/30 rounded-lg px-4 py-2 border border-dim-700/20">
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-cyan-400/70"></span>
                {calendarStats.scheduled_this_month} scheduled this month
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-green-400/70"></span>
                {calendarStats.total_posted} posted
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-neural/70"></span>
                {calendarStats.videos_ready} videos ready
              </span>
            </div>
          )}

          {/* Day Names Header */}
          <div className="grid grid-cols-7 gap-1">
            {DAY_NAMES.map(day => (
              <div key={day} className="text-center text-xs font-orbitron text-dim-500 uppercase tracking-wider py-2">
                {day}
              </div>
            ))}
          </div>

          {/* Calendar Grid */}
          <div className="grid grid-cols-7 gap-1">
            {calendarDays.map((day, idx) => {
              const hasPosts = day.posts.length > 0
              const scheduledCount = day.posts.filter(p => p.type === 'scheduled').length
              const postedCount = day.posts.filter(p => p.type === 'posted').length

              return (
                <motion.div
                  key={day.date}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: idx * 0.005 }}
                  onClick={() => setSelectedDay(selectedDay === day.date ? null : day.date)}
                  className={`
                    relative min-h-[80px] rounded-lg border p-1.5 cursor-pointer
                    transition-all duration-150
                    ${!day.isCurrentMonth ? 'opacity-30' : ''}
                    ${day.isToday ? 'border-cyan-500/40 bg-cyan-500/5' : 'border-dim-700/20 hover:border-dim-500/40'}
                    ${selectedDay === day.date ? 'ring-1 ring-cyan-400/30' : ''}
                  `}
                >
                  <span className={`text-xs font-share-tech ${
                    day.isToday ? 'text-cyan-300 font-bold' : 'text-dim-400'
                  }`}>
                    {day.day}
                  </span>

                  {hasPosts && (
                    <div className="mt-1 space-y-0.5">
                      {scheduledCount > 0 && (
                        <div className="flex items-center gap-1 text-2xs text-cyan-300/80">
                          <Clock className="w-2.5 h-2.5" />
                          <span>{scheduledCount}</span>
                        </div>
                      )}
                      {postedCount > 0 && (
                        <div className="flex items-center gap-1 text-2xs text-green-400/70">
                          <CheckCircle className="w-2.5 h-2.5" />
                          <span>{postedCount}</span>
                        </div>
                      )}
                    </div>
                  )}
                </motion.div>
              )
            })}
          </div>

          {/* Selected Day Details */}
          <AnimatePresence>
            {selectedDay && (() => {
              const dayData = calendarDays.find(d => d.date === selectedDay)
              return (
                <motion.div
                  key={selectedDay}
                  initial={{ opacity: 0, y: 10, height: 0 }}
                  animate={{ opacity: 1, y: 0, height: 'auto' }}
                  exit={{ opacity: 0, y: -10, height: 0 }}
                  className="glass-card p-4 space-y-3 overflow-hidden"
                >
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">
                      {formatDate(selectedDay)}
                    </h3>
                    <div className="flex items-center gap-2">
                      {dayData && dayData.isCurrentMonth && (
                        <button
                          onClick={() => handleSchedule(selectedDay)}
                          className="btn-cyan text-xs flex items-center gap-1"
                        >
                          <Plus className="w-3 h-3" />
                          Schedule Post
                        </button>
                      )}
                      <button
                        onClick={() => setSelectedDay(null)}
                        className="p-1 rounded hover:bg-void-600/50 text-dim-400"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {dayData && dayData.posts.length > 0 ? (
                    <div className="space-y-2">
                      {dayData.posts.map(post => (
                        <div
                          key={`${post.id}-${post.platform}`}
                          className="flex items-center justify-between bg-void-700/50 rounded-lg p-3 border border-dim-700/20"
                        >
                          <div className="flex items-center gap-3">
                            <span className={`text-lg ${PLATFORM_COLORS[post.platform] ?? 'text-dim-400'}`}>
                              {PLATFORM_ICONS[post.platform] ?? '●'}
                            </span>
                            <div>
                              <p className="text-sm font-rajdhani font-semibold text-ghost">
                                {post.title || post.video_title || 'Untitled'}
                              </p>
                              <p className="text-2xs font-exo text-dim-400">
                                {post.platform} · {post.script_format || 'video'}
                                {post.scheduled_at && ` · ${formatTime(post.scheduled_at)}`}
                              </p>
                            </div>
                          </div>

                          <span className={`text-2xs font-share-tech uppercase px-2 py-1 rounded ${
                            post.status === 'posted' || post.type === 'posted'
                              ? 'bg-green-500/10 text-green-400'
                              : post.status === 'scheduled'
                                ? 'bg-cyan-500/10 text-cyan-300'
                                : 'bg-yellow-500/10 text-yellow-400'
                          }`}>
                            {post.status || post.type || 'queued'}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8">
                      <p className="text-xs font-rajdhani text-dim-400">No content scheduled for this day.</p>
                      <button
                        onClick={() => handleSchedule(selectedDay)}
                        className="btn-cyan text-sm mt-3"
                      >
                        <Plus className="w-4 h-4 mr-1" />
                        Schedule Content
                      </button>
                    </div>
                  )}
                </motion.div>
              )
            })()}
          </AnimatePresence>
        </motion.div>
      )}

      {/* ─── Trends Tab ──────────────────────────────────────────────────── */}
      {activeTab === 'trends' && (
        <motion.div
          key="trends-view"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          {/* Trends Header */}
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-orbitron font-bold text-ghost tracking-wider">
              Trending Topics
            </h2>
            <button
              onClick={fetchTrends}
              className="btn-glass text-xs flex items-center gap-1"
              disabled={trendsLoading}
            >
              <Loader2 className={`w-3 h-3 ${trendsLoading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          {/* Trends Source Filter */}
          <div className="flex gap-2 flex-wrap">
            {['all', 'reddit', 'twitter', 'google_trends', 'github', 'product_hunt'].map(source => (
              <button
                key={source}
                onClick={() => setTrendSourceFilter(source)}
                className={`text-xs font-share-tech uppercase px-3 py-1.5 rounded-full border transition-all ${
                  trendSourceFilter === source
                    ? 'border-cyan-500/30 text-cyan-300 bg-cyan-500/5'
                    : 'border-dim-700/30 text-dim-400 hover:border-dim-500/50 hover:text-ghost'
                }`}
              >
                {source === 'google_trends' ? 'Google' : source === 'product_hunt' ? 'Product Hunt' : source}
              </button>
            ))}
          </div>

          {/* Trends Grid */}
          {trendsLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 text-cyan-300 animate-spin" />
              <span className="ml-3 text-sm font-rajdhani text-dim-400">Discovering trends...</span>
            </div>
          ) : trends.length === 0 ? (
            <div className="text-center py-16">
              <TrendingUp className="w-10 h-10 mx-auto text-dim-500 mb-3" />
              <p className="text-sm font-rajdhani text-dim-400">
                No trends fetched yet. Click Refresh to discover trending topics.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {trends
                .filter(t => trendSourceFilter === 'all' || t.source === trendSourceFilter)
                .map((trend, i) => {
                const sourceIcon = trend.source === 'reddit' ? MessageCircle
                  : trend.source === 'twitter' ? Twitter
                    : trend.source === 'google_trends' ? TrendingUp
                      : trend.source === 'github' ? BarChart3
                        : Globe
                const SourceIcon = sourceIcon

                return (
                  <motion.a
                    key={`${trend.id}-${i}`}
                    href={trend.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.03 }}
                    className="glass-card-hover group flex items-start gap-3 p-3"
                  >
                    <div className="p-2 rounded-lg bg-void-700/50 shrink-0">
                      <SourceIcon className="w-4 h-4 text-dim-400" />
                    </div>

                    <div className="flex-1 min-w-0">
                      <h3 className="text-sm font-rajdhani font-semibold text-ghost group-hover:text-cyan-300 transition-colors truncate">
                        {trend.title}
                      </h3>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-2xs font-share-tech uppercase text-dim-500">
                          {trend.source}
                        </span>
                        {trend.subreddit && (
                          <span className="text-2xs font-exo text-dim-500">
                            r/{trend.subreddit}
                          </span>
                        )}
                        {trend.score > 0 && (
                          <span className="text-2xs font-rajdhani font-semibold text-plasma">
                            Score: {trend.score.toFixed(1)}
                          </span>
                        )}
                      </div>
                      {trend.engagement > 0 && (
                        <div className="flex items-center gap-1 mt-1">
                          <Hash className="w-3 h-3 text-dim-500" />
                          <span className="text-2xs font-exo text-dim-500">
                            {trend.engagement.toLocaleString()} interactions
                          </span>
                        </div>
                      )}
                    </div>

                    <ExternalLink className="w-3.5 h-3.5 text-dim-600 group-hover:text-dim-400 transition-colors shrink-0 mt-1" />
                  </motion.a>
                )
              })}
            </div>
          )}
        </motion.div>
      )}
    </div>
  )
}
