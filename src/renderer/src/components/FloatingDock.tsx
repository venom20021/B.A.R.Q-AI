import { useState } from 'react'
import { motion } from 'framer-motion'
import { useNavigate, useLocation } from 'react-router-dom'
import { GlassPanel } from './GlassPanel'
import {
  LayoutDashboard, Briefcase, Video, BarChart3, FolderOpen,
  Search, Settings,
} from 'lucide-react'

interface DockItem {
  path: string
  label: string
  icon: typeof LayoutDashboard
}

const dockItems: DockItem[] = [
  { path: '/dashboard', label: 'Home', icon: LayoutDashboard },
  { path: '/jobs', label: 'Jobs', icon: Briefcase },
  { path: '/content', label: 'Social', icon: Video },
  { path: '/analytics', label: 'Analytics', icon: BarChart3 },
  { path: '/files', label: 'Files', icon: FolderOpen },
  { path: '/research', label: 'Research', icon: Search },
  { path: '/settings', label: 'Settings', icon: Settings },
]

export function FloatingDock(): JSX.Element {
  const navigate = useNavigate()
  const location = useLocation()
  const [hoveredPath, setHoveredPath] = useState<string | null>(null)

  return (
    <motion.div
      initial={{ y: 24, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ delay: 0.6, duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
      className="fixed bottom-0 left-1/2 -translate-x-1/2 z-30"
>
      <GlassPanel className="flex items-center gap-1.5 px-3.5 py-2.5 !rounded-t-2xl !rounded-b-none border-b-0 !bg-white/5 !backdrop-blur-md !border-white/10 !shadow-xl">
      {dockItems.map((item, i) => {
        const isActive = location.pathname === item.path
        const Icon = item.icon
        return (
          <motion.button
            key={item.path}
            onClick={() => navigate(item.path)}
            onMouseEnter={() => setHoveredPath(item.path)}
            onMouseLeave={() => setHoveredPath(null)}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.7 + i * 0.04, duration: 0.3 }}
            whileHover={{ scale: 1.2, transition: { duration: 0.15 } }}
            whileTap={{ scale: 0.92 }}
            className={`relative flex items-center justify-center w-10 h-10 rounded-xl transition-colors duration-200 ${
              isActive
                ? 'bg-[#00E5FF]/15 text-[#00E5FF]'
                : 'text-[#E2E8F0]/40 hover:text-[#E2E8F0]/70 hover:bg-[#E2E8F0]/5'
            }`}
          >
            <Icon className="w-[18px] h-[18px]" />

            {/* Active indicator dot */}
            {isActive && (
              <motion.div
                layoutId="dock-active-indicator"
                className="absolute -bottom-1 w-1 h-1 rounded-full bg-[#00E5FF] shadow-[0_0_6px_rgba(0,229,255,0.6)]"
              />
            )}

            {/* Tooltip label on hover */}
            {hoveredPath === item.path && (
              <motion.span
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                transition={{ duration: 0.12 }}
                className="absolute -top-8 left-1/2 -translate-x-1/2 px-2 py-0.5 text-[9px] font-rajdhani font-semibold text-[#E2E8F0]/80 bg-[#0D0D15]/90 backdrop-blur-xl border border-[#00E5FF]/10 rounded-md whitespace-nowrap pointer-events-none"
              >
                {item.label}
              </motion.span>
            )}
          </motion.button>
        )
      })}
      </GlassPanel>
    </motion.div>
  )
}
