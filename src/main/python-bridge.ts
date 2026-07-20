import { ChildProcess, spawn, execSync } from 'child_process'
import { join } from 'path'
import { existsSync } from 'fs'
import { app } from 'electron'
import { is } from '@electron-toolkit/utils'

const SIDECAR_PORT = 8970
const SIDECAR_HOST = '127.0.0.1'
const SIDECAR_URL = `http://${SIDECAR_HOST}:${SIDECAR_PORT}`

/**
 * Common Python installation paths on Windows, checked in order.
 */
const WINDOWS_PYTHON_PATHS = [
  // User-local Python 3.13 (most common for winget installs)
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

  /**
   * Kill any existing process holding the sidecar port (Windows only).
   * Uses multiple methods to find and kill the offending process.
   */
  private async freePort(): Promise<void> {
    if (process.platform !== 'win32') return

    const pids = new Set<number>()

    // Method 1: netstat
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
      // netstat not available — fall through
    }

    if (pids.size === 0) return // No process found on port

    // Kill all PIDs found
    for (const pid of pids) {
      try {
        console.log(`[PythonSidecar] Killing process ${pid} on port ${SIDECAR_PORT}...`)
        execSync(`taskkill /F /PID ${pid}`, { encoding: 'utf8', timeout: 3000 })
        console.log(`[PythonSidecar] Killed PID ${pid}`)
      } catch {
        // Process may have already exited — that's fine
      }
    }

    // Wait for the port to be released (OS may hold TIME_WAIT for a bit)
    await new Promise((resolve) => setTimeout(resolve, 1500))

    // Verify the port is actually free now
    try {
      const check = execSync(
        `netstat -ano | findstr :${SIDECAR_PORT}`,
        { encoding: 'utf8', timeout: 3000 },
      )
      if (check.trim().length > 0) {
        console.warn(`[PythonSidecar] Port ${SIDECAR_PORT} still in use after killing. Retrying in 2s...`)
        // Give it more time for TIME_WAIT to clear
        await new Promise((resolve) => setTimeout(resolve, 2000))
      } else {
        console.log(`[PythonSidecar] Port ${SIDECAR_PORT} is now free`)
      }
    } catch {
      // No output means port is free
      console.log(`[PythonSidecar] Port ${SIDECAR_PORT} is now free`)
    }
  }

  /**
   * Start the Python sidecar process.
   * In development, runs `uvicorn main:app` directly.
   * In production, runs the PyInstaller-bundled executable.
   */
  async start(): Promise<void> {
    if (this.isRunning) return

    // Try starting with up to 2 retries
    for (let attempt = 0; attempt < 3; attempt++) {
      if (attempt > 0) {
        console.log(`[PythonSidecar] Retry attempt ${attempt + 1}/3...`)
        // Aggressively free the port before retry
        await this.freePort()
      } else {
        // Free the port if another process is holding it
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

      // Track if this attempt failed early (port in use, etc.)
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
        // Log stderr but detect address-in-use errors
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

      // Wait for the sidecar to become healthy, but also race against early exit
      try {
        // If the process exits for ANY reason before the health check passes,
        // reject immediately instead of waiting 30s for timeout
        const exitRace = exitPromise.then(() => {
          throw new Error(
            earlyExit
              ? 'Process exited early (likely port in use)'
              : 'Process exited unexpectedly before health check'
          )
        })
        // Prevent unhandled rejection if health check wins and process later exits
        exitRace.catch(() => {})

        await Promise.race([this.waitForHealth(30_000), exitRace])
        this.isRunning = true
        this.startHealthChecks()
        return // Success!
      } catch (err) {
        // Save reference before any null-assignment in callbacks
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

      // Try graceful shutdown via API first
      try {
        await this.request('/shutdown', {}, 2000)
      } catch {
        // Ignore shutdown request failures
      }

      // Force kill after a short delay
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
   * Get whether Vosk verbose logs are shown in the console.
   */
  get showVoskLogs(): boolean {
    return this._showVoskLogs
  }

  /**
   * Set whether Vosk verbose logs are shown in the console.
   */
  set showVoskLogs(enabled: boolean) {
    this._showVoskLogs = enabled
    console.log(`[PythonSidecar] Vosk verbose logs ${enabled ? 'enabled' : 'disabled'}`)
  }

  /**
   * Get whether Whisper/STT verbose logs are shown in the console.
   */
  get showWhisperLogs(): boolean {
    return this._showWhisperLogs
  }

  /**
   * Set whether Whisper/STT verbose logs are shown in the console.
   */
  set showWhisperLogs(enabled: boolean) {
    this._showWhisperLogs = enabled
    console.log(`[PythonSidecar] Whisper/STT verbose logs ${enabled ? 'enabled' : 'disabled'}`)
  }

  /**
   * Send a request to the Python sidecar HTTP API.
   */
  async request<T = unknown>(endpoint: string, data?: unknown, timeout = 10_000): Promise<T> {
    const url = `${SIDECAR_URL}${endpoint}`

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeout)

    try {
      const response = await fetch(url, {
        method: data ? 'POST' : 'GET',
        headers: {
          'Content-Type': 'application/json',
          ...(data ? {} : {})
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
      // In production, use the bundled executable
      const resourcesPath = join(process.resourcesPath, 'python')
      const ext = process.platform === 'win32' ? '.exe' : ''
      return join(resourcesPath, `barq-sidecar${ext}`)
    }
  }

  /**
   * Find a working Python executable on Windows.
   * Tries `python` command first (skipping the WindowsApp shim),
   * then checks common installation paths.
   */
  private findWindowsPython(): string {
    // 1. Try `py -3` (Python launcher) — avoids the Store redirect
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
      // py launcher not available — fall through
    }

    // 2. Try `python -c` and check the actual path isn't the WindowsApp shim
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
      // Not on PATH — fall through
    }

    // 3. Check known installation paths
    for (const candidate of WINDOWS_PYTHON_PATHS) {
      if (existsSync(candidate)) {
        console.log(`[PythonSidecar] Found Python at: ${candidate}`)
        return candidate
      }
    }

    // 4. Final fallback — let the OS decide (will likely fail with a clear error)
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
        const response = await this.request('/health', undefined, 2000)
        if (response && typeof response === 'object' && 'status' in (response as object)) {
          console.log('[PythonSidecar] Health check passed')
          return
        }
      } catch {
        // Not ready yet, retry
      }

      const elapsed = Date.now() - startTime
      // Log progress every 5 seconds
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
        await this.request('/health', undefined, 2000)
        // Reset restart count on successful health check
        this.restartCount = 0
      } catch {
        const now = Date.now()
        const timeSinceLastRestart = now - this.lastRestartAttempt

        // Backoff: wait at least 10s, 30s, 60s between restart attempts
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
    }, 30_000) // Check every 30 seconds
  }
}

// Singleton instance
export const pythonBridge = new PythonSidecar()
export { PythonSidecar }
