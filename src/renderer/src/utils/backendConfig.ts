/**
 * Backend configuration utility for the renderer.
 *
 * Provides HTTP and WebSocket base URLs by fetching config from
 * the main process via IPC.  The config tells the renderer whether
 * the app is in local mode (Python sidecar on localhost) or remote
 * mode (cloud BARQ instance).
 *
 * Usage:
 *   import { getBackendConfig } from '../utils/backendConfig'
 *   const config = await getBackendConfig()
 *   // config.httpUrl  → "http://155.248.247.224" or "http://127.0.0.1:8956"
 *   // config.wsUrl    → "ws://155.248.247.224" or "ws://127.0.0.1:8970"
 *   // config.isRemote → true | false
 */

export interface BackendConfig {
  httpUrl: string
  wsUrl: string
  isRemote: boolean
}

let cachedConfig: BackendConfig | null = null
let fetching: Promise<BackendConfig> | null = null

// Default fallback config (local mode)
const DEFAULT_CONFIG: BackendConfig = {
  httpUrl: 'http://127.0.0.1:8956',
  wsUrl: 'ws://127.0.0.1:8970',
  isRemote: false,
}

/**
 * Get the backend configuration (HTTP URL, WS URL, remote mode status).
 * Results are cached after the first call.
 */
export async function getBackendConfig(): Promise<BackendConfig> {
  if (cachedConfig) return cachedConfig

  if (!fetching) {
    fetching = (async () => {
      try {
        const resp = await window.barq?.python.getConfig()
        if (resp?.success && resp.data) {
          const config: BackendConfig = {
            httpUrl: resp.data.httpUrl,
            wsUrl: resp.data.wsUrl,
            isRemote: resp.data.isRemote,
          }
          cachedConfig = config
          return config
        }
      } catch {
        // Fall through to defaults
      }

      cachedConfig = DEFAULT_CONFIG
      return DEFAULT_CONFIG
    })()
  }

  return fetching
}

/**
 * Invalidate the cached config so the next call re-fetches.
 */
export function invalidateBackendConfig(): void {
  cachedConfig = null
  fetching = null
}

/**
 * Synchronous HTTP URL getter — returns cached config or default.
 * Use in contexts where await is not possible (EventSource constructor, etc.).
 * The async getBackendConfig() should be called early to populate the cache.
 */
export function getSyncHttpUrl(): string {
  return cachedConfig?.httpUrl ?? DEFAULT_CONFIG.httpUrl
}

/**
 * Synchronous WS URL getter — returns cached config or default.
 */
export function getSyncWsUrl(): string {
  return cachedConfig?.wsUrl ?? DEFAULT_CONFIG.wsUrl
}

/**
 * Switch to remote mode at runtime (no restart needed).
 */
export async function setRemoteMode(enabled: boolean, url?: string): Promise<BackendConfig> {
  try {
    const resp = await window.barq?.python.setRemoteMode(enabled, url)
    if (resp?.success && resp.data) {
      const config: BackendConfig = {
        httpUrl: resp.data.httpUrl,
        wsUrl: resp.data.wsUrl,
        isRemote: resp.data.isRemote,
      }
      cachedConfig = config
      return config
    }
  } catch {
    // ignore
  }
  invalidateBackendConfig()
  return getBackendConfig()
}
