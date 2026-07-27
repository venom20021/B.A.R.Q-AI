import { ChildProcess, spawn, execSync } from 'child_process'
import { join } from 'path'
import { existsSync } from 'fs'
import { app } from 'electron'
import { is } from '@electron-toolkit/utils'

const SIDECAR_PORT = 8956
const SIDECAR_HOST = '127.0.0.1'
const SIDECAR_URL = `http://${SIDECAR_HOST}:${SIDECAR_PORT}`

/**
 * Default remote URL — the Oracle VM backend.
 * When reachable, non-voice API calls go to this URL.
 * Voice always runs locally (mic/speakers are on this machine).
 * Set SIDECAR_REMOTE_URL to override, or SIDECAR_AUTO_REMOTE=false to skip auto-connect.
 */
const DEFAULT_REMOTE_URL = 'http://155.248.247.224'

/**
 * Auto-remote mode: try the default remote URL first.
 * Disable by setting SIDECAR_AUTO_REMOTE=false in env.
 */
const AUTO_REMOTE = process.env['SIDECAR_AUTO_REMOTE'] !== 'false'

/**
 * Remote sidecar URL — when set, the app connects to a remote BARQ instance.
 * Voice endpoints always route to local Python regardless.
 * Set via SIDECAR_REMOTE_URL env var.
 */
const SIDECAR_REMOTE_URL = process.env['SIDECAR_REMOTE_URL'] || ''
const isRemote = !!SIDECAR_REMOTE_URL

/** Endpoint prefixes that must always hit the local Python sidecar (voice needs local mic/speakers) */
const LOCAL_ONLY_PREFIXES = ['/voice/', '/speech/']

/**
 * Common Python installation paths on Windows, checked in order.
 */
const WINDOWS_PYTHON_PATHS = [
  join(process.env['LOCALAPPDATA'] || 'C:\\Users\\Default', 'Programs', 'Python', 'Python313', 'python.exe'),
  join(process.env['LOCALAPPDATA'] || 'C:\\Users\\Default', 'Programs', 'Python', 'Python312', 'python.exe'),
  join(process.env['LOCALAPPDATA'] || 'C:\\Users\\Default', 'Programs', 'Python', 'Python311', 'python.exe'),
  'C:\\Python313\\python.exe',
  'C:\\Python312\\python.exe',
  'C:\\Python311\\python.exe',
  join(process.env['ProgramFiles'] || 'C:\\Program Files', 'Python313', 'python.exe'),
  join(process.env['ProgramFiles'] || 'C:\\Program Files', 'Python312', 'python.exe'),
]

class PythonSidecar {
  private process: ChildProcess | null = null
  private isRunning = false
  private healthCheckInterval: ReturnType<typeof setInterval> | null = null
  private _showVoskLogs = false
  private _showWhisperLogs = false
  private restartCount = 0
  private lastRestartAttempt = 0
  private remoteMode = isRemote
  private _remoteUrl = SIDECAR_REMOTE_URL
  /** Whether a remote backend is actually connected and healthy */
  private _remoteConnected = false

  /**
   * Set remote mode configuration.
   * Non-voice requests route to the remote URL when enabled.
   * Voice requests always route to the local Python sidecar.
   */
  setRemoteMode(enabled: boolean, url?: string): void {
    this.remoteMode = enabled
    if (url) this._remoteUrl = url
  }

  /** Whether the sidecar is in remote mode */
  get isRemoteMode(): boolean {
    return this.remoteMode
  }

  /** Whether a remote backend is actually connected */
  get isRemoteConnected(): boolean {
    return this._remoteConnected
  }

  /** The remote URL (empty string when not in remote mode) */
  get remoteUrl(): string {
    return this._remoteUrl
  }

  /** Whether auto-remote fallback is available */
  get isAutoRemoteEnabled(): boolean {
    return AUTO_REMOTE
  }

  /**
   * Get backend configuration for the renderer.
   * Voice WS always points to localhost (voice pipeline runs locally).
   * HTTP API points to remote when in cloud mode, local otherwise.
   */
  getBackendConfig(): { httpUrl: string; wsUrl: string; isRemote: boolean } {
    if (this.remoteMode && this._remoteUrl) {
      const base = this._remoteUrl.replace(/\/+$/, '')
      return {
        httpUrl: base,
        // Non-voice WS (vision, etc.) connects to the remote backend.
        // Voice WS always uses localhost (VoiceContext hardcodes it).
        wsUrl: base.replace(/^http:/, 'ws:'),
        isRemote: true,
      }
    }
    return {
      httpUrl: `http://${SIDECAR_HOST}:${SIDECAR_PORT}`,
      wsUrl: `ws://${SIDECAR_HOST}:${SIDECAR_PORT}`,
      isRemote: false,
    }
  }

  /**
   * Kill any existing process holding the sidecar port (Windows only).
   */
  private async freePort(): Promise<void> {
    if (process.platform !== 'win32') return

    const pids = new Set<number>()

    try {
      const result = execSync(
        `netstat -ano | findstr :${SIDECAR_PORT}`,
        { encoding: 'utf8', timeout: 3000 },
      )
      const lines = result.trim().split(/\r?\n/)
      for (const line of lines) {
        const parts = line.trim().split(/\s+/)
        const pid = parseInt(parts[parts.length - 1], 10)
        if (!isNaN(pid) && pid > 0) {
          pids.add(pid)
        }
      }
    } catch {
      // netstat not available
    }

    if (pids.size === 0) return

    for (const pid of pids) {
      try {
        console.log(`[PythonSidecar] Killing process ${pid} on port ${SIDECAR_PORT}...`)
        execSync(`taskkill /F /PID ${pid}`, { encoding: 'utf8', timeout: 3000 })
      } catch {
        // Process may have already exited
      }
    }

    await new Promise((resolve) => setTimeout(resolve, 1500))

    try {
      const check = execSync(
        `netstat -ano | findstr :${SIDECAR_PORT}`,
        { encoding: 'utf8', timeout: 3000 },
      )
      if (check.trim().length > 0) {
        await new Promise((resolve) => setTimeout(resolve, 2000))
      }
    } catch {
      // Port is free
    }
  }

  /**
   * Start the Python sidecar.
   *
   * Architecture:
   * - Voice endpoints (talk, listen, wake word) ALWAYS go to the LOCAL Python process
   *   because the microphone and speakers are physically on this machine.
   * - Non-voice endpoints go to the REMOTE backend when in cloud mode.
   *
   * So this method always starts a local Python process. If a remote backend
   * is also reachable, non-voice requests are forwarded there.
   */
  async start(): Promise<void> {
    if (this.isRunning) return

    // ── If explicitly set to remote or auto-remote, probe the remote URL ──
    let remoteUrl = ''
    if (this.remoteMode && this._remoteUrl) {
      remoteUrl = this._remoteUrl
      console.log(`[PythonSidecar] Remote mode configured — will probe ${remoteUrl}`)
    } else if (AUTO_REMOTE && !this.remoteMode) {
      const autoUrl = DEFAULT_REMOTE_URL
      console.log(`[PythonSidecar] Auto-remote — probing ${autoUrl}...`)
      try {
        const response = await fetch(`${autoUrl}/health`, { signal: AbortSignal.timeout(5000) })
        if (response.ok) {
          console.log('[PythonSidecar] ✅ Remote backend reachable — voice stays local, API uses cloud')
          remoteUrl = autoUrl
          this.remoteMode = true
          this._remoteUrl = autoUrl
          this._remoteConnected = true
        }
      } catch {
        console.warn('[PythonSidecar] Remote backend not reachable — local only')
      }
    }

    // ── ALWAYS start local Python for voice (mic/speakers are on this machine) ──
    console.log('[PythonSidecar] Starting local Python backend for voice...')
    try {
      await this._startLocalProcess()
    } catch (err) {
      // Catch the final error after all retries are exhausted.
      // The error is already logged in _startLocalProcess with full detail.
      // We swallow it here so the caller (index.ts) doesn't get an unhandled
      // promise rejection. The app will show "Waiting for backend..." until
      // the health check system restarts the sidecar or the user intervenes.
      console.warn(`[PythonSidecar] Local backend failed to start — ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  /**
   * Start the local Python process (voice + API fallback).
   */
  private async _startLocalProcess(): Promise<void> {
    for (let attempt = 0; attempt < 3; attempt++) {
      if (attempt > 0) {
        console.log(`[PythonSidecar] Retry attempt ${attempt + 1}/3...`)
        await this.freePort()
      } else {
        await this.freePort()
      }

      const pythonPath = this.getPythonPath()
      const args = this.getArgs()

      console.log(`[PythonSidecar] Starting: ${pythonPath} ${args.join(' ')}`)

      this.process = spawn(pythonPath, args, {
        cwd: this.getWorkingDir(),
        stdio: ['pipe', 'pipe', 'pipe'],
        env: {
          ...process.env,
          SIDECAR_PORT: String(SIDECAR_PORT),
          SIDECAR_HOST: SIDECAR_HOST,
          HF_HUB_DISABLE_SYMLINKS_WARNING: '1'
        }
      })

      let earlyExit = false

      this.process.stdout?.on('data', (data: Buffer) => {
        const text = data.toString().trim()
        if (text.includes('[Speech]') || /whisper/i.test(text)) {
          if (this._showWhisperLogs) {
            console.log(`[STT] ${text}`)
          }
          return
        }
        console.log(`[Python] ${text}`)
      })

      this.process.stderr?.on('data', (data: Buffer) => {
        const text = data.toString().trim()
        if (text.startsWith('LOG (')) {
          if (this._showVoskLogs) {
            console.log(`[Vosk] ${text}`)
          }
          return
        }
        if (text.includes('Address already in use') || text.includes('errno 10048') || text.includes('EADDRINUSE')) {
          console.error(`[PythonSidecar] Port ${SIDECAR_PORT} is already in use (detected in stderr)`)
          earlyExit = true
        } else {
          console.warn(`[Python stderr] ${text}`)
        }
      })

      const exitPromise = new Promise<void>((resolve) => {
        const onExit = (code: number | null): void => {
          console.log(`[PythonSidecar] Process exited with code ${code}`)
          this.isRunning = false
          this.process = null
          if (code === 1 || code === null) {
            earlyExit = true
          }
          resolve()
        }
        this.process!.on('exit', onExit)
        this.process!.on('error', (err) => {
          console.error(`[PythonSidecar] Failed to start:`, err.message)
          this.isRunning = false
          this.process = null
          earlyExit = true
          resolve()
        })
      })

      try {
        const exitRace = exitPromise.then(() => {
          throw new Error(
            earlyExit
              ? 'Process exited early (likely port in use)'
              : 'Process exited unexpectedly before health check'
          )
        })
        exitRace.catch(() => {})

        await Promise.race([this.waitForHealth(30_000), exitRace])
        this.isRunning = true
        this.startHealthChecks()
        console.log('[PythonSidecar] ✅ Local Python backend ready for voice')
        return
      } catch (err) {
        const proc = this.process
        console.warn(
          `[PythonSidecar] Attempt ${attempt + 1}/3 failed` +
          (earlyExit ? ' (process exited early)' : ' (health check timed out)') +
          (attempt >= 2 ? '. No more retries.' : ', retrying...')
        )
        if (proc) proc.kill('SIGTERM')
        this.process = null
        this.isRunning = false
        if (attempt >= 2) throw err
      }
    }

    throw new Error('[PythonSidecar] Failed to start after 3 attempts')
  }

  /**
   * Stop the Python sidecar process gracefully.
   */
  async stop(): Promise<void> {
    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval)
      this.healthCheckInterval = null
    }

    if (this.process) {
      console.log('[PythonSidecar] Stopping...')

      try {
        await this.request('/shutdown', {}, 2000)
      } catch {
        // Ignore
      }

      setTimeout(() => {
        if (this.process) {
          this.process.kill('SIGTERM')
          this.process = null
        }
      }, 1000)
    }

    this.isRunning = false
  }

  /**
   * Get whether Vosk verbose logs are shown.
   */
  get showVoskLogs(): boolean {
    return this._showVoskLogs
  }

  set showVoskLogs(enabled: boolean) {
    this._showVoskLogs = enabled
    console.log(`[PythonSidecar] Vosk verbose logs ${enabled ? 'enabled' : 'disabled'}`)
  }

  /**
   * Get whether Whisper/STT verbose logs are shown.
   */
  get showWhisperLogs(): boolean {
    return this._showWhisperLogs
  }

  set showWhisperLogs(enabled: boolean) {
    this._showWhisperLogs = enabled
    console.log(`[PythonSidecar] Whisper/STT verbose logs ${enabled ? 'enabled' : 'disabled'}`)
  }

  /**
   * Send a request to the Python sidecar HTTP API.
   *
   * Voice endpoints (/voice/*, /speech/*) ALWAYS route to the LOCAL Python
   * process because the microphone and speakers are on this machine.
   *
   * Non-voice endpoints route to the REMOTE backend when in cloud mode,
   * or to the LOCAL backend otherwise.
   */
  async request<T = unknown>(endpoint: string, data?: unknown, timeout = 10_000): Promise<T> {
    // Voice endpoints always hit localhost (mic/speakers are on this machine)
    const isLocalOnly = LOCAL_ONLY_PREFIXES.some((prefix) => endpoint.startsWith(prefix))
    const baseUrl = (this.remoteMode && this._remoteUrl && !isLocalOnly) ? this._remoteUrl : SIDECAR_URL
    const url = `${baseUrl}${endpoint}`

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeout)

    try {
      const response = await fetch(url, {
        method: data ? 'POST' : 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        body: data ? JSON.stringify(data) : undefined,
        signal: controller.signal
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      return (await response.json()) as T
    } finally {
      clearTimeout(timeoutId)
    }
  }

  private getPythonPath(): string {
    if (is.dev) {
      if (process.platform === 'win32') {
        return this.findWindowsPython()
      }
      return 'python3'
    } else {
      const resourcesPath = join(process.resourcesPath, 'python')
      const ext = process.platform === 'win32' ? '.exe' : ''
      return join(resourcesPath, `barq-sidecar${ext}`)
    }
  }

  private findWindowsPython(): string {
    try {
      const result = execSync('py -3 -c "import sys; print(sys.executable)"', {
        encoding: 'utf8',
        timeout: 3000,
        stdio: ['pipe', 'pipe', 'pipe'],
      })
      const path = result.trim()
      if (path && existsSync(path)) {
        console.log(`[PythonSidecar] Found Python via launcher: ${path}`)
        return path
      }
    } catch {
      // py launcher not available
    }

    try {
      const result = execSync('python -c "import sys; print(sys.executable)"', {
        encoding: 'utf8',
        timeout: 3000,
        stdio: ['pipe', 'pipe', 'pipe'],
      })
      const path = result.trim()
      if (path && !path.includes('WindowsApps') && existsSync(path)) {
        console.log(`[PythonSidecar] Found Python via PATH: ${path}`)
        return path
      }
    } catch {
      // Not on PATH
    }

    for (const candidate of WINDOWS_PYTHON_PATHS) {
      if (existsSync(candidate)) {
        console.log(`[PythonSidecar] Found Python at: ${candidate}`)
        return candidate
      }
    }

    console.warn('[PythonSidecar] Could not find a real Python installation — falling back to "python"')
    return 'python'
  }

  private getArgs(): string[] {
    if (is.dev) {
      return ['-m', 'uvicorn', 'main:app', '--host', SIDECAR_HOST, '--port', String(SIDECAR_PORT), '--log-level', 'info']
    } else {
      return []
    }
  }

  private getWorkingDir(): string {
    if (is.dev) {
      return join(app.getAppPath(), 'python')
    } else {
      return join(process.resourcesPath, 'python')
    }
  }

  private async waitForHealth(timeoutMs: number): Promise<void> {
    const startTime = Date.now()
    let lastLogTime = 0

    while (Date.now() - startTime < timeoutMs) {
      try {
        // Always check localhost — this is the LOCAL voice pipeline's health
        const response = await fetch(`${SIDECAR_URL}/health`, { signal: AbortSignal.timeout(2000) })
        if (response.ok) {
          const body = await response.json()
          if (body && typeof body === 'object' && body.status === 'ok') {
            console.log('[PythonSidecar] Local health check passed')
            return
          }
        }
      } catch {
        // Not ready yet
      }

      const elapsed = Date.now() - startTime
      if (elapsed - lastLogTime >= 5000) {
        lastLogTime = elapsed
        console.log(`[PythonSidecar] Waiting for backend... (${Math.round(elapsed / 1000)}s/${Math.round(timeoutMs / 1000)}s)`)
      }

      await new Promise((resolve) => setTimeout(resolve, 500))
    }

    throw new Error('[PythonSidecar] Failed to start within timeout')
  }

  private startHealthChecks(): void {
    this.healthCheckInterval = setInterval(async () => {
      try {
        // Always check localhost — this monitors the LOCAL voice pipeline
        const response = await fetch(`${SIDECAR_URL}/health`, { signal: AbortSignal.timeout(2000) })
        if (!response.ok) throw new Error('Health check failed')
        this.restartCount = 0
      } catch {
        const now = Date.now()
        const timeSinceLastRestart = now - this.lastRestartAttempt

        const minDelay = [10_000, 30_000, 60_000][Math.min(this.restartCount, 2)]
        if (timeSinceLastRestart < minDelay) {
          console.warn(
            `[PythonSidecar] Health check failed, but too soon to restart ` +
            `(${Math.round(timeSinceLastRestart / 1000)}s since last attempt). Waiting.`
          )
          return
        }

        this.restartCount++
        this.lastRestartAttempt = now
        console.warn(
          `[PythonSidecar] Health check failed, attempting restart ` +
          `(attempt #${this.restartCount})...`
        )
        await this.stop()
        await this.start()
      }
    }, 30_000)
  }
}

// Singleton instance
export const pythonBridge = new PythonSidecar()
export { PythonSidecar }
