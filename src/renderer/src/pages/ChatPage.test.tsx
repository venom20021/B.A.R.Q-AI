import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { ChatPage } from './ChatPage'

// Mock window.barq API — scoped to this file, reset each test
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

  // Do NOT mock SpeechRecognition — happy-dom doesn't have it,
  // so the component's `supported` check returns `false` and the
  // recognition useEffect is safely skipped. This avoids React 18
  // concurrent-mode conflicts with sttText state updates.

  // Mock localStorage so chat history persistence doesn't interfere
  vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null)
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {})
  vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {})
})

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).barq
  vi.restoreAllMocks()
  cleanup()
})

describe('ChatPage', () => {
  it('renders the chat page with input field', () => {
    render(<ChatPage />)
    expect(screen.getByPlaceholderText('Type a message or click the mic...')).toBeInTheDocument()
  })

  it('dispatches barq:voice-command event when command returns an action', async () => {
    mockPythonRequest.mockResolvedValue({
      action: 'show_diagnostics',
      text: 'Showing system diagnostics',
    })

    const eventPromise = new Promise<CustomEvent>((resolve) => {
      window.addEventListener('barq:voice-command', (e) => {
        resolve(e as CustomEvent)
      }, { once: true })
    })

    render(<ChatPage />)

    const input = screen.getByPlaceholderText('Type a message or click the mic...')
    fireEvent.change(input, { target: { value: 'show diagnostics' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    const event = await eventPromise
    expect(event.detail).toEqual({ action: 'show_diagnostics' })
  })

  it('dispatches barq:voice-command with navigate action', async () => {
    mockPythonRequest.mockResolvedValue({
      action: 'navigate',
      text: 'Navigating to settings',
      target: '/settings',
    })

    const eventPromise = new Promise<CustomEvent>((resolve) => {
      window.addEventListener('barq:voice-command', (e) => {
        resolve(e as CustomEvent)
      }, { once: true })
    })

    render(<ChatPage />)

    const input = screen.getByPlaceholderText('Type a message or click the mic...')
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

    const input = screen.getByPlaceholderText('Type a message or click the mic...')
    fireEvent.change(input, { target: { value: 'show diagnostics' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    // The api() helper swallows errors — shows the connection fallback message
    const fallbackMsg = await screen.findByText(/could not process a response/, {}, { timeout: 2000 })
    expect(fallbackMsg).toBeInTheDocument()

    expect(eventSpy).not.toHaveBeenCalled()
    window.removeEventListener('barq:voice-command', eventSpy)
  })

  it('dispatches event for scan_jobs action', async () => {
    mockPythonRequest.mockResolvedValue({
      action: 'scan_jobs',
      text: 'Scanning for new job listings',
    })

    const eventPromise = new Promise<CustomEvent>((resolve) => {
      window.addEventListener('barq:voice-command', (e) => {
        resolve(e as CustomEvent)
      }, { once: true })
    })

    render(<ChatPage />)

    const input = screen.getByPlaceholderText('Type a message or click the mic...')
    fireEvent.change(input, { target: { value: 'scan jobs' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    const event = await eventPromise
    expect(event.detail).toEqual({ action: 'scan_jobs' })
  })

  it('displays the response text from the backend', async () => {
    mockPythonRequest.mockResolvedValue({
      text: 'Navigating to settings',
      action: 'navigate',
    })

    render(<ChatPage />)

    const input = screen.getByPlaceholderText('Type a message or click the mic...')
    fireEvent.change(input, { target: { value: 'go to settings' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    const response = await screen.findByText(/Navigating to settings/, {}, { timeout: 2000 })
    expect(response).toBeInTheDocument()
  })

  it('displays fallback text when backend returns no text', async () => {
    mockPythonRequest.mockResolvedValue({
      action: 'show_diagnostics',
    })

    render(<ChatPage />)

    const input = screen.getByPlaceholderText('Type a message or click the mic...')
    fireEvent.change(input, { target: { value: 'show diagnostics' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    const response = await screen.findByText('Command processed.', {}, { timeout: 2000 })
    expect(response).toBeInTheDocument()
  })

  it('clears chat history', async () => {
    mockPythonRequest.mockResolvedValue({
      text: 'Response',
      action: 'conversation',
    })

    render(<ChatPage />)

    const input = screen.getByPlaceholderText('Type a message or click the mic...')
    fireEvent.change(input, { target: { value: 'hello' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    // Wait for response
    await screen.findByText('Response', {}, { timeout: 2000 })

    // Clear history
    const clearButton = screen.getByTitle('Clear chat history')
    fireEvent.click(clearButton)

    // Should show the empty state again
    expect(screen.getByText(/Start a conversation with BARQ/)).toBeInTheDocument()
  })
})
