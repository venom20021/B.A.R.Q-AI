import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { GuardianWolf } from './GuardianWolf'

describe('GuardianWolf', () => {
  it('renders a canvas element', () => {
    const { container } = render(<GuardianWolf />)
    const canvas = container.querySelector('canvas')
    expect(canvas).toBeInTheDocument()
  })

  it('applies the className prop', () => {
    const { container } = render(<GuardianWolf className="test-class" />)
    const canvas = container.querySelector('canvas')
    expect(canvas).toHaveClass('test-class')
  })

  it('renders with cyan theme by default', () => {
    const { container } = render(<GuardianWolf />)
    const canvas = container.querySelector('canvas')
    expect(canvas).toBeInTheDocument()
    // Theme is applied to the canvas rendering context at runtime — just verify no crash
  })

  it('renders with gold theme', () => {
    const { container } = render(<GuardianWolf theme="gold" />)
    const canvas = container.querySelector('canvas')
    expect(canvas).toBeInTheDocument()
  })

  it('renders with custom size when not fullscreen', () => {
    const { container } = render(<GuardianWolf size={400} />)
    const canvas = container.querySelector('canvas')
    expect(canvas).toBeInTheDocument()
  })

  it('wraps canvas in a full-height container when fullscreen is true', () => {
    const { container } = render(<GuardianWolf fullscreen />)
    const wrapper = container.firstChild as HTMLElement
    expect(wrapper).toHaveClass('w-full h-full')
  })

  it('adds relative positioning class when not fullscreen', () => {
    const { container } = render(<GuardianWolf />)
    const wrapper = container.firstChild as HTMLElement
    expect(wrapper.className).toBe('relative')
  })

  it('renders without errors when fullscreen and container has size', () => {
    // Simulate a container with dimensions
    const { container } = render(
      <div style={{ width: '500px', height: '500px' }}>
        <GuardianWolf fullscreen />
      </div>,
    )
    const canvas = container.querySelector('canvas')
    expect(canvas).toBeInTheDocument()
  })

  it('calls getContext on the canvas', () => {
    const getContextSpy = vi.spyOn(
      HTMLCanvasElement.prototype,
      'getContext',
    )
    render(<GuardianWolf />)
    expect(getContextSpy).toHaveBeenCalledWith('2d')
    getContextSpy.mockRestore()
  })
})
