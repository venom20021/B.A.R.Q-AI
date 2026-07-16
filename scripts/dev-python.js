/**
 * BARQ - Python Dev Server Launcher
 *
 * Cross-platform helper that finds a working Python installation
 * and starts the FastAPI dev server (uvicorn).
 *
 * Used by: npm run dev:python
 *
 * Logic mirrors src/main/python-bridge.ts so dev and production
 * find Python the same way.
 */

const { spawn, execSync } = require('child_process')
const { existsSync } = require('fs')
const { join } = require('path')

const PORT = 8970
const HOST = '127.0.0.1'

// ── Python discovery (mirrors python-bridge.ts) ──────────────────────────

const WINDOWS_PYTHON_PATHS = [
  join(process.env.LOCALAPPDATA || 'C:\\Users\\Default', 'Programs', 'Python', 'Python313', 'python.exe'),
  join(process.env.LOCALAPPDATA || 'C:\\Users\\Default', 'Programs', 'Python', 'Python312', 'python.exe'),
  join(process.env.LOCALAPPDATA || 'C:\\Users\\Default', 'Programs', 'Python', 'Python311', 'python.exe'),
  'C:\\Python313\\python.exe',
  'C:\\Python312\\python.exe',
  'C:\\Python311\\python.exe',
  join(process.env.ProgramFiles || 'C:\\Program Files', 'Python313', 'python.exe'),
  join(process.env.ProgramFiles || 'C:\\Program Files', 'Python312', 'python.exe'),
]

function findPython() {
  // 1. Try py -3 (Python launcher on Windows)
  if (process.platform === 'win32') {
    try {
      const result = execSync('py -3 -c "import sys; print(sys.executable)"', {
        encoding: 'utf8',
        timeout: 3000,
        stdio: ['pipe', 'pipe', 'pipe'],
      })
      const path = result.trim()
      if (path && existsSync(path) && !path.includes('WindowsApps')) {
        console.log(`[dev-python] Found Python via launcher: ${path}`)
        return path
      }
    } catch {
      // py launcher not available — fall through
    }
  }

  // 2. Try python from PATH (skip WindowsApp shim)
  try {
    const result = execSync('python -c "import sys; print(sys.executable)"', {
      encoding: 'utf8',
      timeout: 3000,
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    const path = result.trim()
    if (path && !path.includes('WindowsApps') && existsSync(path)) {
      console.log(`[dev-python] Found Python via PATH: ${path}`)
      return path
    }
  } catch {
    // Not on PATH — fall through
  }

  // 3. Try python3 (Unix / Git Bash)
  try {
    const result = execSync('python3 -c "import sys; print(sys.executable)"', {
      encoding: 'utf8',
      timeout: 3000,
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    const path = result.trim()
    if (path && existsSync(path)) {
      console.log(`[dev-python] Found Python via python3: ${path}`)
      return path
    }
  } catch {
    // Not available — fall through
  }

  // 4. Check known installation paths
  for (const candidate of WINDOWS_PYTHON_PATHS) {
    if (existsSync(candidate)) {
      console.log(`[dev-python] Found Python at: ${candidate}`)
      return candidate
    }
  }

  // 5. Final fallback
  console.error('[dev-python] Could not find a working Python installation.')
  console.error('  Install Python 3.11+ from https://python.org')
  process.exit(1)
}

// ── Version check ────────────────────────────────────────────────────────

function checkVersion(pythonPath) {
  try {
    const ver = execSync(`"${pythonPath}" --version`, {
      encoding: 'utf8',
      timeout: 3000,
    }).trim()
    if (!ver.match(/Python 3\.(1[0-9]|[2-9]\d)/)) {
      console.warn(`[dev-python] Warning: ${pythonPath} is ${ver}, expected 3.10+`)
    } else {
      console.log(`[dev-python] ${ver}`)
    }
  } catch {
    console.warn(`[dev-python] Could not verify Python version for: ${pythonPath}`)
  }
}

// ── Main ─────────────────────────────────────────────────────────────────

const pythonPath = findPython()
checkVersion(pythonPath)

const pythonDir = join(__dirname, '..', 'python')

console.log(`[dev-python] Starting uvicorn on ${HOST}:${PORT}...`)
console.log(`[dev-python] Working directory: ${pythonDir}`)

const proc = spawn(
  pythonPath,
  ['-m', 'uvicorn', 'main:app', '--reload', '--host', HOST, '--port', String(PORT), '--log-level', 'info'],
  {
    cwd: pythonDir,
    stdio: 'inherit',
    env: {
      ...process.env,
      SIDECAR_PORT: String(PORT),
    },
  }
)

proc.on('exit', (code) => {
  console.log(`[dev-python] Process exited with code ${code}`)
  process.exit(code ?? 1)
})

proc.on('error', (err) => {
  console.error(`[dev-python] Failed to start: ${err.message}`)
  process.exit(1)
})

// Forward SIGINT/SIGTERM to the child process
process.on('SIGINT', () => {
  proc.kill('SIGINT')
})

process.on('SIGTERM', () => {
  proc.kill('SIGTERM')
})
