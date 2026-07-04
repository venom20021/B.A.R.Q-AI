import { Mic, BrainCircuit, Clock } from 'lucide-react'

export function TitleBar(): JSX.Element {
  return (
    <header className="h-9 flex items-center px-4 bg-[#0A0A0F]/90 backdrop-blur-lg border-b border-cyan-500/10 select-none drag-region z-50 relative">
      {/* Traffic light dots (styled as glowing indicators) */}
      <div className="flex items-center gap-2">
        <div className="w-3 h-3 rounded-full bg-plasma shadow-glow-plasma" />
        <div className="w-3 h-3 rounded-full bg-cyan-300/70 shadow-glow-cyan-sm" />
        <div className="w-3 h-3 rounded-full bg-neural shadow-glow-green" />
      </div>

      {/* Center: BARQ title */}
      <div className="flex-1 flex items-center justify-center">
        <h1 className="text-xs font-orbitron font-bold text-cyan-300 tracking-[0.25em] animate-glow-pulse">
          B A R Q
        </h1>
        <span className="ml-2 text-[8px] font-share-tech text-dim-400 tracking-wider border border-dim-500/20 px-1.5 py-0.5 rounded">
          v2.0
        </span>
      </div>

      {/* Right: Status indicators */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5" title="Voice Engine">
          <div className="w-1.5 h-1.5 rounded-full bg-neural shadow-glow-green animate-pulse-ring" />
          <span className="text-hud font-share-tech text-dim-400 hidden sm:inline">VOICE</span>
        </div>
        <div className="flex items-center gap-1.5" title="Ollama">
          <BrainCircuit className="w-3 h-3 text-cyan-300" />
          <span className="text-hud font-share-tech text-dim-400 hidden sm:inline">AI</span>
        </div>
        <div className="flex items-center gap-1.5" title="Scheduler">
          <Clock className="w-3 h-3 text-dim-400" />
          <span className="text-hud font-share-tech text-dim-400 hidden sm:inline">SCHED</span>
        </div>
      </div>
    </header>
  )
}
