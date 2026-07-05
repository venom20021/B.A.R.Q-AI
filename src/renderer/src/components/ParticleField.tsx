import { useCallback, useMemo } from 'react'
import Particles from '@tsparticles/react'
import { loadSlim } from '@tsparticles/slim'
import type { ISourceOptions } from '@tsparticles/engine'

interface ParticleFieldProps {
  id?: string
  className?: string
}

export function ParticleField({ id, className }: ParticleFieldProps): JSX.Element {
  const particlesInit = useCallback(async (engine: any): Promise<void> => {
    await loadSlim(engine)
  }, [])

  const options: ISourceOptions = useMemo(
    () => ({
      fpsLimit: 30,
      fullScreen: { enable: true, zIndex: 0 },
      particles: {
        number: { value: 40, density: { enable: true } },
        color: { value: '#00F0FF' },
        opacity: {
          value: { min: 0.08, max: 0.25 },
          animation: { enable: true, speed: 0.3, sync: false },
        },
        size: {
          value: { min: 1, max: 2.5 },
          animation: { enable: false },
        },
        move: {
          enable: true,
          speed: { min: 0.1, max: 0.4 },
          direction: 'top' as const,
          random: true,
          straight: false,
          outModes: { default: 'out' as const },
        },
        links: {
          enable: true,
          distance: 150,
          color: '#00F0FF',
          opacity: 0.04,
          width: 1,
        },
      },
      detectRetina: true,
      background: { color: 'transparent' },
    }),
    [],
  )

  return (
    <Particles
      id={id || 'particle-field'}
      init={particlesInit}
      options={options as any}
      className={className || 'fixed inset-0 pointer-events-none z-0'}
    />
  )
}
