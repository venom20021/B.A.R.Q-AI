import { ChildProcess, spawn, execSync } from 'child_process'
import { join } from 'path'
import { app } from 'electron'
import { is } from '@electron-toolkit/utils'

const SIDECAR_PORT = 8956
const SIDECAR_HOST = '127.0.0.1'
const SIDECAR_URL = `http://${SIDECAR_HOST}:${SIDECAR_PORT}`

class PythonSidecar {
  private process: ChildProcess | null = null
  private isRunning = false
  private healthCheckInterval: ReturnType<typeof setInterval> | null = null

  /**
   * Kill any existing process holding the sidecar port (Windows only).
   */
  private async freePort(): Promise<void> {
    if (process.platform !== 'win32') return

    let killed = false
    try {
      const result = execSync(
        `netstat -ano | findstr :${SIDECAR_PORT}`,
        { encoding: 'utf8', timeout: 3000 },
      )
      const lines = result.trim().split(/\r?\n/)
      for (const line of lines) {
        const parts = line.trim().split(/\s+/)
        const pid = parts[parts.length - 1]
        if (pid && !isNaN(Number(pid))) {
          console.log(`[PythonSidecar] Killing process ${pid} on port ${SIDECAR_PORT}...`)
          execSync(`taskkill /F /PID ${pid}`, { encoding: 'utf8', timeout: 3000 })
          console.log(`[PythonSidecar] Freed port ${SIDECAR_PORT}`)
          killed = true
        }
      }
    } catch {
      // No process found on port — proceed normally
    }

    // Only delay if a process was actually killed
    if (killed) {
      await new Promise((resolve) => setTimeout(resolve, 500))
    }
  }

  /**
   * Start the Python sidecar process.
   * In development, runs `uvicorn main:app` directly.
   * In production, runs the PyInstaller-bundled executable.
   */
  async start(): Promise<void> {
    if (this.isRunning) return

    // Free the port if another process is holding it
    await this.freePort()

    const pythonPath = this.getPythonPath()
    const args = this.getArgs()

    console.log(`[PythonSidecar] Starting: ${pythonPath} ${args.join(' ')}`)

    this.process = spawn(pythonPath, args, {
      cwd: this.getWorkingDir(),
      stdio: ['pipe', 'pipe', 'pipe'],
      env: {
        ...process.env,
        SIDECAR_PORT: String(SIDECAR_PORT),
        SIDECAR_HOST: SIDECAR_HOST
      }
    })

    this.process.stdout?.on('data', (data: Buffer) => {
      console.log(`[Python] ${data.toString().trim()}`)
    })

    this.process.stderr?.on('data', (data: Buffer) => {
      console.error(`[Python Error] ${data.toString().trim()}`)
    })

    this.process.on('exit', (code) => {
      console.log(`[PythonSidecar] Process exited with code ${code}`)
      this.isRunning = false
      this.process = null
    })

    this.process.on('error', (err) => {
      console.error(`[PythonSidecar] Failed to start:`, err.message)
      this.isRunning = false
      this.process = null
    })

    // Wait for the sidecar to become healthy
    await this.waitForHealth(30_000) // 30 second timeout
    this.isRunning = true

    // Start periodic health checks
    this.startHealthChecks()
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
      // In development, expect Python to be on PATH
      return process.platform === 'win32' ? 'python' : 'python3'
    } else {
      // In production, use the bundled executable
      const resourcesPath = join(process.resourcesPath, 'python')
      const ext = process.platform === 'win32' ? '.exe' : ''
      return join(resourcesPath, `barq-sidecar${ext}`)
    }
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

      await new Promise((resolve) => setTimeout(resolve, 500))
    }

    throw new Error('[PythonSidecar] Failed to start within timeout')
  }

  private startHealthChecks(): void {
    this.healthCheckInterval = setInterval(async () => {
      try {
        await this.request('/health', undefined, 2000)
      } catch {
        console.warn('[PythonSidecar] Health check failed, attempting restart...')
        await this.stop()
        await this.start()
      }
    }, 30_000) // Check every 30 seconds
  }
}

// Singleton instance
export const pythonBridge = new PythonSidecar()
export { PythonSidecar }
