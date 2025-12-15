'use client'

import { motion } from 'framer-motion'

interface SuggestedPromptsProps {
  onSelect: (prompt: string) => void
}

const SUGGESTED_PROMPTS = [
  {
    icon: '🏎️',
    text: 'Who won the 2024 Bahrain GP?',
    category: 'Race Results',
  },
  {
    icon: '📊',
    text: "Compare Verstappen and Norris's lap times at Monaco 2024",
    category: 'Comparison',
  },
  {
    icon: '🔧',
    text: "Why did Ferrari's strategy fail at Silverstone?",
    category: 'Strategy Analysis',
  },
  {
    icon: '⏱️',
    text: 'Show me the fastest pit stops of 2024',
    category: 'Statistics',
  },
]

export function SuggestedPrompts({ onSelect }: SuggestedPromptsProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center mb-8"
      >
        <div className="text-6xl mb-4">🏁</div>
        <h2 className="text-2xl font-bold text-white mb-2">
          F1 Race Intelligence Agent
        </h2>
        <p className="text-f1-gray text-sm">
          Your AI-powered Race Engineer Co-Pilot
        </p>
      </motion.div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-2xl">
        {SUGGESTED_PROMPTS.map((prompt, i) => (
          <motion.button
            key={i}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            onClick={() => onSelect(prompt.text)}
            className="flex items-start gap-3 p-4 bg-bg-secondary rounded-xl
                       hover:bg-bg-tertiary transition-colors text-left group"
          >
            <span className="text-2xl">{prompt.icon}</span>
            <div>
              <p className="text-sm text-white group-hover:text-f1-red transition-colors">
                {prompt.text}
              </p>
              <p className="text-xs text-f1-gray mt-1">{prompt.category}</p>
            </div>
          </motion.button>
        ))}
      </div>
    </div>
  )
}
