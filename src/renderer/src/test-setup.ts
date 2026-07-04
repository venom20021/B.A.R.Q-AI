import '@testing-library/jest-dom/vitest'

// jsdom/happy-dom doesn't fully implement HTMLCanvasElement.getContext('2d')
// Provide a minimal mock so canvas-rendering components don't crash
if (typeof HTMLCanvasElement !== 'undefined') {
  HTMLCanvasElement.prototype.getContext = function () {
    return {
      fillStyle: '',
      strokeStyle: '',
      lineWidth: 0,
      lineCap: '',
      globalAlpha: 1,
      shadowColor: '',
      shadowBlur: 0,
      font: '',
      textAlign: '',
      textBaseline: '',

      fillRect: () => undefined,
      fillText: () => undefined,
      clearRect: () => undefined,
      beginPath: () => undefined,
      moveTo: () => undefined,
      lineTo: () => undefined,
      closePath: () => undefined,
      stroke: () => undefined,
      fill: () => undefined,
      arc: () => undefined,
      save: () => undefined,
      restore: () => undefined,
      translate: () => undefined,
      scale: () => undefined,
      rotate: () => undefined,
      createRadialGradient: () => ({
        addColorStop: () => undefined,
      }),
      createLinearGradient: () => ({
        addColorStop: () => undefined,
      }),
      setTransform: () => undefined,
    } as unknown as CanvasRenderingContext2D
  } as unknown as typeof HTMLCanvasElement.prototype.getContext
}

// Polyfill for ResizeObserver if not present in the environment
if (typeof ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class ResizeObserver {
    constructor() { /* noop */ }
    observe() { /* noop */ }
    unobserve() { /* noop */ }
    disconnect() { /* noop */ }
  }
}

// requestAnimationFrame shim
globalThis.requestAnimationFrame = (cb: FrameRequestCallback): number => {
  return window.setTimeout(() => cb(performance.now()), 16) as unknown as number
}
globalThis.cancelAnimationFrame = (id: number): void => {
  window.clearTimeout(id)
}
