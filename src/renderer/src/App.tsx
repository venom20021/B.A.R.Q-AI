import { useState, useEffect, useCallback } from 'react'
import {
  MemoryRouter, Routes, Route, useNavigate, useLocation,
} from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Sidebar } from './components/Sidebar'
import { TitleBar } from './components/TitleBar'

import { QuickOverlay } from './components/QuickOverlay'
import { ParticleField } from './components/ParticleField'
import { StartupSequence } from './components/StartupSequence'
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
    nav('/memory')
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

  useEffect(() => {
    if (window.barq?.onNavigate) {
      window.barq.onNavigate((route: string) => navigate(route))
    }

    if (window.barq?.onQuickOverlay) {
      window.barq.onQuickOverlay((pos: { x: number; y: number }) => {
        setQuickOverlay({ visible: true, position: pos })
      })
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
    }
  }, [navigate])

  const handleSubmitText = useCallback(
    (text: string): void => {
      setRecentCommands((prev) => [text, ...prev.slice(0, 9)])
      processQuickCommand(text.toLowerCase(), navigate)
    },
    [navigate],
  )

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

      {/* Particle field background */}
      <ParticleField />

      {/* Main layout */}
      <div className="relative z-10 h-screen flex flex-col">
        {/* Title Bar */}
        <TitleBar />

        {/* Content area: Sidebar + Main */}
        <div className="flex-1 flex overflow-hidden">
          <Sidebar currentRoute={location.pathname} onNavigate={navigate} />

          <main className="flex-1 flex flex-col overflow-hidden">
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
                  <Route path="/" element={<AnimatedPage><DashboardPage /></AnimatedPage>} />
                  <Route path="/dashboard" element={<AnimatedPage><DashboardPage /></AnimatedPage>} />
                  <Route path="/analytics" element={<AnimatedPage><AnalyticsPage /></AnimatedPage>} />
                  <Route path="/jobs" element={<AnimatedPage><JobsPage /></AnimatedPage>} />
                  <Route path="/content" element={<AnimatedPage><ContentPage /></AnimatedPage>} />
                  <Route path="/files" element={<AnimatedPage><FilesPage /></AnimatedPage>} />
                  <Route path="/dev" element={<AnimatedPage><DevPage /></AnimatedPage>} />
                  <Route path="/system" element={<AnimatedPage><SystemPage /></AnimatedPage>} />
                  <Route path="/web" element={<AnimatedPage><WebPage /></AnimatedPage>} />
                  <Route path="/phone" element={<AnimatedPage><PhonePage /></AnimatedPage>} />
                  <Route path="/research" element={<AnimatedPage><ResearchPage /></AnimatedPage>} />
                  <Route path="/docs" element={<AnimatedPage><DocsPage /></AnimatedPage>} />
                  <Route path="/chat" element={<AnimatedPage><ChatPage /></AnimatedPage>} />
                  <Route path="/memory" element={<AnimatedPage><MemoryPage /></AnimatedPage>} />
                  <Route path="/widgets" element={<AnimatedPage><WidgetsPage /></AnimatedPage>} />
                  <Route path="/settings" element={<AnimatedPage><SettingsPage /></AnimatedPage>} />
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
    </>
  )
}

// ─── Root App ──────────────────────────────────────────────────────────────

function App(): JSX.Element {
  return (
    <MemoryRouter>
      <AppContent />
    </MemoryRouter>
  )
}

export default App
