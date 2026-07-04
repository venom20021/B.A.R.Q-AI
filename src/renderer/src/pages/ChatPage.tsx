import { MessageSquare, Mic, Send, History } from 'lucide-react'
import { motion } from 'framer-motion'

export function ChatPage(): JSX.Element {
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">CHAT</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">Conversation history, memory, and notes</p>
      </motion.div>

      <div className="flex flex-col h-[calc(100vh-12rem)]">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex-1 glass-card overflow-y-auto mb-4 scroll-cyan"
        >
          <div className="text-center py-12">
            <MessageSquare className="w-12 h-12 text-dim-500 mx-auto mb-3" />
            <p className="text-dim-400 text-sm font-exo">Start a conversation with BARQ</p>
            <p className="text-dim-500 text-xs mt-1 font-exo">Press / to type, or just speak naturally</p>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center gap-2"
        >
          <button className="p-3 rounded-lg bg-void-700/80 hover:bg-void-600/80 text-dim-400 hover:text-cyan-300 transition-colors border border-cyan-500/10">
            <Mic className="w-5 h-5" />
          </button>
          <input
            type="text"
            placeholder="Type a message or press / to switch modes..."
            className="input-cyan flex-1"
          />
          <button className="btn-cyan p-3">
            <Send className="w-5 h-5" />
          </button>
        </motion.div>
      </div>
    </div>
  )
}
