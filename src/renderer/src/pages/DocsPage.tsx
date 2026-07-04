import { FileText, Presentation, Sheet, File as FilePdf, Download } from 'lucide-react'
import { motion } from 'framer-motion'

export function DocsPage(): JSX.Element {
  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-xl font-orbitron font-bold text-ghost tracking-wider">DOCUMENT GENERATION</h1>
        <p className="text-sm font-rajdhani text-dim-400 mt-1">
          Create PowerPoint presentations, Excel spreadsheets, and PDFs by voice
        </p>
      </motion.div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { icon: Presentation, accent: 'text-plasma', title: 'PowerPoint', desc: 'Generate presentations from a topic or outline', placeholder: 'e.g., "AI Trends 2025"', btn: 'Generate PPT', cmd: 'Create 5-slide deck on Q3 sales' },
          { icon: Sheet, accent: 'text-neural', title: 'Excel', desc: 'Create spreadsheets, export job data to CSV', placeholder: 'Spreadsheet description...', btn: 'Generate Excel', cmd: 'Create expense spreadsheet' },
          { icon: FilePdf, accent: 'text-plasma', title: 'PDF', desc: 'Generate beautiful PDFs, invoices, and reports', placeholder: 'PDF content...', btn: 'Generate PDF', cmd: 'Export report to PDF' },
        ].map((item, i) => {
          const Icon = item.icon
          return (
            <motion.div
              key={item.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
              className="glass-card-hover"
            >
              <Icon className={`w-8 h-8 ${item.accent} mb-3`} />
              <h3 className="text-sm font-rajdhani font-semibold text-ghost mb-1">{item.title}</h3>
              <p className="text-sm font-exo text-dim-400 mb-4">{item.desc}</p>
              <input type="text" placeholder={item.placeholder} className="input-cyan w-full text-sm mb-2" />
              <button className="btn-cyan w-full text-sm">{item.btn}</button>
              <p className="text-xs text-dim-500 mt-2 font-exo">Say: &quot;{item.cmd}&quot;</p>
            </motion.div>
          )
        })}
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="glass-card"
      >
        <div className="flex items-center gap-2 mb-4">
          <FileText className="w-5 h-5 text-cyan-300" />
          <h3 className="text-sm font-orbitron font-bold text-ghost tracking-wider">Recent Documents</h3>
        </div>
        <div className="text-center py-8">
          <FileText className="w-8 h-8 mx-auto mb-2 opacity-30 text-dim-400" />
          <p className="text-sm text-dim-400 font-exo">No documents generated yet</p>
          <p className="text-xs text-dim-500 mt-1 font-exo">Use voice commands to create your first document</p>
        </div>
      </motion.div>
    </div>
  )
}
