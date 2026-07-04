import { useState, useEffect, useRef, useCallback } from 'react'
import { Bell, CheckCheck, X, AlertTriangle, Info, Zap, ExternalLink } from 'lucide-react'
import { useNotificationSound } from '../hooks/useNotificationSound'

interface Notification {
  id: number
  title: string
  body: string
  priority: string
  category: string
  channel: string
  created_at: string
  read: number
}

interface NotificationCounts {
  total: number
  unread: number
  urgent: number
}

export function NotificationCenter(): JSX.Element {
  const [isOpen, setIsOpen] = useState(false)
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [counts, setCounts] = useState<NotificationCounts>({ total: 0, unread: 0, urgent: 0 })
  const [isLoading, setIsLoading] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const isFirstPoll = useRef(true)
  const prevNotifCount = useRef(0)
  const { playChime, playUrgent } = useNotificationSound()

  // Play sound when new notifications arrive, then update baseline
  const handleNewNotifications = useCallback((newNotifs: Notification[]): void => {
    if (newNotifs.length <= prevNotifCount.current) {
      prevNotifCount.current = newNotifs.length
      return
    }
    const newOnes = newNotifs.slice(0, newNotifs.length - prevNotifCount.current)
    const hasUrgent = newOnes.some((n) => n.priority === 'urgent')
    if (hasUrgent) playUrgent()
    else playChime()
    prevNotifCount.current = newNotifs.length
  }, [playChime, playUrgent])

  // Poll for notifications on mount and listen for updates
  useEffect(() => {
    const poll = async (): Promise<void> => {
      try {
        const result = await window.barq?.notification.poll()
        if (result?.success && result.data) {
          const data = result.data as { notifications?: Notification[]; counts?: NotificationCounts }
          if (data.notifications) {
            setNotifications(data.notifications)
            if (!isFirstPoll.current) {
              handleNewNotifications(data.notifications)
            } else {
              // Set baseline count silently on mount
              prevNotifCount.current = data.notifications.length
            }
            isFirstPoll.current = false
          }
          if (data.counts) setCounts(data.counts)
        }
      } catch {
        // Silently ignore polling errors
      }
    }

    // Initial poll
    poll()

    // Listen for real-time updates from main process
    if (window.barq?.onNotificationsUpdate) {
      window.barq.onNotificationsUpdate((data: unknown) => {
        const d = data as { notifications?: Notification[]; counts?: NotificationCounts }
        if (d.notifications) {
          setNotifications(d.notifications)
          handleNewNotifications(d.notifications)
        }
        if (d.counts) setCounts(d.counts)
      })
    }

    // Poll every 15 seconds as fallback
    const interval = setInterval(poll, 15000)
    return () => clearInterval(interval)
  }, [handleNewNotifications])

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent): void => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen])

  const handleMarkAllRead = useCallback(async (): Promise<void> => {
    setIsLoading(true)
    try {
      // Mark each notification as read sequentially
      for (const notif of notifications.filter((n) => !n.read)) {
        await window.barq?.notification.markRead(notif.id)
      }
      setNotifications((prev) => prev.map((n) => ({ ...n, read: 1 })))
      setCounts((prev) => ({ ...prev, unread: 0 }))
    } catch {
      // Silently ignore errors
    } finally {
      setIsLoading(false)
    }
  }, [notifications])

  const handleDismiss = useCallback(async (id: number): Promise<void> => {
    await window.barq?.notification.markRead(id)
    setNotifications((prev) => prev.filter((n) => n.id !== id))
    setCounts((prev) => ({
      ...prev,
      unread: Math.max(0, prev.unread - 1),
    }))
  }, [])

  const getPriorityIcon = (priority: string): JSX.Element => {
    switch (priority) {
      case 'urgent':
        return <Zap className="w-3.5 h-3.5 text-plasma-400" />
      case 'high':
        return <AlertTriangle className="w-3.5 h-3.5 text-holographic" />
      case 'low':
        return <Info className="w-3.5 h-3.5 text-dim" />
      default:
        return <Info className="w-3.5 h-3.5 text-cyan-400" />
    }
  }

  const getPriorityBorder = (priority: string): string => {
    switch (priority) {
      case 'urgent': return 'border-l-plasma-500'
      case 'high': return 'border-l-holographic'
      case 'low': return 'border-l-dim-500'
      default: return 'border-l-cyan-500'
    }
  }

  const formatTime = (dateStr: string): string => {
    try {
      const date = new Date(dateStr)
      const now = new Date()
      const diff = now.getTime() - date.getTime()
      const mins = Math.floor(diff / 60000)
      const hours = Math.floor(diff / 3600000)
      if (mins < 1) return 'Just now'
      if (mins < 60) return `${mins}m ago`
      if (hours < 24) return `${hours}h ago`
      return date.toLocaleDateString()
    } catch {
      return ''
    }
  }

  return (
    <div ref={dropdownRef} className="relative">
      {/* Bell Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-lg text-dim-400 hover:text-ghost hover:bg-void-600 transition-colors"
        title="Notifications"
      >
        <Bell className="w-5 h-5" />
        {counts.unread > 0 && (
          <>
            <span className="absolute -top-0.5 -right-0.5 w-4.5 h-4.5 bg-plasma-500 rounded-full flex items-center justify-center">
              <span className="text-[10px] font-bold text-white leading-none">
                {counts.unread > 9 ? '9+' : counts.unread}
              </span>
            </span>
            {counts.urgent > 0 && (
              <span className="absolute -top-0.5 -right-0.5 w-4.5 h-4.5 animate-ping bg-plasma-500/30 rounded-full" />
            )}
          </>
        )}
      </button>

      {/* Dropdown Panel */}
      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-80 sm:w-96 overflow-hidden z-50">
          {/* Void backdrop with glass morphism */}
          <div className="relative rounded-xl bg-void-800/90 backdrop-blur-2xl border border-cyan-500/10 shadow-glass shadow-2xl shadow-black/50">
            {/* Glowing top border accent */}
            <div className="absolute top-0 left-4 right-4 h-px bg-gradient-to-r from-transparent via-cyan-400/40 to-transparent" />

            {/* Scanline overlay */}
            <div className="absolute inset-0 pointer-events-none opacity-[0.015]"
              style={{
                backgroundImage: 'repeating-linear-gradient(transparent 0px, transparent 2px, rgba(0,240,255,0.03) 2px, rgba(0,240,255,0.03) 4px)',
              }}
            />

            {/* Header */}
            <div className="relative flex items-center justify-between px-4 py-3 border-b border-cyan-500/8">
              <div>
                <h3 className="text-sm font-semibold text-ghost">Notifications</h3>
                {counts.unread > 0 && (
                  <p className="text-[11px] text-dim mt-0.5">
                    {counts.unread} unread{counts.urgent > 0 ? ` (${counts.urgent} urgent)` : ''}
                  </p>
                )}
              </div>
              {notifications.some((n) => !n.read) && (
                <button
                  onClick={handleMarkAllRead}
                  disabled={isLoading}
                  className="flex items-center gap-1 text-xs text-neural hover:text-cyan-300 transition-colors disabled:opacity-50"
                >
                  <CheckCheck className="w-3.5 h-3.5" />
                  Mark all read
                </button>
              )}
            </div>

            {/* Notification List */}
            <div className="relative max-h-80 overflow-y-auto scroll-cyan">
              {notifications.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-dim-500">
                  <Bell className="w-8 h-8 mb-2 opacity-50" />
                  <p className="text-sm">No notifications yet</p>
                </div>
              ) : (
                <div className="divide-y divide-cyan-500/8">
                  {notifications.map((notif) => (
                    <div
                      key={notif.id}
                      className={`relative px-4 py-3 border-l-2 transition-colors ${
                        getPriorityBorder(notif.priority)
                      } ${notif.read ? 'opacity-60' : 'hover:bg-void-700/50'}`}
                    >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 flex-shrink-0">
                        {getPriorityIcon(notif.priority)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2">
                          <p className={`text-sm ${notif.read ? 'text-dim-400' : 'text-ghost font-medium'}`}>
                            {notif.title}
                          </p>
                          <button
                            onClick={() => handleDismiss(notif.id)}
                            className="flex-shrink-0 p-0.5 rounded text-dim-500 hover:text-dim-400 hover:bg-void-600 transition-colors"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                        <p className="text-xs text-dim mt-0.5 line-clamp-2">{notif.body}</p>
                        <div className="flex items-center gap-2 mt-1.5">
                          <span className="text-[10px] text-dim-500">{formatTime(notif.created_at)}</span>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                            notif.priority === 'urgent' ? 'bg-plasma-500/10 text-plasma-400' :
                            notif.priority === 'high' ? 'bg-holographic/10 text-holographic' :
                            'bg-void-600 text-dim'
                          }`}>
                            {notif.priority}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
