'use client'

import { motion } from 'framer-motion'
import { TrendingUp, Trophy, Gauge, Timer, ArrowRight } from 'lucide-react'

interface SuggestedPromptsProps {
  onSelect: (prompt: string) => void
}

const SUGGESTED_PROMPTS = [
  {
    icon: Trophy,
    text: 'Who won the 2024 Bahrain GP?',
    category: 'Race Results',
    gradient: 'from-yellow-500/20 to-orange-500/20',
    borderColor: 'border-yellow-500/30',
    iconColor: 'text-yellow-400',
  },
  {
    icon: TrendingUp,
    text: "Compare Verstappen and Norris's lap times at Monaco 2024",
    category: 'Head-to-Head',
    gradient: 'from-blue-500/20 to-purple-500/20',
    borderColor: 'border-blue-500/30',
    iconColor: 'text-blue-400',
  },
  {
    icon: Gauge,
    text: "Why did Ferrari's strategy fail at Silverstone?",
    category: 'Strategy Analysis',
    gradient: 'from-red-500/20 to-pink-500/20',
    borderColor: 'border-red-500/30',
    iconColor: 'text-red-400',
  },
  {
    icon: Timer,
    text: 'Show me the fastest pit stops of 2024',
    category: 'Statistics',
    gradient: 'from-green-500/20 to-emerald-500/20',
    borderColor: 'border-green-500/30',
    iconColor: 'text-green-400',
  },
]

export function SuggestedPrompts({ onSelect }: SuggestedPromptsProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-2xl">
      {SUGGESTED_PROMPTS.map((prompt, i) => {
        const IconComponent = prompt.icon
        return (
          <motion.button
            key={i}
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ delay: 0.3 + i * 0.1, duration: 0.4 }}
            whileHover={{ scale: 1.02, y: -2 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => onSelect(prompt.text)}
            className={`relative group flex items-start gap-4 p-5 rounded-2xl border ${prompt.borderColor}
                       bg-gradient-to-br ${prompt.gradient} backdrop-blur-sm
                       hover:border-white/20 transition-all duration-300 text-left overflow-hidden`}
            style={{
              boxShadow: '0 4px 20px rgba(0, 0, 0, 0.2)',
            }}
          >
            {/* Hover glow effect */}
            <motion.div
              className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300"
              style={{
                background: 'radial-gradient(circle at 50% 50%, rgba(255,255,255,0.05) 0%, transparent 70%)',
              }}
            />

            {/* Icon container */}
            <div className={`relative flex-shrink-0 p-3 rounded-xl bg-black/30 ${prompt.iconColor}`}>
              <IconComponent className="w-5 h-5" />
            </div>

            {/* Text content */}
            <div className="relative flex-1 min-w-0">
              <p className="text-sm text-white/90 group-hover:text-white transition-colors line-clamp-2 pr-6">
                {prompt.text}
              </p>
              <p className="text-xs text-f1-gray/70 mt-2 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-current" />
                {prompt.category}
              </p>
            </div>

            {/* Arrow indicator */}
            <motion.div
              className="absolute right-4 top-1/2 -translate-y-1/2 text-white/20 group-hover:text-white/50 transition-colors"
              initial={{ x: 0 }}
              whileHover={{ x: 3 }}
            >
              <ArrowRight className="w-4 h-4" />
            </motion.div>

            {/* Corner accent */}
            <div className="absolute top-0 right-0 w-16 h-16 overflow-hidden">
              <div className="absolute top-0 right-0 w-px h-8 bg-gradient-to-b from-white/20 to-transparent" />
              <div className="absolute top-0 right-0 w-8 h-px bg-gradient-to-l from-white/20 to-transparent" />
            </div>
          </motion.button>
        )
      })}
    </div>
  )
}

export default SuggestedPrompts
