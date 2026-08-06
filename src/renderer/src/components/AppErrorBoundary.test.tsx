import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

import { AppErrorBoundary } from './AppErrorBoundary'

// Silence the expected console.error noise React + the boundary log on purpose.
beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// ─── Fixtures ────────────────────────────────────────────────────────────

function Boom(): JSX.Element {
  throw new Error('render boom')
}

// Throws only while `shouldThrow` is true — used to prove recovery works.
let shouldThrow = true
function Flaky(): JSX.Element {
  if (shouldThrow) {
    throw new Error('flaky boom')
  }
  return <div>recovered content</div>
}

// ─── Normal rendering ────────────────────────────────────────────────────

describe('normal rendering', () => {
  it('renders children when no error occurs', () => {
    render(
      <AppErrorBoundary>
        <div>hello world</div>
      </AppErrorBoundary>,
    )
    expect(screen.getByText('hello world')).toBeInTheDocument()
    expect(screen.queryByText(/Something went wrong/)).toBeNull()
  })

  it('renders children with a custom resetKey', () => {
    render(
      <AppErrorBoundary resetKey="/dashboard">
        <div>content</div>
      </AppErrorBoundary>,
    )
    expect(screen.getByText('content')).toBeInTheDocument()
  })
})

// ─── Crash capture ───────────────────────────────────────────────────────

describe('crash capture', () => {
  it('shows the recovery screen when a child throws during render', () => {
    render(
      <AppErrorBoundary>
        <Boom />
      </AppErrorBoundary>,
    )
    expect(screen.getByText(/Something went wrong/)).toBeInTheDocument()
    expect(screen.getByText('render boom')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reload app/i })).toBeInTheDocument()
  })

  it('uses the custom title when provided', () => {
    render(
      <AppErrorBoundary title="Custom crash title">
        <Boom />
      </AppErrorBoundary>,
    )
    expect(screen.getByText('Custom crash title')).toBeInTheDocument()
  })

  it('dispatches a barq:renderer-error event on crash', () => {
    const spy = vi.fn()
    window.addEventListener('barq:renderer-error', spy)

    render(
      <AppErrorBoundary>
        <Boom />
      </AppErrorBoundary>,
    )

    expect(spy).toHaveBeenCalledTimes(1)
    const detail = (spy.mock.calls[0][0] as CustomEvent<{ message: string }>).detail
    expect(detail.message).toBe('render boom')
    window.removeEventListener('barq:renderer-error', spy)
  })
})

// ─── Recovery actions ────────────────────────────────────────────────────

describe('recovery actions', () => {
  it('"Try again" resets the boundary and re-renders children', () => {
    shouldThrow = true
    render(
      <AppErrorBoundary>
        <Flaky />
      </AppErrorBoundary>,
    )
    expect(screen.getByText(/Something went wrong/)).toBeInTheDocument()

    // Stop the child from throwing, then retry.
    shouldThrow = false
    fireEvent.click(screen.getByRole('button', { name: /try again/i }))
    expect(screen.getByText('recovered content')).toBeInTheDocument()
    expect(screen.queryByText(/Something went wrong/)).toBeNull()
    shouldThrow = true
  })

  it('renders "Back to dashboard" and calls onReset when provided', () => {
    const onReset = vi.fn()
    render(
      <AppErrorBoundary onReset={onReset}>
        <Boom />
      </AppErrorBoundary>,
    )
    const backButton = screen.getByRole('button', { name: /back to dashboard/i })
    expect(backButton).toBeInTheDocument()
    fireEvent.click(backButton)
    expect(onReset).toHaveBeenCalledTimes(1)
  })

  it('hides "Back to dashboard" when onReset is not provided', () => {
    render(
      <AppErrorBoundary>
        <Boom />
      </AppErrorBoundary>,
    )
    expect(screen.queryByRole('button', { name: /back to dashboard/i })).toBeNull()
  })
})

// ─── resetKey auto-reset ─────────────────────────────────────────────────

describe('resetKey auto-reset', () => {
  it('clears a crash when resetKey changes', () => {
    shouldThrow = true
    const { rerender } = render(
      <AppErrorBoundary resetKey="/page-a">
        <Flaky />
      </AppErrorBoundary>,
    )
    expect(screen.getByText(/Something went wrong/)).toBeInTheDocument()

    // The child no longer throws — a navigation (resetKey change) must
    // automatically clear the boundary and render the healthy page.
    shouldThrow = false
    rerender(
      <AppErrorBoundary resetKey="/page-b">
        <Flaky />
      </AppErrorBoundary>,
    )
    expect(screen.getByText('recovered content')).toBeInTheDocument()
    expect(screen.queryByText(/Something went wrong/)).toBeNull()
    shouldThrow = true
  })
})
