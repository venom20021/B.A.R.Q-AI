import { useState, useCallback } from 'react'
import { Terminal as TerminalIcon, GitBranch, Globe, Play, Code, Loader2, ExternalLink } from 'lucide-react'
import { motion } from 'framer-motion'

export function DevPage(): JSX.Element {
  const [terminalCmd, setTerminalCmd] = useState('')
  const [terminalOutput, setTerminalOutput] = useState<string[]>([])
  const [running, setRunning] = useState(false)
  const [tunnelPort, setTunnelPort] = useState('')
  const [tunnelUrl, setTunnelUrl] = useState('')
  const [tunneling, setTunneling] = useState(false)

  const runCommand = useCallback(async (cmd?: string) => {
    const command = cmd || terminalCmd
    if (!command.trim()) return
    setRunning(true)
    setTerminalOutput((prev) => [...prev, `$ ${command}`])
    try {
      const resp = await window.barq?.python.request('/system/terminal/run', {
        method: 'POST',
        body: JSON.stringify({ command, cwd: '.' }),
        headers: { 'Content-Type': 'application/json' },
      })
      if (resp && typeof resp === 'object') {
        const data = resp as { output?: string; return_code?: number; status?: string }
        const output = data.output || 'No output'
        const lines = output.split('\n').filter(Boolean)
        setTerminalOutput((prev) => [...prev, ...lines])
        if (data.return_code !== undefined && data.return_code !== 0) {
          setTerminalOutput((prev) => [...prev, `[Exit code: ${data.return_code}]`])
        }
      }
    } catch {
      setTerminalOutput((prev) => [...prev, '[Error: Command failed]'])
    }
    setRunning(false)
  }, [terminalCmd])

  const handleExposePort = useCallback(async () => {
    if (!tunnelPort.trim()) return
    setTunneling(true)
    try {
      const resp = await window.barq?.python.request('/system/tunnel/expose', {
        method: 'POST',
        body: JSON.stringify({ port: parseInt(tunnelPort) }),
        headers: { 'Content-Type': 'application/json' },
      })
      if (resp && typeof resp === 'object') {
        const data = resp as { url?: string; status?: string; message?: string }
        setTunnelUrl(data.url || data.message || 'Tunnel unavailable')
      }
    } catch {
      setTunnelUrl('Failed to create tunnel')
    }
    setTunneling(false)
  }, [tunnelPort])

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">DEVELOPER TOOLS</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">
          Terminal, git, macros, and localhost tunneling
        </p>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-card"
        >
          <div className="flex items-center gap-2 mb-4">
            <TerminalIcon className="w-5 h-5 text-neural" />
            <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Terminal</h3>
          </div>
          <div className="bg-void-900/80 rounded-lg p-4 font-jetbrains text-sm min-h-[200px] border border-cyan-500/5 overflow-y-auto max-h-[300px] scroll-cyan mb-3">
            {terminalOutput.length === 0 ? (
              <>
                <p className="text-neural">$ BARQ ready</p>
                <p className="text-dim-500 mt-2">Type a command or say: &quot;Run npm install&quot;</p>
              </>
            ) : (
              terminalOutput.map((line, i) => (
                <p key={i} className={`${line.startsWith('$') ? 'text-neural' : line.startsWith('[Exit') ? 'text-red-400' : line.startsWith('[Error') ? 'text-red-400' : 'text-dim-400'}`}>
                  {line}
                </p>
              ))
            )}
            {running && <p className="text-dim-500 mt-1"><Loader2 className="w-3 h-3 inline animate-spin" /> Running...</p>}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={terminalCmd}
              onChange={(e) => setTerminalCmd(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && runCommand()}
              placeholder="e.g., git status"
              className="input-cyan flex-1 text-sm"
            />
            <button onClick={() => runCommand()} disabled={running} className="btn-cyan text-sm flex items-center gap-1">
              {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
              Run
            </button>
          </div>
        </motion.div>

        <div className="space-y-4">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="glass-card"
          >
            <div className="flex items-center gap-2 mb-3">
              <GitBranch className="w-5 h-5 text-plasma" />
              <h3 className="text-sm font-rajdhani font-semibold text-ghost">Quick Git</h3>
            </div>
            <div className="space-y-2">
              <button onClick={() => runCommand('git status')} className="btn-ghost-cyan w-full text-left text-sm">git status</button>
              <button onClick={() => runCommand('git log --oneline -5')} className="btn-ghost-cyan w-full text-left text-sm">Recent commits</button>
              <button onClick={() => runCommand('git diff --stat')} className="btn-ghost-cyan w-full text-left text-sm">Uncommitted changes</button>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="glass-card"
          >
            <div className="flex items-center gap-2 mb-3">
              <Globe className="w-5 h-5 text-cyan-300" />
              <h3 className="text-sm font-rajdhani font-semibold text-ghost">Wormhole Tunnel</h3>
            </div>
            <p className="text-xs font-exo text-dim-400 mb-3">Expose localhost to the internet</p>
            <div className="flex gap-2">
              <input
                type="text"
                value={tunnelPort}
                onChange={(e) => setTunnelPort(e.target.value)}
                placeholder="Port (e.g., 3000)"
                className="input-cyan flex-1 text-sm"
              />
              <button onClick={handleExposePort} disabled={tunneling} className="btn-cyan text-sm">
                {tunneling ? <Loader2 className="w-3 h-3 animate-spin" /> : 'Expose'}
              </button>
            </div>
            {tunnelUrl && (
              <div className="mt-2 flex items-center gap-2 text-xs font-exo text-neural">
                <ExternalLink className="w-3 h-3" />
                <span className="truncate">{tunnelUrl}</span>
              </div>
            )}
          </motion.div>
        </div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="glass-card"
      >
        <div className="flex items-center gap-2 mb-4">
          <Play className="w-5 h-5 text-holographic" />
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Macros</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <button onClick={() => runCommand('npm install && npm run dev')} className="bg-void-700/50 rounded-lg p-4 cursor-pointer hover:bg-void-600/50 transition-colors border border-cyan-500/5 hover:border-cyan-500/15 text-left">
            <p className="text-sm font-rajdhani font-semibold text-ghost">Start Dev Mode</p>
            <p className="text-xs font-exo text-dim-400 mt-1">npm install → npm run dev → open browser</p>
          </button>
          <button onClick={() => runCommand('npm run build && npm test')} className="bg-void-700/50 rounded-lg p-4 cursor-pointer hover:bg-void-600/50 transition-colors border border-cyan-500/5 hover:border-cyan-500/15 text-left">
            <p className="text-sm font-rajdhani font-semibold text-ghost">Build & Test</p>
            <p className="text-xs font-exo text-dim-400 mt-1">Build → test → ready for deploy</p>
          </button>
          <div className="bg-void-700/50 rounded-lg p-4 border border-dashed border-cyan-500/20 cursor-pointer hover:bg-void-600/50 transition-colors">
            <Code className="w-4 h-4 text-dim-400 mb-1" />
            <p className="text-sm font-rajdhani font-semibold text-dim-400">Create New Macro</p>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
