import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { ChatPage } from './ChatPage'

// Mock window.barq API
const mockPythonRequest = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  // Set up window.barq mock
  Object.defineProperty(window, 'barq', {
    value: {
      python: {
        request: mockPythonRequest,
      },
    },
    configurable: true,
    writable: true,
  })
})

afterEach(() => {
  // Clean up mock
  delete (window as unknown as Record<string, unknown>).barq
})

describe('ChatPage - barq:voice-command event dispatch', () => {
  it('renders the chat page with input field', () => {
    render(<ChatPage />)
    expect(screen.getByPlaceholderText('Type a command or ask a question...')).toBeInTheDocument()
  })

  it('dispatches barq:voice-command event when command returns an action', async () => {
    mockPythonRequest.mockResolvedValue({
      action: 'show_diagnostics',
      status: 'triggered',
    })

    // Listen for the custom event
    const eventPromise = new Promise<CustomEvent>((resolve) => {
      window.addEventListener('barq:voice-command', (e) => {
        resolve(e as CustomEvent)
      }, { once: true })
    })

    render(<ChatPage />)

    // Type a command and press Enter (reliable, maps to real user interaction)
    const input = screen.getByPlaceholderText('Type a command or ask a question...')
    fireEvent.change(input, { target: { value: 'show diagnostics' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    // Wait for the event
    const event = await eventPromise
    expect(event.detail).toEqual({ action: 'show_diagnostics' })
  })

  it('dispatches barq:voice-command with navigate action', async () => {
    mockPythonRequest.mockResolvedValue({
      action: 'navigate',
      target: '/settings',
      status: 'triggered',
    })

    const eventPromise = new Promise<CustomEvent>((resolve) => {
      window.addEventListener('barq:voice-command', (e) => {
        resolve(e as CustomEvent)
      }, { once: true })
    })

    render(<ChatPage />)

    const input = screen.getByPlaceholderText('Type a command or ask a question...')
    fireEvent.change(input, { target: { value: 'go to settings' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    const event = await eventPromise
    expect(event.detail).toEqual({ action: 'navigate' })
  })

  it('does not dispatch event when python request fails', async () => {
    mockPythonRequest.mockRejectedValue(new Error('Network error'))

    const eventSpy = vi.fn()
    window.addEventListener('barq:voice-command', eventSpy)

    render(<ChatPage />)

    const input = screen.getByPlaceholderText('Type a command or ask a question...')
    fireEvent.change(input, { target: { value: 'show diagnostics' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    // Wait for the "Failed to process command" error message to appear
    const errorMsg = await screen.findByText('Failed to process command.')
    expect(errorMsg).toBeInTheDocument()

    // Verify the event was NOT dispatched
    expect(eventSpy).not.toHaveBeenCalled()
    window.removeEventListener('barq:voice-command', eventSpy)
  })

  it('dispatches event for scan_jobs action', async () => {
    mockPythonRequest.mockResolvedValue({
      action: 'scan_jobs',
      status: 'triggered',
    })

    const eventPromise = new Promise<CustomEvent>((resolve) => {
      window.addEventListener('barq:voice-command', (e) => {
        resolve(e as CustomEvent)
      }, { once: true })
    })

    render(<ChatPage />)

    const input = screen.getByPlaceholderText('Type a command or ask a question...')
    fireEvent.change(input, { target: { value: 'scan jobs' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    const event = await eventPromise
    expect(event.detail).toEqual({ action: 'scan_jobs' })
  })

  it('dispatches event for navigate action and shows friendly response', async () => {
    mockPythonRequest.mockResolvedValue({
      action: 'navigate',
      target: '/settings',
    })

    render(<ChatPage />)

    const input = screen.getByPlaceholderText('Type a command or ask a question...')
    fireEvent.change(input, { target: { value: 'go to settings' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    // Wait for the friendly response to appear
    const response = await screen.findByText(/Navigating to/, {}, { timeout: 2000 })
    expect(response).toBeInTheDocument()
  })

  it('shows friendly response for known actions', async () => {
    mockPythonRequest.mockResolvedValue({
      action: 'show_diagnostics',
      status: 'triggered',
    })

    render(<ChatPage />)

    const input = screen.getByPlaceholderText('Type a command or ask a question...')
    fireEvent.change(input, { target: { value: 'show diagnostics' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    // The response for show_diagnostics is: 'Showing system diagnostics' (special-cased in ChatPage.tsx)
    const response = await screen.findByText('Showing system diagnostics', {}, { timeout: 2000 })
    expect(response).toBeInTheDocument()
  })
})
