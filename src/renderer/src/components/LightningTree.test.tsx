import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { ArcReactor } from './ArcReactor'

describe('ArcReactor', () => {
  it('renders a canvas element', () => {
    const { container } = render(<ArcReactor />)
    const canvas = container.querySelector('canvas')
    expect(canvas).toBeInTheDocument()
  })

  it('applies the className prop', () => {
    const { container } = render(<ArcReactor className="reactor-canvas" />)
    const canvas = container.querySelector('canvas')
    expect(canvas).toHaveClass('reactor-canvas')
  })

  it('renders with cyan theme by default', () => {
    const { container } = render(<ArcReactor />)
    const canvas = container.querySelector('canvas')
    expect(canvas).toBeInTheDocument()
  })

  it('renders with gold theme', () => {
    const { container } = render(<ArcReactor theme="gold" />)
    expect(container.querySelector('canvas')).toBeInTheDocument()
  })

  it('wraps canvas in a full-height container when fullscreen is true', () => {
    const { container } = render(<ArcReactor fullscreen />)
    const wrapper = container.firstChild as HTMLElement
    expect(wrapper).toHaveClass('w-full h-full')
  })

  it('calls getContext on the canvas', () => {
    const getContextSpy = vi.spyOn(
      HTMLCanvasElement.prototype,
      'getContext',
    )
    render(<ArcReactor />)
    expect(getContextSpy).toHaveBeenCalledWith('2d')
    getContextSpy.mockRestore()
  })

  it('renders without crashing when wrapped in a sized container with fullscreen', () => {
    const { container } = render(
      <div style={{ width: '800px', height: '600px' }}>
        <ArcReactor fullscreen />
      </div>,
    )
    expect(container.querySelector('canvas')).toBeInTheDocument()
  })
})
