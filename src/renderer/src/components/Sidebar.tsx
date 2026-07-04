import { useState } from 'react'
import {
  LayoutDashboard, Briefcase, Video, BarChart3, Settings, Mic,
  FolderOpen, Terminal, Monitor, Globe, Smartphone, Search,
  FileText, MessageSquare, Palette, ChevronDown, PanelRightOpen,
  BrainCircuit, Bell,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { NotificationCenter } from './NotificationCenter'

interface SidebarProps {
  currentRoute: string
  onNavigate: (route: string) => void
}

interface NavItemDef {
  path: string
  label: string
  icon: typeof LayoutDashboard
}

const navSections: { label: string; items: NavItemDef[] }[] = [
  {
    label: 'Overview',
    items: [
      { path: '/dashboard', label: 'Home', icon: LayoutDashboard },
      { path: '/analytics', label: 'Analytics', icon: BarChart3 },
    ],
  },
  {
    label: 'Workspace',
    items: [
      { path: '/files', label: 'Files', icon: FolderOpen },
      { path: '/dev', label: 'Dev', icon: Terminal },
      { path: '/system', label: 'System', icon: Monitor },
      { path: '/web', label: 'Web', icon: Globe },
      { path: '/phone', label: 'Phone', icon: Smartphone },
      { path: '/research', label: 'Research', icon: Search },
      { path: '/docs', label: 'Docs', icon: FileText },
    ],
  },
  {
    label: 'Automation',
    items: [
      { path: '/jobs', label: 'Jobs', icon: Briefcase },
      { path: '/content', label: 'Social', icon: Video },
    ],
  },
  {
    label: 'Tools',
    items: [
      { path: '/chat', label: 'Chat', icon: MessageSquare },
      { path: '/memory', label: 'Memory', icon: BrainCircuit },
      { path: '/widgets', label: 'Widgets', icon: Palette },
      { path: '/settings', label: 'Settings', icon: Settings },
    ],
  },
]

export function Sidebar({ currentRoute, onNavigate }: SidebarProps): JSX.Element {
  const [expanded, setExpanded] = useState(false)
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set())

  const toggleSection = (label: string): void => {
    setCollapsedSections((prev) => {
      const next = new Set(prev)
      if (next.has(label)) next.delete(label)
      else next.add(label)
      return next
    })
  }

  return (
    <aside
      className={`relative h-full flex flex-col bg-void-800/90 backdrop-blur-xl border-r border-cyan-500/10 transition-all duration-200 z-40 ${
        expanded ? 'w-56' : 'w-16'
      }`}
      onMouseEnter={() => setExpanded(true)}
      onMouseLeave={() => setExpanded(false)}
    >
      {/* Left-edge glow line */}
      <div className="absolute left-0 top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-cyan-400/30 to-transparent" />

      {/* Logo */}
      <div className={`h-10 flex items-center border-b border-cyan-500/10 ${expanded ? 'px-4 justify-start' : 'justify-center'}`}>
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-cyan-400 to-cyan-600 flex items-center justify-center shadow-glow-cyan-sm">
            <Mic className="w-3.5 h-3.5 text-[#0A0A0F]" />
          </div>
          <AnimatePresence>
            {expanded && (
              <motion.div
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                className="flex items-center gap-1.5 overflow-hidden"
              >
                <span className="text-sm font-orbitron font-bold text-cyan-300 tracking-wider">
                  BARQ
                </span>
                <span className="text-[8px] font-share-tech text-holographic bg-holographic/10 px-1 py-0.5 rounded">
                  v2
                </span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 overflow-y-auto scroll-cyan">
        {navSections.map((section) => {
          const isCollapsed = collapsedSections.has(section.label)
          return (
            <div key={section.label} className="mb-1">
              {/* Section header */}
              <AnimatePresence>
                {expanded && (
                  <motion.button
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    onClick={() => toggleSection(section.label)}
                    className="flex w-full items-center justify-between px-4 py-1"
                  >
                    <span className="text-hud font-share-tech text-dim-400 uppercase tracking-[0.15em]">
                      {section.label}
                    </span>
                    <ChevronDown
                      className={`w-2.5 h-2.5 text-dim-500 transition-transform ${
                        isCollapsed ? '-rotate-90' : ''
                      }`}
                    />
                  </motion.button>
                )}
              </AnimatePresence>
              <ul className="space-y-0.5 px-1.5">
                {section.items.map((item) => {
                  const isActive = currentRoute === item.path
                  const Icon = item.icon
                  return (
                    <li key={item.path}>
                      <button
                        onClick={() => onNavigate(item.path)}
                        className={`w-full flex items-center gap-3 rounded-lg transition-all duration-150 group ${
                          expanded ? 'px-3 py-2' : 'px-2 py-2 justify-center'
                        } ${
                          isActive
                            ? 'bg-cyan-500/10 text-cyan-300'
                            : 'text-dim-400 hover:text-ghost hover:bg-void-600/50'
                        }`}
                        title={item.label}
                      >
                        <div className="relative flex-shrink-0">
                          <Icon className={`w-4 h-4 transition-all duration-200 ${
                            isActive ? 'text-cyan-300' : 'group-hover:text-cyan-300/60'
                          }`} />
                          {isActive && (
                            <span className="absolute -left-3 top-1/2 -translate-y-1/2 w-1 h-5 rounded-r-full bg-cyan-400 shadow-glow-cyan-sm" />
                          )}
                        </div>
                        <AnimatePresence>
                          {expanded && (
                            <motion.span
                              initial={{ opacity: 0, x: -5 }}
                              animate={{ opacity: 1, x: 0 }}
                              exit={{ opacity: 0, x: -5 }}
                              className={`text-sm font-rajdhani font-semibold whitespace-nowrap ${
                                isActive ? 'text-cyan-300' : ''
                              }`}
                            >
                              {item.label}
                            </motion.span>
                          )}
                        </AnimatePresence>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          )
        })}
      </nav>

      {/* Bottom status */}
      <div className="p-3 border-t border-cyan-500/8">
        <div className={`flex items-center ${expanded ? 'justify-between' : 'justify-center'}`}>
          <AnimatePresence>
            {expanded && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex items-center gap-2"
              >
                <div className="w-1.5 h-1.5 rounded-full bg-neural shadow-glow-green" />
                <span className="text-hud font-share-tech text-dim-400">READY</span>
              </motion.div>
            )}
          </AnimatePresence>
          <div className="flex items-center gap-0.5">
            <NotificationCenter />
            <button
              className="p-1.5 rounded-lg text-dim-400 hover:text-cyan-300 hover:bg-cyan-500/5 transition-colors"
              title="Quick Overlay (Ctrl+Shift+I)"
            >
              <PanelRightOpen className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </aside>
  )
}
