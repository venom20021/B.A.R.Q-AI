/**
 * Shared API helper for BARQ Python backend communication.
 *
 * The Electron bridge (`window.barq.python.request`) expects data to be sent
 * directly as the JSON body — NOT wrapped in a `{ method, body, headers }`
 * fetch-style envelope. This helper enforces the correct format everywhere.
 *
 * @example
 *   // Good — data sent directly as JSON body
 *   await api('/voice/tts-backend', { backend: 'edge' })
 *
 *   // GET — no data
 *   const status = await api('/voice/status')
 */

export type ApiResponse<T = Record<string, unknown>> =
  | { success: true; data: T }
  | { success: false; error: string }

/**
 * Send a request to a Python backend endpoint.
 *
 * @param endpoint  The API path (e.g. `/voice/status`)
 * @param data      Optional payload — when provided, the bridge sends it as
 *                  the JSON body via POST. When omitted, a GET is sent.
 * @returns         The parsed response object, or `undefined` if the bridge
 *                  is unavailable.
 */
export async function api<T = Record<string, unknown>>(
  endpoint: string,
  data?: Record<string, unknown>,
): Promise<T | undefined> {
  try {
    const resp = await window.barq?.python.request(endpoint, data ?? undefined)
    if (resp && typeof resp === 'object' && 'success' in resp) {
      if (resp.success && resp.data) {
        return resp.data as T
      }
      return undefined
    }
    // Some endpoints return raw JSON (not wrapped in { success, data })
    return resp as T | undefined
  } catch {
    return undefined
  }
}

/**
 * Convenience wrapper that returns a typed response even when the bridge
 * wraps responses in `{ success, data }`. Falls back to raw response.
 */
export async function apiRaw<T = unknown>(
  endpoint: string,
  data?: Record<string, unknown>,
): Promise<T | undefined> {
  try {
    const resp = await window.barq?.python.request(endpoint, data ?? undefined)
    return resp as T | undefined
  } catch {
    return undefined
  }
}
