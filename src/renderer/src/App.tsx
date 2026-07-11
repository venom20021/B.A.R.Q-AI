import { useState, useEffect, useCallback, Suspense, lazy } from 'react'
import {
  MemoryRouter, Routes, Route, useNavigate, useLocation,
} from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Sidebar } from './components/Sidebar'
import { QuickOverlay} from './components/QuickOverlay'
import { StartupSequence } from './components/StartupSequence'
import { ApprovalModal } from './components/ApprovalModal'
import { TransientDiagnostics } from './components/TransientDiagnostics'
import { Navbar } from './components/Navbar'
import type { NavTab } from './components/Navbar'
import { ThemeProvider } from './contexts/ThemeContext'
import { DashboardPage } from './pages/DashboardPage'
import { AnalyticsPage } from './pages/AnalyticsPage'
import { JobsPage } from './pages/JobsPage'
import { ContentPage } from './pages/ContentPage'
import { FilesPage } from './pages/FilesPage'
import { DevPage } from './pages/DevPage'
import { SystemPage } from './pages/SystemPage'
import { WebPage } from './pages/WebPage'
import { PhonePage } from './pages/PhonePage'
import { ResearchPage } from './pages/ResearchPage'
import { DocsPage } from './pages/DocsPage'
import { ChatPage } from './pages/ChatPage'
import { MemoryPage } from './pages/MemoryPage'
import { WidgetsPage } from './pages/WidgetsPage'
import { SettingsPage } from './pages/SettingsPage'
import { AgentPage } from './pages/AgentPage'
import { VisionPage } from './pages/VisionPage'

// Lazy loaded views for the main navbar tabs
const NotesView = lazy(() => import('./views/NotesView'))
const GalleryView = lazy(() => import('./views/GalleryView'))

// ─── Quick Command Router ──────────────────────────────────────────────────

function processQuickCommand(cmd: string, nav: (route: string) => void): void {
  if (cmd.includes('scan') && cmd.includes('job')) {
    void window.barq?.jobs.scan()
  } else if (cmd.includes('trend') || cmd.includes('trending')) {
    void window.barq?.social.trends()
  } else if (cmd.includes('open') || cmd.includes('navigate') || cmd.includes('go to')) {
    const routeMap: Record<string, string> = {
      files: '/files', dev: '/dev', system: '/system', web: '/web',
      phone: '/phone', research: '/research', docs: '/docs',
      chat: '/chat', memory: '/memory', jobs: '/jobs',
      social: '/content', settings: '/settings', home: '/dashboard',
      dashboard: '/dashboard',
    }
    for (const [key, route] of Object.entries(routeMap)) {
      if (cmd.includes(key)) {
        nav(route)
        return
      }
    }
    nav('/dashboard')
  } else if (cmd.includes('weather')) {
    const city = cmd.replace('weather', '').replace('in', '').trim() || 'London'
    nav(`/web?weather=${encodeURIComponent(city)}`)
  } else if (cmd.includes('stock') || cmd.includes('price')) {
    nav('/web?tab=stocks')
  } else if (cmd.includes('create note') || cmd.includes('note')) {
    nav('/notes')
  } else if (cmd.includes('approval') && cmd.includes('clear')) {
    void window.barq?.system.command.clearApprovals()
  } else if (cmd.includes('approval')) {
    nav('/settings')
  } else if (cmd.includes('diagnostics') || cmd.includes('system status')) {
    window.dispatchEvent(
      new CustomEvent('barq:voice-command', { detail: { action: 'show_diagnostics' } })
    )
  } else if (cmd.includes('overlay')) {
    if (cmd.includes('show')) {
      window.barq?.overlay.show()
    } else if (cmd.includes('hide')) {
      window.barq?.overlay.hide()
    } else {
      window.barq?.overlay.toggle()
    }
  } else if (cmd.includes('voice') || cmd.includes('listen')) {
    void window.barq?.voice.start()
  } else {
    void window.barq?.voice.command(cmd)
  }
}

// ─── Page Transition Wrapper ───────────────────────────────────────────────

import type { Variants } from 'framer-motion'

const pageVariants: Variants = {
  initial: { opacity: 0, x: 20 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -20 },
}

function AnimatedPage({ children }: { children: React.ReactNode }): JSX.Element {
  return (
    <motion.div
      variants={pageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className="h-full"
    >
      {children}
    </motion.div>
  )
}

// ─── Tab View Wrapper (no animated transitions for tab views) ──────────────

function TabView({ children }: { children: React.ReactNode }): JSX.Element {
  return <div className="h-full">{children}</div>
}

// ─── Map route to navbar tab ──────────────────────────────────────────────

function routeToTab(pathname: string): NavTab {
  if (pathname === '/' || pathname.startsWith('/dashboard')) return 'DASHBOARD'
  if (pathname.startsWith('/notes')) return 'NOTES'
  if (pathname.startsWith('/gallery')) return 'GALLERY'
  if (pathname.startsWith('/phone')) return 'PHONE'
  if (pathname.startsWith('/settings')) return 'SETTINGS'
  return 'DASHBOARD'
}

// ─── App Content ───────────────────────────────────────────────────────────

function AppContent(): JSX.Element {
  const navigate = useNavigate()
  const location = useLocation()
  const [bootComplete, setBootComplete] = useState(false)
  const [quickOverlay, setQuickOverlay] = useState<{
    visible: boolean
    position: { x: number; y: number }
  }>({ visible: false, position: { x: 0, y: 0 } })
  const [recentCommands, setRecentCommands] = useState<string[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [isConversationActive, setIsConversationActive] = useState(false)
  const [aiState, setAiState] = useState<'idle' | 'listening' | 'thinking' | 'responding'>('idle')
  const [language, setLanguage] = useState('en')           // 'en' or 'hi'
  const [ttsVoice, setTtsVoice] = useState('en-US-JennyNeural')

  const activeTab = routeToTab(location.pathname)

  const handleTabChange = useCallback((tab: NavTab) => {
    const routeMap: Record<NavTab, string> = {
      DASHBOARD: '/dashboard',
      NOTES: '/notes',
      GALLERY: '/gallery',
      PHONE: '/phone',
      SETTINGS: '/settings',
    }
    navigate(routeMap[tab])
  }, [navigate])

  const handleMicToggle = useCallback(() => {
    const nextMuted = !isMuted
    setIsMuted(nextMuted)
    if (nextMuted) {
      void window.barq?.voice.stop()
    } else {
      void window.barq?.voice.start()
    }
  }, [isMuted])

  // Poll connection status
  useEffect(() => {
    const check = async () => {
      try {
        const resp = await window.barq?.python.request('/health')
        setIsConnected(resp !== undefined)
      } catch {
        setIsConnected(false)
      }
    }
    check()
    const interval = setInterval(check, 10000)
    return () => clearInterval(interval)
  }, [])

  // Listen for voice status from DashboardPage's WebSocket
  useEffect(() => {
    const handler = (e: CustomEvent<{
      conversation_active: boolean
      is_listening: boolean
      is_speaking: boolean
      is_processing: boolean
      language: string
      tts_voice: string
    }>): void => {
      const detail = e.detail
      setIsConversationActive(detail.conversation_active)
      setIsSpeaking(detail.is_speaking)
      setLanguage(detail.language ?? 'en')
      setTtsVoice(detail.tts_voice ?? 'en-US-JennyNeural')

      // Derive AI state from backend status (same logic as DashboardPage)
      if (detail.is_speaking) {
        setAiState('responding')
      } else if (detail.is_processing) {
        setAiState('thinking')
      } else if (detail.conversation_active) {
        setAiState('listening')
      } else {
        setAiState('idle')
      }
    }
    window.addEventListener('barq:voice-status', handler as EventListener)
    return () => window.removeEventListener('barq:voice-status', handler as EventListener)
  }, [])

  // Listen for barq:voice-command events from ChatPage and voice pipeline
  useEffect(() => {
    const handler = (e: CustomEvent<{ action: string }>): void => {
      const action = e.detail?.action
      if (action === 'clear_approvals') {
        void window.barq?.system.command.clearApprovals()
      } else if (action === 'overlay_show') {
        window.barq?.overlay.show()
      } else if (action === 'overlay_hide') {
        window.barq?.overlay.hide()
      } else if (action === 'overlay_toggle') {
        window.barq?.overlay.toggle()
      }
    }
    window.addEventListener('barq:voice-command', handler as EventListener)
    return () => window.removeEventListener('barq:voice-command', handler as EventListener)
  }, [])

  useEffect(() => {
    // Track cleanup functions returned by preload listeners
    const cleanups: (() => void)[] = []

    if (window.barq?.onNavigate) {
      const cleanup = window.barq.onNavigate((route: string) => navigate(route))
      if (typeof cleanup === 'function') cleanups.push(cleanup)
    }

    if (window.barq?.onQuickOverlay) {
      const cleanup = window.barq.onQuickOverlay((pos: { x: number; y: number }) => {
        setQuickOverlay({ visible: true, position: pos })
      })
      if (typeof cleanup === 'function') cleanups.push(cleanup)
    }

    const handleQuickCmd = (e: CustomEvent<{ command: string }>): void => {
      const cmd = e.detail.command.toLowerCase()
      setRecentCommands((prev) => [cmd, ...prev.slice(0, 9)])
      processQuickCommand(cmd, navigate)
    }
    window.addEventListener(
      'barq:quick-command',
      handleQuickCmd as EventListener,
    )
    return () => {
      window.removeEventListener(
        'barq:quick-command',
        handleQuickCmd as EventListener,
      )
      // Run all preload listener cleanups
      for (const cleanup of cleanups) {
        cleanup()
      }
    }
  }, [navigate])

  const handleQuickOverlayClose = useCallback((): void => {
    setQuickOverlay((prev) => ({ ...prev, visible: false }))
  }, [])

  const handleBootComplete = useCallback((): void => {
    setBootComplete(true)
  }, [])

  // ─── Render ─────────────────────────────────────────────────────────────

  return (
    <>
      {/* Startup Sequence */}
      <AnimatePresence>
        {!bootComplete && (
          <StartupSequence onComplete={handleBootComplete} />
        )}
      </AnimatePresence>

      {/* Radial gradient background (replaces ParticleField) */}
      <div className="fixed inset-0 bg-[radial-gradient(ellipse_at_center,var(--tw-gradient-stops))] from-zinc-950 via-black to-black pointer-events-none" />

      {/* Main layout */}
      <div className="relative z-10 h-screen flex flex-col">
        {/* Top Navbar */}
        <Navbar
          activeTab={activeTab}
          onTabChange={handleTabChange}
          isConnected={isConnected}
          isSpeaking={isSpeaking}
          isMuted={isMuted}
          isConversationActive={isConversationActive}
          onMicToggle={handleMicToggle}
          aiState={aiState}
          language={language}
          ttsVoice={ttsVoice}
        />

        {/* Content area: Sidebar + Main */}
        <div className="flex-1 flex overflow-hidden">
          {/* Sidebar is fixed-position, add left padding to main content */}
          <Sidebar currentRoute={location.pathname} onNavigate={navigate} />

          <main className="flex-1 flex flex-col overflow-hidden ml-16">
            <div className="flex-1 overflow-y-auto relative">
              {/* Scanline overlay */}
              <div
                className="fixed inset-0 pointer-events-none z-50 opacity-[0.015]"
                style={{
                  backgroundImage:
                    'repeating-linear-gradient(transparent 0px, transparent 2px, rgba(0,240,255,0.02) 2px, rgba(0,240,255,0.02) 4px)',
                }}
              />

              {/* Page content with transitions */}
              <AnimatePresence mode="wait">
                <Routes location={location} key={location.pathname}>
                  {/* Main navbar tabs */}
                  <Route path="/" element={<TabView><DashboardPage /></TabView>} />
                  <Route path="/dashboard" element={<TabView><DashboardPage /></TabView>} />
                  <Route path="/notes" element={
                    <Suspense fallback={
                      <div className="flex h-full items-center justify-center">
                        <div className="w-5 h-5 border-2 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin" />
                      </div>
                    }>
                      <TabView><NotesView glassPanel="bg-zinc-950/40 backdrop-blur-xl border border-white/5 rounded-2xl shadow-xl" /></TabView>
                    </Suspense>
                  } />
                  <Route path="/gallery" element={
                    <Suspense fallback={
                      <div className="flex h-full items-center justify-center">
                        <div className="w-5 h-5 border-2 border-cyan-500/30 border-t-cyan-400 rounded-full animate-spin" />
                      </div>
                    }>
                      <TabView><GalleryView /></TabView>
                    </Suspense>
                  } />
                  <Route path="/phone" element={<TabView><PhonePage /></TabView>} />
                  <Route path="/settings" element={<TabView><SettingsPage /></TabView>} />

                  {/* Sidebar secondary pages */}
                  <Route path="/analytics" element={<AnimatedPage><AnalyticsPage /></AnimatedPage>} />
                  <Route path="/jobs" element={<AnimatedPage><JobsPage /></AnimatedPage>} />
                  <Route path="/content" element={<AnimatedPage><ContentPage /></AnimatedPage>} />
                  <Route path="/files" element={<AnimatedPage><FilesPage /></AnimatedPage>} />
                  <Route path="/dev" element={<AnimatedPage><DevPage /></AnimatedPage>} />
                  <Route path="/system" element={<AnimatedPage><SystemPage /></AnimatedPage>} />
                  <Route path="/web" element={<AnimatedPage><WebPage /></AnimatedPage>} />
                  <Route path="/research" element={<AnimatedPage><ResearchPage /></AnimatedPage>} />
                  <Route path="/docs" element={<AnimatedPage><DocsPage /></AnimatedPage>} />
                  <Route path="/chat" element={<AnimatedPage><ChatPage /></AnimatedPage>} />
                  <Route path="/memory" element={<AnimatedPage><MemoryPage /></AnimatedPage>} />
                  <Route path="/agent" element={<AnimatedPage><AgentPage /></AnimatedPage>} />
                  <Route path="/vision" element={<AnimatedPage><VisionPage /></AnimatedPage>} />
                  <Route path="/widgets" element={<AnimatedPage><WidgetsPage /></AnimatedPage>} />
                </Routes>
              </AnimatePresence>
            </div>
          </main>
        </div>
      </div>

      {/* Quick Overlay */}
      <QuickOverlay
        isVisible={quickOverlay.visible}
        onClose={handleQuickOverlayClose}
        position={quickOverlay.position}
        recentCommands={recentCommands}
      />

      {/* Approval Modal — triggered by dangerous voice commands */}
      <ApprovalModal />

      {/* Transient Diagnostics — auto-dismissing system stats overlay */}
      <TransientDiagnostics />
    </>
  )
}

// ─── Root App ──────────────────────────────────────────────────────────────

function App(): JSX.Element {
  return (
    <ThemeProvider>
      <MemoryRouter>
        <AppContent />
      </MemoryRouter>
    </ThemeProvider>
  )
}

export default App
