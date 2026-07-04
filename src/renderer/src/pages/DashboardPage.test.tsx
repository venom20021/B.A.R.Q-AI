import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DashboardPage } from './DashboardPage'

vi.mock('../components/GuardianWolf', () => ({
  GuardianWolf: () => <div data-testid="guardian-wolf" />,
}))

vi.mock('../components/ArcReactor', () => ({
  ArcReactor: () => <div data-testid="arc-reactor" />,
}))

vi.mock('../components/ArcMonitorPanel', () => ({
  ArcMonitorPanel: ({ side }: { side: string }) => (
    <div data-testid={`monitor-panel-${side}`} />
  ),
}))

vi.mock('../components/AiChatPanel', () => ({
  AiChatPanel: () => <div data-testid="ai-chat-panel" />,
}))

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders arc reactor and monitor panels in default mode', () => {
    render(<DashboardPage />)
    expect(screen.getByTestId('arc-reactor')).toBeInTheDocument()
    expect(screen.getByTestId('monitor-panel-left')).toBeInTheDocument()
    expect(screen.getByTestId('monitor-panel-right')).toBeInTheDocument()
    expect(screen.getByTestId('ai-chat-panel')).toBeInTheDocument()
  })

  it('renders mode toggle buttons', () => {
    render(<DashboardPage />)
    expect(screen.getByText('①')).toBeInTheDocument()
    expect(screen.getByText('②')).toBeInTheDocument()
    expect(screen.getByText('③')).toBeInTheDocument()
  })

  it('renders theme toggle button', () => {
    render(<DashboardPage />)
    expect(screen.getByText('CYAN')).toBeInTheDocument()
  })

  it('switches to wolf mode when pressing 3', () => {
    render(<DashboardPage />)
    expect(screen.getByTestId('arc-reactor')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: '3' })
    expect(screen.getByTestId('guardian-wolf')).toBeInTheDocument()
    expect(screen.queryByTestId('monitor-panel-left')).not.toBeInTheDocument()
    expect(screen.queryByTestId('monitor-panel-right')).not.toBeInTheDocument()
  })

  it('switches to split mode when pressing 2', () => {
    render(<DashboardPage />)
    fireEvent.keyDown(window, { key: '2' })
    // In split mode, both ArcReactor and GuardianWolf render
    expect(screen.getByTestId('arc-reactor')).toBeInTheDocument()
    expect(screen.getByTestId('guardian-wolf')).toBeInTheDocument()
    expect(screen.getByTestId('monitor-panel-left')).toBeInTheDocument()
    expect(screen.getByTestId('monitor-panel-right')).toBeInTheDocument()
  })

  it('cycles through modes with keyboard shortcuts', () => {
    render(<DashboardPage />)
    // Default → Wolf (via 3)
    fireEvent.keyDown(window, { key: '3' })
    expect(screen.getByTestId('guardian-wolf')).toBeInTheDocument()
    // Wolf → Default (via 1)
    fireEvent.keyDown(window, { key: '1' })
    expect(screen.getByTestId('arc-reactor')).toBeInTheDocument()
    // Default → Split (via 2)
    fireEvent.keyDown(window, { key: '2' })
    expect(screen.getByTestId('guardian-wolf')).toBeInTheDocument()
    expect(screen.getByTestId('arc-reactor')).toBeInTheDocument()
  })

  it('toggles theme when theme button clicked', () => {
    render(<DashboardPage />)
    const themeBtn = screen.getByText('CYAN')
    fireEvent.click(themeBtn)
    expect(screen.getByText('GOLD')).toBeInTheDocument()
    fireEvent.click(screen.getByText('GOLD'))
    expect(screen.getByText('CYAN')).toBeInTheDocument()
  })

  it('removes keyboard event listener on unmount', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener')
    const { unmount } = render(<DashboardPage />)
    unmount()
    expect(removeSpy).toHaveBeenCalledWith('keydown', expect.any(Function))
  })
})
