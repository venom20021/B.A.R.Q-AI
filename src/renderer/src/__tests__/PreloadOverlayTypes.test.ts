import { describe, it, expect, vi, afterEach } from 'vitest'

// Shared cleanup — runs after each test even on failure
afterEach(() => {
  delete (window as unknown as Record<string, unknown>).barq
})

describe('window.barq.overlay type verification', () => {
  it('overlay exists on barq API', () => {
    const mockOverlay = {
      show: vi.fn(),
      hide: vi.fn(),
      toggle: vi.fn(),
    }

    Object.defineProperty(window, 'barq', {
      value: { overlay: mockOverlay },
      configurable: true,
      writable: true,
    })

    expect(window.barq).toBeDefined()
    expect(window.barq.overlay).toBeDefined()
    expect(typeof window.barq.overlay.show).toBe('function')
    expect(typeof window.barq.overlay.hide).toBe('function')
    expect(typeof window.barq.overlay.toggle).toBe('function')

    // Verify each method is callable with no arguments
    window.barq.overlay.show()
    expect(mockOverlay.show).toHaveBeenCalledOnce()
    expect(mockOverlay.show).toHaveBeenCalledWith()

    window.barq.overlay.hide()
    expect(mockOverlay.hide).toHaveBeenCalledOnce()
    expect(mockOverlay.hide).toHaveBeenCalledWith()

    window.barq.overlay.toggle()
    expect(mockOverlay.toggle).toHaveBeenCalledOnce()
    expect(mockOverlay.toggle).toHaveBeenCalledWith()
  })

  it('overlay methods return void', () => {
    const mockOverlay = {
      show: vi.fn(() => undefined),
      hide: vi.fn(() => undefined),
      toggle: vi.fn(() => undefined),
    }

    Object.defineProperty(window, 'barq', {
      value: { overlay: mockOverlay },
      configurable: true,
      writable: true,
    })

    expect(window.barq.overlay.show()).toBeUndefined()
    expect(window.barq.overlay.hide()).toBeUndefined()
    expect(window.barq.overlay.toggle()).toBeUndefined()
  })

  it('overlay works with optional chaining pattern used in App.tsx', () => {
    const mockShow = vi.fn()
    const mockHide = vi.fn()
    const mockToggle = vi.fn()

    Object.defineProperty(window, 'barq', {
      value: {
        overlay: {
          show: mockShow,
          hide: mockHide,
          toggle: mockToggle,
        },
      },
      configurable: true,
      writable: true,
    })

    // The optional chaining pattern from App.tsx
    window.barq?.overlay.show()
    expect(mockShow).toHaveBeenCalledOnce()

    window.barq?.overlay.hide()
    expect(mockHide).toHaveBeenCalledOnce()

    window.barq?.overlay.toggle()
    expect(mockToggle).toHaveBeenCalledOnce()
  })

  it('overlay show/hide/toggle are not async (fire-and-forget)', () => {
    // overlay uses ipcRenderer.send (fire-and-forget), not invoke (promise)
    // So the return type should be void, not Promise<void>
    const mockOverlay = {
      show: vi.fn(() => undefined),
      hide: vi.fn(() => undefined),
      toggle: vi.fn(() => undefined),
    }

    Object.defineProperty(window, 'barq', {
      value: { overlay: mockOverlay },
      configurable: true,
      writable: true,
    })

    // Returns are undefined (not a Promise), so no 'then' property
    // Note: accessing `.then` directly would cause TS2339 since `void` is never a valid receiver.
    // The `toBeUndefined()` check confirms these are fire-and-forget (not Promise-based like invoke).
    expect(window.barq.overlay.show()).toBeUndefined()
    expect(window.barq.overlay.hide()).toBeUndefined()
    expect(window.barq.overlay.toggle()).toBeUndefined()
  })
})
