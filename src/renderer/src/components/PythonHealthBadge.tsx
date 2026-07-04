import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'

type HealthStatus = 'checking' | 'healthy' | 'unhealthy'

export function PythonHealthBadge(): JSX.Element {
  const [status, setStatus] = useState<HealthStatus>('checking')
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true

    const check = async (): Promise<void> => {
      try {
        const resp = await window.barq?.python.request('/health')
        if (!mountedRef.current) return

        if (resp && typeof resp === 'object' && 'status' in (resp as Record<string, unknown>) && (resp as Record<string, unknown>).status === 'ok') {
          setStatus('healthy')
        } else {
          setStatus('unhealthy')
        }
      } catch {
        if (mountedRef.current) setStatus('unhealthy')
      }
    }

    // Immediate first check
    void check()

    // Poll every 30 seconds
    const interval = setInterval(check, 30_000)

    return () => {
      mountedRef.current = false
      clearInterval(interval)
    }
  }, [])

  const isHealthy = status === 'healthy'
  const dotColor = isHealthy ? 'bg-neural' : status === 'unhealthy' ? 'bg-red-500' : 'bg-yellow-500'
  const glowColor = isHealthy ? 'shadow-glow-green' : status === 'unhealthy' ? 'shadow-glow-red' : ''
  const label = isHealthy ? 'PYTHON' : status === 'unhealthy' ? 'OFFLINE' : '...'

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex items-center gap-1.5"
      title={
        isHealthy
          ? 'Python backend connected'
          : status === 'unhealthy'
            ? 'Python backend unreachable'
            : 'Checking Python backend...'
      }
    >
      <motion.div
        animate={
          status === 'checking'
            ? { scale: [1, 1.3, 1] }
            : { scale: 1 }
        }
        transition={
          status === 'checking'
            ? { repeat: Infinity, duration: 1.5 }
            : { duration: 0.3 }
        }
        className={`w-1.5 h-1.5 rounded-full ${dotColor} ${glowColor}`}
      />
      <span className={`text-hud font-share-tech tracking-wider ${
        isHealthy ? 'text-neural' : status === 'unhealthy' ? 'text-red-400' : 'text-yellow-400'
      }`}>
        {label}
      </span>
    </motion.div>
  )
}
