/**
 * Shared helpers for persisting frontend conversations to the backend's
 * `agent_chat_history` setting (GET/POST /api/memory/agent-history).
 *
 * The backend stores a dict `{ [agentKey]: [{role, content, timestamp}] }`.
 * The brain re-import reads this setting and extracts user topics into the
 * `ai_chats` knowledge graph, so every conversation surface (Chat page,
 * Jarvis/AiChat panel, voice sessions) should mirror its threads here under
 * its own agent key.
 */

import { api } from './api'

export interface AgentHistoryMessage {
  role: string
  content: string
  timestamp: number
}

/**
 * Fetch one agent key's history from the backend. Returns `[]` when the
 * key is missing or the backend is unreachable.
 */
export async function fetchAgentHistory(agentKey: string): Promise<AgentHistoryMessage[]> {
  try {
    const resp = await api<{ history?: Record<string, unknown> }>('/memory/agent-history')
    const history = resp?.history
    if (history && typeof history === 'object') {
      const mine = (history as Record<string, unknown>)[agentKey]
      if (Array.isArray(mine)) return mine as AgentHistoryMessage[]
    }
  } catch { /* backend unavailable — fall through to local fallback */ }
  return []
}

/**
 * Merge this agent key's messages into the history dict (preserving other
 * agents' keys so we never clobber voice sessions etc.) and persist.
 * Returns true on success.
 */
export async function pushAgentHistory(agentKey: string, messages: AgentHistoryMessage[]): Promise<boolean> {
  try {
    // Read the full dict so we don't clobber other agents' history keys.
    const resp = await api<{ history?: Record<string, unknown> }>('/memory/agent-history')
    const merged: Record<string, unknown> = (resp?.history && typeof resp.history === 'object')
      ? { ...(resp.history as Record<string, unknown>) }
      : {}
    merged[agentKey] = messages
    const saved = await api('/memory/agent-history', { history: merged })
    return saved !== undefined
  } catch { /* ignore */ }
  return false
}

/** Remove one agent key from the history dict (clear action). */
export async function clearAgentHistoryKey(agentKey: string): Promise<void> {
  try {
    const resp = await api<{ history?: Record<string, unknown> }>('/memory/agent-history')
    const merged: Record<string, unknown> = (resp?.history && typeof resp.history === 'object')
      ? { ...(resp.history as Record<string, unknown>) }
      : {}
    delete merged[agentKey]
    await api('/memory/agent-history', { history: merged })
  } catch { /* ignore */ }
}
